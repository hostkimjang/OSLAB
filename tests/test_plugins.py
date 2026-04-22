from __future__ import annotations

import pytest

from oslab.errors import PluginError
from oslab.plugins import normalize_output


def test_canonical_inventory_adapter_passes_through_records() -> None:
    result = normalize_output(
        "canonical.inventory",
        {"records": [{"name": "Git", "sources": ["Registry"]}]},
    )

    assert result.adapter == "canonical.inventory"
    assert result.plugin_name is None
    assert result.canonical == {
        "schemaVersion": 1,
        "kind": "inventory",
        "records": [{"name": "Git", "sources": ["Registry"]}],
    }


def test_canonical_command_adapter_passes_through_command_result() -> None:
    result = normalize_output(
        "canonical.command",
        {
            "schemaVersion": 1,
            "kind": "commandResult",
            "command": "python hello.py",
            "exitCode": 0,
            "stdout": "hello from python\n",
            "stderr": "",
            "metadata": {"runtime": "python"},
        },
    )

    assert result.adapter == "canonical.command"
    assert result.plugin_name is None
    assert result.canonical == {
        "schemaVersion": 1,
        "kind": "commandResult",
        "command": "python hello.py",
        "exitCode": 0,
        "stdout": "hello from python\n",
        "stderr": "",
        "metadata": {"runtime": "python"},
    }


def test_supplyscan_inventory_adapter_normalizes_common_raw_shapes() -> None:
    result = normalize_output(
        "supplyscan.inventory",
        {
            "software": [
                {
                    "sw_name": "Git",
                    "sw_version": "2.0.0",
                    "sw_publisher": "Git Project",
                    "sw_scan_method": "registry, pe",
                    "registry_path": r"HKLM\Software\Microsoft\Windows\CurrentVersion\Uninstall\Git",
                }
            ]
        },
    )

    record = result.canonical["records"][0]
    assert result.plugin_name == "supplyscan"
    assert record["name"] == "Git"
    assert record["version"] == "2.0.0"
    assert record["publisher"] == "Git Project"
    assert record["sources"] == ["Registry", "PE"]
    assert record["evidence"][0]["type"] == "registry"
    assert record["metadata"]["adapter"] == "supplyscan.inventory"


def test_supplyscan_inventory_adapter_accepts_existing_canonical_output() -> None:
    result = normalize_output(
        "supplyscan.inventory",
        {"schemaVersion": 1, "kind": "inventory", "records": [{"name": "Git"}]},
    )

    assert result.canonical["records"] == [{"name": "Git"}]


def test_unknown_plugin_raises_plugin_error() -> None:
    with pytest.raises(PluginError, match="Plugin was not found"):
        normalize_output("missing.inventory", {"records": []})
