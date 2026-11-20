import hashlib
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest


pytest.importorskip("PIL")
EDITOR = Path(__file__).resolve().parents[1] / "validation/artifacts/intro-video/edit_intro.py"
spec = importlib.util.spec_from_file_location("intro_video_editor", EDITOR)
editor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(editor)


def test_yaml_indentation_advances_without_drawing_a_whitespace_glyph(monkeypatch):
    def unexpected_draw(*args, **kwargs):
        pytest.fail("Whitespace-only indentation has no pixels to draw")

    monkeypatch.setattr(editor.ImageDraw, "Draw", unexpected_draw)
    editor.text(None, (81.6, 465.00000000000006), "    ", None, alpha=0.42)


def write_json(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")


def timestamp(seconds):
    return datetime.fromtimestamp(seconds, timezone.utc).isoformat()


def write_progress(path, events):
    path.write_text("\n".join(json.dumps({"timestamp": timestamp(at), "phase": phase, "details": details})
                              for at, phase, details in events), encoding="utf-8")


@pytest.fixture
def suite_folder(tmp_path):
    rows = []
    for entry in editor.ENVIRONMENTS:
        folder = tmp_path / entry
        folder.mkdir()
        run_id = f"matrix-run-{entry}"
        scenario_id = f"matrix.{entry}"
        scenario = folder / "scenario.yaml"
        scenario.write_text(f"id: {scenario_id}\n", encoding="utf-8")
        rows.append({"id": entry, "scenario": f"scenarios/{entry}.yaml", "scenarioId": scenario_id,
                     "scenarioSha256": hashlib.sha256(scenario.read_text(encoding="utf-8").encode("utf-8")).hexdigest(),
                     "status": "passed", "runId": run_id, "folder": entry})
        write_json(folder / "run.json", {"runId": run_id, "scenarioId": scenario_id, "status": "passed",
                                         "startedAt": timestamp(1), "completedAt": timestamp(12),
                                         "details": {"assertions": {"failed": 0, "total": 4}}})
        write_progress(folder / "progress.jsonl", [(1, "run.created", {"runId": run_id}),
                                                  (2, "vm.clone.start", {}), (3, "vm.clone.done", {}),
                                                  (6, "product.step.start", {"stepId": "scan"}),
                                                  (8, "product.step.done", {"stepId": "scan"}),
                                                  (9, "product.steps.write.done", {}), (12, "run.done", {})])
        write_json(folder / "console.json", {"runId": run_id, "suiteRunId": "matrix-run", "seconds": 7,
                                             "fps": 8, "status": "complete"})
    write_json(tmp_path / editor.FOCUS / "report.json", {"runId": f"matrix-run-{editor.FOCUS}", "seconds": 2})
    write_json(tmp_path / "suite.json", {"runId": "matrix-run", "suiteId": "demo-matrix", "status": "passed",
                                       "entries": rows, "summary": {"passed": 4, "total": 4}})
    write_json(tmp_path / "terminal.json", {"runId": "matrix-run"})
    write_json(tmp_path / "entries.json", rows)
    return tmp_path


def test_suite_attestation_binds_chapters_to_their_children(suite_folder):
    capture = editor.SuiteCapture(suite_folder)
    record = editor.suite_record(capture)
    children = {child["entry_id"]: child for child in record["children"]}
    assert record["run_chapter_entry"] == "windows-fresh"
    assert record["evidence_chapter_entry"] == "ubuntu-upgrade"
    assert children["windows-fresh"]["lifecycle"][-1] == {
        "name": "Run", "start_phase": "product.step.start", "finish_phase": "product.steps.write.done", "seconds": 3,
    }
    assert children["windows-fresh"]["console_recording"] == {"seconds": 7, "fps": 8, "frames": 56}
    assert "report_recording" not in children["windows-fresh"]
    assert children["ubuntu-upgrade"]["report_recording"]["seconds"] == 2
    assert record["all_product_checks_overlapped"] is True


@pytest.mark.parametrize("asset", ["terminal", "console", "report"])
def test_suite_rejects_a_recording_from_another_run(suite_folder, asset):
    folder = suite_folder if asset == "terminal" else suite_folder / editor.FOCUS
    write_json(folder / f"{asset}.json", {"runId": "different-run"})
    with pytest.raises(ValueError, match=f"{asset} recording.*different"):
        editor.SuiteCapture(suite_folder).media(editor.FOCUS, "report")


def test_failed_step_and_final_vm_state_use_recorded_events(tmp_path):
    log = tmp_path / "progress.jsonl"
    write_progress(log, [(1, "run.created", {}), (2, "vm.clone.start", {}), (3, "vm.start.done", {}),
                         (5, "desktop.signin.done", {}), (6, "product.step.start", {"stepId": "scan"}),
                         (7, "product.step.failed", {"stepId": "scan"}), (8, "vm.stop.done", {}),
                         (9, "run.failed", {})])
    progress = editor.Progress(log)
    assert progress.completed == 9
    assert progress.product_steps() == [["scan", 6, 7, "failed"]]
    assert not progress.vm_running(2)
    assert progress.vm_running(7)
    assert not progress.vm_running(8)
    for powered_off in (None, 4):  # No reading or a transient reading during the sign-in reboot.
        clip = SimpleNamespace(t0=3, end=8, meta={"powered_off": powered_off})
        assert progress.console_visible(clip, 6)
        assert not progress.console_visible(clip, 8)


def test_recorded_scenario_is_checked_before_rendering(suite_folder, monkeypatch):
    capture = editor.SuiteCapture(suite_folder)
    monkeypatch.setattr(editor, "REPO", suite_folder)
    scenario = suite_folder / "scenarios/windows-fresh.yaml"
    scenario.parent.mkdir()
    scenario.write_bytes((suite_folder / "windows-fresh/scenario.yaml").read_bytes())
    assert capture.scenario_path() == scenario
    scenario.write_text("id: other\n", encoding="utf-8")
    with pytest.raises(ValueError, match="has changed"):
        capture.scenario_path()


def test_product_steps_must_overlap_on_one_instant():
    def step(start, end):
        return ["scan", start, end, "passed"]

    assert not editor.concurrent_testing([[step(2, 4), step(6, 7)], [step(4, 6)]])
    assert editor.concurrent_testing([[step(2, 4), step(6, 7)], [step(3, 6)]])


def test_finale_groups_ties_and_never_rewinds():
    keys = editor.finale_timing([10, 10.2, 10.2, 10.4, 10.8, 10.8], 10.3, [2, 2.75, 3.45, 4.25], 5.5)
    assert [epoch for _, epoch in keys] == [9.5, 10, 10.2, 10.4, 10.8, 12.3]
    assert editor.crossing(keys, 10.2) == pytest.approx(2.75)
    assert editor.crossing(keys, 10.8) == pytest.approx(4.25)
    assert editor.piecewise(keys, 5.6) == (12.3, 0)
