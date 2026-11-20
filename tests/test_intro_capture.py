import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def capture(monkeypatch):
    pytest.importorskip("PIL")
    pytest.importorskip("websockets")
    path = Path(__file__).resolve().parents[1] / "validation" / "artifacts" / "intro-video"
    monkeypatch.syspath_prepend(str(path))
    import capture_suite

    return capture_suite


def test_capture_checks_child_and_live_clone_identity(capture):
    scenario = SimpleNamespace(vmid_range={"start": 9185, "end": 9189})
    client = SimpleNamespace(config=SimpleNamespace(node="pve01"), get_vm_config=lambda _: {"name": "owned"})
    event = {"details": {"vmId": 9185, "runId": "suite-ubuntu", "cloneName": "owned", "node": "pve01"}}

    assert capture.owned_recording_vm(client, event, scenario, "suite-ubuntu") == 9185
    with pytest.raises(RuntimeError, match="suite child and node"):
        capture.owned_recording_vm(client, event, scenario, "other-suite-ubuntu")
    event["details"]["cloneName"] = "other-clone"
    with pytest.raises(RuntimeError, match="VM name"):
        capture.owned_recording_vm(client, event, scenario, "suite-ubuntu")


def test_manifest_rejects_result_from_other_child(capture, monkeypatch, tmp_path):
    monkeypatch.setattr(capture, "REPO", tmp_path)
    entry = SimpleNamespace(id="ubuntu", scenario=Path("scenario.yaml"))
    entry.scenario = tmp_path / entry.scenario
    entry.scenario.write_text("os: linux\n", encoding="utf-8")
    scenario = SimpleNamespace(scenario_id="linux.demo", os_family="linux", raw={})
    child = tmp_path / entry.id
    child.mkdir()
    result = {"runId": "suite", "entries": [{"id": "ubuntu", "runId": "suite-ubuntu", "status": "passed"}]}
    child_result = {"runId": "wrong-child", "scenarioId": "linux.demo", "status": "passed"}
    entries = [(entry, scenario)]
    hashes = capture.scenario_hashes(None, entries)
    capture.write_json(child / "run.json", child_result)

    with pytest.raises(RuntimeError, match="child result does not match"):
        capture.write_entries(tmp_path, None, entries, result, hashes)
    assert not (tmp_path / "entries.json").exists()

    child_result["runId"] = "suite-ubuntu"
    capture.write_json(child / "run.json", child_result)
    capture.write_entries(tmp_path, None, entries, result, hashes)
    row = capture.read_json(tmp_path / "entries.json")[0]
    assert (row["scenario"], row["suiteRunId"], row["runId"]) == ("scenario.yaml", "suite", "suite-ubuntu")
    assert row["scenarioSha256"] == hashes[entry.id]
    entry.scenario.write_bytes(b"os: linux\n")
    assert capture.scenario_hashes(None, entries) == hashes
    entry.scenario.write_text("os: windows\n", encoding="utf-8")
    assert capture.scenario_hashes(None, entries) != hashes
