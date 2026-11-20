"""Capture the environment chapters of the OSLab introduction film from one real `oslab suite-run`.

A suite runs each of its entries on a disposable VM of its own. The script runs a suite with
`uv run --locked oslab suite-run` from the repository root, as the film shows it, and records the console of
every entry's VM at the same time. It writes the files edit_intro.py reads from the capture folder:

- terminal.json: the command and every stdout and stderr line with the time it arrived.
- entries.json: every enabled entry in suite order, with its scenario, OS family, run id and status.
- <entry>/console.mkv and console.json: the console of the entry's VM from its first picture until the run
  destroys the VM, recorded over the LAN route by capture_cli.py's recorder.
- <entry>/progress.jsonl, run.json, reports/ and runtree.txt: copies from the entry's run folder.
- <entry>/report.mkv and report.json for each --report-entry: the entry's HTML report recorded by record_page.mjs.
- suite.json: the suite's own result, and aliases.json: public stand-ins for private names in the terminal text
  and the report pages, built as capture_cli.py builds them.

Run it in PowerShell from the repository root:

    uv run --locked --extra computer-use python validation/artifacts/intro-video/capture_suite.py `
        --output <capture folder>/suite --suite <suite YAML> --artifact-path <artifact folder> `
        --config config/oslab.local.yaml --env-file config/oslab.local.env `
        --lan-address <LAN address of the node's API> --max-parallel 4 --report-entry <entry id> --ffmpeg <ffmpeg>
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import capture_cli as cli  # noqa: E402  The single-run capture provides the console recorder and the evidence helpers.

from oslab.config import load_config  # noqa: E402
from oslab.env_file import load_env_file  # noqa: E402
from oslab.errors import ProviderError  # noqa: E402
from oslab.models.scenario import load_scenario  # noqa: E402
from oslab.models.suite import load_suite  # noqa: E402
from oslab.providers.proxmox import ProxmoxClient, proxmox_config_from_oslab  # noqa: E402

REPO = cli.REPO
LINUX_COMPUTER = "oslab-ubuntu"


def scenario_path(suite, entry):
    """The scenario file of a suite entry, resolved as the suite runner resolves it."""
    if entry.scenario.is_absolute():
        return entry.scenario
    if (REPO / entry.scenario).exists():
        return REPO / entry.scenario
    return suite.path.parent / entry.scenario


def entry_run_dir(suite_dir, run_id, entry_id):
    return suite_dir / "scenarios" / f"{run_id}-{entry_id}"


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def scenario_hashes(suite, entries):
    return {entry.id: hashlib.sha256(scenario_path(suite, entry).read_text(encoding="utf-8").encode("utf-8")).hexdigest()
            for entry, _ in entries}


def owned_recording_vm(client, clone, scenario, child_id):
    details = clone["details"]
    vm_id = details["vmId"]
    vm_range = scenario.vmid_range
    if not vm_range["start"] <= vm_id <= vm_range["end"]:
        raise RuntimeError("Cloned VM is outside the scenario's VMID range")
    if details.get("runId") != child_id or details.get("node") != client.config.node:
        raise RuntimeError("Clone progress does not belong to this suite child and node")
    current_vm = client.get_vm_config(vm_id)
    if not details.get("cloneName") or current_vm.get("name") != details["cloneName"]:
        raise RuntimeError("Proxmox VM name does not match this suite child's clone")
    return vm_id


async def run_and_record(args, folder, run_id, client, suite_dir, entries, environment):
    """Run the suite, record its output and the console of every entry's VM, and return terminal.json's content."""
    command = ["uv", "run", "--locked", "oslab", "suite-run", "--suite", args.suite,
               "--artifact-path", args.artifact_path, "--config", args.config, "--env-file", args.env_file,
               "--max-parallel", str(args.max_parallel), "--run-id", run_id]
    lines, memory = [], []
    started = time.time()
    process = await asyncio.create_subprocess_exec(
        shutil.which("uv"), *command[1:], cwd=REPO, env=environment,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    readers = asyncio.gather(cli.read_lines(process.stdout, "stdout", lines),
                             cli.read_lines(process.stderr, "stderr", lines))
    exited = asyncio.create_task(process.wait())
    sampler = asyncio.create_task(cli.watch_memory(client, memory))
    progress = {entry.id: cli.ProgressLog(entry_run_dir(suite_dir, run_id, entry.id) / "logs" / "progress.jsonl")
                for entry, _ in entries}
    stops = {entry.id: asyncio.Event() for entry, _ in entries}
    recordings, failed = {}, {}
    try:
        while not exited.done():
            for entry, scenario in entries:
                log = progress[entry.id]
                for event in log.read():
                    cli.log(f"{entry.id:<18} T+{cli.event_time(event) - started:6.1f} s  {event['phase']}")
                clone = log.phases.get("vm.clone.done")
                if clone and entry.id not in recordings and entry.id not in failed:
                    try:
                        vm_id = await asyncio.to_thread(owned_recording_vm, client, clone, scenario,
                                                        f"{run_id}-{entry.id}")
                    except ProviderError:
                        continue  # A transient config read can recover before the child finishes.
                    except RuntimeError as exc:
                        failed[entry.id] = {"status": "unverified-vm", "error": str(exc)}
                    else:
                        (folder / entry.id).mkdir(parents=True, exist_ok=True)
                        recordings[entry.id] = asyncio.create_task(cli.record_console(
                            client, vm_id, folder / entry.id / "console.mkv", args.fps, args.ffmpeg, stops[entry.id]))
                finished = {"vm.destroy.done", "run.failed"} & log.phases.keys()
                if entry.id in recordings and finished:
                    stops[entry.id].set()
            await asyncio.sleep(.1)
    finally:
        # Let the suite finish and remove its VMs, whatever happens to the recordings.
        for stop in stops.values():
            stop.set()
        exit_code = await exited
        await readers
        ended = time.time()
        sampler.cancel()
        await asyncio.gather(sampler, return_exceptions=True)
        results = await asyncio.gather(*recordings.values(), return_exceptions=True)
    consoles = dict(zip(recordings, results))
    for entry, _ in entries:
        for event in progress[entry.id].read():
            cli.log(f"{entry.id:<18} T+{cli.event_time(event) - started:6.1f} s  {event['phase']}")
        console = consoles.get(entry.id, failed.get(entry.id, {"status": "no-console"}))
        if isinstance(console, BaseException):
            console = {"status": "failed", "error": type(console).__name__}
        console.update(suiteRunId=run_id, runId=f"{run_id}-{entry.id}")
        (folder / entry.id).mkdir(parents=True, exist_ok=True)
        cli.write_meta(folder / entry.id / "console.json", console)
        cli.log(f"{entry.id}: console {console['status']}")
    if memory:
        cli.log(f"Node memory available during the suite: {min(memory) / cli.GIB:.1f} to {max(memory) / cli.GIB:.1f} GiB")
    cli.log(f"Suite finished with exit code {exit_code} after {ended - started:.1f} s")
    return {"runId": run_id, "command": cli.typed(command), "started": started, "finished": ended, "exit_code": exit_code,
            "lines": sorted(lines, key=lambda row: row["t"])}


def build_aliases(args, suite_dir, run_id, entries, terminal, markers):
    """The aliases of every entry's run, with Linux guests named as Linux machines."""
    aliases, seen = [], set()
    for entry, scenario in entries:
        rows = cli.build_aliases(REPO / args.config, entry_run_dir(suite_dir, run_id, entry.id), terminal, markers)
        for row in rows:
            if scenario.os_family == "linux" and row["replace"] == cli.COMPUTER:
                row = {**row, "replace": LINUX_COMPUTER}
            if row["find"] and row["find"] not in seen:
                seen.add(row["find"])
                aliases.append(row)
    return aliases


def collect_evidence(args, folder, suite_dir, run_id, entries, terminal, suite_result):
    markers = cli.private_markers(args.blocklist)
    issues = []
    for entry, _ in entries:
        source = entry_run_dir(suite_dir, run_id, entry.id)
        target = folder / entry.id
        try:
            cli.copy_run_files(source, target)
        except FileNotFoundError:
            issues.append(f"{entry.id}: incomplete run evidence")
    write_json(folder / "suite.json", suite_result)
    aliases = build_aliases(args, suite_dir, run_id, entries, terminal, markers)
    (folder / "aliases.json").write_text(json.dumps(aliases, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    texts = [cli.aliased(terminal["command"], aliases)] + [cli.aliased(row["text"], aliases) for row in terminal["lines"]]
    remaining = cli.leaks(texts, markers)
    if remaining:
        raise RuntimeError("Private markers remain in the terminal text after aliasing: "
                           + ", ".join(f"#{index}" for index in remaining))
    cli.log(f"No private marker remains in the terminal text after {len(aliases)} aliases")
    for entry_id in args.report_entry:
        target = folder / entry_id
        if not (target / "reports" / "result.html").is_file():
            issues.append(f"{entry_id}: HTML report is missing")
            continue
        command = [
            shutil.which("node"), str(HERE / "record_page.mjs"), "--page", str(target / "reports" / "result.html"),
            "--output", str(target / "report.mkv"), "--screenshot", str(target / "report-full.png"),
            "--aliases", str(folder / "aliases.json"), "--markers", str(args.blocklist), "--ffmpeg", args.ffmpeg,
        ]
        if args.chromium:
            command.extend(["--chromium", str(args.chromium)])
        recorded = subprocess.run(command, cwd=REPO, check=False)
        if recorded.returncode:
            issues.append(f"{entry_id}: HTML report recording failed")
            continue
        report_path = target / "report.json"
        report = read_json(report_path)
        report.update(suiteRunId=run_id, runId=f"{run_id}-{entry_id}")
        write_json(report_path, report)
    return issues


def write_entries(folder, suite, entries, suite_result, hashes):
    """entries.json: what each entry ran and how it ended, in suite order."""
    run_id = suite_result["runId"]
    results = {row["id"]: row for row in suite_result["entries"]}
    rows = []
    for entry, scenario in entries:
        result = results.get(entry.id, {})
        scenario_file = scenario_path(suite, entry)
        child_id = f"{run_id}-{entry.id}"
        output = folder / entry.id
        if result.get("runId") not in (None, child_id):
            raise RuntimeError(f"{entry.id}: unexpected run ID in suite result")
        if (output / "run.json").is_file():
            run = read_json(output / "run.json")
            if (run["runId"], run["scenarioId"], run["status"]) != (
                result.get("runId"), scenario.scenario_id, result.get("status")
            ):
                raise RuntimeError(f"{entry.id}: child result does not match the suite")
        rows.append({
            "id": entry.id,
            "scenario": scenario_file.relative_to(REPO).as_posix(),
            "scenarioSha256": hashes[entry.id],
            "scenarioId": scenario.scenario_id,
            "os": scenario.os_family,
            "osVersion": scenario.raw.get("os", {}).get("version"),
            "name": scenario.raw.get("name"),
            "runId": result.get("runId"),
            "suiteRunId": run_id,
            "status": result.get("status"),
            "folder": entry.id,
        })
    write_json(folder / "entries.json", rows)


def check_memory(client, entries, reserve_gib):
    """Refuse to start when the clones of all entries would leave less than reserve_gib of node memory."""
    status = client.request("GET", f"/nodes/{client.config.node}/status")
    needed = 0
    for _, scenario in entries:
        template = client.request("GET", f"/nodes/{client.config.node}/qemu/{scenario.template_vm_id}/config")
        needed += int(template["memory"]) * 2**20
    available = status["memory"]["available"]
    cli.log(f"Node memory available: {available / cli.GIB:.1f} GiB; the clones need {needed / cli.GIB:.1f} GiB")
    if available - needed < reserve_gib * cli.GIB:
        raise RuntimeError(f"Starting the suite would leave less than {reserve_gib} GiB of node memory available")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", type=Path, required=True, help="Capture folder that edit_intro.py reads")
    parser.add_argument("--suite", required=True, help="Suite path relative to the repository root")
    parser.add_argument("--artifact-path", required=True, help="Artifact path relative to the repository root")
    parser.add_argument("--config", required=True, help="OSLab config relative to the repository root")
    parser.add_argument("--env-file", required=True, help="Env file relative to the repository root")
    parser.add_argument("--lan-address", help="LAN address of the Proxmox node's API for a new recording")
    parser.add_argument("--run-id", help="Defaults to intro-suite-<yyyymmdd-hhmmss>")
    parser.add_argument("--max-parallel", type=int, default=4)
    parser.add_argument("--report-entry", action="append", default=[], help="Record this entry's HTML report")
    parser.add_argument("--blocklist", type=Path, default=REPO / "config" / "public-release-blocklist.local.txt")
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--reserve-gib", type=float, default=20, help="Node memory to keep available")
    parser.add_argument("--evidence-only", action="store_true",
                        help="Skip the run and redo the copies, aliases and report recordings for --run-id")
    parser.add_argument("--ffmpeg", default=os.environ.get("OSLAB_FFMPEG", "ffmpeg"))
    parser.add_argument("--chromium", type=Path, help="Chromium executable for recording HTML reports")
    args = parser.parse_args()
    if args.evidence_only and not args.run_id:
        parser.error("--evidence-only needs --run-id")
    if not args.evidence_only and not args.lan_address:
        parser.error("a new recording needs --lan-address")

    # The suite gets the shell's environment and loads the env file itself, as a viewer's run would.
    environment = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8")
    environment.pop("VIRTUAL_ENV", None)
    load_env_file(REPO / args.env_file)
    folder = args.output.resolve()
    run_id = args.run_id or time.strftime("intro-suite-%Y%m%d-%H%M%S")
    if Path(run_id).name != run_id or run_id in (".", "..") or any(c in run_id for c in "\\/:"):
        parser.error("--run-id must be a single directory name")
    config = load_config(REPO / args.config)
    suite = load_suite(REPO / args.suite)
    entries = [(entry, load_scenario(scenario_path(suite, entry))) for entry in suite.entries if entry.enabled]
    hashes = scenario_hashes(suite, entries)
    unknown = set(args.report_entry) - {entry.id for entry, _ in entries}
    if unknown:
        parser.error(f"--report-entry names entries the suite does not run: {', '.join(sorted(unknown))}")
    suite_dir = REPO / config.output_root / run_id
    if args.evidence_only:
        terminal = read_json(folder / "terminal.json")
        if terminal.get("runId") != run_id:
            parser.error("--run-id does not match the existing recording")
        recorded_hashes = terminal.get("scenarioSha256")
        if recorded_hashes is None and (folder / "entries.json").is_file():
            recorded_hashes = {row["id"]: row["scenarioSha256"] for row in read_json(folder / "entries.json")}
        if recorded_hashes != hashes:
            parser.error("Scenario YAML differs from the existing recording")
        suite_result = read_json(suite_dir / "suite.json")
        if suite_result.get("runId") != run_id or suite_result.get("suiteId") != suite.suite_id:
            parser.error("The suite result does not match the existing recording")
        for entry, _ in entries:
            console = read_json(folder / entry.id / "console.json")
            if console.get("suiteRunId") != run_id or console.get("runId") != f"{run_id}-{entry.id}":
                parser.error(f"{entry.id}: the console does not belong to the existing recording")
    elif folder.exists() or suite_dir.exists():
        parser.error("Use a new output folder and run ID for a new recording")
    with tempfile.TemporaryDirectory(prefix="oslab-capture-suite-") as work:
        if args.evidence_only:
            cleanup = read_json(folder / "cleanup.json")
        else:
            cli.private_markers(args.blocklist)
            remote = ProxmoxClient(proxmox_config_from_oslab(config))
            lan_config = cli.lan.prepare(remote, REPO / args.config, REPO / config.output_root, Path(work), args.lan_address)
            client = ProxmoxClient(proxmox_config_from_oslab(load_config(lan_config)))
            check_memory(client, entries, args.reserve_gib)
            folder.mkdir(parents=True, exist_ok=False)
            cli.log(f"Suite {run_id}")
            terminal = asyncio.run(run_and_record(args, folder, run_id, client, suite_dir, entries, environment))
            terminal["scenarioSha256"] = hashes
            write_json(folder / "terminal.json", terminal)
            suite_result = read_json(suite_dir / "suite.json")
            if suite_result.get("runId") != run_id or suite_result.get("suiteId") != suite.suite_id:
                raise RuntimeError("The suite result does not match the recording")
            cleanup = {}
            for entry, scenario in entries:
                vm_id = read_json(folder / entry.id / "console.json").get("vm_id")
                if vm_id is not None:
                    cleanup[entry.id] = cli.confirm_cleanup(
                        client, vm_id, REPO / config.output_root / ".locks", scenario.template_vm_id)
            write_json(folder / "cleanup.json", cleanup)
    if scenario_hashes(suite, entries) != hashes:
        raise RuntimeError("Scenario YAML changed during the recording")
    issues = collect_evidence(args, folder, suite_dir, run_id, entries, terminal, suite_result)
    write_entries(folder, suite, entries, suite_result, hashes)
    for entry, _ in entries:
        console = read_json(folder / entry.id / "console.json")
        if console.get("status") != "complete" or not console.get("frames") or not (folder / entry.id / "console.mkv").is_file():
            issues.append(f"{entry.id}: console recording is incomplete")
        if entry.id not in cleanup or any(cleanup[entry.id].values()):
            issues.append(f"{entry.id}: VM and reservation cleanup could not be verified")
    for issue in issues:
        cli.log(issue)
    return int(terminal["exit_code"] != 0 or bool(issues))


if __name__ == "__main__":
    raise SystemExit(main())
