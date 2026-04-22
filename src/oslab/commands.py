"""Command template rendering."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping

from oslab.errors import ScenarioValidationError

TOKEN_PATTERN = re.compile(r"\{([A-Za-z][A-Za-z0-9_]*)\}")


@dataclass(frozen=True)
class CommandSpec:
    """A shell command after template rendering."""

    shell: str
    template: str
    rendered: str
    redacted: str | None = None

    @property
    def safe_rendered(self) -> str:
        return self.redacted or self.rendered


def render_command_template(
    command: Mapping[str, object],
    tokens: Mapping[str, str],
    *,
    secret_tokens: Mapping[str, str] | None = None,
) -> CommandSpec:
    """Render a scenario command template with explicit tokens.

    Unknown tokens fail fast. This keeps scenario mistakes from turning into
    remote shell surprises once guest execution is implemented.
    """

    shell = command.get("shell")
    template = command.get("template")
    if not isinstance(shell, str) or not shell.strip():
        raise ScenarioValidationError("Command requires non-empty `shell`")
    if not isinstance(template, str) or not template.strip():
        raise ScenarioValidationError("Command requires non-empty `template`")

    secrets = dict(secret_tokens or {})
    overlap = sorted(set(tokens).intersection(secrets))
    if overlap:
        raise ScenarioValidationError(f"Command token cannot be both public and secret: `{overlap[0]}`")

    def replace(match: re.Match[str]) -> str:
        token_name = match.group(1)
        if token_name in tokens:
            return tokens[token_name]
        if token_name in secrets:
            return secrets[token_name]
        raise ScenarioValidationError(f"Unknown command template token `{token_name}`")

    def replace_redacted(match: re.Match[str]) -> str:
        token_name = match.group(1)
        if token_name in tokens:
            return tokens[token_name]
        if token_name in secrets:
            return "<redacted>"
        if token_name not in tokens:
            raise ScenarioValidationError(f"Unknown command template token `{token_name}`")
        return tokens[token_name]

    rendered = TOKEN_PATTERN.sub(replace, template)
    redacted = TOKEN_PATTERN.sub(replace_redacted, template) if secrets else None
    return CommandSpec(shell=shell, template=template, rendered=rendered, redacted=redacted)
