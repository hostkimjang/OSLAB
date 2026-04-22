"""Scenario model and validation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from oslab.errors import ScenarioValidationError
from oslab.yaml_io import load_yaml_mapping

ALLOWED_OS_FAMILIES = {"windows", "linux"}
ALLOWED_GUEST_MODES = {"auto", "qemuAgent", "winrm", "ssh"}
ALLOWED_GUEST_CHANNELS = {"qemuAgent", "winrm", "ssh"}
ALLOWED_ARTIFACT_TYPES = {"folder", "installer"}
ALLOWED_ARTIFACT_TRANSFERS = {"files", "archive"}
ALLOWED_FIXTURE_TYPES = {"powershell", "shell"}
ALLOWED_REPORT_FORMATS = {"junit", "json", "html"}
ALLOWED_SHELLS = {"powershell", "cmd", "sh", "bash"}
SUPPORTED_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class Scenario:
    """A validated scenario YAML document."""

    path: Path
    raw: dict[str, Any]

    @property
    def schema_version(self) -> int:
        return int(self.raw["schemaVersion"])

    @property
    def scenario_id(self) -> str:
        return str(self.raw["id"])

    @property
    def name(self) -> str:
        return str(self.raw.get("name") or self.scenario_id)

    @property
    def os_family(self) -> str:
        return str(self.raw["os"]["family"])

    @property
    def provider_type(self) -> str:
        return str(self.raw["provider"]["type"])

    @property
    def provider(self) -> dict[str, Any]:
        return dict(self.raw["provider"])

    @property
    def template_vm_id(self) -> int | None:
        value = self.raw["provider"].get("templateVmId")
        return value if isinstance(value, int) else None

    @property
    def template_name(self) -> str | None:
        value = self.raw["provider"].get("template")
        return value if isinstance(value, str) and value.strip() else None

    @property
    def vmid_range(self) -> dict[str, int] | None:
        value = self.raw["provider"].get("vmIdRange")
        if not isinstance(value, dict):
            return None
        start = value.get("start")
        end = value.get("end")
        if isinstance(start, int) and isinstance(end, int):
            return {"start": start, "end": end}
        return None

    @property
    def guest_mode(self) -> str:
        return str(self.raw["guest"]["mode"])

    @property
    def report_formats(self) -> list[str]:
        reports = self.raw.get("reports") or {}
        formats = reports.get("formats") or ["json"]
        return [str(item) for item in formats]

    @property
    def assertions(self) -> list[dict[str, Any]]:
        return [dict(assertion) for assertion in self.raw["assertions"] if isinstance(assertion, dict)]

    @property
    def output_adapter(self) -> str:
        outputs = self.raw.get("outputs")
        if isinstance(outputs, dict):
            actual = outputs.get("actual")
            if isinstance(actual, dict):
                adapter = actual.get("adapter")
                if isinstance(adapter, str) and adapter.strip():
                    return adapter
        return "canonical.inventory"


def load_scenario(path: Path) -> Scenario:
    """Load and validate a scenario from disk."""

    raw = load_yaml_mapping(path, kind="scenario")
    validate_scenario_mapping(raw, path=path)
    return Scenario(path=path, raw=raw)


def validate_scenario_mapping(raw: dict[str, Any], *, path: Path | None = None) -> None:
    """Validate the MVP scenario contract."""

    where = f" in {path}" if path else ""
    required = ["schemaVersion", "id", "os", "provider", "guest", "assertions"]
    for field in required:
        if field not in raw:
            raise ScenarioValidationError(f"Missing required scenario field `{field}`{where}")

    schema_version = raw["schemaVersion"]
    if schema_version != SUPPORTED_SCHEMA_VERSION:
        raise ScenarioValidationError(
            f"Unsupported scenario schemaVersion `{schema_version}`{where}; expected {SUPPORTED_SCHEMA_VERSION}"
        )

    _require_non_empty_string(raw, "id", where=where)

    os_config = _require_mapping(raw, "os", where=where)
    os_family = _require_non_empty_string(os_config, "family", where=where)
    if os_family not in ALLOWED_OS_FAMILIES:
        raise ScenarioValidationError(
            f"Unsupported os.family `{os_family}`{where}; expected one of {sorted(ALLOWED_OS_FAMILIES)}"
        )

    provider = _require_mapping(raw, "provider", where=where)
    _require_non_empty_string(provider, "type", where=where)
    _validate_vmid_range(provider, where=where)

    guest = _require_mapping(raw, "guest", where=where)
    guest_mode = _require_non_empty_string(guest, "mode", where=where)
    if guest_mode not in ALLOWED_GUEST_MODES:
        raise ScenarioValidationError(
            f"Unsupported guest.mode `{guest_mode}`{where}; expected one of {sorted(ALLOWED_GUEST_MODES)}"
        )
    _validate_guest_order(guest, "windowsOrder", where=where)
    _validate_guest_order(guest, "linuxOrder", where=where)

    if "isolation" in raw:
        isolation = _require_mapping(raw, "isolation", where=where)
        mode = isolation.get("mode")
        if mode != "ephemeralClone":
            raise ScenarioValidationError(f"Unsupported isolation.mode `{mode}`{where}; expected `ephemeralClone`")

    if "artifact" in raw:
        _validate_artifact(_require_mapping(raw, "artifact", where=where), where=where)

    if "product" in raw:
        _validate_product(_require_mapping(raw, "product", where=where), where=where)

    if "fixtures" in raw:
        fixtures = _require_list(raw, "fixtures", where=where)
        for index, fixture in enumerate(fixtures):
            if not isinstance(fixture, dict):
                raise ScenarioValidationError(f"`fixtures[{index}]` must be a mapping{where}")
            _validate_fixture(fixture, index=index, where=where)

    assertions = _require_list(raw, "assertions", where=where)
    if not assertions:
        raise ScenarioValidationError(f"`assertions` must contain at least one assertion{where}")
    for index, assertion in enumerate(assertions):
        if not isinstance(assertion, dict):
            raise ScenarioValidationError(f"`assertions[{index}]` must be a mapping{where}")
        _require_non_empty_string(assertion, "type", where=where)
        _require_non_empty_string(assertion, "id", where=where)
        if "command" in assertion:
            _validate_command(_require_mapping(assertion, "command", where=where), where=where)

    if "reports" in raw:
        reports = _require_mapping(raw, "reports", where=where)
        formats = _require_list(reports, "formats", where=where)
        for report_format in formats:
            if report_format not in ALLOWED_REPORT_FORMATS:
                raise ScenarioValidationError(
                    f"Unsupported report format `{report_format}`{where}; expected one of {sorted(ALLOWED_REPORT_FORMATS)}"
                )

    if "outputs" in raw:
        _validate_outputs(_require_mapping(raw, "outputs", where=where), where=where)

    if "cleanup" in raw:
        cleanup = _require_mapping(raw, "cleanup", where=where)
        for bool_field in ("destroyVm", "keepVmOnFailure"):
            if bool_field in cleanup and not isinstance(cleanup[bool_field], bool):
                raise ScenarioValidationError(f"`cleanup.{bool_field}` must be a boolean{where}")


def _validate_artifact(artifact: dict[str, Any], *, where: str) -> None:
    artifact_type = _require_non_empty_string(artifact, "type", where=where)
    if artifact_type not in ALLOWED_ARTIFACT_TYPES:
        raise ScenarioValidationError(
            f"Unsupported artifact.type `{artifact_type}`{where}; expected one of {sorted(ALLOWED_ARTIFACT_TYPES)}"
        )
    _require_non_empty_string(artifact, "pathParam", where=where)
    _require_non_empty_string(artifact, "destination", where=where)
    if "exclude" in artifact:
        excludes = _require_list(artifact, "exclude", where=where)
        for index, pattern in enumerate(excludes):
            if not isinstance(pattern, str) or not pattern.strip():
                raise ScenarioValidationError(f"`artifact.exclude[{index}]` must be a non-empty string{where}")
    if "transfer" in artifact:
        transfer = _require_non_empty_string(artifact, "transfer", where=where)
        if transfer not in ALLOWED_ARTIFACT_TRANSFERS:
            raise ScenarioValidationError(
                f"Unsupported artifact.transfer `{transfer}`{where}; expected one of {sorted(ALLOWED_ARTIFACT_TRANSFERS)}"
            )
    if "command" in artifact:
        _validate_command(_require_mapping(artifact, "command", where=where), where=where)
    if artifact_type == "installer":
        if "installCommand" not in artifact:
            raise ScenarioValidationError("Installer artifact requires `installCommand`")
        _validate_command(_require_mapping(artifact, "installCommand", where=where), where=where)


def _validate_product(product: dict[str, Any], *, where: str) -> None:
    if "steps" not in product:
        return
    steps = _require_list(product, "steps", where=where)
    if not steps:
        raise ScenarioValidationError(f"`product.steps` cannot be empty{where}")
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            raise ScenarioValidationError(f"`product.steps[{index}]` must be a mapping{where}")
        _require_non_empty_string(step, "id", where=where)
        _validate_command(_require_mapping(step, "command", where=where), where=where)
        if "captureStdoutJson" in step and not isinstance(step["captureStdoutJson"], bool):
            raise ScenarioValidationError(f"`product.steps[{index}].captureStdoutJson` must be a boolean{where}")
        if "secretTokens" in step:
            secret_tokens = _require_mapping(step, "secretTokens", where=where)
            for token_name, source in secret_tokens.items():
                if not isinstance(token_name, str) or not token_name.strip():
                    raise ScenarioValidationError(f"`product.steps[{index}].secretTokens` keys must be non-empty strings{where}")
                if not isinstance(source, dict):
                    raise ScenarioValidationError(
                        f"`product.steps[{index}].secretTokens.{token_name}` must be a mapping{where}"
                    )
                _require_non_empty_string(source, "env", where=where)


def _validate_fixture(fixture: dict[str, Any], *, index: int, where: str) -> None:
    _require_non_empty_string(fixture, "id", where=where)
    fixture_type = _require_non_empty_string(fixture, "type", where=where)
    if fixture_type not in ALLOWED_FIXTURE_TYPES:
        raise ScenarioValidationError(
            f"Unsupported fixtures[{index}].type `{fixture_type}`{where}; expected one of {sorted(ALLOWED_FIXTURE_TYPES)}"
        )
    _require_non_empty_string(fixture, "source", where=where)


def _validate_command(command: dict[str, Any], *, where: str) -> None:
    shell = _require_non_empty_string(command, "shell", where=where)
    if shell not in ALLOWED_SHELLS:
        raise ScenarioValidationError(
            f"Unsupported command shell `{shell}`{where}; expected one of {sorted(ALLOWED_SHELLS)}"
        )
    _require_non_empty_string(command, "template", where=where)


def _validate_outputs(outputs: dict[str, Any], *, where: str) -> None:
    if "actual" not in outputs:
        return
    actual = _require_mapping(outputs, "actual", where=where)
    if "path" in actual:
        _require_non_empty_string(actual, "path", where=where)
    if "adapter" in actual:
        adapter = _require_non_empty_string(actual, "adapter", where=where)
        if "." not in adapter:
            raise ScenarioValidationError(f"`outputs.actual.adapter` must use `<plugin>.<kind>` format{where}")


def _validate_guest_order(guest: dict[str, Any], field: str, *, where: str) -> None:
    if field not in guest:
        return
    order = _require_list(guest, field, where=where)
    if not order:
        raise ScenarioValidationError(f"`guest.{field}` cannot be empty{where}")
    for channel in order:
        if channel not in ALLOWED_GUEST_CHANNELS:
            raise ScenarioValidationError(
                f"Unsupported guest channel `{channel}` in guest.{field}{where}; expected one of {sorted(ALLOWED_GUEST_CHANNELS)}"
            )


def _validate_vmid_range(provider: dict[str, Any], *, where: str) -> None:
    if "vmIdRange" not in provider:
        return
    vmid_range = _require_mapping(provider, "vmIdRange", where=where)
    start = vmid_range.get("start")
    end = vmid_range.get("end")
    if not isinstance(start, int) or not isinstance(end, int):
        raise ScenarioValidationError(f"`provider.vmIdRange.start` and `end` must be integers{where}")
    if start > end:
        raise ScenarioValidationError(f"`provider.vmIdRange.start` must be <= `end`{where}")


def _require_mapping(raw: dict[str, Any], field: str, *, where: str) -> dict[str, Any]:
    value = raw.get(field)
    if not isinstance(value, dict):
        raise ScenarioValidationError(f"`{field}` must be a mapping{where}")
    return value


def _require_list(raw: dict[str, Any], field: str, *, where: str) -> list[Any]:
    value = raw.get(field)
    if not isinstance(value, list):
        raise ScenarioValidationError(f"`{field}` must be a list{where}")
    return value


def _require_non_empty_string(raw: dict[str, Any], field: str, *, where: str) -> str:
    value = raw.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ScenarioValidationError(f"`{field}` must be a non-empty string{where}")
    return value
