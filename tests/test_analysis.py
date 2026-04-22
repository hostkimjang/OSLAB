from __future__ import annotations

import pytest

from oslab.analysis import analyze_inventory
from oslab.errors import AnalysisError


def test_analyze_inventory_summarizes_records_and_quality() -> None:
    analysis = analyze_inventory(
        {
            "schemaVersion": 1,
            "kind": "inventory",
            "records": [
                {
                    "name": "Git",
                    "version": "2.0.0",
                    "publisher": "Git Project",
                    "sources": ["Registry", "PE"],
                    "confidence": "high",
                    "evidence": [{"path": r"HKLM\Software\Git"}],
                },
                {
                    "name": "Unknown Tool",
                    "version": "",
                    "publisher": None,
                    "sources": ["Registry"],
                    "confidence": "unknown",
                    "evidence": [{"path": None}],
                },
            ],
        }
    )

    assert analysis["kind"] == "inventoryAnalysis"
    assert analysis["recordCount"] == 2
    assert analysis["sourceCounts"] == {"PE": 1, "Registry": 2}
    assert analysis["publisherCounts"]["Git Project"] == 1
    assert analysis["publisherCounts"]["<missing>"] == 1
    assert analysis["quality"]["missingVersion"] == 1
    assert analysis["quality"]["missingPublisher"] == 1
    assert analysis["quality"]["missingEvidencePath"] == 1
    assert "missingPublisher" in analysis["warnings"]
    assert analysis["records"][0]["name"] == "Git"


def test_analyze_inventory_requires_records_list() -> None:
    with pytest.raises(AnalysisError):
        analyze_inventory({"kind": "inventory", "records": {}})
