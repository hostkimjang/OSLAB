"""Provider contracts for VM lifecycle operations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class TemplateRef:
    """Reference to a VM template."""

    vm_id: int | None = None
    name: str | None = None


@dataclass(frozen=True)
class VmSpec:
    """Requested clone shape."""

    vm_id: int
    name: str
    full_clone: bool = False


@dataclass(frozen=True)
class VmRef:
    """Reference to a managed VM."""

    vm_id: int
    name: str | None = None
    node: str | None = None


@dataclass(frozen=True)
class VmStatus:
    """Provider-neutral VM status."""

    vm_id: int
    status: str
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GuestInfo:
    """Provider-neutral guest info snapshot."""

    vm_id: int
    raw: dict[str, Any] = field(default_factory=dict)


class Provider(Protocol):
    """Provider lifecycle interface."""

    def create_clone(self, template: TemplateRef, vm_spec: VmSpec) -> VmRef: ...

    def start_vm(self, vm: VmRef) -> None: ...

    def stop_vm(self, vm: VmRef) -> None: ...

    def destroy_vm(self, vm: VmRef) -> None: ...

    def get_vm_status(self, vm: VmRef) -> VmStatus: ...

    def get_guest_info(self, vm: VmRef) -> GuestInfo: ...

