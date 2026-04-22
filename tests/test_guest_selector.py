import pytest

from oslab.errors import OslabError
from oslab.guests.selector import StaticProbe, default_order_for_os, select_guest_channel


def test_windows_auto_prefers_qemu_agent() -> None:
    channel = select_guest_channel(
        os_family="windows",
        mode="auto",
        probe=StaticProbe(frozenset({"qemuAgent", "winrm"})),
    )

    assert channel == "qemuAgent"


def test_windows_auto_falls_back_to_winrm() -> None:
    channel = select_guest_channel(
        os_family="windows",
        mode="auto",
        probe=StaticProbe(frozenset({"winrm"})),
    )

    assert channel == "winrm"


def test_linux_auto_prefers_ssh() -> None:
    assert default_order_for_os("linux") == ["ssh", "qemuAgent"]
    channel = select_guest_channel(
        os_family="linux",
        mode="auto",
        probe=StaticProbe(frozenset({"ssh", "qemuAgent"})),
    )

    assert channel == "ssh"


def test_explicit_channel_must_be_available() -> None:
    with pytest.raises(OslabError, match="Requested guest channel is not available"):
        select_guest_channel(
            os_family="windows",
            mode="winrm",
            probe=StaticProbe(frozenset({"qemuAgent"})),
        )

