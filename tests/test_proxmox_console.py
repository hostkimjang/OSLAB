import asyncio
import io
import struct
from contextlib import asynccontextmanager
from urllib.parse import parse_qs, urlsplit

import pytest

pytest.importorskip("cryptography")
pytest.importorskip("PIL")
pytest.importorskip("websockets.asyncio.client")

from PIL import Image

from oslab.errors import OslabError, ProviderError
from oslab.providers import proxmox_console
from oslab.providers.base import VmRef
from oslab.providers.proxmox import ProxmoxClient, ProxmoxConfig


class FakeWebSocket:
    def __init__(self, received: list[bytes]) -> None:
        self.received = iter(received)
        self.sent: list[bytes] = []

    async def recv(self) -> bytes:
        return next(self.received)

    async def send(self, data: bytes) -> None:
        self.sent.append(data)


@pytest.mark.parametrize("explicit_password", [True, False])
def test_console_ticket_framebuffer_and_guest_input(monkeypatch, explicit_password):
    client = ProxmoxClient(ProxmoxConfig("https://lab.example/pve", "default", "user@test!mcp", "demo-token"))
    ticket = "password:PVEVNC:fake/+"
    response = {"ticket": ticket, "port": 5912}
    if explicit_password:
        ticket = "PVEVNC:distinct+ticket"
        response.update(ticket=ticket, password="password")

    def request(method, path, params):
        assert (method, path, params) == ("POST", "/nodes/test-node/qemu/101/vncproxy", {"websocket": 1})
        return response

    monkeypatch.setattr(client, "request", request)
    challenge = bytes(range(16))
    server_init = struct.pack(">HH16xI", 2, 2, 4) + b"test"
    resize = struct.pack(">BxHHHHHi", 0, 1, 0, 0, 3, 1, -223)
    rectangle = struct.pack(">BxHHHHHi", 0, 1, 0, 0, 3, 1, 0)
    pixels = b"\x00\x00\xff\x00\x00\xff\x00\x00\xff\x00\x00\x00"
    socket = FakeWebSocket([
        b"RFB 003.",
        b"008\n\x01\x02" + challenge,
        b"\x00" * 4 + server_init,
        resize + rectangle + pixels[:7],
        pixels[7:],
    ])
    opened = []

    @asynccontextmanager
    async def connector(url, **kwargs):
        parsed = urlsplit(url)
        assert (parsed.scheme, parsed.netloc, parsed.path) == (
            "wss", "lab.example", "/pve/api2/json/nodes/test-node/qemu/101/vncwebsocket"
        )
        assert parse_qs(parsed.query) == {"port": ["5912"], "vncticket": [ticket]}
        assert kwargs["additional_headers"]["Authorization"] == "PVEAPIToken=user@test!mcp=demo-token"
        assert kwargs["compression"] is None
        opened.append("open")
        try:
            yield socket
        finally:
            opened.append("closed")

    monkeypatch.setattr(proxmox_console, "_ConsoleWebSocket", connector)

    async def run():
        async with proxmox_console.open_console(client, VmRef(101, node="test-node")) as console:
            png, width, height = await console.screenshot()
            assert (width, height) == (3, 1)
            with Image.open(io.BytesIO(png)) as image:
                assert image.getpixel((0, 0)) == (255, 0, 0)
                assert image.getpixel((1, 0)) == (0, 255, 0)
                assert image.getpixel((2, 0)) == (0, 0, 255)
            with pytest.raises(OslabError, match="coordinates"):
                await console.click(3, 0)
            with pytest.raises(OslabError, match="Unknown key"):
                await console.press_key(["unknown"])
            await console.click(2, 0, "right")
            await console.press_key(["Win", "r"])

    asyncio.run(run())

    assert opened == ["open", "closed"]
    assert socket.sent[:4] == [
        b"RFB 003.008\n",
        b"\x02",
        bytes.fromhex("b866924125c8eebb9debc1db61c538e2"),
        b"\x01",
    ]
    assert len(socket.sent[4]) == 32
    assert [struct.unpack(">BBHHHH", request) for request in socket.sent[5:7]] == [
        (3, 0, 0, 0, 2, 2),
        (3, 0, 0, 0, 3, 1),
    ]
    assert list(struct.iter_unpack(">BBHH", socket.sent[7])) == [(5, 0, 2, 0), (5, 4, 2, 0), (5, 0, 2, 0)]
    assert list(struct.iter_unpack(">BBxxI", socket.sent[8])) == [
        (4, 1, 0xFFEB), (4, 1, ord("r")), (4, 0, ord("r")), (4, 0, 0xFFEB)
    ]


def test_redacts_ticket_request_failure(monkeypatch):
    client = ProxmoxClient(ProxmoxConfig("https://lab.example", "test-node", "user@test!mcp", "demo-token"))

    def request(*args):
        raise ProviderError("secret-token", details={"status": 403, "body": "secret-token"})

    monkeypatch.setattr(client, "request", request)

    async def run():
        async with proxmox_console.open_console(client, VmRef(101)):
            pytest.fail("A refused ticket request cannot open a console")

    with pytest.raises(ProviderError, match=r"for VM 101 \(HTTP 403\)$") as caught:
        asyncio.run(run())
    assert not caught.value.details
    assert caught.value.__suppress_context__
