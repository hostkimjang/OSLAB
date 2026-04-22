"""Guest channel selection logic."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Protocol

from oslab.errors import OslabError, ScenarioValidationError

WINDOWS_AUTO_ORDER = ["qemuAgent", "winrm"]
LINUX_AUTO_ORDER = ["ssh", "qemuAgent"]
SUPPORTED_CHANNELS = {"qemuAgent", "winrm", "ssh"}


class ChannelProbe(Protocol):
    def probe(self, channel: str) -> bool:
        """Return true when a channel is available."""


@dataclass(frozen=True)
class StaticProbe:
    """Probe implementation useful for tests and dry-run planning."""

    available_channels: frozenset[str]

    def probe(self, channel: str) -> bool:
        return channel in self.available_channels


def default_order_for_os(os_family: str) -> list[str]:
    if os_family == "windows":
        return list(WINDOWS_AUTO_ORDER)
    if os_family == "linux":
        return list(LINUX_AUTO_ORDER)
    raise ScenarioValidationError(f"Unsupported os family for guest channel selection: {os_family}")


def select_guest_channel(
    *,
    os_family: str,
    mode: str,
    probe: ChannelProbe,
    windows_order: Iterable[str] | None = None,
    linux_order: Iterable[str] | None = None,
) -> str:
    """Select the first available guest channel for a scenario."""

    if mode != "auto":
        _ensure_supported(mode)
        if probe.probe(mode):
            return mode
        raise OslabError(
            f"Requested guest channel is not available: {mode}",
            details={"failureClass": "guest_channel_failure", "mode": mode},
        )

    order = list(windows_order or WINDOWS_AUTO_ORDER) if os_family == "windows" else list(linux_order or LINUX_AUTO_ORDER)
    if os_family not in {"windows", "linux"}:
        raise ScenarioValidationError(f"Unsupported os family for guest channel selection: {os_family}")

    for channel in order:
        _ensure_supported(channel)
        if probe.probe(channel):
            return channel

    raise OslabError(
        "No guest channel is available",
        details={"failureClass": "guest_channel_failure", "osFamily": os_family, "attempted": order},
    )


def _ensure_supported(channel: str) -> None:
    if channel not in SUPPORTED_CHANNELS:
        raise ScenarioValidationError(f"Unsupported guest channel `{channel}`")

