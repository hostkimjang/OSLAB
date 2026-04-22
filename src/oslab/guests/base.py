"""Guest command channel contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, Sequence

from oslab.providers.base import VmRef


@dataclass(frozen=True)
class GuestCommandResult:
    """Provider-neutral result for a command executed inside a guest OS."""

    command: tuple[str, ...]
    exited: bool
    exit_code: int | None
    stdout: str = ""
    stderr: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.exited and self.exit_code == 0


@dataclass(frozen=True)
class GuestFileWriteResult:
    """Result for writing a file into a guest OS."""

    guest_path: str
    bytes_written: int
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GuestFileReadResult:
    """Result for reading a text file from a guest OS."""

    guest_path: str
    content: str
    truncated: bool = False
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def bytes_read(self) -> int:
        return len(self.content.encode("utf-8"))


class GuestChannel(Protocol):
    """Protocol for command-capable guest channels."""

    def probe(self, vm: VmRef) -> bool: ...

    def execute(
        self,
        vm: VmRef,
        command: Sequence[str],
        *,
        timeout_seconds: int = 60,
        poll_interval_seconds: float = 1.0,
    ) -> GuestCommandResult: ...

    def upload_bytes(self, vm: VmRef, guest_path: str, content: bytes) -> GuestFileWriteResult: ...

    def download_text(self, vm: VmRef, guest_path: str) -> GuestFileReadResult: ...
