"""Capture chapters 2 and 3 of the OSLab introduction film from one real `oslab run`.

The script runs a scenario with `uv run --locked oslab run` from the repository root, as the film
shows it, and writes the files edit_intro.py reads from the capture folder:

- terminal.json: the command and every stdout and stderr line with the time it arrived.
- console.mkv and console.json: the console of the VM that the run creates, from its first picture after
  the VM starts until the run destroys the VM. The recorder reaches the Proxmox node over the LAN route of
  windows-product-qa/lan.py and follows the resolution changes of the firmware and Windows during boot.
- progress.jsonl, run.json and reports/: copies from the run folder, and runtree.txt listing its files.
- aliases.json: public stand-ins for the Proxmox host names, the local user folder, the guest computer
  name and environment variable names that contain a private marker. edit_intro.py applies them to the
  terminal text, and record_page.mjs applies them to the report page.
- report.mkv, report.json and report-full.png: the HTML report recorded by record_page.mjs.

Run it in PowerShell from the repository root with the project's Python:

    .venv/Scripts/python validation/artifacts/intro-video/capture_cli.py `
        --output <capture folder> `
        --scenario scenarios/windows/demo-powershell-system.local.yaml `
        --artifact-path validation/artifacts/powershell-system `
        --config config/oslab.local.yaml --env-file config/oslab.local.env `
        --lan-address <LAN address of the node's API> --ffmpeg <ffmpeg>
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import zlib
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from PIL import Image
from websockets.exceptions import WebSocketException

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(HERE.parent / "windows-product-qa"))

import lan  # noqa: E402
from screen_recorder import DESKTOP_SIZE, RAW, ZLIB, Stream, console_ticket, handshake, write_meta  # noqa: E402

from oslab.config import load_config  # noqa: E402
from oslab.env_file import load_env_file  # noqa: E402
from oslab.errors import ProviderError  # noqa: E402
from oslab.models.scenario import load_scenario  # noqa: E402
from oslab.providers.proxmox import DEFAULT_USER_AGENT, ProxmoxClient, proxmox_config_from_oslab  # noqa: E402
from oslab.providers.proxmox_console import _PRIVATE_LOG, _ConsoleWebSocket  # noqa: E402

GIB = 2**30
# Public stand-ins for private names. The host and node names match config/oslab.local.example.yaml.
API_HOST = "proxmox.example.local"
NODE = "pve01"
USER_FOLDER = "C:\\Users\\demo"
COMPUTER = "OSLAB-WIN11"


def log(message):
    print(time.strftime("%H:%M:%S"), message, flush=True)


def event_time(event):
    return datetime.fromisoformat(event["timestamp"]).timestamp()


class BootConsole:
    """The console picture of one VM from power-on to power-off.

    The picture follows the resolution changes of the firmware and Windows during boot. When the VM
    stops after showing a picture, the picture turns black, as the screen of a powered-off machine.
    """

    def __init__(self, client, vm_id):
        self.client = client
        self.vm_id = vm_id
        self.image = None
        self.ready = asyncio.Event()
        self.updates = 0
        self.received = 0
        self.sessions = 0
        self.last_error = None
        self.powered_off = None

    def running(self):
        try:
            return self.client.get_vm_status(self.vm_id).get("status") == "running"
        except ProviderError:
            return False  # The clone does not exist yet, or no longer.

    async def follow(self):
        while True:
            if await asyncio.to_thread(self.running):
                try:
                    await self.session()
                except (OSError, WebSocketException, ProviderError, zlib.error, asyncio.TimeoutError) as exc:
                    # The VM is still starting or has just stopped; check its state again.
                    self.last_error = type(exc).__name__
            elif self.image is not None and self.powered_off is None:
                self.image = Image.new("RGB", self.image.size)
                self.powered_off = time.time()
            await asyncio.sleep(.25)

    async def session(self):
        url, password = await asyncio.to_thread(console_ticket, self.client, self.vm_id)
        config = self.client.config
        async with _ConsoleWebSocket(
            url,
            additional_headers={"Authorization": f"PVEAPIToken={config.token_id}={config.token_secret}"},
            user_agent_header=DEFAULT_USER_AGENT,
            compression=None,
            open_timeout=config.timeout_seconds,
            close_timeout=3,
            max_size=2**27,
            logger=_PRIVATE_LOG,
        ) as websocket:
            self.sessions += 1
            stream = Stream(websocket)
            size = await asyncio.wait_for(handshake(stream, password), config.timeout_seconds)
            if self.image is None or self.image.size != size:
                self.image = Image.new("RGB", size)
            inflate = zlib.decompressobj()
            incremental = 0
            counted = 0
            while True:
                width, height = self.image.size
                await stream.write(struct.pack(">BBHHHH", 3, incremental, 0, 0, width, height))
                # Ask for the whole screen again after a resolution change.
                incremental = 0 if await self.update(stream, inflate) else 1
                self.received += stream.received - counted
                counted = stream.received

    async def update(self, stream, inflate):
        """Apply one framebuffer update at once and report whether the resolution changed."""
        while (kind := (await stream.read(1))[0]) != 0:
            if kind == 3:  # Clipboard text.
                (length,) = struct.unpack(">3xI", await stream.read(7))
                await stream.read(length)
            elif kind != 2:  # Bell messages carry no data.
                raise ProviderError("The console sent an unsupported VNC message")
        (count,) = struct.unpack(">xH", await stream.read(3))
        width, height = self.image.size
        resized = None
        tiles = []
        for _ in range(count):
            x, y, w, h, encoding = struct.unpack(">HHHHi", await stream.read(12))
            if encoding == DESKTOP_SIZE:
                # The screen starts over at the new size; earlier rectangles drew on the old screen.
                width, height = resized = (w, h)
                tiles.clear()
                continue
            if encoding == ZLIB:
                (size,) = struct.unpack(">I", await stream.read(4))
                pixels = inflate.decompress(await stream.read(size))
            elif encoding == RAW:
                pixels = await stream.read(w * h * 4)
            else:
                raise ProviderError("The console sent an unsupported VNC encoding")
            if len(pixels) != w * h * 4 or x + w > width or y + h > height:
                raise ProviderError("The console sent a malformed rectangle")
            if w and h:
                tiles.append(((x, y), Image.frombytes("RGB", (w, h), pixels, "raw", "BGRX")))
        # Apply the whole update at once so sampled frames never show half of it.
        if resized:
            self.image = Image.new("RGB", resized)
        for position, tile in tiles:
            self.image.paste(tile, position)
        self.updates += 1
        self.ready.set()
        return resized is not None


class Segment:
    """Lossless video of the console at one resolution."""

    def __init__(self, ffmpeg, path, size, fps, first_frame):
        self.path = path
        self.size = size
        self.first_frame = first_frame
        self.frames = 0
        self.process = subprocess.Popen([
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
            "-s", f"{size[0]}x{size[1]}", "-framerate", str(fps), "-i", "pipe:0",
            "-c:v", "libx264rgb", "-preset", "ultrafast", "-qp", "0", "-f", "matroska", str(path),
        ], stdin=subprocess.PIPE)

    def write(self, frame, count):
        for _ in range(count):
            self.process.stdin.write(frame)
        self.frames += count

    def close(self):
        self.process.stdin.close()
        return self.process.wait()


def join_segments(ffmpeg, segments, video, size, fps):
    """Fit every segment into one frame size, keeping its aspect ratio, and join them in order."""
    width, height = size
    inputs, filters = [], []
    for index, segment in enumerate(segments):
        inputs += ["-i", str(segment.path)]
        filters.append(f"[{index}:v]scale={width}:{height}:force_original_aspect_ratio=decrease:flags=lanczos,"
                       f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1[v{index}]")
    joined = "".join(f"[v{index}]" for index in range(len(segments)))
    filters.append(f"{joined}concat=n={len(segments)}:v=1:a=0,format=yuv444p[out]")
    subprocess.run([
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y", *inputs, "-filter_complex", ";".join(filters),
        "-map", "[out]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "14", "-g", str(fps * 2),
        "-r", str(fps), "-f", "matroska", str(video),
    ], check=True)


async def record_console(client, vm_id, video, fps, ffmpeg, stop):
    """Record the console from its first picture until stop is set, and return the recording's metadata."""
    screen = BootConsole(client, vm_id)
    follower = asyncio.create_task(screen.follow())
    meta = {"vm_id": vm_id, "file": video.name, "fps": fps}
    waits = [asyncio.create_task(screen.ready.wait()), asyncio.create_task(stop.wait())]
    await asyncio.wait(waits, return_when=asyncio.FIRST_COMPLETED)
    for wait in waits:
        wait.cancel()
    if not screen.ready.is_set():
        follower.cancel()
        return {**meta, "status": "no-console", "last_error": screen.last_error}
    log(f"Recording the console of VM {vm_id}")
    start = time.time()
    period = 1 / fps
    segments = []
    exit_codes = []
    frames = 0
    try:
        while not stop.is_set() or not frames:
            due = start + frames * period
            now = time.time()
            if now < due:
                await asyncio.sleep(min(due - now, .05))
                continue
            image = screen.image
            if not segments or segments[-1].size != image.size:
                if segments:
                    exit_codes.append(await asyncio.to_thread(segments[-1].close))
                part = video.with_name(f"{video.stem}.part{len(segments)}.mkv")
                segments.append(Segment(ffmpeg, part, image.size, fps, frames))
            # Repeat the current picture for any missed slots to keep a constant frame rate.
            count = 1 + int((now - due) / period)
            await asyncio.to_thread(segments[-1].write, image.tobytes(), count)
            frames += count
    finally:
        follower.cancel()
        if segments:
            exit_codes.append(await asyncio.to_thread(segments[-1].close))
    # The resolution shown longest, normally the Windows desktop, sets the size of the video.
    size = max(segments, key=lambda segment: segment.frames).size
    await asyncio.to_thread(join_segments, ffmpeg, segments, video, size, fps)
    for segment in segments:
        segment.path.unlink()
    return {
        **meta,
        "status": "complete" if not any(exit_codes) else "failed",
        "t0": start,
        "width": size[0],
        "height": size[1],
        "frames": frames,
        "seconds": round(frames / fps, 3),
        "segments": [{"width": segment.size[0], "height": segment.size[1], "frames": segment.frames,
                      "t": round(start + segment.first_frame / fps, 3)} for segment in segments],
        "powered_off": screen.powered_off,
        "updates": screen.updates,
        "received_bytes": screen.received,
        "sessions": screen.sessions,
    }


class ProgressLog:
    """The lifecycle events a run appends to logs/progress.jsonl, read as they arrive."""

    def __init__(self, path):
        self.path = path
        self.offset = 0
        self.phases = {}

    def read(self):
        if not self.path.exists():
            return []
        with self.path.open("rb") as handle:
            handle.seek(self.offset)
            data = handle.read()
        complete = data[:data.rfind(b"\n") + 1]
        self.offset += len(complete)
        events = [json.loads(line) for line in complete.decode("utf-8").splitlines() if line.strip()]
        for event in events:
            self.phases.setdefault(event["phase"], event)
        return events


async def read_lines(stream, name, lines):
    while line := await stream.readline():
        text = line.decode("utf-8", errors="replace").rstrip("\r\n")
        lines.append({"t": time.time(), "stream": name, "text": text})


async def watch_memory(client, samples):
    """Sample the node's available memory every five seconds."""
    while True:
        try:
            status = await asyncio.to_thread(client.request, "GET", f"/nodes/{client.config.node}/status")
            samples.append(status["memory"]["available"])
        except ProviderError as exc:
            log(f"Memory sample failed ({type(exc).__name__})")
        await asyncio.sleep(5)


def typed(command):
    """The command as a viewer would type it in PowerShell, with one option per line."""
    options = [f"  {command[index]} {command[index + 1]}" for index in range(5, len(command), 2)]
    return " `\n".join([" ".join(command[:5]), *options])


async def run_and_record(args, folder, run_id, client, run_dir, environment):
    """Run the scenario, record its output and the console of its VM, and return terminal.json's content."""
    command = ["uv", "run", "--locked", "oslab", "run", "--scenario", args.scenario,
               "--artifact-path", args.artifact_path, "--config", args.config, "--env-file", args.env_file,
               "--run-id", run_id]
    vm_range = load_scenario(REPO / args.scenario).vmid_range
    lines, memory = [], []
    started = time.time()
    process = await asyncio.create_subprocess_exec(
        shutil.which("uv"), *command[1:], cwd=REPO, env=environment,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    readers = asyncio.gather(read_lines(process.stdout, "stdout", lines), read_lines(process.stderr, "stderr", lines))
    exited = asyncio.create_task(process.wait())
    sampler = asyncio.create_task(watch_memory(client, memory))
    progress = ProgressLog(run_dir / "logs" / "progress.jsonl")
    stop = asyncio.Event()
    recording = None
    try:
        while not exited.done() and "vm.destroy.done" not in progress.phases:
            for event in progress.read():
                log(f"T+{event_time(event) - started:5.1f} s  {event['phase']}")
            allocated = progress.phases.get("vm.allocate.done")
            if recording is None and allocated:
                # Record only the VM this run allocated from the scenario's range.
                vm_id = allocated["details"]["vmId"]
                if not vm_range["start"] <= vm_id <= vm_range["end"]:
                    raise RuntimeError(f"VM {vm_id} is outside the scenario's VMID range")
                recording = asyncio.create_task(
                    record_console(client, vm_id, folder / "console.mkv", args.fps, args.ffmpeg, stop))
            await asyncio.sleep(.1)
        # Keep a moment of the powered-off console at the end of the clip.
        await asyncio.sleep(.3)
    finally:
        # Let the run finish and remove its VM, whatever happens to the recording.
        stop.set()
        exit_code = await exited
        await readers
        finished = time.time()
        sampler.cancel()
    for event in progress.read():
        log(f"T+{event_time(event) - started:5.1f} s  {event['phase']}")
    console = await recording if recording else {"status": "no-vm"}
    write_meta(folder / "console.json", console)
    if memory:
        log(f"Node memory available during the run: {min(memory) / GIB:.1f} to {max(memory) / GIB:.1f} GiB")
    log(f"Run finished with exit code {exit_code} after {finished - started:.1f} s; console: {console['status']}")
    return {"command": typed(command), "started": started, "finished": finished, "exit_code": exit_code,
            "lines": sorted(lines, key=lambda row: row["t"])}


def copy_run_files(run_dir, folder):
    """Copy the files edit_intro.py reads and list every file in the run folder."""
    shutil.copy2(run_dir / "logs" / "progress.jsonl", folder / "progress.jsonl")
    shutil.copy2(run_dir / "run.json", folder / "run.json")
    shutil.copytree(run_dir / "reports", folder / "reports", dirs_exist_ok=True)
    files = sorted((path.relative_to(run_dir) for path in run_dir.rglob("*") if path.is_file()),
                   key=lambda path: (len(path.parts) > 1, path.as_posix()))
    listing = [f"{path.as_posix()} {(run_dir / path).stat().st_size}" for path in files]
    (folder / "runtree.txt").write_text("\n".join(listing) + "\n", encoding="utf-8")


def private_markers(path):
    lines = (line.strip() for line in path.read_text(encoding="utf-8").splitlines())
    return [line for line in lines if line and not line.startswith("#")]


def leaks(texts, markers):
    """Indexes of the markers found in any of the texts, compared without case. Never print the markers."""
    joined = "\n".join(texts).lower()
    return [index for index, marker in enumerate(markers) if marker.lower() in joined]


def aliased(value, aliases):
    """The replacement edit_intro.py applies."""
    for row in aliases:
        value = value.replace(row["find"], row["replace"])
    return value


def build_aliases(config_path, run_dir, terminal, markers):
    """Public stand-ins for private names in the terminal text and the report page."""
    proxmox = load_config(config_path).raw["providerDefaults"]["proxmox"]
    # Replace the API host before the node, because the host name may contain the node name.
    aliases = [{"find": urlsplit(proxmox["apiUrl"]).hostname, "replace": API_HOST},
               {"find": proxmox["node"], "replace": NODE}]
    profile = Path.home()
    aliases += [{"find": str(profile), "replace": USER_FOLDER},
                {"find": profile.as_posix(), "replace": USER_FOLDER.replace("\\", "/")}]
    output = json.loads((run_dir / "raw" / "actual-output.json").read_text(encoding="utf-8-sig"))
    computer = output.get("metadata", {}).get("computerName")
    if computer:
        aliases.append({"find": computer, "replace": COMPUTER})
    # oslab lists the names of the variables it loaded from the env file. Drop the private ones.
    for row in terminal["lines"]:
        label, _, value = row["text"].strip().partition(": ")
        if label in ("loadedKeys", "skippedExistingKeys"):
            names = value.split(", ")
            public = [name for name in names if not leaks([name], markers)]
            if public != names:
                aliases.append({"find": value, "replace": ", ".join(public) or "<none>"})
    return aliases


def record_report(args, folder):
    subprocess.run([
        shutil.which("node"), str(HERE / "record_page.mjs"), "--page", str(folder / "reports" / "result.html"),
        "--output", str(folder / "report.mkv"), "--screenshot", str(folder / "report-full.png"),
        "--aliases", str(folder / "aliases.json"), "--markers", str(args.blocklist), "--ffmpeg", args.ffmpeg,
    ], cwd=REPO, check=True)


def collect_evidence(args, folder, run_dir, terminal):
    copy_run_files(run_dir, folder)
    markers = private_markers(args.blocklist)
    aliases = build_aliases(REPO / args.config, run_dir, terminal, markers)
    (folder / "aliases.json").write_text(json.dumps(aliases, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    texts = [aliased(terminal["command"], aliases)] + [aliased(row["text"], aliases) for row in terminal["lines"]]
    remaining = leaks(texts, markers)
    if remaining:
        raise RuntimeError("Private markers remain in the terminal text after aliasing: "
                           + ", ".join(f"#{index}" for index in remaining))
    log(f"No private marker remains in the terminal text after {len(aliases)} aliases")
    record_report(args, folder)


def confirm_cleanup(client, vm_id, lock_dir, template_vm_id):
    """Check that the run removed its VM and its VMID reservation and left the template unlocked."""
    resources = client.request("GET", "/cluster/resources", {"type": "vm"})
    template = client.request("GET", f"/nodes/{client.config.node}/qemu/{template_vm_id}/config")
    result = {
        "vm_exists": any(row.get("vmid") == vm_id for row in resources),
        "vmid_lock_file": (lock_dir / f"vmid-{vm_id}.lock").exists(),
        "template_lock": template.get("lock"),
    }
    log(f"Cleanup of VM {vm_id}: {json.dumps(result)}")
    return result


def check_memory(client, template_vm_id, reserve_gib):
    status = client.request("GET", f"/nodes/{client.config.node}/status")
    template = client.request("GET", f"/nodes/{client.config.node}/qemu/{template_vm_id}/config")
    available = status["memory"]["available"]
    clone = int(template["memory"]) * 2**20
    log(f"Node memory available: {available / GIB:.1f} GiB; the clone needs {clone / GIB:.1f} GiB")
    if available - clone < reserve_gib * GIB:
        raise RuntimeError(f"Starting the clone would leave less than {reserve_gib} GiB of node memory available")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", type=Path, required=True, help="Capture folder that edit_intro.py reads")
    parser.add_argument("--scenario", required=True, help="Scenario path relative to the repository root")
    parser.add_argument("--artifact-path", required=True, help="Artifact path relative to the repository root")
    parser.add_argument("--config", required=True, help="OSLab config relative to the repository root")
    parser.add_argument("--env-file", required=True, help="Env file relative to the repository root")
    parser.add_argument("--lan-address", required=True, help="LAN address of the Proxmox node's API")
    parser.add_argument("--run-id", help="Defaults to intro-cli-<yyyymmdd-hhmmss>")
    parser.add_argument("--blocklist", type=Path, default=REPO / "config" / "public-release-blocklist.local.txt")
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--reserve-gib", type=float, default=20, help="Node memory to keep available")
    parser.add_argument("--evidence-only", action="store_true",
                        help="Skip the run and redo the copies, aliases and report recording for --run-id")
    parser.add_argument("--ffmpeg", default=os.environ.get("OSLAB_FFMPEG", "ffmpeg"))
    args = parser.parse_args()
    if args.evidence_only and not args.run_id:
        parser.error("--evidence-only needs --run-id")

    # The run gets the shell's environment and loads the env file itself, as a viewer's run would.
    environment = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8")
    environment.pop("VIRTUAL_ENV", None)
    load_env_file(REPO / args.env_file)
    folder = args.output.resolve()
    folder.mkdir(parents=True, exist_ok=True)
    run_id = args.run_id or time.strftime("intro-cli-%Y%m%d-%H%M%S")
    config = load_config(REPO / args.config)
    run_dir = REPO / config.output_root / run_id
    scenario = load_scenario(REPO / args.scenario)
    work = Path(tempfile.mkdtemp(prefix="oslab-capture-cli-"))
    try:
        remote = ProxmoxClient(proxmox_config_from_oslab(config))
        lan_config = lan.prepare(remote, REPO / args.config, REPO / config.output_root, work, args.lan_address)
        client = ProxmoxClient(proxmox_config_from_oslab(load_config(lan_config)))
        if args.evidence_only:
            terminal = json.loads((folder / "terminal.json").read_text(encoding="utf-8"))
        else:
            check_memory(client, scenario.template_vm_id, args.reserve_gib)
            log(f"Run {run_id}")
            terminal = asyncio.run(run_and_record(args, folder, run_id, client, run_dir, environment))
            (folder / "terminal.json").write_text(json.dumps(terminal, indent=1, ensure_ascii=False) + "\n",
                                                  encoding="utf-8")
        collect_evidence(args, folder, run_dir, terminal)
        vm_id = json.loads((folder / "console.json").read_text(encoding="utf-8")).get("vm_id")
        if vm_id is not None:
            confirm_cleanup(client, vm_id, REPO / config.output_root / ".locks", scenario.template_vm_id)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return int(terminal["exit_code"] != 0)


if __name__ == "__main__":
    raise SystemExit(main())

