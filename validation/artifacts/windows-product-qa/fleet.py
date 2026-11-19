"""Run the 32 Windows release QA workflows in waves and record every console.

Each workflow gets its own linked clone of the sealed product source. A wave
starts its VMs in small batches while the runner watches the node's available
memory, records each console to its own video with screen_recorder.py, and
starts the wave's workflows at the same moment. The wave's VMs are removed
before the next wave starts. Rerunning the command repeats only the
workflows that have not passed yet.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

import lan
import run as product
from lab import READY, Lab, log, write_json
from oslab.config import load_config
from oslab.errors import ProviderError
from run_matrix import record

HERE = Path(__file__).resolve().parent
GIB = 2**30
# LibreOffice, media editors, VS Code, ILSpy, Inkscape and Process Monitor get more memory.
HEAVY = {"02", "03", "05", "10", "11", "12", "13", "14", "15", "16", "17", "25"}


class Watchdog(threading.Thread):
    """Sample node memory and flag when it falls below the safety floor."""

    def __init__(self, lab, floor):
        super().__init__(daemon=True)
        self.lab = lab
        self.floor = floor
        self.samples = []
        self.breached = threading.Event()
        self.finished = threading.Event()

    def sample(self):
        status = self.lab.client.request("GET", f"{self.lab.api}/status")
        row = {"time": time.time(), "available": status["memory"]["available"], "cpu": status.get("cpu"),
               "ksm_shared": (status.get("ksm") or {}).get("shared", 0)}
        self.samples.append(row)
        if row["available"] < self.floor:
            self.breached.set()
        return row

    def run(self):
        while not self.finished.wait(5):
            try:
                self.sample()
            except Exception as exc:  # Keep sampling through a transient API error.
                log(f"memory sample failed: {type(exc).__name__}")


class FleetDesktop(product.ProductDesktop):
    """Product workflow desktop with load-scaled waits and a visible pointer path."""

    time_scale = 1.0
    glide = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.pointer = None

    async def wait(self, condition, seconds=70):
        await super().wait(condition, seconds * self.time_scale)

    async def click(self, frame, x, y):
        if self.glide:
            start_x, start_y = self.pointer or (frame["width"] // 2, frame["height"] // 2)
            distance = math.dist((start_x, start_y), (x, y))
            steps = max(4, min(16, int(distance / 45)))
            bend = min(60.0, distance * .12)
            for step in range(1, steps):
                t = step / steps
                eased = t * t * (3 - 2 * t)
                # Curve slightly away from the straight line, as a hand moving a mouse would.
                offset = math.sin(math.pi * t) * bend
                px = start_x + (x - start_x) * eased - offset * (y - start_y) / max(distance, 1)
                py = start_y + (y - start_y) * eased + offset * (x - start_x) / max(distance, 1)
                px = min(max(int(px), 0), frame["width"] - 1)
                py = min(max(int(py), 0), frame["height"] - 1)
                await self.call("move_mouse", frame_id=frame["frame_id"], x=px, y=py)
                await asyncio.sleep(.024)
        await super().click(frame, x, y)
        self.pointer = (int(x), int(y))


@asynccontextmanager
async def lan_mcp(lab, lan_config, env_file, vms):
    """Start one MCP server for a group of VMs over the LAN route."""
    args = ["-B", str(HERE / "lan.py"), "--config", str(lan_config)]
    if env_file:
        args.extend(["--env-file", str(env_file)])
    for vm in vms:
        args.extend(["--vm-id", str(vm.vm_id)])
    with (lab.output / "mcp.log").open("a", encoding="utf-8") as error_log:
        server = StdioServerParameters(command=sys.executable, args=args, env=dict(os.environ))
        async with stdio_client(server, errlog=error_log) as (read, write):
            async with ClientSession(read, write) as client:
                await client.initialize()
                yield client


def memory_for(case, args):
    return args.heavy_memory if case in HEAVY else args.light_memory


def start_desktop(lab, vm):
    """Log in a clone's desktop, repeating the login once if the guest agent drops a request."""
    for attempt in range(2):
        try:
            lab.start_desktop(vm, boot_seconds=480, login_seconds=360)
            return
        except (OSError, ProviderError, RuntimeError, TimeoutError) as exc:
            try:
                # A slow API response may leave Windows ready even though startup polling failed.
                lab.wait(vm, f"Test-Path -LiteralPath '{READY}'", 45)
                return
            except TimeoutError:
                if attempt:
                    raise
                log(f"{vm.name.rsplit('-', 1)[-1]}: login did not finish ({type(exc).__name__}); trying again")


def emergency_stop(lab, roles):
    log("Node memory fell below the safety floor. Stopping every fleet VM.")
    with ThreadPoolExecutor(max_workers=8) as workers:
        list(workers.map(lambda role: lab.provider.stop_vm(lab.ref(role)), roles))
    raise RuntimeError("Fleet stopped to protect the Proxmox node")


def boot(lab, args, cases, watchdog):
    """Create linked clones, start them in batches within the memory budget, and log in."""
    base = lab.ref("base")
    if not lab.verify(base).get("template"):
        raise RuntimeError("Seal the product source before starting the fleet")
    guests = {}
    for case in cases:
        guests[case] = lab.ref(case) if case in lab.owned else lab.create(
            case, base.vm_id, memory=memory_for(case, args), cores=args.cores, start=False)
    log(f"{len(guests)} linked clones ready")
    desktops = {}
    with ThreadPoolExecutor(max_workers=len(guests)) as workers:
        pending = list(cases)
        while pending:
            batch, pending = pending[:args.boot_batch], pending[args.boot_batch:]
            need = sum(memory_for(case, args) for case in batch) * 2**20 + len(batch) * GIB // 4
            deadline = time.monotonic() + 180
            while (free := watchdog.sample()["available"]) - need < args.reserve_gib * GIB:
                if time.monotonic() > deadline:
                    raise RuntimeError(f"Only {free / GIB:.1f} GiB available; the next batch needs {need / GIB:.1f} GiB "
                                       f"plus the {args.reserve_gib} GiB reserve")
                log(f"Waiting for node memory ({free / GIB:.1f} GiB available)")
                time.sleep(10)
            for case in batch:
                if lab.client.get_vm_status(guests[case].vm_id)["status"] != "running":
                    lab.provider.start_vm(guests[case])
                desktops[case] = workers.submit(start_desktop, lab, guests[case])
            log(f"Started {len(desktops)}/{len(guests)} VMs; {free / GIB:.1f} GiB was available")
            if watchdog.breached.is_set():
                emergency_stop(lab, list(desktops))
            if pending:
                time.sleep(args.boot_interval)
        ready = {}
        for case, future in desktops.items():
            try:
                future.result()
                ready[case] = guests[case]
            except Exception as exc:
                log(f"{case}: desktop setup failed ({type(exc).__name__}); it will run in a later wave")
                lab.remove(case)
    if not ready:
        raise RuntimeError("No desktop in this wave became ready")
    return ready


def start_recorders(args, lan_config, guests, registry, folder):
    folder.mkdir(parents=True, exist_ok=True)
    stop = folder / "stop.flag"
    stop.unlink(missing_ok=True)
    processes = {}
    for case, vm in guests.items():
        command = [sys.executable, "-B", str(HERE / "screen_recorder.py"), "--config", str(lan_config),
                   "--vm-id", str(vm.vm_id), "--label", registry[case][1]["title"],
                   "--output", str(folder / f"{case}.mkv"), "--fps", str(args.fps), "--stop-file", str(stop)]
        if args.env_file:
            command[5:5] = ["--env-file", str(args.env_file)]
        processes[case] = subprocess.Popen(command, env=dict(os.environ, OSLAB_FFMPEG=args.ffmpeg))
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        states = {}
        for case in guests:
            meta = folder / f"{case}.json"
            states[case] = json.loads(meta.read_text(encoding="utf-8"))["status"] if meta.exists() else "starting"
        if all(state != "starting" and state != "connecting" for state in states.values()):
            break
        time.sleep(1)
    failed = [case for case, state in states.items() if state != "recording"]
    if failed:
        stop.touch()
        raise RuntimeError(f"Console recording did not start for {', '.join(failed)}")
    log(f"Recording {len(processes)} consoles at {args.fps} fps")
    return stop, processes


async def run_workflows(lab, args, lan_config, guests, registry, paths, wave):
    FleetDesktop.time_scale = args.time_scale
    FleetDesktop.glide = not args.no_glide
    slots = asyncio.Semaphore(args.qga_slots)
    cases = list(guests)
    groups = [cases[index:index + args.group_size] for index in range(0, len(cases), args.group_size)]
    results = {}
    async with AsyncExitStack() as stack:
        sessions = {}
        for group in groups:
            client = await stack.enter_async_context(lan_mcp(lab, lan_config, args.env_file, [guests[c] for c in group]))
            sessions.update({case: client for case in group})
        clock = time.time()
        log(f"All {len(cases)} workflows start now")

        async def workflow(case):
            module, meta = registry[case]
            desktop = FleetDesktop(lab, sessions[case], guests[case], case, clock, slots, paths=paths)
            started = time.time()
            try:
                checks = await module.execute(case, desktop)
                if isinstance(checks, dict):
                    checks = checks["checks"]
                failures = [row["name"] for row in checks if not row["passed"]]
                if not checks or failures:
                    (lab.output / f"unmatched-{case}.json").write_text(json.dumps(checks, ensure_ascii=True), encoding="utf-8")
                    raise ValueError("Unmatched evidence: " + ", ".join(failures))
                await asyncio.to_thread(record, lab, desktop, {**meta, "actions": meta["steps"]}, checks, wave,
                                        "installed Windows program")
                outcome, detail = "pass", f"{len(checks)} checks"
            except Exception as exc:
                outcome, detail = "fail", f"{type(exc).__name__}: {exc}"[:400]
                log(f"{case} {meta['title']}: FAIL {detail}")
            results[case] = {"title": meta["title"], "result": outcome, "detail": detail,
                             "started": started, "finished": time.time()}

        await asyncio.gather(*(workflow(case) for case in cases))
    return clock, results


def run_wave(lab, args, lan_config, registry, paths, watchdog, cases, wave):
    folder = lab.output / "recordings" / f"wave-{wave}"
    entry = {"wave": wave, "cases": {}}
    log(f"Wave {wave}: {' '.join(cases)}")
    stop = None
    recorders = {}
    try:
        started = time.time()
        guests = boot(lab, args, cases, watchdog)
        entry["desktops_ready_seconds"] = round(time.time() - started, 1)
        log(f"Wave {wave}: {len(guests)} desktops ready after {entry['desktops_ready_seconds']} s; settling")
        time.sleep(args.settle)
        if watchdog.breached.is_set():
            emergency_stop(lab, list(guests))
        stop, recorders = start_recorders(args, lan_config, guests, registry, folder)
        time.sleep(3)

        async def guarded():
            work = asyncio.create_task(run_workflows(lab, args, lan_config, guests, registry, paths, wave))
            while not work.done():
                if watchdog.breached.is_set():
                    work.cancel()
                    await asyncio.to_thread(emergency_stop, lab, list(guests))
                await asyncio.sleep(1)
            return work.result()

        clock, results = asyncio.run(guarded())
        entry.update(workflows_started=clock, cases=results)
        time.sleep(args.tail)
    finally:
        if stop is not None:
            stop.touch()
            for process in recorders.values():
                process.wait(timeout=180)
        entry["recordings"] = {
            path.stem: json.loads(path.read_text(encoding="utf-8")) for path in sorted(folder.glob("*.json"))
        } if folder.exists() else {}
        for case in cases:
            if case in lab.owned:
                lab.remove(case)
    return entry


def run(args):
    source = Lab(args)
    config = load_config(args.config.resolve())
    lan_config = lan.prepare(source.client, args.config, config.output_root, source.output, args.lan_address)
    lab = Lab(SimpleNamespace(**{**vars(args), "config": lan_config}))
    registry = product.load_cases()
    paths = json.loads((lab.output / "programs.json").read_text(encoding="utf-8"))
    cases = args.cases or sorted(registry)
    if not set(cases) <= set(registry):
        raise ValueError("Unknown test case")
    if set(lab.owned) - {"base"}:
        raise RuntimeError("A previous wave still owns VMs; run cleanup-fleet first")
    summary_path = lab.output / "fleet.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {"waves": [], "memory": []}
    summary["settings"] = {"fps": args.fps, "cores": args.cores, "light_memory_mib": args.light_memory,
                           "heavy_memory_mib": args.heavy_memory, "wave_size": args.wave_size}
    watchdog = Watchdog(lab, args.floor_gib * GIB)
    first = watchdog.sample()
    log(f"Node memory available before the fleet: {first['available'] / GIB:.1f} GiB")
    watchdog.start()
    pending = [case for case in dict.fromkeys(cases) if not (lab.output / f"case-{case}.json").exists()]
    attempts = dict.fromkeys(pending, 0)
    try:
        while pending:
            batch, pending = pending[:args.wave_size], pending[args.wave_size:]
            wave = len(summary["waves"]) + 1
            summary["waves"].append({"wave": wave, "cases": {}, "status": "running"})
            write_json(summary_path, summary)
            entry = run_wave(lab, args, lan_config, registry, paths, watchdog, batch, wave)
            summary["waves"][-1] = {**entry, "status": "finished"}
            write_json(summary_path, summary)
            for case in batch:
                attempts[case] += 1
                if not (lab.output / f"case-{case}.json").exists() and attempts[case] <= args.retries:
                    pending.append(case)
    finally:
        watchdog.finished.set()
        summary["memory"].extend(watchdog.samples)
        write_json(summary_path, summary)
    passed = [case for case in cases if (lab.output / f"case-{case}.json").exists()]
    lowest = min(row["available"] for row in watchdog.samples) / GIB
    log(f"Fleet result: {len(passed)}/{len(cases)} passed; lowest node memory available {lowest:.1f} GiB")
    return int(len(passed) != len(cases))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("run", "cleanup-fleet", "cleanup"))
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--template-vmid", type=int, required=True)
    parser.add_argument("--vmid-start", type=int, required=True)
    parser.add_argument("--vmid-end", type=int, required=True)
    parser.add_argument("--lan-address", required=True, help="LAN address of the Proxmox node's API")
    parser.add_argument("--cases", nargs="+")
    parser.add_argument("--wave-size", type=int, default=8, help="VMs that run and record together")
    parser.add_argument("--retries", type=int, default=1, help="Repeat a failed workflow in a later wave")
    parser.add_argument("--light-memory", type=int, default=3072, help="MiB for lightweight programs")
    parser.add_argument("--heavy-memory", type=int, default=4096, help="MiB for office, media and IDE programs")
    parser.add_argument("--cores", type=int, default=4)
    parser.add_argument("--boot-batch", type=int, default=4)
    parser.add_argument("--boot-interval", type=float, default=10)
    parser.add_argument("--reserve-gib", type=float, default=20, help="Memory to keep free on the node while starting VMs")
    parser.add_argument("--floor-gib", type=float, default=10, help="Stop the fleet if node memory falls below this")
    parser.add_argument("--settle", type=float, default=30)
    parser.add_argument("--tail", type=float, default=5)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--time-scale", type=float, default=2.0, help="Multiply guest waits for a loaded node")
    parser.add_argument("--qga-slots", type=int, default=16)
    parser.add_argument("--group-size", type=int, default=8, help="VMs per MCP server process")
    parser.add_argument("--no-glide", action="store_true", help="Click without moving the pointer along a path")
    parser.add_argument("--ffmpeg", default=os.environ.get("OSLAB_FFMPEG", "ffmpeg"))
    args = parser.parse_args()
    if args.operation == "run":
        return run(args)
    Lab(args).cleanup(keep_base=args.operation == "cleanup-fleet")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
