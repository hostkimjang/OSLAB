"""VMID allocation helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from oslab.errors import ProviderError


@dataclass(frozen=True)
class VmidRange:
    start: int
    end: int

    def __post_init__(self) -> None:
        if self.start > self.end:
            raise ProviderError("VMID range start must be <= end")

    def values(self) -> range:
        return range(self.start, self.end + 1)


@dataclass(frozen=True)
class VmidReservation:
    vm_id: int
    lock_path: Path

    def release(self) -> None:
        try:
            self.lock_path.unlink(missing_ok=True)
        except OSError as exc:
            raise ProviderError(f"Cannot release VMID reservation: {self.lock_path}", details={"error": str(exc)}) from exc


def parse_vmid_range(raw: dict[str, object]) -> VmidRange:
    start = raw.get("start")
    end = raw.get("end")
    if not isinstance(start, int) or not isinstance(end, int):
        raise ProviderError("VMID range requires integer `start` and `end`")
    return VmidRange(start=start, end=end)


def used_vmids_from_resources(resources: Iterable[dict[str, object]]) -> set[int]:
    used: set[int] = set()
    for resource in resources:
        vmid = resource.get("vmid")
        if isinstance(vmid, int):
            used.add(vmid)
        elif isinstance(vmid, str) and vmid.isdigit():
            used.add(int(vmid))
    return used


def allocate_vmid(vmid_range: VmidRange, *, used_vmids: Iterable[int], reserved_vmids: Iterable[int] = ()) -> int:
    unavailable = set(used_vmids) | set(reserved_vmids)
    for vm_id in vmid_range.values():
        if vm_id not in unavailable:
            return vm_id
    raise ProviderError(
        "No available VMID in configured range",
        details={"start": vmid_range.start, "end": vmid_range.end, "used": sorted(unavailable)},
    )


class LocalVmidLock:
    """Atomic lock-file based VMID reservation for local runs."""

    def __init__(self, lock_dir: Path) -> None:
        self.lock_dir = lock_dir

    def reserve(self, vmid_range: VmidRange, *, used_vmids: Iterable[int]) -> VmidReservation:
        self.lock_dir.mkdir(parents=True, exist_ok=True)
        used = set(used_vmids)
        for vm_id in vmid_range.values():
            if vm_id in used:
                continue
            lock_path = self.lock_dir / f"vmid-{vm_id}.lock"
            try:
                fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                continue
            except OSError as exc:
                raise ProviderError(f"Cannot create VMID lock: {lock_path}", details={"error": str(exc)}) from exc

            with os.fdopen(fd, "w", encoding="utf-8") as lock_file:
                lock_file.write(str(vm_id))
            return VmidReservation(vm_id=vm_id, lock_path=lock_path)

        raise ProviderError(
            "No available VMID lock in configured range",
            details={"start": vmid_range.start, "end": vmid_range.end, "used": sorted(used)},
        )

