"""Headless access to a Proxmox QEMU console over its VNC WebSocket."""

from __future__ import annotations

import asyncio
import io
import logging
import ssl
import struct
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from urllib.parse import quote, urlencode, urlsplit, urlunsplit

from cryptography.hazmat.decrepit.ciphers.algorithms import TripleDES
from cryptography.hazmat.primitives.ciphers import Cipher, modes
from PIL import Image
from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import InvalidStatus, WebSocketException

from oslab.errors import OslabError, ProviderError
from oslab.providers.base import VmRef
from oslab.providers.proxmox import DEFAULT_USER_AGENT, ProxmoxClient

_MAX_PIXELS = 16 * 1024 * 1024
_MAX_TEXT_BYTES = 1024 * 1024
_RFB_38 = b"RFB 003.008\n"
_RFB_37 = b"RFB 003.007\n"
_DESKTOP_SIZE = -223
_RAW = 0
_VNC_AUTH = 2
_PASSWORD_BIT_ORDER = bytes(int(f"{value:08b}"[::-1], 2) for value in range(256))
_BUTTONS = {"left": 1, "middle": 2, "right": 4}
_KEYSYMS = {
    "backspace": 0xFF08,
    "tab": 0xFF09,
    "enter": 0xFF0D,
    "return": 0xFF0D,
    "escape": 0xFF1B,
    "esc": 0xFF1B,
    "home": 0xFF50,
    "left": 0xFF51,
    "up": 0xFF52,
    "right": 0xFF53,
    "down": 0xFF54,
    "pageup": 0xFF55,
    "pagedown": 0xFF56,
    "end": 0xFF57,
    "insert": 0xFF63,
    "delete": 0xFFFF,
    "shift": 0xFFE1,
    "ctrl": 0xFFE3,
    "control": 0xFFE3,
    "alt": 0xFFE9,
    "win": 0xFFEB,
    "super": 0xFFEB,
    "space": 0x20,
    **{f"f{number}": 0xFFBD + number for number in range(1, 13)},
}

# WebSocket debug output includes the request target and Authorization header.
_PRIVATE_LOG = logging.Logger("oslab.proxmox-console.websocket", logging.WARNING)
_PRIVATE_LOG.addHandler(logging.NullHandler())


class _ConsoleWebSocket(connect):
    def process_redirect(self, exc: Exception) -> Exception:
        # The ticket and API token are valid only at the configured endpoint.
        return exc


class _RfbStream:
    def __init__(self, websocket: ClientConnection) -> None:
        self.websocket = websocket
        self.buffer = bytearray()

    async def read(self, size: int) -> bytes:
        while len(self.buffer) < size:
            data = await self.websocket.recv()
            if not isinstance(data, bytes):
                raise ProviderError("Proxmox console sent a non-binary WebSocket message")
            self.buffer.extend(data)
        with memoryview(self.buffer) as buffer:
            result = bytes(buffer[:size])
        del self.buffer[:size]
        return result

    async def write(self, data: bytes) -> None:
        await self.websocket.send(data)


def _vnc_response(password: str, challenge: bytes) -> bytes:
    # RFB applies DES with reversed key bits. Using the same key for all
    # three TripleDES passes performs the required single-key DES operation.
    key = password.encode("utf-8")[:8].ljust(8, b"\x00").translate(_PASSWORD_BIT_ORDER)
    encryptor = Cipher(TripleDES(key * 3), modes.ECB()).encryptor()
    return encryptor.update(challenge) + encryptor.finalize()


def _check_dimensions(width: int, height: int) -> None:
    if width <= 0 or height <= 0 or width * height > _MAX_PIXELS:
        raise ProviderError("Proxmox console reported an unsupported framebuffer size")


def _keysym(key: str) -> int:
    if len(key) == 1 and " " <= key <= "~":
        return ord(key)
    if (symbol := _KEYSYMS.get(key.lower())) is not None:
        return symbol
    raise OslabError("Unknown key. Use printable ASCII, named keys, or a modifier chord")


@dataclass
class ConsoleConnection:
    """A dedicated VNC session. The caller serializes calls on the session."""

    _stream: _RfbStream
    width: int
    height: int
    _timeout: int

    @classmethod
    async def _initialize(
        cls, stream: _RfbStream, password: str, timeout: int
    ) -> ConsoleConnection:
        version = await stream.read(12)
        if version not in {_RFB_38, _RFB_37}:
            raise ProviderError("Proxmox console requires VNC protocol 3.7 or 3.8")
        await stream.write(version)
        security_count = (await stream.read(1))[0]
        security_types = await stream.read(security_count)
        if _VNC_AUTH not in security_types:
            raise ProviderError("Proxmox console did not offer VNC password authentication")
        await stream.write(bytes([_VNC_AUTH]))
        await stream.write(_vnc_response(password, await stream.read(16)))
        if await stream.read(4) != b"\x00" * 4:
            raise ProviderError("Proxmox VNC authentication failed")

        await stream.write(b"\x01")  # Shared desktop access.
        width, height, name_length = struct.unpack(">HH16xI", await stream.read(24))
        _check_dimensions(width, height)
        if name_length > _MAX_TEXT_BYTES:
            raise ProviderError("Proxmox console name is too large")
        await stream.read(name_length)
        # Request little-endian 32-bit true colour, with B, G, R, padding in memory.
        pixel_format = struct.pack(">BBBBHHHBBBxxx", 32, 24, 0, 1, 255, 255, 255, 16, 8, 0)
        encodings = struct.pack(">BxHii", 2, 2, _RAW, _DESKTOP_SIZE)
        await stream.write(b"\x00" * 4 + pixel_format + encodings)
        return cls(stream, width, height, timeout)

    async def screenshot(self) -> tuple[bytes, int, int]:
        """Request a new framebuffer and return its PNG and native dimensions."""
        try:
            async with asyncio.timeout(self._timeout):
                image = await self._read_frame()
                png = await asyncio.to_thread(_encode_png, image)
        except (OSError, WebSocketException) as exc:
            raise _operation_error("capture the screen", exc) from None
        return png, image.width, image.height

    async def _read_frame(self) -> Image.Image:
        while True:
            await self._stream.write(struct.pack(">BBHHHH", 3, 0, 0, 0, self.width, self.height))
            while True:
                message_type = (await self._stream.read(1))[0]
                if message_type == 0:
                    break
                if message_type == 2:  # Bell.
                    continue
                if message_type != 3:  # ServerCutText.
                    raise ProviderError("Proxmox console sent an unsupported VNC message")
                (length,) = struct.unpack(">3xI", await self._stream.read(7))
                if length > _MAX_TEXT_BYTES:
                    raise ProviderError("Proxmox console clipboard message is too large")
                await self._stream.read(length)
            image = await self._read_rectangles()
            if image is not None:
                return image

    async def _read_rectangles(self) -> Image.Image | None:
        (count,) = struct.unpack(">xH", await self._stream.read(3))
        image = Image.new("RGB", (self.width, self.height))
        has_pixels = False
        resized = False
        for _ in range(count):
            x, y, width, height, encoding = struct.unpack(">HHHHi", await self._stream.read(12))
            if encoding == _DESKTOP_SIZE:
                _check_dimensions(width, height)
                self.width, self.height = width, height
                resized = True
                continue
            if encoding != _RAW:
                raise ProviderError("Proxmox console sent an unsupported framebuffer encoding")
            if width == 0 or height == 0 or x + width > image.width or y + height > image.height:
                raise ProviderError("Proxmox console sent a rectangle outside the framebuffer")
            pixels = await self._stream.read(width * height * 4)
            image.paste(Image.frombytes("RGB", (width, height), pixels, "raw", "BGRX"), (x, y))
            has_pixels = True
        return image if has_pixels and not resized else None

    async def click(self, x: int, y: int, button: str = "left") -> None:
        """Click in native framebuffer coordinates using the guest's pointer."""
        if not (0 <= x < self.width and 0 <= y < self.height):
            raise OslabError(f"Click coordinates must be inside the {self.width}×{self.height} VM screen")
        if button not in _BUTTONS:
            raise OslabError("Button must be left, middle, or right")
        # Move first, then press and release as one WebSocket message.
        await self._send_input(b"".join(
            struct.pack(">BBHH", 5, mask, x, y) for mask in (0, _BUTTONS[button], 0)
        ))

    async def move(self, x: int, y: int) -> None:
        """Move the guest's pointer to native framebuffer coordinates without clicking."""
        if not (0 <= x < self.width and 0 <= y < self.height):
            raise OslabError(f"Pointer coordinates must be inside the {self.width}×{self.height} VM screen")
        await self._send_input(struct.pack(">BBHH", 5, 0, x, y))

    async def press_key(self, keys: list[str]) -> None:
        """Press a printable ASCII key, named key, or modifier chord in the VM."""
        if not 1 <= len(keys) <= 8:
            raise OslabError("Supply between one and eight keys")
        symbols = [_keysym(key) for key in keys]
        if len(symbols) != len(set(symbols)):
            raise OslabError("A key chord cannot contain duplicate keys")
        down = b"".join(struct.pack(">BBxxI", 4, 1, key) for key in symbols)
        up = b"".join(struct.pack(">BBxxI", 4, 0, key) for key in reversed(symbols))
        await self._send_input(down + up)

    async def _send_input(self, messages: bytes) -> None:
        try:
            async with asyncio.timeout(self._timeout):
                await self._stream.write(messages)
        except (OSError, WebSocketException) as exc:
            raise _operation_error("send input", exc) from None


def _encode_png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _operation_error(action: str, cause: Exception) -> ProviderError:
    detail = "connection interrupted"
    if isinstance(cause, TimeoutError):
        detail = "timed out"
    elif isinstance(cause, InvalidStatus):
        detail = f"HTTP {cause.response.status_code}"
    elif isinstance(cause, ssl.SSLCertVerificationError):
        detail = "TLS certificate verification failed"
    return ProviderError(f"Could not {action} through the Proxmox console ({detail})")


@asynccontextmanager
async def open_console(client: ProxmoxClient, vm: VmRef) -> AsyncIterator[ConsoleConnection]:
    """Open a short-lived console ticket and attach directly to the running VM."""
    config = client.config
    origin = urlsplit(config.base_url)
    if origin.scheme not in {"http", "https"} or not origin.netloc:
        raise ProviderError("The Proxmox console API URL must use HTTP or HTTPS")
    node = quote(vm.node or config.node, safe="")
    path = f"/nodes/{node}/qemu/{vm.vm_id}"
    try:
        proxy = await asyncio.to_thread(client.request, "POST", f"{path}/vncproxy", {"websocket": 1})
    except ProviderError as exc:
        status = exc.details.get("status")
        detail = f" (HTTP {status})" if isinstance(status, int) else ""
        raise ProviderError(f"Could not request a Proxmox console ticket for VM {vm.vm_id}{detail}") from None
    except OSError as exc:
        raise _operation_error(f"request a ticket for VM {vm.vm_id}", exc) from None
    if not isinstance(proxy, dict):
        raise ProviderError("Proxmox console returned an invalid ticket response")
    ticket = proxy.get("ticket")
    port = proxy.get("port")
    if not isinstance(ticket, str) or not ticket or not str(port).isdecimal() or not 5900 <= int(port) <= 5999:
        raise ProviderError("Proxmox console returned an invalid ticket or port")
    password = proxy.get("password") or ticket
    if not isinstance(password, str):
        raise ProviderError("Proxmox console returned an invalid VNC password")

    url = urlunsplit((
        "wss" if origin.scheme == "https" else "ws",
        origin.netloc,
        f"{origin.path}{path}/vncwebsocket",
        urlencode({"port": port, "vncticket": ticket}),
        "",
    ))
    tls = {}
    if origin.scheme == "https" and not config.verify_tls:
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        tls = {"ssl": context}

    async with AsyncExitStack() as stack:
        try:
            websocket = await stack.enter_async_context(_ConsoleWebSocket(
                url,
                additional_headers={"Authorization": f"PVEAPIToken={config.token_id}={config.token_secret}"},
                user_agent_header=DEFAULT_USER_AGENT,
                compression=None,
                open_timeout=config.timeout_seconds,
                close_timeout=3,
                max_size=_MAX_PIXELS * 4 + 16,
                logger=_PRIVATE_LOG,
                **tls,
            ))
            async with asyncio.timeout(config.timeout_seconds):
                console = await ConsoleConnection._initialize(
                    _RfbStream(websocket), password, config.timeout_seconds
                )
        except (OSError, WebSocketException) as exc:
            raise _operation_error(f"open a connection to VM {vm.vm_id}", exc) from None
        yield console
