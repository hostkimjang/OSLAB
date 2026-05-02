from pathlib import Path

import pytest

from oslab.errors import SuiteValidationError
from oslab.models.suite import load_suite


def test_supplyscan_windows_v1_suite_is_valid() -> None:
    suite = load_suite(Path("validation/suites/supplyscan-windows-v1.example.yaml"))

    assert suite.suite_id == "supplyscan.windows.v1"
    assert [entry.id for entry in suite.entries] == [
        "clean-baseline",
        "agent-cli",
        "os-profile",
        "path-profile",
        "appx-readonly",
    ]
    assert suite.entries[-1].allow_failure is True
    assert suite.entries[-1].tier == "gap-probe"


def test_suite_requires_unique_run_ids(tmp_path: Path) -> None:
    path = tmp_path / "suite.yaml"
    path.write_text(
        """
schemaVersion: 1
id: duplicate.suite
runs:
  - id: one
    scenario: scenarios/windows/demo-python-hello.example.yaml
  - id: one
    scenario: scenarios/windows/demo-c-hello.example.yaml
""",
        encoding="utf-8",
    )

    with pytest.raises(SuiteValidationError, match="Duplicate suite run id"):
        load_suite(path)


def test_suite_validates_allow_failure_type(tmp_path: Path) -> None:
    path = tmp_path / "suite.yaml"
    path.write_text(
        """
schemaVersion: 1
id: bad.suite
runs:
  - id: one
    scenario: scenarios/windows/demo-python-hello.example.yaml
    allowFailure: maybe
""",
        encoding="utf-8",
    )

    with pytest.raises(SuiteValidationError, match="allowFailure"):
        load_suite(path)
