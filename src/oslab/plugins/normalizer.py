"""Generic product output normalization.

Core code knows how to load plugins and validate the canonical shape. Product
specific parsing lives outside `src/oslab`, under repo-level `plugins/<name>`.
"""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any, Mapping

from oslab.errors import PluginError

CANONICAL_INVENTORY_ADAPTER = "canonical.inventory"
CANONICAL_COMMAND_ADAPTER = "canonical.command"


@dataclass(frozen=True)
class NormalizationResult:
    """Result of plugin normalization."""

    adapter: str
    canonical: dict[str, Any]
    plugin_name: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def normalize_output(
    adapter: str | None,
    raw_output: Mapping[str, Any] | list[Any],
    *,
    context: Mapping[str, Any] | None = None,
    plugin_root: Path | None = None,
) -> NormalizationResult:
    """Normalize raw product output through a scenario adapter."""

    resolved_adapter = (adapter or CANONICAL_INVENTORY_ADAPTER).strip()
    if resolved_adapter == CANONICAL_INVENTORY_ADAPTER:
        return NormalizationResult(
            adapter=resolved_adapter,
            canonical=_ensure_inventory(raw_output),
            plugin_name=None,
            metadata={"mode": "passthrough"},
        )
    if resolved_adapter == CANONICAL_COMMAND_ADAPTER:
        return NormalizationResult(
            adapter=resolved_adapter,
            canonical=_ensure_command_result(raw_output),
            plugin_name=None,
            metadata={"mode": "passthrough"},
        )

    plugin_name, _, kind = resolved_adapter.partition(".")
    if not plugin_name or not kind:
        raise PluginError(
            "Invalid output adapter",
            details={"adapter": resolved_adapter, "expected": "<plugin>.<kind>"},
        )
    if kind != "inventory":
        raise PluginError(
            "Unsupported output adapter kind",
            details={"adapter": resolved_adapter, "kind": kind, "supported": ["inventory"]},
        )

    module = _load_python_plugin(plugin_name, plugin_root=plugin_root)
    normalize = getattr(module, "normalize_output", None)
    if not callable(normalize):
        raise PluginError(
            "Plugin does not expose normalize_output(context, raw_output)",
            details={"adapter": resolved_adapter, "pluginName": plugin_name},
        )

    try:
        canonical = normalize(dict(context or {}), raw_output)
    except PluginError:
        raise
    except Exception as exc:
        raise PluginError(
            "Plugin normalization failed",
            details={"adapter": resolved_adapter, "pluginName": plugin_name, "error": str(exc)},
        ) from exc

    metadata_func = getattr(module, "plugin_metadata", None)
    metadata = metadata_func() if callable(metadata_func) else {}
    return NormalizationResult(
        adapter=resolved_adapter,
        canonical=_ensure_inventory(canonical),
        plugin_name=plugin_name,
        metadata=metadata if isinstance(metadata, dict) else {},
    )


def _load_python_plugin(plugin_name: str, *, plugin_root: Path | None = None) -> ModuleType:
    root = plugin_root or Path.cwd() / "plugins"
    plugin_path = root / plugin_name / "plugin.py"
    if not plugin_path.exists():
        raise PluginError(
            "Plugin was not found",
            details={"pluginName": plugin_name, "pluginPath": str(plugin_path)},
        )

    module_name = f"oslab_external_plugin_{plugin_name}"
    spec = importlib.util.spec_from_file_location(module_name, plugin_path)
    if spec is None or spec.loader is None:
        raise PluginError(
            "Plugin could not be loaded",
            details={"pluginName": plugin_name, "pluginPath": str(plugin_path)},
        )
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        raise PluginError(
            "Plugin import failed",
            details={"pluginName": plugin_name, "pluginPath": str(plugin_path), "error": str(exc)},
        ) from exc
    return module


def _ensure_inventory(payload: Mapping[str, Any] | list[Any]) -> dict[str, Any]:
    if isinstance(payload, list):
        records = payload
        base: dict[str, Any] = {}
    elif isinstance(payload, Mapping):
        base = dict(payload)
        records = base.get("records", [])
    else:
        raise PluginError("Canonical inventory output must be a mapping or list")

    if not isinstance(records, list):
        raise PluginError("Canonical inventory output requires a list `records` field")

    normalized_records = [dict(record) for record in records if isinstance(record, Mapping)]
    return {
        "schemaVersion": int(base.get("schemaVersion") or 1),
        "kind": str(base.get("kind") or "inventory"),
        "records": normalized_records,
    }


def _ensure_command_result(payload: Mapping[str, Any] | list[Any]) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise PluginError("Canonical command output must be a JSON object")

    exit_code = payload.get("exitCode")
    metadata = payload.get("metadata")
    return {
        "schemaVersion": int(payload.get("schemaVersion") or 1),
        "kind": str(payload.get("kind") or "commandResult"),
        "command": str(payload.get("command") or ""),
        "exitCode": exit_code if isinstance(exit_code, int) else None,
        "stdout": str(payload.get("stdout") or ""),
        "stderr": str(payload.get("stderr") or ""),
        "metadata": dict(metadata) if isinstance(metadata, Mapping) else {},
    }
