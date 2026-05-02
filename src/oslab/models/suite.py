"""Suite model and validation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from oslab.errors import SuiteValidationError
from oslab.yaml_io import load_yaml_mapping

SUPPORTED_SUITE_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class SuiteEntry:
    """One scenario entry in a suite YAML document."""

    id: str
    scenario: Path
    allow_failure: bool = False
    enabled: bool = True
    tier: str | None = None


@dataclass(frozen=True)
class Suite:
    """A validated suite YAML document."""

    path: Path
    raw: dict[str, Any]
    entries: list[SuiteEntry]

    @property
    def schema_version(self) -> int:
        return int(self.raw["schemaVersion"])

    @property
    def suite_id(self) -> str:
        return str(self.raw["id"])

    @property
    def name(self) -> str:
        return str(self.raw.get("name") or self.suite_id)


def load_suite(path: Path) -> Suite:
    """Load and validate a suite from disk."""

    raw = load_yaml_mapping(path, kind="suite")
    entries = validate_suite_mapping(raw, path=path)
    return Suite(path=path, raw=raw, entries=entries)


def validate_suite_mapping(raw: dict[str, Any], *, path: Path | None = None) -> list[SuiteEntry]:
    """Validate the MVP suite contract."""

    where = f" in {path}" if path else ""
    for field in ("schemaVersion", "id", "runs"):
        if field not in raw:
            raise SuiteValidationError(f"Missing required suite field `{field}`{where}")

    if raw["schemaVersion"] != SUPPORTED_SUITE_SCHEMA_VERSION:
        raise SuiteValidationError(
            f"Unsupported suite schemaVersion `{raw['schemaVersion']}`{where}; expected {SUPPORTED_SUITE_SCHEMA_VERSION}"
        )
    suite_id = raw.get("id")
    if not isinstance(suite_id, str) or not suite_id.strip():
        raise SuiteValidationError(f"`id` must be a non-empty string{where}")

    runs = raw.get("runs")
    if not isinstance(runs, list) or not runs:
        raise SuiteValidationError(f"`runs` must contain at least one entry{where}")

    entries: list[SuiteEntry] = []
    seen_ids: set[str] = set()
    for index, entry in enumerate(runs):
        if not isinstance(entry, dict):
            raise SuiteValidationError(f"`runs[{index}]` must be a mapping{where}")
        entry_id = entry.get("id")
        if not isinstance(entry_id, str) or not entry_id.strip():
            raise SuiteValidationError(f"`runs[{index}].id` must be a non-empty string{where}")
        if entry_id in seen_ids:
            raise SuiteValidationError(f"Duplicate suite run id `{entry_id}`{where}")
        seen_ids.add(entry_id)
        scenario = entry.get("scenario")
        if not isinstance(scenario, str) or not scenario.strip():
            raise SuiteValidationError(f"`runs[{index}].scenario` must be a non-empty string{where}")
        allow_failure = entry.get("allowFailure", False)
        if not isinstance(allow_failure, bool):
            raise SuiteValidationError(f"`runs[{index}].allowFailure` must be a boolean{where}")
        enabled = entry.get("enabled", True)
        if not isinstance(enabled, bool):
            raise SuiteValidationError(f"`runs[{index}].enabled` must be a boolean{where}")
        tier = entry.get("tier")
        if tier is not None and (not isinstance(tier, str) or not tier.strip()):
            raise SuiteValidationError(f"`runs[{index}].tier` must be a non-empty string when set{where}")
        entries.append(
            SuiteEntry(
                id=entry_id,
                scenario=Path(scenario),
                allow_failure=allow_failure,
                enabled=enabled,
                tier=tier if isinstance(tier, str) else None,
            )
        )
    return entries
