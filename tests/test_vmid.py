from pathlib import Path

import pytest

from oslab.errors import ProviderError
from oslab.providers.vmid import LocalVmidLock, VmidRange, allocate_vmid, parse_vmid_range, used_vmids_from_resources


def test_allocate_vmid_skips_used_and_reserved() -> None:
    vm_id = allocate_vmid(VmidRange(9100, 9103), used_vmids={9100}, reserved_vmids={9101})

    assert vm_id == 9102


def test_allocate_vmid_fails_when_range_is_full() -> None:
    with pytest.raises(ProviderError, match="No available VMID"):
        allocate_vmid(VmidRange(9100, 9101), used_vmids={9100, 9101})


def test_used_vmids_from_resources_accepts_int_and_digit_string() -> None:
    resources = [{"vmid": 9000}, {"vmid": "9100"}, {"vmid": "not-a-number"}, {"name": "missing"}]

    assert used_vmids_from_resources(resources) == {9000, 9100}


def test_parse_vmid_range() -> None:
    assert parse_vmid_range({"start": 9100, "end": 9199}) == VmidRange(9100, 9199)


def test_local_vmid_lock_reserves_and_releases(tmp_path: Path) -> None:
    lock = LocalVmidLock(tmp_path / "locks")

    first = lock.reserve(VmidRange(9100, 9101), used_vmids=set())
    second = lock.reserve(VmidRange(9100, 9101), used_vmids=set())

    assert first.vm_id == 9100
    assert second.vm_id == 9101
    assert first.lock_path.exists()
    assert second.lock_path.exists()

    first.release()
    second.release()

    assert not first.lock_path.exists()
    assert not second.lock_path.exists()

