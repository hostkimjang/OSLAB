"""Record a Proxmox VM console as continuous video.

The recorder keeps a shared VNC session open and asks QEMU only for changed
screen regions. It samples the screen at a fixed rate against the wall clock,
so recordings of many VMs line up on one timeline. Input from the OSLab MCP
server continues to work while the recorder is attached.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import queue
import struct
import subprocess
import threading
import time
import zlib
from pathlib import Path
from urllib.parse import quote, urlencode, urlsplit, urlunsplit

from PIL import Image
from websockets.exceptions import WebSocketException

import lan
from oslab.config import load_config
from oslab.env_file import load_env_file
from oslab.errors import ProviderError
from oslab.providers.proxmox import DEFAULT_USER_AGENT, ProxmoxClient, proxmox_config_from_oslab
from oslab.providers.proxmox_console import _PRIVATE_LOG, _ConsoleWebSocket, _vnc_response

RAW, ZLIB, DESKTOP_SIZE, COMPRESSION_LEVEL_6 = 0, 6, -223, -250
# Little-endian 32-bit true colour with B, G, R and padding bytes in memory.
PIXEL_FORMAT = struct.pack(">BBBBHHHBBBxxx", 32, 24, 0, 1, 255, 255, 255, 16, 8, 0)


class Stream:
    """Buffered RFB reads over WebSocket messages."""

    def __init__(self, websocket):
        self.websocket = websocket
        self.buffer = bytearray()
        self.offset = 0
        self.received = 0

    async def read(self, size):
        while len(self.buffer) - self.offset < size:
            if self.offset:
                del self.buffer[:self.offset]
                self.offset = 0
            data = await self.websocket.recv()
            if not isinstance(data, bytes):
                raise ProviderError("The console sent a text WebSocket message")
            self.received += len(data)
            self.buffer += data
        start = self.offset
        self.offset += size
        return bytes(memoryview(self.buffer)[start:self.offset])

    async def write(self, data):
        await self.websocket.send(data)


def console_ticket(client, vm_id):
    path = f"/nodes/{quote(client.config.node, safe='')}/qemu/{vm_id}"
    proxy = client.request("POST", f"{path}/vncproxy", {"websocket": 1})
    origin = urlsplit(client.config.base_url)
    url = urlunsplit(("wss" if origin.scheme == "https" else "ws", origin.netloc, f"{origin.path}{path}/vncwebsocket",
                      urlencode({"port": proxy["port"], "vncticket": proxy["ticket"]}), ""))
    return url, proxy.get("password") or proxy["ticket"]


async def handshake(stream, password):
    version = await stream.read(12)
    if version not in (b"RFB 003.008\n", b"RFB 003.007\n"):
        raise ProviderError("The console requires VNC protocol 3.7 or 3.8")
    await stream.write(version)
    if 2 not in await stream.read((await stream.read(1))[0]):
        raise ProviderError("The console did not offer VNC password authentication")
    await stream.write(b"\x02")
    await stream.write(_vnc_response(password, await stream.read(16)))
    if await stream.read(4) != bytes(4):
        raise ProviderError("VNC authentication failed")
    await stream.write(b"\x01")  # Share the desktop with the MCP input session.
    width, height, name_length = struct.unpack(">HH16xI", await stream.read(24))
    await stream.read(name_length)
    encodings = (ZLIB, RAW, DESKTOP_SIZE, COMPRESSION_LEVEL_6)
    await stream.write(bytes(4) + PIXEL_FORMAT + struct.pack(f">BxH{len(encodings)}i", 2, len(encodings), *encodings))
    return width, height


class Screen:
    """The latest console image, kept current by incremental VNC updates."""

    def __init__(self, client, vm_id):
        self.client = client
        self.vm_id = vm_id
        self.image = None
        self.updates = 0
        self.received = 0
        self.reconnects = 0
        self.ready = asyncio.Event()

    async def follow(self):
        while True:
            try:
                await self.session()
            except (OSError, WebSocketException, ProviderError, zlib.error, asyncio.TimeoutError):
                self.reconnects += 1
                await asyncio.sleep(1.5)

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
            stream = Stream(websocket)
            width, height = await asyncio.wait_for(handshake(stream, password), config.timeout_seconds)
            if self.image is None:
                self.image = Image.new("RGB", (width, height))
            elif self.image.size != (width, height):
                raise RuntimeError("The VM changed its screen size during recording")
            inflate = zlib.decompressobj()
            incremental = 0
            counted = 0
            while True:
                await stream.write(struct.pack(">BBHHHH", 3, incremental, 0, 0, width, height))
                incremental = 1
                await self.update(stream, inflate, width, height)
                self.received += stream.received - counted
                counted = stream.received

    async def update(self, stream, inflate, width, height):
        while (kind := (await stream.read(1))[0]) != 0:
            if kind == 3:  # Clipboard text.
                (length,) = struct.unpack(">3xI", await stream.read(7))
                await stream.read(length)
            elif kind != 2:  # Bell messages carry no data.
                raise ProviderError("The console sent an unsupported VNC message")
        (count,) = struct.unpack(">xH", await stream.read(3))
        tiles = []
        for _ in range(count):
            x, y, w, h, encoding = struct.unpack(">HHHHi", await stream.read(12))
            if encoding == DESKTOP_SIZE:
                raise RuntimeError("The VM changed its screen size during recording")
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
        for position, tile in tiles:
            self.image.paste(tile, position)
        self.updates += 1
        self.ready.set()


class Encoder:
    def __init__(self, ffmpeg, path, size, fps):
        width, height = size
        self.process = subprocess.Popen([
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
            "-s", f"{width}x{height}", "-framerate", str(fps), "-i", "pipe:0", "-c:v", "libx264",
            "-preset", "veryfast", "-crf", "14", "-pix_fmt", "yuv444p", "-g", str(fps * 2), "-f", "matroska", str(path),
        ], stdin=subprocess.PIPE)
        self.frames = queue.Queue(maxsize=60)
        self.thread = threading.Thread(target=self.drain, daemon=True)
        self.thread.start()

    def drain(self):
        while (frame := self.frames.get()) is not None:
            self.process.stdin.write(frame)
        self.process.stdin.close()

    def finish(self):
        self.frames.put(None)
        self.thread.join()
        return self.process.wait()


def write_meta(path, meta):
    scratch = path.with_suffix(".tmp")
    scratch.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    scratch.replace(path)


async def record(args):
    if args.env_file:
        load_env_file(args.env_file)
    lan.apply_from_environment()
    client = ProxmoxClient(proxmox_config_from_oslab(load_config(args.config)))
    screen = Screen(client, args.vm_id)
    follower = asyncio.create_task(screen.follow())
    meta_path = args.output.with_suffix(".json")
    meta = {"vm_id": args.vm_id, "label": args.label, "file": args.output.name, "fps": args.fps, "status": "connecting"}
    try:
        await asyncio.wait_for(screen.ready.wait(), 90)
    except asyncio.TimeoutError:
        follower.cancel()
        write_meta(meta_path, {**meta, "status": "no-console", "reconnects": screen.reconnects})
        return 1
    encoder = Encoder(args.ffmpeg, args.output, screen.image.size, args.fps)
    period = 1 / args.fps
    start = time.time()
    meta.update(status="recording", t0=start, width=screen.image.width, height=screen.image.height)
    write_meta(meta_path, meta)
    frames = 0
    failure = None
    try:
        while not args.stop_file.exists() and time.time() - start < args.max_seconds:
            if follower.done():
                failure = repr(follower.exception())
                break
            due = start + frames * period
            now = time.time()
            if now < due:
                await asyncio.sleep(min(due - now, .25))
                continue
            frame = screen.image.tobytes()
            # Repeat the current image for any missed slots to keep a constant frame rate.
            for _ in range(1 + int((now - due) / period)):
                await asyncio.to_thread(encoder.frames.put, frame)
                frames += 1
    finally:
        follower.cancel()
        code = await asyncio.to_thread(encoder.finish)
    status = "complete" if code == 0 and failure is None else "failed"
    meta.update(status=status, failure=failure, encoder_exit=code, frames=frames, seconds=round(frames / args.fps, 3),
                updates=screen.updates, received_bytes=screen.received, reconnects=screen.reconnects, ended=time.time())
    write_meta(meta_path, meta)
    return int(status != "complete")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--vm-id", type=int, required=True)
    parser.add_argument("--label", default="")
    parser.add_argument("--output", type=Path, required=True, help="Matroska file to write")
    parser.add_argument("--fps", type=int, default=15)
    parser.add_argument("--stop-file", type=Path, required=True, help="Stop when this file exists")
    parser.add_argument("--max-seconds", type=float, default=1800)
    parser.add_argument("--ffmpeg", default=os.environ.get("OSLAB_FFMPEG", "ffmpeg"))
    return asyncio.run(record(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
