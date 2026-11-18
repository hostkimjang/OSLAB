"""Run real Windows programs on disposable OSLab VM desktops."""

from __future__ import annotations

import argparse
import asyncio
import base64
import importlib.util
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
MATRIX_LIB = HERE.with_name("windows-app-matrix")
sys.path.insert(0, str(MATRIX_LIB))
import native as matrix_native
from lab import Lab, READY, ROOT, log
from oslab.errors import ProviderError
from run_matrix import Desktop, connect, record, settled
sys.modules["matrix_native"] = matrix_native

MODULES = ("archive_db", "office", "media_apps", "dev_apps", "asset_apps",
           "windows_platform", "sysinternals_apps", "windows_desktop")


def load_cases():
    registry = {}
    for name in MODULES:
        spec = importlib.util.spec_from_file_location(name, HERE / (name + ".py"))
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        for identifier, fixture in module.CASES.items():
            if identifier in registry:
                raise ValueError(f"Duplicate workflow {identifier}")
            registry[identifier] = (module, fixture)
    if set(registry) != {f"{index:02}" for index in range(1, 33)}:
        raise ValueError("The release QA catalog must contain 32 distinct workflows")
    return registry


def quoted(value):
    return "'" + value.replace("'", "''") + "'"


class ProductDesktop(Desktop):
    def __init__(self, *args, paths):
        super().__init__(*args)
        self.paths = paths
        self.clipboard_marker = 0

    def package_path(self, alias):
        return self.paths[alias]

    async def executable(self, alias):
        return self.package_path(alias)

    async def launch(self, alias, args=()):
        binary = self.package_path(alias)
        flags = subprocess.list2cmdline(list(args))
        params = f" -ArgumentList {quoted(flags)}" if flags else ""
        working = f"([IO.Path]::GetDirectoryName({quoted(binary)}))"
        # Resolve the executable in the guest, away from the session 0 desktop.
        await self.task("OSLabProductLaunch", f"Start-Process -FilePath {quoted(binary)} -WorkingDirectory {working}{params}")

    async def inspect(self, process_regex, control_regex):
        return await matrix_native.inspect_controls(self, process_regex, control_regex)

    async def paste(self, value):
        # Set the clipboard in the guest's logged-in Windows session and send the actual paste chord via MCP.
        self.clipboard_marker += 1
        marker = rf"{ROOT}\clipboard-{self.clipboard_marker}.ok"
        data = base64.b64encode(value.encode("utf-8")).decode("ascii")
        await self.ps(f"if (Test-Path -LiteralPath {quoted(marker)}) {{ Remove-Item -LiteralPath {quoted(marker)} }}")
        await self.task("OSLabProductClipboard", f"""
            $bytes=[Convert]::FromBase64String('{data}')
            Set-Clipboard -Value ([Text.Encoding]::UTF8.GetString($bytes))
            [IO.File]::WriteAllText({quoted(marker)},'ready')
        """)
        await self.wait(f"Test-Path -LiteralPath {quoted(marker)}", seconds=15)
        await self.key("Ctrl", "v")


async def capture(lab, registry, guests, paths, wave):
    if not guests:
        return []
    clk = time.time()
    available_calls = asyncio.Semaphore(6)
    async with connect(lab, guests.values()) as client:
        async def task(identifier, vm):
            module, meta = registry[identifier]
            d = ProductDesktop(lab, client, vm, identifier, clk, available_calls, paths=paths)
            checks = await module.execute(identifier, d)
            if isinstance(checks, dict):
                checks = checks["checks"]
            failures = [row["name"] for row in checks if not row["passed"]]
            if not checks or failures:
                details = json.dumps(checks, ensure_ascii=True)
                (lab.output / f"unmatched-{identifier}.json").write_text(details, encoding="utf-8")
                raise ValueError("Unmatched evidence: " + ", ".join(failures))
            return record(lab, d, {**meta, "actions": meta["steps"]}, checks, wave, "installed Windows program")

        results = await settled(guests, task)
        return list(results.values())


def previous(output):
    result = [json.loads(path.read_text(encoding="utf-8")) for path in output.glob("case-*.json")]
    return {row["id"]: row for row in result}


def start_capture_desktop(lab, vm):
    try:
        lab.start_desktop(vm)
    except (OSError, ProviderError):
        # A slow API response may leave Windows ready even though startup polling failed.
        lab.wait(vm, f"Test-Path -LiteralPath '{READY}'", seconds=35)


def run(lab, args):
    registry = load_cases()
    if "base" not in lab.owned or not lab.verify(lab.ref("base")).get("template"):
        raise RuntimeError("Prepare the isolated Windows source with the actual programs first")
    paths = json.loads((lab.output / "programs.json").read_text(encoding="utf-8"))
    complete = previous(lab.output)
    cases = args.cases or sorted(registry)
    if not set(cases) <= set(registry):
        raise ValueError("Unknown test case")
    pending = [identifier for identifier in dict.fromkeys(cases) if identifier not in complete]
    wave = max((row["wave"] for row in complete.values()), default=0)
    if args.keep_wave and len(pending) > args.wave_size:
        raise ValueError("Retain only one explicitly selected batch")
    stalled = set(lab.owned) - {"base"}
    if stalled and (not args.keep_wave or not stalled <= set(registry)):
        raise RuntimeError("A previous capture batch is still registered")
    while pending:
        mem = lab.client.request("GET", f"{lab.api}/status")["memory"]["available"]
        free = max(0, int((mem - 12 * 2**30) // (5 * 2**30)))
        width = min(len(pending), args.wave_size, free + len(stalled & set(pending)))
        if width < 1:
            raise RuntimeError("Not enough memory for another Windows test guest")
        current, pending = pending[:width], pending[width:]
        wave += 1
        guests = {}
        log(f"Capture batch {wave}: {len(current)} real Windows app workflows")
        try:
            with ThreadPoolExecutor(max_workers=min(width, 4)) as workers:
                starting = {}
                for case in current:
                    try:
                        if case in stalled:
                            guests[case] = lab.ref(case)
                        else:
                            vm = lab.create(case, lab.ref("base").vm_id)
                            starting[case] = (vm, workers.submit(start_capture_desktop, lab, vm))
                    except Exception as exc:
                        log(f"{case}: Windows clone provision {type(exc).__name__}")
                for case, (vm, started) in starting.items():
                    try:
                        started.result()
                        guests[case] = vm
                    except Exception as exc:
                        log(f"{case}: guest desktop setup {type(exc).__name__}")
            for row in asyncio.run(capture(lab, registry, guests, paths, wave)):
                complete[row["id"]] = row
        finally:
            if not args.keep_wave:
                lab.cleanup(keep_base=True)
        complete = previous(lab.output)
        log(f"Recorded and verified {len(complete)}/32 product workflows")
    return int(any(case not in complete for case in cases))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("catalog", "run", "cleanup", "cleanup-wave"))
    parser.add_argument("--config", type=Path)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--template-vmid", type=int)
    parser.add_argument("--vmid-start", type=int)
    parser.add_argument("--vmid-end", type=int)
    parser.add_argument("--cases", nargs="+")
    parser.add_argument("--wave-size", type=int, choices=range(1, 9), default=4)
    parser.add_argument("--keep-wave", action="store_true", help="Keep the selected batch while diagnosing guest input")
    args = parser.parse_args()
    if args.operation == "catalog":
        for key, (_, case) in sorted(load_cases().items()):
            print(key, case["title"])
        return 0
    if not all(getattr(args, name) is not None for name in ("config", "output", "template_vmid", "vmid_start", "vmid_end")):
        parser.error("Lab operations require --config, --output, --template-vmid, --vmid-start and --vmid-end")
    lab = Lab(args)
    if args.operation == "run":
        return run(lab, args)
    lab.cleanup(keep_base=args.operation == "cleanup-wave")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
