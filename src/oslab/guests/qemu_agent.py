"""QEMU Guest Agent channel over the Proxmox API."""

from __future__ import annotations

import base64
import time
from collections.abc import Callable, Sequence
from pathlib import PureWindowsPath
from typing import Any

from oslab.errors import OslabError, ProviderError
from oslab.guests.base import GuestCommandResult, GuestFileReadResult, GuestFileWriteResult
from oslab.providers.base import VmRef
from oslab.providers.proxmox import ProxmoxClient

MAX_FILE_WRITE_CONTENT_LENGTH = 60 * 1024
MAX_CHUNK_RAW_BYTES = 44 * 1024
UploadProgressCallback = Callable[[int, int], None]


def _latin1_view(value: bytes) -> str:
    return value.decode("latin-1")


def _latin1_chars(values: tuple[int, ...]) -> tuple[str, ...]:
    return tuple(_latin1_view(bytes((value,))) for value in values)


_MOJIBAKE_UTF8_BOM = _latin1_view(b"\xef\xbb\xbf")
_UTF8_MOJIBAKE_MARKERS = _latin1_chars((0xEC, 0xED, 0xEB, 0xEA, 0xC2, 0xC3)) + (_MOJIBAKE_UTF8_BOM,)
_CP949_MOJIBAKE_MARKERS = _latin1_chars(
    (
        0xC0,
        0xC1,
        0xC4,
        0xC5,
        0xC7,
        0xB8,
        0xB9,
        0xBA,
        0xBC,
        0xBD,
        0xBE,
        0xBF,
        0xB0,
        0xB1,
        0xB2,
        0xB3,
        0xB4,
        0xB5,
        0xB6,
        0xB7,
        0xC6,
    )
)
_ALL_MOJIBAKE_MARKERS = _UTF8_MOJIBAKE_MARKERS + _CP949_MOJIBAKE_MARKERS


class QemuAgentChannel:
    """Execute guest commands through Proxmox QEMU Guest Agent endpoints."""

    def __init__(
        self,
        client: ProxmoxClient,
        *,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.client = client
        self.sleep = sleep
        self.monotonic = monotonic

    def probe(self, vm: VmRef) -> bool:
        try:
            self.client.get_guest_network_interfaces(vm.vm_id)
        except ProviderError:
            return False
        return True

    def execute(
        self,
        vm: VmRef,
        command: Sequence[str],
        *,
        timeout_seconds: int = 60,
        poll_interval_seconds: float = 1.0,
    ) -> GuestCommandResult:
        argv = tuple(str(part) for part in command)
        if not argv:
            raise OslabError("Guest command must not be empty")
        if timeout_seconds <= 0:
            raise OslabError("Guest command timeout must be a positive integer")
        if poll_interval_seconds < 0:
            raise OslabError("Guest command poll interval must not be negative")

        start_result = self.client.guest_exec(vm.vm_id, list(argv))
        pid = _coerce_pid(start_result.get("pid"))
        return self.wait_for_exec_status(
            vm,
            pid=pid,
            command=argv,
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
        )

    def wait_for_exec_status(
        self,
        vm: VmRef,
        *,
        pid: int,
        command: tuple[str, ...],
        timeout_seconds: int,
        poll_interval_seconds: float,
    ) -> GuestCommandResult:
        deadline = self.monotonic() + timeout_seconds
        last_status: dict[str, Any] | None = None
        while self.monotonic() <= deadline:
            last_status = self.client.get_guest_exec_status(vm.vm_id, pid)
            if bool(last_status.get("exited")):
                return _result_from_status(command, last_status)
            self.sleep(poll_interval_seconds)

        raise ProviderError(
            f"Timed out waiting for QEMU Guest Agent command on VM {vm.vm_id}",
            details={
                "failureClass": "guest_execution_timeout",
                "vmId": vm.vm_id,
                "pid": pid,
                "command": list(command),
                "lastStatus": last_status,
            },
        )

    def upload_bytes(
        self,
        vm: VmRef,
        guest_path: str,
        content: bytes,
        *,
        progress: UploadProgressCallback | None = None,
    ) -> GuestFileWriteResult:
        if not guest_path.strip():
            raise OslabError("Guest path must not be empty")
        if len(base64.b64encode(content)) > MAX_FILE_WRITE_CONTENT_LENGTH:
            return self._upload_large_bytes(vm, guest_path, content, progress=progress)
        self._upload_small_bytes(vm, guest_path, content)
        if progress is not None:
            progress(len(content), len(content))
        return GuestFileWriteResult(guest_path=guest_path, bytes_written=len(content))

    def _upload_small_bytes(self, vm: VmRef, guest_path: str, content: bytes) -> None:
        encoded = base64.b64encode(content).decode("ascii")
        if len(encoded) > MAX_FILE_WRITE_CONTENT_LENGTH:
            raise OslabError(
                "Guest file upload is too large for Proxmox QEMU Guest Agent file-write",
                details={
                    "guestPath": guest_path,
                    "bytes": len(content),
                    "encodedBytes": len(encoded),
                    "maxEncodedBytes": MAX_FILE_WRITE_CONTENT_LENGTH,
                },
            )
        self.client.guest_file_write(vm.vm_id, guest_path, encoded, encode=False)

    def _upload_large_bytes(
        self,
        vm: VmRef,
        guest_path: str,
        content: bytes,
        *,
        progress: UploadProgressCallback | None,
    ) -> GuestFileWriteResult:
        target = PureWindowsPath(guest_path)
        parent = str(target.parent)
        safe_name = _safe_chunk_name(target.name)
        parts_dir = str(PureWindowsPath(parent) / f".{safe_name}.chunks")
        encoded = base64.b64encode(content).decode("ascii")
        chunks = [encoded[index : index + MAX_CHUNK_RAW_BYTES] for index in range(0, len(encoded), MAX_CHUNK_RAW_BYTES)]

        prep = self.execute(
            vm,
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                (
                    "$ErrorActionPreference = 'Stop'; "
                    f"Remove-Item -LiteralPath {_ps_single_quote(parts_dir)} -Recurse -Force -ErrorAction SilentlyContinue; "
                    f"New-Item -ItemType Directory -Force -Path {_ps_single_quote(parts_dir)} | Out-Null"
                ),
            ],
            timeout_seconds=60,
            poll_interval_seconds=1.0,
        )
        if not prep.passed:
            raise ProviderError(
                "Failed to prepare guest chunk upload directory",
                details={"guestPath": guest_path, "partsDir": parts_dir, "exitCode": prep.exit_code, "stderr": prep.stderr},
            )

        encoded_written = 0
        encoded_total = len(encoded)
        for index, chunk in enumerate(chunks):
            part_path = str(PureWindowsPath(parts_dir) / f"part-{index:06d}.b64")
            self._upload_small_bytes(vm, part_path, chunk.encode("ascii"))
            encoded_written += len(chunk)
            if progress is not None:
                bytes_written = min(len(content), int((encoded_written / encoded_total) * len(content)))
                progress(bytes_written, len(content))

        decode = self.execute(
            vm,
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                _decode_chunks_command(parts_dir, guest_path),
            ],
            timeout_seconds=120,
            poll_interval_seconds=1.0,
        )
        if not decode.passed:
            raise ProviderError(
                "Failed to decode guest chunk upload",
                details={
                    "guestPath": guest_path,
                    "partsDir": parts_dir,
                    "chunks": len(chunks),
                    "exitCode": decode.exit_code,
                    "stdout": decode.stdout,
                    "stderr": decode.stderr,
                },
            )
        return GuestFileWriteResult(guest_path=guest_path, bytes_written=len(content))

    def upload_text(self, vm: VmRef, guest_path: str, content: str, *, encoding: str = "utf-8") -> GuestFileWriteResult:
        return self.upload_bytes(vm, guest_path, content.encode(encoding))

    def download_text(self, vm: VmRef, guest_path: str) -> GuestFileReadResult:
        if not guest_path.strip():
            raise OslabError("Guest path must not be empty")
        try:
            raw = self.client.guest_file_read(vm.vm_id, guest_path)
        except ProviderError as exc:
            return self._download_text_via_powershell(vm, guest_path, cause=exc)
        content = _file_content_to_text(raw.get("content"))
        truncated = bool(raw.get("truncated"))
        if truncated:
            raise ProviderError(
                f"QEMU Guest Agent file-read result was truncated for VM {vm.vm_id}",
                details={"failureClass": "guest_file_read_truncated", "vmId": vm.vm_id, "guestPath": guest_path},
            )
        return GuestFileReadResult(guest_path=guest_path, content=content, truncated=truncated, raw=raw)

    def _download_text_via_powershell(self, vm: VmRef, guest_path: str, *, cause: ProviderError) -> GuestFileReadResult:
        command = [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            (
                "$ErrorActionPreference = 'Stop'; "
                f"$path = {_ps_single_quote(guest_path)}; "
                "if (-not (Test-Path -LiteralPath $path)) { throw \"Guest file does not exist: $path\" }; "
                "[System.Convert]::ToBase64String([System.IO.File]::ReadAllBytes($path))"
            ),
        ]
        result = self.execute(vm, command, timeout_seconds=60, poll_interval_seconds=1.0)
        if not result.passed:
            raise ProviderError(
                "QEMU Guest Agent file-read failed and PowerShell fallback failed",
                details={
                    "guestPath": guest_path,
                    "fileReadCause": cause.details,
                    "exitCode": result.exit_code,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                },
            ) from cause
        try:
            raw_bytes = base64.b64decode(result.stdout.strip())
        except ValueError as exc:
            raise ProviderError(
                "PowerShell file-read fallback returned invalid base64",
                details={"guestPath": guest_path, "stdout": result.stdout},
            ) from exc
        return GuestFileReadResult(
            guest_path=guest_path,
            content=raw_bytes.decode("utf-8-sig", errors="replace"),
            raw={"fallback": "powershell-base64", "fileReadCause": cause.details},
        )


def _coerce_pid(value: Any) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    raise ProviderError("Proxmox guest exec pid must be an integer", details={"pid": value})


def _result_from_status(command: tuple[str, ...], status: dict[str, Any]) -> GuestCommandResult:
    exit_code = status.get("exitcode")
    return GuestCommandResult(
        command=command,
        exited=True,
        exit_code=exit_code if isinstance(exit_code, int) else None,
        stdout=_output_to_text(status.get("out-data")),
        stderr=_output_to_text(status.get("err-data")),
        raw=status,
    )


def _output_to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return _decode_bytes_best_effort(value)
    return _repair_mojibake_text(str(value))


def _file_content_to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        text = _decode_bytes_best_effort(value)
    else:
        text = str(value)
    text = _repair_mojibake_text(text)
    return text.removeprefix("\ufeff").removeprefix(_MOJIBAKE_UTF8_BOM)


def _decode_bytes_best_effort(value: bytes) -> str:
    candidates: list[str] = []
    for encoding in ("utf-8-sig", "cp949", "euc-kr"):
        try:
            candidates.append(value.decode(encoding))
        except UnicodeError:
            continue
    if not candidates:
        candidates.append(value.decode("utf-8", errors="replace"))
    best = max(candidates, key=_text_quality_score)
    return _repair_mojibake_text(best)


def _repair_mojibake_text(text: str) -> str:
    """Repair common Windows QGA mojibake in stdout/stderr/file-read text."""

    if not text or not _looks_like_mojibake(text):
        return text
    original_score = _text_quality_score(text)
    if _has_utf8_mojibake_markers(text):
        repaired = _decode_latin1_text_as(text, "utf-8")
        if repaired is not None and _text_quality_score(repaired) > original_score:
            return repaired
    if _has_cp949_mojibake_markers(text):
        for encoding in ("cp949", "euc-kr"):
            repaired = _decode_latin1_text_as(text, encoding)
            if repaired is not None and _text_quality_score(repaired) > original_score:
                return repaired
    return text


def _decode_latin1_text_as(text: str, encoding: str) -> str | None:
    try:
        return text.encode("latin-1").decode(encoding)
    except UnicodeError:
        return None


def _looks_like_mojibake(text: str) -> bool:
    if any("\u0080" <= char <= "\u009f" for char in text):
        return True
    return _has_utf8_mojibake_markers(text) or _has_cp949_mojibake_markers(text)


def _has_utf8_mojibake_markers(text: str) -> bool:
    if any("\u0080" <= char <= "\u009f" for char in text):
        return True
    return any(marker in text for marker in _UTF8_MOJIBAKE_MARKERS)


def _has_cp949_mojibake_markers(text: str) -> bool:
    return any(marker in text for marker in _CP949_MOJIBAKE_MARKERS)


def _text_quality_score(text: str) -> int:
    hangul = sum(1 for char in text if "\uac00" <= char <= "\ud7a3")
    c1_controls = sum(1 for char in text if "\u0080" <= char <= "\u009f")
    replacement = text.count("\ufffd")
    mojibake_markers = sum(text.count(marker) for marker in _ALL_MOJIBAKE_MARKERS)
    return (hangul * 10) - (c1_controls * 4) - (replacement * 8) - (mojibake_markers * 2)


def _safe_chunk_name(value: str) -> str:
    return "".join(char if char.isalnum() or char in "._-" else "_" for char in value)


def _decode_chunks_command(parts_dir: str, guest_path: str) -> str:
    return (
        "$ErrorActionPreference = 'Stop'; "
        f"$partsDir = {_ps_single_quote(parts_dir)}; "
        f"$target = {_ps_single_quote(guest_path)}; "
        "$builder = [System.Text.StringBuilder]::new(); "
        "Get-ChildItem -LiteralPath $partsDir -Filter '*.b64' | "
        "Sort-Object Name | "
        "ForEach-Object { [void]$builder.Append([System.IO.File]::ReadAllText($_.FullName, [System.Text.Encoding]::ASCII)) }; "
        "[System.IO.File]::WriteAllBytes($target, [System.Convert]::FromBase64String($builder.ToString())); "
        "Remove-Item -LiteralPath $partsDir -Recurse -Force"
    )


def _ps_single_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"
