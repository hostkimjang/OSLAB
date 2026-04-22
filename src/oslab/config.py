"""Local config loading and resolution."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from oslab.errors import ConfigError
from oslab.yaml_io import load_yaml_mapping


@dataclass(frozen=True)
class OslabConfig:
    """Resolved oslab configuration."""

    path: Path | None
    raw: dict[str, Any]

    @property
    def output_root(self) -> Path:
        run_defaults = self.raw.get("runDefaults") or {}
        return Path(run_defaults.get("outputRoot") or "runs")

    @property
    def timeout_minutes(self) -> int:
        run_defaults = self.raw.get("runDefaults") or {}
        value = run_defaults.get("timeoutMinutes", 45)
        if not isinstance(value, int) or value <= 0:
            raise ConfigError("`runDefaults.timeoutMinutes` must be a positive integer")
        return value

    @property
    def keep_vm_on_failure(self) -> bool:
        run_defaults = self.raw.get("runDefaults") or {}
        value = run_defaults.get("keepVmOnFailure", False)
        if not isinstance(value, bool):
            raise ConfigError("`runDefaults.keepVmOnFailure` must be a boolean")
        return value

    def resolve_env_reference(self, env_name: str) -> str:
        value = os.environ.get(env_name)
        if value is None:
            raise ConfigError(f"Required environment variable is not set: {env_name}")
        return value


def load_config(path: Path | None) -> OslabConfig:
    if path is None:
        return OslabConfig(path=None, raw={})
    raw = load_yaml_mapping(path, kind="config")
    return OslabConfig(path=path, raw=raw)

