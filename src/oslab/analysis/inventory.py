"""Analysis for canonical inventory payloads."""

from __future__ import annotations

from collections import Counter
from typing import Any, Mapping

from oslab.errors import AnalysisError

MISSING = "<missing>"


def analyze_inventory(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Create a product-neutral summary from canonical inventory JSON."""

    if not isinstance(payload, Mapping):
        raise AnalysisError("Inventory analysis requires a JSON object")
    records = payload.get("records")
    if not isinstance(records, list):
        raise AnalysisError("Inventory analysis requires a list `records` field")

    source_counts: Counter[str] = Counter()
    publisher_counts: Counter[str] = Counter()
    confidence_counts: Counter[str] = Counter()
    duplicate_counts: Counter[str] = Counter()
    compact_records: list[dict[str, Any]] = []
    missing_name: list[int] = []
    missing_version: list[int] = []
    missing_publisher: list[int] = []
    missing_sources: list[int] = []
    missing_evidence: list[int] = []
    missing_evidence_path: list[int] = []

    for index, item in enumerate(records):
        if not isinstance(item, Mapping):
            continue
        name = _clean_string(item.get("name"))
        version = _clean_string(item.get("version"))
        publisher = _clean_string(item.get("publisher"))
        confidence = _clean_string(item.get("confidence")) or "unknown"
        sources = _string_list(item.get("sources"))
        evidence = item.get("evidence") if isinstance(item.get("evidence"), list) else []

        if not name:
            missing_name.append(index)
        if not version:
            missing_version.append(index)
        if not publisher:
            missing_publisher.append(index)
        if not sources:
            missing_sources.append(index)
        if not evidence:
            missing_evidence.append(index)
        elif any(isinstance(entry, Mapping) and not _clean_string(entry.get("path")) for entry in evidence):
            missing_evidence_path.append(index)

        publisher_counts[publisher or MISSING] += 1
        confidence_counts[confidence] += 1
        for source in sources or [MISSING]:
            source_counts[source] += 1
        duplicate_counts[_dedupe_key(name, version, publisher)] += 1

        compact_records.append(
            {
                "index": index,
                "name": name,
                "version": version,
                "publisher": publisher,
                "sources": sources,
                "confidence": confidence,
                "evidenceCount": len(evidence),
                "evidencePathMissing": index in missing_evidence_path,
            }
        )

    duplicate_records = sum(count - 1 for key, count in duplicate_counts.items() if key != MISSING and count > 1)
    quality = {
        "missingName": len(missing_name),
        "missingVersion": len(missing_version),
        "missingPublisher": len(missing_publisher),
        "missingSources": len(missing_sources),
        "missingEvidence": len(missing_evidence),
        "missingEvidencePath": len(missing_evidence_path),
        "duplicateRecords": duplicate_records,
    }

    return {
        "schemaVersion": 1,
        "kind": "inventoryAnalysis",
        "input": {
            "schemaVersion": payload.get("schemaVersion"),
            "kind": payload.get("kind"),
        },
        "recordCount": len(compact_records),
        "sourceCounts": _sorted_counter(source_counts),
        "publisherCounts": _sorted_counter(publisher_counts),
        "confidenceCounts": _sorted_counter(confidence_counts),
        "quality": quality,
        "warnings": _quality_warnings(quality, len(compact_records)),
        "records": compact_records,
    }


def _clean_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        text = _clean_string(item)
        if text and text not in result:
            result.append(text)
    return result


def _dedupe_key(name: str | None, version: str | None, publisher: str | None) -> str:
    if not name:
        return MISSING
    return "\u001f".join((name.lower(), (version or "").lower(), (publisher or "").lower()))


def _sorted_counter(counter: Counter[str]) -> dict[str, int]:
    return {key: counter[key] for key in sorted(counter)}


def _quality_warnings(quality: Mapping[str, int], record_count: int) -> list[str]:
    warnings: list[str] = []
    if record_count == 0:
        warnings.append("inventory_empty")
    for key in (
        "missingName",
        "missingVersion",
        "missingPublisher",
        "missingSources",
        "missingEvidence",
        "missingEvidencePath",
        "duplicateRecords",
    ):
        if int(quality.get(key, 0)) > 0:
            warnings.append(key)
    return warnings
