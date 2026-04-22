from __future__ import annotations

import pytest

from oslab.errors import OslabError, ProviderError
from oslab.guests.qemu_agent import QemuAgentChannel
from oslab.providers.base import VmRef


class FakeClient:
    def __init__(self, statuses: list[dict]) -> None:
        self.statuses = list(statuses)
        self.commands: list[list[str]] = []
        self.file_writes: list[tuple[int, str, str, bool]] = []
        self.file_reads: list[tuple[int, str]] = []
        self.file_read_result = {"content": "downloaded\n", "truncated": 0}

    def get_guest_network_interfaces(self, vmid: int):
        return {"result": [{"name": "Ethernet"}]}

    def guest_exec(self, vmid: int, command: list[str]):
        self.commands.append(command)
        return {"pid": 42}

    def get_guest_exec_status(self, vmid: int, pid: int):
        if not self.statuses:
            raise AssertionError("No fake exec status configured")
        return self.statuses.pop(0)

    def guest_file_write(self, vmid: int, guest_path: str, content: str, *, encode: bool = True):
        self.file_writes.append((vmid, guest_path, content, encode))

    def guest_file_read(self, vmid: int, guest_path: str):
        self.file_reads.append((vmid, guest_path))
        return self.file_read_result


def _latin1_view(value: bytes) -> str:
    return value.decode("latin-1")


def _utf8_mojibake(text: str) -> str:
    return _latin1_view(text.encode("utf-8"))


def _cp949_mojibake(text: str) -> str:
    return _latin1_view(text.encode("cp949"))


def test_qemu_agent_channel_executes_and_collects_output() -> None:
    client = FakeClient(
        [
            {"exited": False},
            {"exited": 1, "exitcode": 0, "out-data": "hello\n", "err-data": ""},
        ]
    )
    channel = QemuAgentChannel(client, sleep=lambda _: None)

    result = channel.execute(VmRef(vm_id=9101), ["cmd.exe", "/c", "echo hello"], poll_interval_seconds=0)

    assert result.passed is True
    assert result.exit_code == 0
    assert result.stdout == "hello\n"
    assert result.stderr == ""
    assert result.command == ("cmd.exe", "/c", "echo hello")
    assert client.commands == [["cmd.exe", "/c", "echo hello"]]


def test_qemu_agent_channel_reports_nonzero_exit_code() -> None:
    client = FakeClient([{"exited": True, "exitcode": 5, "out-data": "", "err-data": "bad\n"}])
    channel = QemuAgentChannel(client, sleep=lambda _: None)

    result = channel.execute(VmRef(vm_id=9101), ["cmd.exe", "/c", "exit 5"], poll_interval_seconds=0)

    assert result.passed is False
    assert result.exit_code == 5
    assert result.stderr == "bad\n"


def test_qemu_agent_channel_repairs_utf8_mojibake_output() -> None:
    client = FakeClient(
        [
            {
                "exited": True,
                "exitcode": 0,
                "out-data": _utf8_mojibake("스캔 완료\n"),
                "err-data": _utf8_mojibake("취약점 ScanAgent을 시작합니다.\n"),
            }
        ]
    )
    channel = QemuAgentChannel(client, sleep=lambda _: None)

    result = channel.execute(VmRef(vm_id=9101), ["powershell.exe", "-Command", "scan"], poll_interval_seconds=0)

    assert result.stdout == "스캔 완료\n"
    assert result.stderr == "취약점 ScanAgent을 시작합니다.\n"


def test_qemu_agent_channel_repairs_cp949_mojibake_output() -> None:
    cp949_mojibake = "Python runtime was not found.\r\n" + _cp949_mojibake(
        "위치 C:\\Oslab\\artifact\\run-python-demo.ps1:15 문자:3\r\n"
    )
    client = FakeClient(
        [
            {
                "exited": True,
                "exitcode": 1,
                "out-data": "",
                "err-data": cp949_mojibake,
            }
        ]
    )
    channel = QemuAgentChannel(client, sleep=lambda _: None)

    result = channel.execute(VmRef(vm_id=9101), ["powershell.exe", "-File", "demo.ps1"], poll_interval_seconds=0)

    assert result.stderr == "Python runtime was not found.\r\n위치 C:\\Oslab\\artifact\\run-python-demo.ps1:15 문자:3\r\n"


def test_qemu_agent_channel_repairs_utf8_symbol_without_misreading_cp949() -> None:
    client = FakeClient(
        [
            {
                "exited": True,
                "exitcode": 0,
                "out-data": _utf8_mojibake("Microsoft® Concurrency Runtime Library\n"),
                "err-data": "",
            }
        ]
    )
    channel = QemuAgentChannel(client, sleep=lambda _: None)

    result = channel.execute(VmRef(vm_id=9101), ["powershell.exe", "-Command", "echo"], poll_interval_seconds=0)

    assert result.stdout == "Microsoft® Concurrency Runtime Library\n"


def test_qemu_agent_channel_rejects_empty_command() -> None:
    channel = QemuAgentChannel(FakeClient([]), sleep=lambda _: None)

    with pytest.raises(OslabError, match="must not be empty"):
        channel.execute(VmRef(vm_id=9101), [])


def test_qemu_agent_channel_timeout_includes_diagnostics() -> None:
    ticks = iter([0.0, 0.0, 1.1])
    client = FakeClient([{"exited": False}])
    channel = QemuAgentChannel(client, sleep=lambda _: None, monotonic=lambda: next(ticks))

    with pytest.raises(ProviderError, match="Timed out waiting for QEMU Guest Agent command") as exc:
        channel.execute(
            VmRef(vm_id=9101),
            ["cmd.exe", "/c", "timeout"],
            timeout_seconds=1,
            poll_interval_seconds=0,
        )

    assert exc.value.details["failureClass"] == "guest_execution_timeout"
    assert exc.value.details["vmId"] == 9101
    assert exc.value.details["pid"] == 42
    assert exc.value.details["command"] == ["cmd.exe", "/c", "timeout"]


def test_qemu_agent_probe_returns_false_on_provider_error() -> None:
    class BrokenProbeClient(FakeClient):
        def get_guest_network_interfaces(self, vmid: int):
            raise ProviderError("QEMU guest agent is not running")

    channel = QemuAgentChannel(BrokenProbeClient([]), sleep=lambda _: None)

    assert channel.probe(VmRef(vm_id=9101)) is False


def test_qemu_agent_upload_bytes_base64_encodes_without_double_encoding() -> None:
    client = FakeClient([])
    channel = QemuAgentChannel(client, sleep=lambda _: None)

    result = channel.upload_bytes(VmRef(vm_id=9101), r"C:\Oslab\fixture.txt", b"hello\n")

    assert result.guest_path == r"C:\Oslab\fixture.txt"
    assert result.bytes_written == 6
    assert client.file_writes == [(9101, r"C:\Oslab\fixture.txt", "aGVsbG8K", False)]


def test_qemu_agent_upload_chunks_large_payload() -> None:
    client = FakeClient(
        [
            {"exited": 1, "exitcode": 0, "out-data": "", "err-data": ""},
            {"exited": 1, "exitcode": 0, "out-data": "", "err-data": ""},
        ]
    )
    channel = QemuAgentChannel(client, sleep=lambda _: None)
    progress_events: list[tuple[int, int]] = []

    result = channel.upload_bytes(
        VmRef(vm_id=9101),
        r"C:\Oslab\large.bin",
        b"x" * 50000,
        progress=lambda written, total: progress_events.append((written, total)),
    )

    assert result.guest_path == r"C:\Oslab\large.bin"
    assert result.bytes_written == 50000
    assert progress_events[-1] == (50000, 50000)
    assert all(total == 50000 for _, total in progress_events)
    assert len(client.commands) == 2
    assert "New-Item -ItemType Directory" in client.commands[0][-1]
    assert "[System.Convert]::FromBase64String" in client.commands[1][-1]
    assert len(client.file_writes) == 2
    assert client.file_writes[0][1] == r"C:\Oslab\.large.bin.chunks\part-000000.b64"


def test_qemu_agent_download_text_returns_content() -> None:
    client = FakeClient([])
    channel = QemuAgentChannel(client, sleep=lambda _: None)

    result = channel.download_text(VmRef(vm_id=9101), r"C:\Oslab\result.json")

    assert result.content == "downloaded\n"
    assert result.bytes_read == len(b"downloaded\n")
    assert result.truncated is False
    assert client.file_reads == [(9101, r"C:\Oslab\result.json")]


def test_qemu_agent_download_text_falls_back_to_powershell_base64() -> None:
    class BrokenFileReadClient(FakeClient):
        def guest_file_read(self, vmid: int, guest_path: str):
            raise ProviderError("agent file-read failed", details={"status": 596})

    client = BrokenFileReadClient(
        [
            {
                "exited": 1,
                "exitcode": 0,
                "out-data": "eyJvayI6IHRydWV9Cg==\n",
                "err-data": "",
            }
        ]
    )
    channel = QemuAgentChannel(client, sleep=lambda _: None)

    result = channel.download_text(VmRef(vm_id=9101), r"C:\Oslab\result.json")

    assert result.content == '{"ok": true}\n'
    assert result.raw["fallback"] == "powershell-base64"
    assert "[System.Convert]::ToBase64String" in client.commands[0][-1]


def test_qemu_agent_download_text_strips_mojibake_utf8_bom() -> None:
    client = FakeClient([])
    client.file_read_result = {"content": _latin1_view(b"\xef\xbb\xbf") + '{"ok": true}\n', "truncated": 0}
    channel = QemuAgentChannel(client, sleep=lambda _: None)

    result = channel.download_text(VmRef(vm_id=9101), r"C:\Oslab\result.json")

    assert result.content == '{"ok": true}\n'


def test_qemu_agent_download_text_repairs_utf8_mojibake() -> None:
    client = FakeClient([])
    client.file_read_result = {"content": _utf8_mojibake("스캔 결과\n"), "truncated": 0}
    channel = QemuAgentChannel(client, sleep=lambda _: None)

    result = channel.download_text(VmRef(vm_id=9101), r"C:\Oslab\korean.log")

    assert result.content == "스캔 결과\n"


def test_qemu_agent_download_text_repairs_cp949_mojibake() -> None:
    client = FakeClient([])
    client.file_read_result = {"content": _cp949_mojibake("위치: C:\\Oslab\r\n"), "truncated": 0}
    channel = QemuAgentChannel(client, sleep=lambda _: None)

    result = channel.download_text(VmRef(vm_id=9101), r"C:\Oslab\korean.log")

    assert result.content == "위치: C:\\Oslab\r\n"


def test_qemu_agent_download_rejects_truncated_content() -> None:
    client = FakeClient([])
    client.file_read_result = {"content": "partial", "truncated": 1}
    channel = QemuAgentChannel(client, sleep=lambda _: None)

    with pytest.raises(ProviderError, match="truncated"):
        channel.download_text(VmRef(vm_id=9101), r"C:\Oslab\large.log")
