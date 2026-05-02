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


def test_file_and_directory_assertions_use_command_metadata() -> None:
    summary = evaluate_assertions(
        [
            {"type": "file.exists", "id": "state-file", "path": r"C:\Oslab\demo-fixture-state.json"},
            {"type": "file.notExists", "id": "old-state-missing", "path": r"C:\Oslab\old-state.json"},
            {"type": "directory.exists", "id": "oslab-dir", "path": r"C:\Oslab"},
        ],
        {
            "schemaVersion": 1,
            "kind": "commandResult",
            "exitCode": 0,
            "stdout": "",
            "stderr": "",
            "metadata": {
                "files": [
                    {"path": r"C:\Oslab\demo-fixture-state.json", "exists": True, "length": 128},
                    {"path": r"C:\Oslab\old-state.json", "exists": False},
                ],
                "directories": [{"path": r"C:\Oslab", "exists": True}],
            },
        },
    )

    assert summary.passed is True
    assert [result.id for result in summary.results] == ["state-file", "old-state-missing", "oslab-dir"]


def test_file_exists_fails_when_state_is_not_reported() -> None:
    summary = evaluate_assertions(
        [{"type": "file.exists", "id": "missing-report", "path": r"C:\Oslab\missing.json"}],
        {"schemaVersion": 1, "kind": "commandResult", "metadata": {"files": []}},
    )

    assert summary.passed is False
    assert summary.results[0].failure_class == "assertion_failure"
    assert "not reported" in summary.results[0].message


def test_named_state_assertions_use_command_metadata() -> None:
    summary = evaluate_assertions(
        [
            {"type": "process.exists", "id": "python-process", "nameContains": "python"},
            {"type": "service.exists", "id": "spooler-service", "name": "Spooler"},
            {"type": "package.exists", "id": "demo-package", "name": "Demo Runtime"},
        ],
        {
            "schemaVersion": 1,
            "kind": "commandResult",
            "metadata": {
                "processes": [{"name": "python.exe", "exists": True, "pid": 1234}],
                "services": [{"name": "Spooler", "exists": True, "status": "Running"}],
                "packages": [{"name": "Demo Runtime", "exists": True, "version": "1.0.0"}],
            },
        },
    )

    assert summary.passed is True
    assert summary.failed_count == 0


def test_named_state_assertion_requires_name_or_name_contains() -> None:
    summary = evaluate_assertions(
        [{"type": "process.exists", "id": "bad-process"}],
        {"schemaVersion": 1, "kind": "commandResult", "metadata": {"processes": []}},
    )

    assert summary.passed is False
    assert summary.results[0].failure_class == "assertion_config_error"


def test_unsupported_assertion_type_fails_explicitly() -> None:
    summary = evaluate_assertions(
        [{"type": "future.assertion", "id": "future-check"}],
        CANONICAL_INVENTORY,
    )

    assert summary.passed is False
    assert summary.results[0].failure_class == "unsupported_assertion"
