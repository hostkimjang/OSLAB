"""Record a Windows VM console while an AI agent operates the desktop through the OSLab MCP server.

Chapter 5 of the introduction film (edit_intro.py) shows this recording next to the agent's MCP
calls. This script prepares and records the VM. The agent works through its own OSLab MCP tools
in the meantime and keeps its own call log.

    run      Create a linked clone of a Windows template, sign in its desktop and record its console
             over the LAN route until the stop file appears. Then stop the recorder and remove the VM.
    check    Read the agent's file on the guest Desktop through QEMU Guest Agent and write checks.json.
    cleanup  Remove the VM that an interrupted run left behind.

Run the commands from the repository root so VMID reservations share the lock folder of other OSLab
runs. The clone gets the MatrixQA desktop account of windows-app-matrix/lab.py, a random password
and autologon, so nobody types a password on the VM.

    $capture = @('--config', 'config/oslab.local.yaml', '--env-file', 'config/oslab.local.env',
                 '--work', "$env:TEMP/oslab-agent-capture", '--output', 'runs/intro/agent',
                 '--template-vmid', '9200', '--vmid-start', '9185', '--vmid-end', '9189',
                 '--lan-address', '192.168.0.10')
    uv run --locked --extra computer-use python validation/artifacts/intro-video/capture_agent.py run @capture
    # When the agent has finished:
    uv run --locked --extra computer-use python validation/artifacts/intro-video/capture_agent.py check @capture
    New-Item -ItemType File "$env:TEMP/oslab-agent-capture/stop.flag"
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import secrets
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

ARTIFACTS = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ARTIFACTS / "windows-app-matrix"), str(ARTIFACTS / "windows-product-qa")]

import lan
from lab import READY, ROOT, USER, Lab, log, write_json

from oslab.config import load_config
from oslab.errors import ProviderError

ROLE = "agent"
GIB = 2**30
RECORDER = ARTIFACTS / "windows-product-qa" / "screen_recorder.py"
# The logon task of Lab.prepare(): turn autologon off again and tell the runner that the desktop is up.
LOGON_MARKER = rf"""
$ErrorActionPreference='Stop'
$winlogon='HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon'
Set-ItemProperty $winlogon AutoAdminLogon '0'
Remove-ItemProperty $winlogon DefaultPassword -ErrorAction SilentlyContinue
Start-Sleep -Seconds 4
[IO.File]::WriteAllText('{READY}','ready')
"""


def open_lab(args):
    """Return a Lab for the work folder that reaches the Proxmox node over the LAN route."""
    settings = {"output": args.work, "env_file": args.env_file, "template_vmid": args.template_vmid,
                "vmid_start": args.vmid_start, "vmid_end": args.vmid_end}
    source = Lab(SimpleNamespace(config=args.config, **settings))
    output_root = load_config(args.config.resolve()).output_root
    lan_config = lan.prepare(source.client, args.config, output_root, source.output, args.lan_address)
    return Lab(SimpleNamespace(config=lan_config, **settings)), lan_config


def available_memory(lab):
    return lab.client.request("GET", f"{lab.api}/status")["memory"]["available"]


def wait_for_memory(lab, args):
    """Wait until the node keeps the memory reserve available after the VM takes its memory."""
    need = args.memory * 2**20 + GIB // 4
    deadline = time.monotonic() + 300
    while (free := available_memory(lab)) - need < args.reserve_gib * GIB:
        if time.monotonic() > deadline:
            raise RuntimeError(f"Only {free / GIB:.1f} GiB available; the VM needs {need / GIB:.1f} GiB "
                               f"plus the {args.reserve_gib:g} GiB reserve")
        log(f"Waiting for node memory ({free / GIB:.1f} GiB available)")
        time.sleep(15)
    log(f"Node memory available before the capture: {free / GIB:.1f} GiB")


def add_desktop_account(lab, vm):
    """Give a plain Windows template the account and logon marker that Lab.start_desktop() expects."""
    password = "Win9!" + secrets.token_hex(22)  # Replaced by Lab.start_desktop() before the first sign-in.
    lab.ps(vm, rf"""
        New-Item -Path '{ROOT}' -ItemType Directory -Force | Out-Null
        if (-not (Get-LocalUser -Name '{USER}' -ErrorAction SilentlyContinue)) {{
            $account=New-LocalUser -Name '{USER}' -Password (ConvertTo-SecureString '{password}' -AsPlainText -Force) -PasswordNeverExpires
            Add-LocalGroupMember -SID 'S-1-5-32-544' -Member $account
        }}
        $oobe='HKLM:\Software\Policies\Microsoft\Windows\OOBE'
        New-Item $oobe -Force | Out-Null
        New-ItemProperty $oobe DisablePrivacyExperience -Type DWord -Value 1 -Force | Out-Null
    """)
    lab.task(vm, "OSLabMatrixLogin", LOGON_MARKER, logon=True)


def wait_for_shell(lab, vm, seconds=300):
    """Wait until Explorer runs for the desktop user and the first sign-in animation has ended."""
    lab.wait(vm, f"(Get-Process explorer -IncludeUserName -ErrorAction SilentlyContinue | "
                 f"Where-Object UserName -like '*\\{USER}') -and "
                 f"-not (Get-Process FirstLogonAnim -ErrorAction SilentlyContinue)", seconds)


def start_recorder(args, lan_config, vm):
    """Record the console over the LAN route into console.mkv until the stop file appears."""
    args.output.mkdir(parents=True, exist_ok=True)
    video = args.output / "console.mkv"
    meta = video.with_suffix(".json")
    meta.unlink(missing_ok=True)
    command = [sys.executable, "-B", str(RECORDER), "--config", str(lan_config)]
    if args.env_file:
        command += ["--env-file", str(args.env_file)]
    command += ["--vm-id", str(vm.vm_id), "--label", "AI agent", "--output", str(video), "--fps", str(args.fps),
                "--stop-file", str(args.stop_file), "--max-seconds", str(args.max_minutes * 60), "--ffmpeg", args.ffmpeg]
    with (args.work / "recorder.log").open("a", encoding="utf-8") as errors:
        # The recorder inherits the LAN route from the environment that lan.prepare() set.
        recorder = subprocess.Popen(command, stdout=errors, stderr=errors)
    status = "starting"
    deadline = time.monotonic() + 120
    while status in ("starting", "connecting") and time.monotonic() < deadline:
        time.sleep(1)
        if meta.exists():
            status = json.loads(meta.read_text(encoding="utf-8"))["status"]
    if status != "recording":
        stop_recorder(args, recorder)
        raise RuntimeError(f"Console recording did not start ({status})")
    return recorder


def stop_recorder(args, recorder):
    """Let the recorder finish its video, or stop it if it hangs."""
    args.stop_file.touch()
    try:
        recorder.wait(timeout=180)
    except subprocess.TimeoutExpired:
        log("The recorder did not finish; stopping it")
        recorder.kill()
        recorder.wait()


def watch(lab, args, recorder):
    """Wait for the stop file. End early if the recorder exits or node memory falls below the reserve."""
    deadline = time.monotonic() + args.max_minutes * 60
    lowest = None
    while not args.stop_file.exists() and recorder.poll() is None and time.monotonic() < deadline:
        try:
            free = available_memory(lab)
        except (OSError, ProviderError) as exc:  # Keep waiting through a transient API error.
            log(f"Memory sample failed: {type(exc).__name__}")
        else:
            lowest = free if lowest is None else min(lowest, free)
            if free < args.reserve_gib * GIB:
                log(f"Node memory fell to {free / GIB:.1f} GiB; ending the capture to free the VM")
                break
        time.sleep(5)
    return lowest


def run(args):
    lab, lan_config = open_lab(args)
    if lab.owned:
        raise RuntimeError("The work folder still owns a VM; run cleanup first")
    if not lab.client.get_vm_config(args.template_vmid).get("template"):
        raise RuntimeError("Select a Windows template")
    args.stop_file.unlink(missing_ok=True)
    wait_for_memory(lab, args)
    recorder = None
    try:
        vm = lab.create(ROLE, args.template_vmid, memory=args.memory, cores=args.cores)
        lab.wait(vm, "$true", 300)
        add_desktop_account(lab, vm)
        lab.start_desktop(vm, boot_seconds=300, login_seconds=300)
        wait_for_shell(lab, vm)
        log(f"{vm.name} (VM {vm.vm_id}) is signed in; settling for {args.settle:g} s")
        time.sleep(args.settle)
        recorder = start_recorder(args, lan_config, vm)
        write_json(args.work / "session.json", {"vm_id": vm.vm_id, "name": vm.name, "recording": time.time()})
        log(f"Recording VM {vm.vm_id}. The agent can start. Create {args.stop_file} to finish.")
        lowest = watch(lab, args, recorder)
        if lowest is not None:
            log(f"Lowest node memory available during the capture: {lowest / GIB:.1f} GiB")
    finally:
        if recorder is not None:
            stop_recorder(args, recorder)
        lab.cleanup()
    meta = json.loads((args.output / "console.json").read_text(encoding="utf-8"))
    log(f"Recording {meta['status']}: {meta.get('seconds')} s at {meta['width']}x{meta['height']}; VM removed")
    return int(meta["status"] != "complete")


def check(args):
    """Compare the file on the desktop user's Desktop with the line the agent was asked to type."""
    lab, _ = open_lab(args)
    if ROLE not in lab.owned:
        raise RuntimeError("The work folder owns no capture VM")
    vm = lab.ref(ROLE)
    lab.verify(vm)
    result = lab.ps(vm, rf"""
        $sid = (Get-LocalUser -Name '{USER}').SID.Value
        $userFolder = (Get-CimInstance Win32_UserProfile -Filter "SID='$sid'").LocalPath
        $path = Join-Path $userFolder 'Desktop\{args.file_name}'
        $file = [ordered]@{{ path = $path; found = (Test-Path -LiteralPath $path -PathType Leaf) }}
        if ($file.found) {{
            $file.text = [Text.Encoding]::UTF8.GetString([IO.File]::ReadAllBytes($path))
            $file.sha256 = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
        }}
        [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes(($file | ConvertTo-Json -Compress)))
    """)
    file = json.loads(base64.b64decode(result.stdout.strip(), validate=True))
    checked = time.time()
    expected_hash = hashlib.sha256(args.text.encode("utf-8")).hexdigest()
    checks = [
        {"name": "File saved on the Desktop", "expected": file["path"],
         "observed": file["path"] if file["found"] else "not found", "passed": file["found"]},
        {"name": "Text matches the typed line", "expected": args.text, "observed": file.get("text", ""),
         "passed": file.get("text") == args.text},
        {"name": "SHA-256 matches", "expected": expected_hash, "observed": file.get("sha256", ""),
         "passed": file.get("sha256") == expected_hash},
    ]
    for row in checks:
        row["t"] = checked
        log(f"{'PASS' if row['passed'] else 'FAIL'}  {row['name']}: {row['observed']}")
    args.output.mkdir(parents=True, exist_ok=True)
    write_json(args.output / "checks.json", checks)
    return int(not all(row["passed"] for row in checks))


def cleanup(args):
    lab, _ = open_lab(args)
    lab.cleanup()
    log("Capture VM and reservation removed")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("operation", choices=("run", "check", "cleanup"))
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--work", type=Path, required=True, help="Folder for VM ownership, the LAN config and the stop file")
    parser.add_argument("--output", type=Path, required=True, help="Folder for console.mkv, console.json and checks.json")
    parser.add_argument("--template-vmid", type=int, required=True)
    parser.add_argument("--vmid-start", type=int, required=True)
    parser.add_argument("--vmid-end", type=int, required=True)
    parser.add_argument("--lan-address", required=True, help="LAN address of the Proxmox node's API")
    parser.add_argument("--cores", type=int, default=4)
    parser.add_argument("--memory", type=int, default=4096, help="VM memory in MiB")
    parser.add_argument("--reserve-gib", type=float, default=20, help="Node memory to keep available")
    parser.add_argument("--settle", type=float, default=20, help="Seconds between sign-in and recording")
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--max-minutes", type=float, default=45, help="End the capture after this long")
    parser.add_argument("--stop-file", type=Path, help="Finish when this file exists (default: stop.flag in --work)")
    parser.add_argument("--file-name", default="agent-note.txt", help="File the agent saves on the Desktop")
    parser.add_argument("--text", default="release 2.4 checked by OSLab agent", help="Line the agent types")
    parser.add_argument("--ffmpeg", default=os.environ.get("OSLAB_FFMPEG", "ffmpeg"))
    args = parser.parse_args()
    args.work = args.work.resolve()
    args.output = args.output.resolve()
    args.stop_file = (args.stop_file or args.work / "stop.flag").resolve()
    args.work.mkdir(parents=True, exist_ok=True)
    return {"run": run, "check": check, "cleanup": cleanup}[args.operation](args)


if __name__ == "__main__":
    raise SystemExit(main())
