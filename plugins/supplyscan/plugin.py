"""SupplyScan raw JSON to oslab canonical inventory adapter."""

from __future__ import annotations

import re
from typing import Any, Mapping


def plugin_metadata() -> dict[str, Any]:
    return {
        "name": "supplyscan",
        "adapter": "supplyscan.inventory",
        "schemaVersion": 1,
        "outputKind": "inventory",
    }


def normalize_output(context: dict[str, Any], raw_output: Mapping[str, Any] | list[Any]) -> dict[str, Any]:
    """Normalize flexible SupplyScan output shapes to canonical inventory."""

    if _looks_canonical(raw_output):
        return _canonical_passthrough(raw_output)

    records = []
    for index, item in enumerate(_iter_raw_records(raw_output)):
        record = _normalize_record(item, index=index)
        if record is not None:
            records.append(record)
    return {
        "schemaVersion": 1,
        "kind": "inventory",
        "records": records,
    }


def _looks_canonical(raw_output: Mapping[str, Any] | list[Any]) -> bool:
    return isinstance(raw_output, Mapping) and isinstance(raw_output.get("records"), list)


def _canonical_passthrough(raw_output: Mapping[str, Any] | list[Any]) -> dict[str, Any]:
    assert isinstance(raw_output, Mapping)
    records = raw_output.get("records")
    return {
        "schemaVersion": int(raw_output.get("schemaVersion") or 1),
        "kind": str(raw_output.get("kind") or "inventory"),
        "records": [dict(record) for record in records if isinstance(record, Mapping)],
    }


def _iter_raw_records(raw_output: Mapping[str, Any] | list[Any]) -> list[Mapping[str, Any]]:
    if isinstance(raw_output, list):
        return [item for item in raw_output if isinstance(item, Mapping)]
    if not isinstance(raw_output, Mapping):
        return []

    for key in (
        "software",
        "installedSoftware",
        "installed_software",
        "applications",
        "apps",
        "programs",
        "items",
        "results",
        "inventory",
    ):
        value = raw_output.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, Mapping)]
    return [raw_output]


def _normalize_record(item: Mapping[str, Any], *, index: int) -> dict[str, Any] | None:
    name = _first_string(
        item,
        "name",
        "Name",
        "displayName",
        "DisplayName",
        "display_name",
        "sw_name",
        "softwareName",
        "SoftwareName",
    )
    if not name:
        return None

    version = _first_string(
        item,
        "version",
        "Version",
        "displayVersion",
        "DisplayVersion",
        "display_version",
        "sw_version",
        "softwareVersion",
        "SoftwareVersion",
    )
    publisher = _first_string(item, "publisher", "Publisher", "vendor", "Vendor", "sw_publisher", "manufacturer")
    sources = _normalize_sources(item)
    evidence = _normalize_evidence(item, sources=sources)

    return {
        "name": name,
        "version": version,
        "publisher": publisher,
        "sources": sources,
        "confidence": _first_string(item, "confidence", "Confidence", "confidenceLevel") or "unknown",
        "evidence": evidence,
        "metadata": {
            "adapter": "supplyscan.inventory",
            "rawIndex": index,
            "rawKeys": sorted(str(key) for key in item.keys()),
        },
    }


def _normalize_sources(item: Mapping[str, Any]) -> list[str]:
    raw_sources: list[str] = []
    for key in ("sources", "Sources", "source", "Source", "sw_scan_method", "scanMethod", "scan_method", "method"):
        value = item.get(key)
        raw_sources.extend(_split_sources(value))
    if not raw_sources:
        raw_sources = [_source_from_evidence(evidence) for evidence in _raw_evidence(item)]
    normalized = [_normalize_source(source) for source in raw_sources if source]
    deduped: list[str] = []
    for source in normalized:
        if source and source not in deduped:
            deduped.append(source)
    return deduped


def _split_sources(value: object) -> list[str]:
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            result.extend(_split_sources(item))
        return result
    if not isinstance(value, str):
        return []
    return [part.strip() for part in re.split(r"[,;/|]+", value) if part.strip()]


def _normalize_source(source: str) -> str:
    compact = re.sub(r"[\s_-]+", "", source).casefold()
    aliases = {
        "reg": "Registry",
        "registry": "Registry",
        "uninstallregistry": "Registry",
        "pe": "PE",
        "portableexe": "PE",
        "file": "File",
        "filesystem": "File",
        "startmenu": "StartMenu",
        "shortcut": "StartMenu",
        "appx": "Appx",
        "msix": "Appx",
        "msi": "MSI",
        "service": "Service",
        "scheduledtask": "ScheduledTask",
        "task": "ScheduledTask",
        "winget": "Winget",
        "choco": "Chocolatey",
        "chocolatey": "Chocolatey",
        "scoop": "Scoop",
    }
    return aliases.get(compact, source.strip())


def _normalize_evidence(item: Mapping[str, Any], *, sources: list[str]) -> list[dict[str, Any]]:
    evidence_items: list[dict[str, Any]] = []
    for evidence in _raw_evidence(item):
        normalized = _normalize_evidence_item(evidence)
        if normalized is not None:
            evidence_items.append(normalized)

    for key, evidence_type, source in (
        ("registryPath", "registry", "Registry"),
        ("registry_path", "registry", "Registry"),
        ("uninstallKey", "registry", "Registry"),
        ("uninstall_key", "registry", "Registry"),
        ("path", "file", "File"),
        ("filePath", "file", "File"),
        ("file_path", "file", "File"),
        ("installLocation", "directory", "File"),
        ("install_location", "directory", "File"),
    ):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            evidence_items.append({"type": evidence_type, "source": source, "path": value.strip()})

    if not evidence_items and sources:
        evidence_items.append({"type": "source", "source": sources[0], "path": None})
    return _dedupe_evidence(evidence_items)


def _raw_evidence(item: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    value = item.get("evidence") or item.get("Evidence")
    if not isinstance(value, list):
        return []
    return [evidence for evidence in value if isinstance(evidence, Mapping)]


def _normalize_evidence_item(evidence: Mapping[str, Any]) -> dict[str, Any] | None:
    source = _first_string(evidence, "source", "Source")
    path = _first_string(evidence, "path", "Path", "value", "Value")
    evidence_type = _first_string(evidence, "type", "Type")
    if not source and not path and not evidence_type:
        return None
    normalized_source = _normalize_source(source) if source else None
    return {
        "type": evidence_type or _guess_evidence_type(path),
        "source": normalized_source,
        "path": path,
    }


def _source_from_evidence(evidence: Mapping[str, Any]) -> str:
    source = _first_string(evidence, "source", "Source")
    return source or ""


def _guess_evidence_type(path: str | None) -> str:
    if not path:
        return "source"
    if path.startswith("HKLM") or path.startswith("HKCU"):
        return "registry"
    return "file"


def _dedupe_evidence(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[object, object, object]] = set()
    deduped: list[dict[str, Any]] = []
    for item in items:
        key = (item.get("type"), item.get("source"), item.get("path"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _first_string(item: Mapping[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, (int, float)):
            return str(value)
    return None
