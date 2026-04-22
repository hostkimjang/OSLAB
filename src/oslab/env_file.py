"""Local env-file loading for ignored lab secrets."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from oslab.errors import ConfigError


@dataclass(frozen=True)
class EnvFileResult:
    path: Path
    loaded: list[str]
    skipped_existing: list[str]


def load_env_file(path: Path, *, override: bool = False) -> EnvFileResult:
    """Load KEY=VALUE lines into the process environment.

    The parser is intentionally small: comments and blank lines are ignored,
    optional single/double quotes are removed, and values are never returned.
    """

    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError as exc:
        raise ConfigError(f"Cannot read env file: {path}", details={"error": str(exc)}) from exc

    loaded: list[str] = []
    skipped_existing: list[str] = []
    for line_number, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ConfigError(
                f"Invalid env file line {line_number}: expected KEY=VALUE",
                details={
                    "path": str(path),
                    "expectedExample": "OSLAB_PROXMOX_TOKEN_ID=root@pam!oslab",
                    "secretExample": "OSLAB_PROXMOX_TOKEN_SECRET=<token-secret>",
                    "note": "Do not paste dashboard text blocks or raw passwords into this file.",
                },
            )
        key, value = line.split("=", 1)
        key = key.strip()
        value = _strip_optional_quotes(value.strip())
        if not key:
            raise ConfigError(
                f"Invalid env file line {line_number}: empty key",
                details={"path": str(path), "expectedExample": "OSLAB_PROXMOX_TOKEN_ID=root@pam!oslab"},
            )
        if key in os.environ and not override:
            skipped_existing.append(key)
            continue
        os.environ[key] = value
        loaded.append(key)
    return EnvFileResult(path=path, loaded=loaded, skipped_existing=skipped_existing)


def _strip_optional_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value
