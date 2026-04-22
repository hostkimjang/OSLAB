"""Small console diagnostics helpers.

The CLI output should be readable during lab setup, but it must never leak
secrets. Keep this module dependency-free so early bootstrap stays boring.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from typing import TextIO


def redact_value(value: str, *, keep_start: int = 8, keep_end: int = 4) -> str:
    """Return a stable redacted representation of a non-secret identifier."""

    if not value:
        return "<empty>"
    if len(value) <= keep_start + keep_end:
        return "<redacted>"
    return f"{value[:keep_start]}...{value[-keep_end:]}"


def format_detail_value(value: object) -> str:
    """Format structured detail values without ASCII-escaping Unicode text."""

    if isinstance(value, dict | list):
        return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str)
    return str(value)


@dataclass
class Console:
    """Simple structured console printer."""

    stream: TextIO | None = None

    @property
    def output(self) -> TextIO:
        return self.stream or sys.stdout

    def section(self, title: str) -> None:
        print(f"\n== {title} ==", file=self.output)

    def step(self, title: str) -> None:
        print(f"[..] {title}", file=self.output)

    def ok(self, title: str) -> None:
        print(f"[OK] {title}", file=self.output)

    def warn(self, title: str) -> None:
        print(f"[WARN] {title}", file=self.output)

    def fail(self, title: str) -> None:
        print(f"[FAIL] {title}", file=self.output)

    def detail(self, key: str, value: object) -> None:
        formatted = format_detail_value(value)
        lines = formatted.splitlines()
        if not lines:
            print(f"     {key}: ", file=self.output)
            return
        print(f"     {key}: {lines[0]}", file=self.output)
        for line in lines[1:]:
            print(f"     {line}", file=self.output)
