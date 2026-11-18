"""Run and record the app matrix on disposable Windows 11 Proxmox guests."""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import io
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from PIL import Image
from oslab.errors import ProviderError

import native
from lab import Lab, READY, ROOT, log, write_json


@asynccontextmanager
async def connect(lab, vms):
    args = ["-m", "oslab.mcp_server", "--config", str(lab.config_path)]
    if lab.env_path:
        args.extend(["--env-file", str(lab.env_path)])
    for vm in vms:
        args.extend(["--vm-id", str(vm.vm_id)])
    with (lab.output / "mcp.log").open("a", encoding="utf-8") as error_log:
        server = StdioServerParameters(command=sys.executable, args=args)
        async with stdio_client(server, errlog=error_log) as (read, write):
            async with ClientSession(read, write) as client:
                await client.initialize()
                yield client


class Desktop:
    def __init__(self, lab, client, vm, case, clock, qga_slots):
        self.lab = lab
        self.client = client
        self.vm = vm
        self.id = case
        self.clock = clock
        self.qga_slots = qga_slots
        self.timeline = []
        self.inputs = []

    async def call(self, tool, **args):
        result = await self.client.call_tool(tool, {"vm_id": self.vm.vm_id, **args})
        if result.isError:
            detail = next((item.text for item in result.content if item.type == "text"), tool)
            raise RuntimeError(detail)
        return result

    async def screenshot(self, name):
        now = time.time()
        result = await self.call("screenshot")
        frame = json.loads(next(item.text for item in result.content if item.type == "text"))
        data = base64.b64decode(next(item.data for item in result.content if item.type == "image"))
        path = self.lab.output / f"{self.id}-{name}.png"
        path.write_bytes(data)
        self.timeline.append({"file": path.name, "time": now, "offset": round(now - self.clock, 3), "stage": name})
        return frame, Image.open(io.BytesIO(data)).convert("RGB")

    async def click(self, frame, x, y):
        await self.call("click", frame_id=frame["frame_id"], x=int(x), y=int(y))
        self.inputs.append({"device": "mouse", "x": int(x), "y": int(y), "time": time.time()})

    async def key(self, *keys):
        await self.call("press_key", keys=list(keys))
        self.inputs.append({"device": "keyboard", "keys": list(keys), "time": time.time()})

    async def ps(self, command, timeout=45):
        async with self.qga_slots:
            return await asyncio.to_thread(self.lab.ps, self.vm, command, timeout)

    async def task(self, name, command, *, system=False):
        async with self.qga_slots:
            await asyncio.to_thread(self.lab.task, self.vm, name, command, system=system)

    async def wait(self, condition, seconds=70):
        # Each wait releases the shared request slot before polling again.
        deadline = time.monotonic() + seconds
        error = None
        while time.monotonic() < deadline:
            try:
                if (await self.ps(f"if ({condition}) {{ 'ready' }}", timeout=10)).stdout.strip() == "ready":
                    return
            except (RuntimeError, OSError, ProviderError) as exc:
                error = exc
            await asyncio.sleep(1.1)
        raise TimeoutError(f"Guest condition timed out: {condition}") from error

    async def upload(self, basename, content):
        async with self.qga_slots:
            await asyncio.to_thread(self.lab.upload, self.vm, basename, content)

    async def read_json(self, path):
        # Transport the exact UTF-8 receipt bytes as ASCII through QGA stdout.
        value = await self.ps(f"[Convert]::ToBase64String([IO.File]::ReadAllBytes('{path}'))")
        return json.loads(base64.b64decode(value.stdout.strip(), validate=True))


def marker(image):
    w, h = image.size
    source = image.load()
    for y in range(int(h * .80), int(h * .96)):
        for x in range(int(w * .08), int(w * .95)):
            if source[x, y] == (21, 233, 171) and source[x + 5, y + 5] == (21, 233, 171):
                return x + 4, y + 4
    raise ValueError("Could not locate the enabled action marker in the Windows screenshot")


def contains(actual, expected):
    """Compare the asserted fields while retaining computed detail in the receipt."""
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(
            key in actual and contains(actual[key], value) for key, value in expected.items()
        )
    if isinstance(expected, list):
        return isinstance(actual, list) and len(actual) == len(expected) and all(
            contains(got, want) for got, want in zip(actual, expected)
        )
    if isinstance(expected, bool) or isinstance(actual, bool):
        return actual is expected
    return actual == expected


async def open_browser(desktop, case, bundle):
    await desktop.upload("app.html", (bundle / f"{case}.html").read_bytes())
    await desktop.task("OSLabMatrixServer", rf"& '{ROOT}\listen.ps1'", system=True)
    await desktop.wait("(Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:7788/health' -TimeoutSec 2).StatusCode -eq 204")
    await desktop.task("OSLabMatrixBrowser", rf"""
        $edge="${{env:ProgramFiles(x86)}}\Microsoft\Edge\Application\msedge.exe"
        & $edge '--no-first-run' '--no-default-browser-check' '--disable-background-networking' '--disable-features=msEdgeSidebarV2' '--user-data-dir={ROOT}\edge' '--start-maximized' '--app=http://127.0.0.1:7788/'
    """)
    await desktop.wait(rf"Test-Path '{ROOT}\evidence-0.json'", seconds=105)
    await asyncio.sleep(.5)
    # A new Explorer session can open its Start menu during the first sign-in.
    await desktop.screenshot("initial")
    await desktop.key("Escape")


async def apply_phase(desktop, phase, expected, label):
    frame, image = await desktop.screenshot(f"before-{phase}")
    coordinates = marker(image)
    await desktop.click(frame, *coordinates)
    await asyncio.sleep(.20)
    await desktop.screenshot(f"input-{phase}")
    file = rf"{ROOT}\evidence-{phase}.json"
    await desktop.wait(f"Test-Path '{file}'")
    evidence = await desktop.read_json(file)
    if (str(evidence["id"]), evidence["step"]) != (desktop.id, phase):
        raise ValueError("Evidence belongs to another app or action")
    observed = evidence["result"]
    checks = []
    for key, want in expected.items():
        got = observed.get(key)
        checks.append({"name": f"{label} / {key}", "expected": want, "observed": got,
                       "passed": key in observed and contains(got, want)})
    mismatch = [check["name"] for check in checks if not check["passed"]]
    if mismatch:
        raise ValueError("Unexpected app outcome: " + ", ".join(mismatch))
    await desktop.screenshot(f"stage-{phase}")
    return checks


async def settled(pairings, work):
    ids = list(pairings)
    results = await asyncio.gather(*(work(case, pairings[case]) for case in ids), return_exceptions=True)
    values = {}
    for case, result in zip(ids, results):
        if isinstance(result, BaseException):
            log(f"{case}: {type(result).__name__}: {result}")
        else:
            values[case] = result
    return values


async def capture_wave(lab, rows, available, bundle, wave, native):
    ready = {case: vm for case, vm in available.items()}
    async def boot(case, vm):
        await asyncio.to_thread(lab.wait, vm, f"Test-Path '{READY}'", 185)
        return vm

    ready = await settled(ready, boot)
    if not ready:
        return []
    clock = time.time()
    slots = asyncio.Semaphore(4)
    async with connect(lab, ready.values()) as client:
        desktops = {case: Desktop(lab, client, vm, case, clock, slots) for case, vm in ready.items()}
        web = {case: desktop for case, desktop in desktops.items() if case in rows}
        native_desktops = {case: desktop for case, desktop in desktops.items() if case not in rows}
        results = []

        async def record_native():
            if not native_desktops:
                return {}
            return await settled(native_desktops, lambda case, desktop: native.execute(int(case), desktop))

        task = asyncio.create_task(record_native())
        started = await settled(web, lambda case, desktop: open_browser(desktop, case, bundle))
        working = {case: web[case] for case in started}
        first = await settled(working, lambda case, desktop: desktop.screenshot("stage-0"))
        working = {case: web[case] for case in first}
        all_checks = {case: [] for case in working}
        for phase in range(1, 4):
            outcomes = await settled(working, lambda case, desktop: apply_phase(
                desktop, phase, rows[case]["expected"][phase - 1], rows[case]["actions"][phase - 1]))
            for case, count in outcomes.items():
                all_checks[case].extend(count)
            working = {case: web[case] for case in outcomes}
        for case in working:
            results.append(record(lab, web[case], rows[case], all_checks[case], wave, "offline Chromium app"))
        for case, result in (await task).items():
            data = native.NATIVE[case]
            label = {**data, "actions": data["steps"]}
            checks = result["checks"]
            if not checks or any(not check["passed"] for check in checks):
                log(f"{case}: native app scenario failed validation")
                continue
            results.append(record(lab, native_desktops[case], label, checks, wave, "Windows native app"))
    return results


def record(lab, desktop, metadata, checks, wave, kind):
    frames = [f"{desktop.id}-stage-{step}.png" for step in range(4)]
    if not set(frames).issubset(shot["file"] for shot in desktop.timeline):
        raise ValueError(f"Case {desktop.id} is missing a stage from this attempt")
    hashes = [hashlib.sha256((lab.output / frame).read_bytes()).hexdigest() for frame in frames]
    if len(set(hashes)) < 3:
        raise ValueError(f"Case {desktop.id} did not capture distinct UI states")
    started = datetime.fromtimestamp(desktop.timeline[0]["time"], timezone.utc).isoformat()
    row = {key: metadata[key] for key in ("title", "kicker", "scenario", "actions")}
    row.update(id=desktop.id, wave=wave, kind=kind, frames=frames, frame_hashes=hashes, timeline=desktop.timeline,
               inputs=desktop.inputs, capture_started_at=started, checks=checks, result="pass")
    write_json(lab.output / f"case-{desktop.id}.json", row)
    log(f"{desktop.id} {row['title']}: PASS ({len(checks)} checks)")
    return row


def run(lab, args, native):
    bundle = args.bundle.resolve()
    rows = {row["id"]: row for row in json.loads((bundle / "cases.json").read_text(encoding="utf-8"))}
    if "base" not in lab.owned or not lab.verify(lab.ref("base")).get("template"):
        raise RuntimeError("Prepare an isolated source before starting a wave")
    if set(lab.owned) != {"base"}:
        raise RuntimeError("A previous wave still owns guests; run cleanup-wave first")
    valid = set(rows) | set(native.NATIVE)
    wanted = args.cases or sorted(valid)
    if set(wanted) - valid:
        raise ValueError("Some requested cases have not been built")
    completed = {row["id"]: row for row in (json.loads(file.read_text(encoding="utf-8"))
                    for file in lab.output.glob("case-*.json"))}
    pending = [case for case in dict.fromkeys(wanted) if case not in completed]
    wave = max((row["wave"] for row in completed.values()), default=0)
    while pending:
        memory = lab.client.request("GET", f"{lab.api}/status")["memory"]["available"]
        free_slots = int(max(0, memory - 12 * 1024**3) // (5 * 1024**3))
        size = min(len(pending), args.wave_size, free_slots)
        if size == 0:
            raise RuntimeError("No memory available for another isolated Windows guest")
        selected, pending = pending[:size], pending[size:]
        wave += 1
        log(f"Wave {wave}: starting {len(selected)} different Windows apps")
        available = {}
        try:
            with ThreadPoolExecutor(max_workers=min(4, size)) as starters:
                starting = {}
                for case in selected:
                    try:
                        vm = lab.create(case, lab.ref("base").vm_id)
                        starting[case] = (vm, starters.submit(lab.start_desktop, vm))
                    except Exception as exc:
                        log(f"{case}: provisioning {type(exc).__name__}")
                for case, (vm, result) in starting.items():
                    try:
                        result.result()
                        available[case] = vm
                    except Exception as exc:
                        log(f"{case}: desktop setup {type(exc).__name__}: {exc}")
            for row in asyncio.run(capture_wave(lab, rows, available, bundle, wave, native)):
                completed[row["id"]] = row
        finally:
            lab.cleanup(keep_base=True)
        log(f"Wave {wave} captured {sum(row['wave'] == wave for row in completed.values())}; total {len(completed)}")
    return int(any(case not in completed for case in wanted))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "run", "cleanup", "cleanup-wave"))
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--template-vmid", type=int, required=True)
    parser.add_argument("--vmid-start", type=int, required=True)
    parser.add_argument("--vmid-end", type=int, required=True)
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--wave-size", type=int, choices=range(1, 9), default=4)
    parser.add_argument("--cases", nargs="+")
    args = parser.parse_args()
    lab = Lab(args)
    if args.operation == "prepare":
        lab.prepare()
    elif args.operation == "run":
        if args.bundle is None:
            parser.error("run requires --bundle")
        return run(lab, args, native)
    else:
        lab.cleanup(keep_base=args.operation == "cleanup-wave")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
