from __future__ import annotations

from oslab.assertions import evaluate_assertions


CANONICAL_INVENTORY = {
    "schemaVersion": 1,
    "kind": "inventory",
    "records": [
        {
            "name": "Git",
            "version": "2.0.0",
            "publisher": "Fake Scanner",
            "sources": ["Registry", "PE"],
            "confidence": "high",
            "evidence": [
                {
                    "type": "registry",
                    "source": "Registry",
                    "path": r"HKLM\Software\Microsoft\Windows\CurrentVersion\Uninstall\Git",
                }
            ],
            "metadata": {},
        }
    ],
}


def test_inventory_contains_passes_with_required_sources() -> None:
    summary = evaluate_assertions(
        [
            {
                "type": "inventory.contains",
                "id": "git-registry",
                "match": {"nameContains": "git"},
                "requiredSources": ["registry"],
            }
        ],
        CANONICAL_INVENTORY,
    )

    assert summary.passed is True
    assert summary.failed_count == 0
    assert summary.results[0].passed is True
    assert summary.results[0].details["record"]["name"] == "Git"


def test_inventory_contains_fails_when_sources_are_missing() -> None:
    summary = evaluate_assertions(
        [
            {
                "type": "inventory.contains",
                "id": "git-winget",
                "match": {"name": "Git"},
                "requiredSources": ["Winget"],
            }
        ],
        CANONICAL_INVENTORY,
    )

    assert summary.passed is False
    assert summary.failed_count == 1
    assert summary.results[0].failure_class == "assertion_failure"
    assert "required sources were missing" in summary.results[0].message


def test_inventory_source_present_and_absent() -> None:
    summary = evaluate_assertions(
        [
            {"type": "inventory.sourcePresent", "id": "pe-present", "match": {"name": "Git"}, "source": "PE"},
            {"type": "inventory.sourceAbsent", "id": "msi-absent", "match": {"name": "Git"}, "source": "MSI"},
        ],
        CANONICAL_INVENTORY,
    )

    assert summary.passed is True
    assert [result.id for result in summary.results] == ["pe-present", "msi-absent"]


def test_inventory_evidence_present_passes_with_filter() -> None:
    summary = evaluate_assertions(
        [
            {
                "type": "inventory.evidencePresent",
                "id": "registry-evidence",
                "match": {"name": "Git"},
                "evidence": {"source": "Registry", "pathContains": "Uninstall"},
            }
        ],
        CANONICAL_INVENTORY,
    )

    assert summary.passed is True
    assert summary.results[0].details["evidence"]["source"] == "Registry"


def test_command_assertions_pass_for_hello_world_output() -> None:
    summary = evaluate_assertions(
        [
            {"type": "command.exitCode", "id": "exit-zero", "exitCode": 0},
            {"type": "command.stdoutContains", "id": "stdout-hello", "text": "hello from python"},
        ],
        {
            "schemaVersion": 1,
            "kind": "commandResult",
            "command": "python hello.py",
            "exitCode": 0,
            "stdout": "hello from python\n",
            "stderr": "",
        },
    )

    assert summary.passed is True
    assert summary.failed_count == 0
    assert [result.id for result in summary.results] == ["exit-zero", "stdout-hello"]


def test_command_stdout_contains_can_fail() -> None:
    summary = evaluate_assertions(
        [{"type": "command.stdoutContains", "id": "stdout-hello", "text": "hello from c"}],
        {
            "schemaVersion": 1,
            "kind": "commandResult",
            "exitCode": 0,
            "stdout": "hello from python\n",
            "stderr": "",
        },
    )

    assert summary.passed is False
    assert summary.results[0].failure_class == "assertion_failure"
    assert "did not contain" in summary.results[0].message


def test_unsupported_assertion_type_fails_explicitly() -> None:
    summary = evaluate_assertions(
        [{"type": "file.exists", "id": "future-file", "path": "/tmp/file"}],
        CANONICAL_INVENTORY,
    )

    assert summary.passed is False
    assert summary.results[0].failure_class == "unsupported_assertion"
