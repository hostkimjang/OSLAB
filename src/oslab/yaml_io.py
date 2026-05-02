"""YAML loading helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from oslab.errors import ConfigError, ScenarioValidationError, SuiteValidationError


def load_yaml_mapping(path: Path, *, kind: str) -> dict[str, Any]:
    """Load a YAML file and require the top-level value to be a mapping."""

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        error_type = _error_type_for_kind(kind)
        raise error_type(f"Cannot read {kind} file: {path}", details={"error": str(exc)}) from exc

    try:
        loaded = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        error_type = _error_type_for_kind(kind)
        raise error_type(f"Invalid YAML in {kind} file: {path}", details={"error": str(exc)}) from exc

    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        error_type = _error_type_for_kind(kind)
        raise error_type(f"{kind.capitalize()} file must contain a YAML mapping at the top level: {path}")
    return loaded


def _error_type_for_kind(kind: str):
    if kind == "scenario":
        return ScenarioValidationError
    if kind == "suite":
        return SuiteValidationError
    return ConfigError
