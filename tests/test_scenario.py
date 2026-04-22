from pathlib import Path

import pytest

from oslab.errors import ScenarioValidationError
from oslab.models.scenario import load_scenario


def test_windows_supplyscan_scenario_is_valid() -> None:
    scenario = load_scenario(Path("scenarios/windows/supplyscan-gold-lite.yaml"))

    assert scenario.scenario_id == "supplyscan.gold-lite.windows"
    assert scenario.os_family == "windows"
    assert scenario.provider_type == "proxmox"
    assert scenario.guest_mode == "auto"
    assert scenario.report_formats == ["junit", "json", "html"]
    assert scenario.output_adapter == "supplyscan.inventory"


def test_linux_example_scenario_is_valid() -> None:
    scenario = load_scenario(Path("scenarios/linux/generic-smoke.example.yaml"))

    assert scenario.scenario_id == "generic.linux.smoke"
    assert scenario.os_family == "linux"
    assert scenario.guest_mode == "auto"


def test_fake_artifact_smoke_scenario_is_valid() -> None:
    scenario = load_scenario(Path("scenarios/windows/fake-artifact-smoke.example.yaml"))

    assert scenario.scenario_id == "fake.artifact-smoke.windows"
    assert scenario.os_family == "windows"
    assert scenario.guest_mode == "auto"
    assert scenario.output_adapter == "canonical.inventory"


def test_fake_installer_smoke_scenario_is_valid() -> None:
    scenario = load_scenario(Path("scenarios/windows/fake-installer-smoke.example.yaml"))

    assert scenario.scenario_id == "fake.installer-smoke.windows"
    assert scenario.os_family == "windows"
    assert scenario.output_adapter == "canonical.inventory"


def test_fake_agent_cli_smoke_scenario_is_valid() -> None:
    scenario = load_scenario(Path("scenarios/windows/fake-agent-cli-smoke.example.yaml"))

    assert scenario.scenario_id == "fake.agent-cli-smoke.windows"
    assert scenario.os_family == "windows"
    assert scenario.output_adapter == "canonical.inventory"
    assert [step["id"] for step in scenario.raw["product"]["steps"]] == ["register", "status", "scan"]


def test_generic_powershell_system_demo_scenario_is_valid() -> None:
    scenario = load_scenario(Path("scenarios/windows/demo-powershell-system.example.yaml"))

    assert scenario.scenario_id == "demo.powershell-system.windows"
    assert scenario.os_family == "windows"
    assert scenario.output_adapter == "canonical.command"
    assert scenario.report_formats == ["junit", "json", "html"]


def test_generic_python_hello_demo_scenario_is_valid() -> None:
    scenario = load_scenario(Path("scenarios/windows/demo-python-hello.example.yaml"))

    assert scenario.scenario_id == "demo.python-hello.windows"
    assert scenario.os_family == "windows"
    assert scenario.output_adapter == "canonical.command"
    assert [assertion["type"] for assertion in scenario.assertions] == ["command.exitCode", "command.stdoutContains"]


def test_generic_c_hello_demo_scenario_is_valid() -> None:
    scenario = load_scenario(Path("scenarios/windows/demo-c-hello.example.yaml"))

    assert scenario.scenario_id == "demo.c-hello.windows"
    assert scenario.os_family == "windows"
    assert scenario.output_adapter == "canonical.command"
    assert [assertion["type"] for assertion in scenario.assertions] == ["command.exitCode", "command.stdoutContains"]


def test_generic_fixture_state_demo_scenario_is_valid() -> None:
    scenario = load_scenario(Path("scenarios/windows/demo-fixture-state.example.yaml"))

    assert scenario.scenario_id == "demo.fixture-state.windows"
    assert scenario.os_family == "windows"
    assert scenario.output_adapter == "canonical.command"
    assert scenario.raw["fixtures"][0]["id"] == "demo-state-file"


def test_generic_agent_steps_demo_scenario_is_valid() -> None:
    scenario = load_scenario(Path("scenarios/windows/demo-agent-steps.example.yaml"))

    assert scenario.scenario_id == "demo.agent-steps.windows"
    assert scenario.os_family == "windows"
    assert scenario.output_adapter == "canonical.inventory"
    assert [step["id"] for step in scenario.raw["product"]["steps"]] == ["register", "status", "scan"]


def test_generic_python_unittest_demo_scenario_is_valid() -> None:
    scenario = load_scenario(Path("scenarios/windows/demo-python-unittest.example.yaml"))

    assert scenario.scenario_id == "demo.python-unittest.windows"
    assert scenario.os_family == "windows"
    assert scenario.output_adapter == "canonical.command"
    assert [assertion["id"] for assertion in scenario.assertions] == [
        "python-unittest-exit-zero",
        "python-unittest-ran-tests",
        "python-unittest-ok",
    ]


def test_generic_python_http_service_demo_scenario_is_valid() -> None:
    scenario = load_scenario(Path("scenarios/windows/demo-python-http-service.example.yaml"))

    assert scenario.scenario_id == "demo.python-http-service.windows"
    assert scenario.os_family == "windows"
    assert scenario.output_adapter == "canonical.command"
    assert scenario.raw["fixtures"][0]["id"] == "demo-python-runtime"


def test_generic_c_unit_demo_scenario_is_valid() -> None:
    scenario = load_scenario(Path("scenarios/windows/demo-c-unit.example.yaml"))

    assert scenario.scenario_id == "demo.c-unit.windows"
    assert scenario.os_family == "windows"
    assert scenario.output_adapter == "canonical.command"
    assert scenario.raw["fixtures"][0]["id"] == "demo-c-compiler"


def test_intentional_assertion_failure_demo_scenario_is_valid() -> None:
    scenario = load_scenario(Path("scenarios/windows/demo-intentional-assertion-failure.example.yaml"))

    assert scenario.scenario_id == "demo.intentional-assertion-failure.windows"
    assert scenario.os_family == "windows"
    assert scenario.output_adapter == "canonical.command"
    assert scenario.assertions[-1]["id"] == "intentionally-missing-text"


def test_supplyscan_agent_cli_scenario_is_valid() -> None:
    scenario = load_scenario(Path("scenarios/windows/supplyscan-agent-cli.example.yaml"))

    assert scenario.scenario_id == "supplyscan.agent-cli.windows"
    assert scenario.os_family == "windows"
    assert scenario.output_adapter == "supplyscan.inventory"
    assert scenario.report_formats == ["junit", "json", "html"]
    register_step = scenario.raw["product"]["steps"][0]
    assert register_step["id"] == "register"
    assert "OSLAB_SUPPLYSCAN_TOKEN" not in register_step["command"]["template"]
    assert sorted(register_step["secretTokens"]) == ["SupplyScanSabun", "SupplyScanServerUrl"]


def test_supplyscan_agent_status_scenario_is_valid() -> None:
    scenario = load_scenario(Path("scenarios/windows/supplyscan-agent-status.example.yaml"))

    assert scenario.scenario_id == "supplyscan.agent-status.windows"
    assert scenario.os_family == "windows"
    assert scenario.output_adapter == "canonical.inventory"


def test_missing_required_field_fails(tmp_path: Path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text(
        """
schemaVersion: 1
os:
  family: windows
provider:
  type: proxmox
guest:
  mode: auto
assertions:
  - type: file.exists
    id: file-check
    path: C:\\Temp\\x.txt
""",
        encoding="utf-8",
    )

    with pytest.raises(ScenarioValidationError, match="Missing required scenario field `id`"):
        load_scenario(path)


def test_installer_artifact_requires_install_command(tmp_path: Path) -> None:
    path = tmp_path / "bad-installer.yaml"
    path.write_text(
        """
schemaVersion: 1
id: bad.installer
os:
  family: windows
provider:
  type: proxmox
guest:
  mode: auto
artifact:
  type: installer
  pathParam: artifactPath
  destination: C:\\Oslab\\installer.exe
assertions:
  - type: file.exists
    id: output
    path: C:\\Oslab\\scan-result.json
""",
        encoding="utf-8",
    )

    with pytest.raises(ScenarioValidationError, match="Installer artifact requires `installCommand`"):
        load_scenario(path)
