from pathlib import Path

import pytest

from oslab.config import load_config
from oslab.errors import ConfigError


def test_example_config_loads() -> None:
    config = load_config(Path("config/oslab.local.example.yaml"))

    assert config.output_root == Path("runs")
    assert config.timeout_minutes == 45
    assert config.keep_vm_on_failure is False


def test_env_reference_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    config = load_config(None)
    monkeypatch.setenv("OSLAB_TEST_SECRET", "secret-value")

    assert config.resolve_env_reference("OSLAB_TEST_SECRET") == "secret-value"


def test_missing_env_reference_fails() -> None:
    config = load_config(None)

    with pytest.raises(ConfigError, match="Required environment variable is not set"):
        config.resolve_env_reference("OSLAB_DOES_NOT_EXIST")

