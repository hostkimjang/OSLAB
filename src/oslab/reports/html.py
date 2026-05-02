"""Static HTML report writer."""

from __future__ import annotations

import html
from pathlib import Path
from typing import Any


def write_artifact_html(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    status = str(payload.get("status") or "unknown")
    scenario_id = str(payload.get("scenarioId") or "unknown")
    title = f"oslab report - {scenario_id}"
    assertions = payload.get("assertions") if isinstance(payload.get("assertions"), dict) else {}
    product = payload.get("product") if isinstance(payload.get("product"), dict) else {}
    outputs = payload.get("outputs") if isinstance(payload.get("outputs"), dict) else {}
    analysis = payload.get("analysis") if isinstance(payload.get("analysis"), dict) else {}
    artifact = payload.get("artifact") if isinstance(payload.get("artifact"), dict) else {}
    preflight = payload.get("preflight") if isinstance(payload.get("preflight"), dict) else {}
    fixtures = payload.get("fixtures") if isinstance(payload.get("fixtures"), dict) else {}
    vm = payload.get("vm") if isinstance(payload.get("vm"), dict) else {}
    logs = payload.get("logs") if isinstance(payload.get("logs"), dict) else {}
    reports = payload.get("reports") if isinstance(payload.get("reports"), dict) else {}

    body = "\n".join(
        [
            "<!doctype html>",
            '<html lang="en">',
            "<head>",
            '<meta charset="utf-8">',
            f"<title>{_e(title)}</title>",
            "<style>",
            "body{font-family:Segoe UI,Arial,sans-serif;margin:32px;color:#17202a;background:#f7f8fa}",
            "main{max-width:1040px;margin:0 auto;background:white;border:1px solid #d8dee4;padding:24px}",
            "h1,h2{margin:0 0 12px} h2{margin-top:28px}",
            ".status{display:inline-block;padding:4px 10px;border-radius:4px;font-weight:600}",
            ".passed{background:#dafbe1;color:#116329}.failed{background:#ffebe9;color:#82071e}",
            "table{border-collapse:collapse;width:100%;margin-top:8px}th,td{border:1px solid #d8dee4;padding:8px;text-align:left;vertical-align:top}",
            "th{background:#f0f3f6}code{font-family:Consolas,monospace;word-break:break-all}",
            "</style>",
            "</head>",
            "<body><main>",
            f"<h1>{_e(scenario_id)}</h1>",
            f'<p><span class="status {_e(status)}">{_e(status.upper())}</span> {_e(str(payload.get("message") or ""))}</p>',
            _section("VM", _mapping_table(vm)),
            _section("Artifact", _mapping_table({k: v for k, v in artifact.items() if k != "files"})),
            _section("Preflight", _checks_table(preflight)),
            _section("Fixtures", _fixtures_table(fixtures)),
            _section("Product", _mapping_table({k: v for k, v in product.items() if k != "steps"})),
            _section("Outputs", _mapping_table(outputs)),
            _section("Inventory Analysis", _analysis_table(analysis)),
            _section("Assertions", _assertions_table(assertions)),
            _section("Logs", _links_table(logs)),
            _section("Reports", _links_table(reports)),
            "</main></body></html>",
        ]
    )
    path.write_text(body + "\n", encoding="utf-8")


def write_suite_html(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    status = str(payload.get("status") or "unknown")
    suite_id = str(payload.get("suiteId") or "unknown")
    title = f"oslab suite - {suite_id}"
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    entries = payload.get("entries") if isinstance(payload.get("entries"), list) else []
    reports = payload.get("reports") if isinstance(payload.get("reports"), dict) else {}

    body = "\n".join(
        [
            "<!doctype html>",
            '<html lang="en">',
            "<head>",
            '<meta charset="utf-8">',
            f"<title>{_e(title)}</title>",
            "<style>",
            "body{font-family:Segoe UI,Arial,sans-serif;margin:32px;color:#17202a;background:#f7f8fa}",
            "main{max-width:1120px;margin:0 auto;background:white;border:1px solid #d8dee4;padding:24px}",
            "h1,h2{margin:0 0 12px} h2{margin-top:28px}",
            ".status{display:inline-block;padding:4px 10px;border-radius:4px;font-weight:600}",
            ".passed{background:#dafbe1;color:#116329}.failed{background:#ffebe9;color:#82071e}",
            ".allowed{background:#fff8c5;color:#7d4e00}",
            "table{border-collapse:collapse;width:100%;margin-top:8px}th,td{border:1px solid #d8dee4;padding:8px;text-align:left;vertical-align:top}",
            "th{background:#f0f3f6}code{font-family:Consolas,monospace;word-break:break-all}",
            "</style>",
            "</head>",
            "<body><main>",
            f"<h1>{_e(suite_id)}</h1>",
            f'<p><span class="status {_e(status)}">{_e(status.upper())}</span> run id <code>{_e(str(payload.get("runId") or ""))}</code></p>',
            _section("Summary", _mapping_table(summary)),
            _section("Entries", _suite_entries_table(entries)),
            _section("Reports", _links_table(reports)),
            "</main></body></html>",
        ]
    )
    path.write_text(body + "\n", encoding="utf-8")


def _section(title: str, content: str) -> str:
    return f"<h2>{_e(title)}</h2>\n{content}"


def _mapping_table(mapping: dict[str, Any]) -> str:
    if not mapping:
        return "<p>None</p>"
    rows = ["<table><tbody>"]
    for key, value in mapping.items():
        rows.append(f"<tr><th>{_e(str(key))}</th><td><code>{_e(_format_value(value))}</code></td></tr>")
    rows.append("</tbody></table>")
    return "\n".join(rows)


def _assertions_table(assertions: dict[str, Any]) -> str:
    results = assertions.get("results")
    if not isinstance(results, list) or not results:
        return _mapping_table(assertions)
    rows = ["<table><thead><tr><th>ID</th><th>Type</th><th>Status</th><th>Message</th></tr></thead><tbody>"]
    for item in results:
        if not isinstance(item, dict):
            continue
        status = "passed" if bool(item.get("passed")) else "failed"
        rows.append(
            "<tr>"
            f"<td>{_e(str(item.get('id') or ''))}</td>"
            f"<td>{_e(str(item.get('type') or ''))}</td>"
            f'<td><span class="status {status}">{_e(status)}</span></td>'
            f"<td>{_e(str(item.get('message') or ''))}</td>"
            "</tr>"
        )
    rows.append("</tbody></table>")
    return "\n".join(rows)


def _checks_table(preflight: dict[str, Any]) -> str:
    checks = preflight.get("checks")
    if not isinstance(checks, list) or not checks:
        return _mapping_table(preflight)
    rows = ["<table><thead><tr><th>ID</th><th>Status</th><th>Message</th></tr></thead><tbody>"]
    for item in checks:
        if not isinstance(item, dict):
            continue
        status = "passed" if bool(item.get("passed")) else "failed"
        rows.append(
            "<tr>"
            f"<td>{_e(str(item.get('id') or ''))}</td>"
            f'<td><span class="status {status}">{_e(status)}</span></td>'
            f"<td>{_e(str(item.get('message') or ''))}</td>"
            "</tr>"
        )
    rows.append("</tbody></table>")
    return "\n".join(rows)


def _fixtures_table(fixtures: dict[str, Any]) -> str:
    items = fixtures.get("items")
    if not isinstance(items, list) or not items:
        return _mapping_table(fixtures)
    rows = [
        "<table><thead><tr><th>ID</th><th>Status</th><th>Exit</th><th>Message</th><th>Stdout</th><th>Stderr</th></tr></thead><tbody>"
    ]
    for item in items:
        if not isinstance(item, dict):
            continue
        status = "passed" if bool(item.get("passed")) else "failed"
        rows.append(
            "<tr>"
            f"<td>{_e(str(item.get('id') or ''))}</td>"
            f'<td><span class="status {status}">{_e(status)}</span></td>'
            f"<td>{_e(_format_value(item.get('exitCode')))}</td>"
            f"<td>{_e(str(item.get('message') or ''))}</td>"
            f"<td><code>{_e(_preview_text(item.get('stdout')))}</code></td>"
            f"<td><code>{_e(_preview_text(item.get('stderr')))}</code></td>"
            "</tr>"
        )
    rows.append("</tbody></table>")
    return "\n".join(rows)


def _analysis_table(analysis: dict[str, Any]) -> str:
    if not analysis:
        return "<p>None</p>"
    quality = analysis.get("quality") if isinstance(analysis.get("quality"), dict) else {}
    summary = {
        "recordCount": analysis.get("recordCount"),
        "sourceCounts": analysis.get("sourceCounts"),
        "publisherCounts": analysis.get("publisherCounts"),
        "confidenceCounts": analysis.get("confidenceCounts"),
        "missingVersion": quality.get("missingVersion"),
        "missingPublisher": quality.get("missingPublisher"),
        "missingEvidencePath": quality.get("missingEvidencePath"),
        "warnings": ", ".join(str(warning) for warning in analysis.get("warnings", []))
        if isinstance(analysis.get("warnings"), list)
        else "",
    }
    return _mapping_table(summary)


def _links_table(mapping: dict[str, Any]) -> str:
    if not mapping:
        return "<p>None</p>"
    rows = ["<table><tbody>"]
    for key, value in mapping.items():
        text = str(value)
        rows.append(f"<tr><th>{_e(str(key))}</th><td><code>{_e(text)}</code></td></tr>")
    rows.append("</tbody></table>")
    return "\n".join(rows)


def _suite_entries_table(entries: list[Any]) -> str:
    if not entries:
        return "<p>None</p>"
    rows = [
        "<table><thead><tr><th>ID</th><th>Status</th><th>Allow Failure</th><th>Tier</th><th>Scenario</th><th>Run</th><th>Failure</th></tr></thead><tbody>"
    ]
    for item in entries:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or "unknown")
        allow_failure = bool(item.get("allowFailure"))
        status_class = "allowed" if allow_failure and status != "passed" else status
        rows.append(
            "<tr>"
            f"<td>{_e(str(item.get('id') or ''))}</td>"
            f'<td><span class="status {status_class}">{_e(status)}</span></td>'
            f"<td>{_e(str(allow_failure))}</td>"
            f"<td>{_e(str(item.get('tier') or ''))}</td>"
            f"<td><code>{_e(str(item.get('scenarioId') or item.get('scenarioPath') or ''))}</code></td>"
            f"<td><code>{_e(str(item.get('runDir') or item.get('runId') or ''))}</code></td>"
            f"<td>{_e(str(item.get('failureClass') or item.get('error') or ''))}</td>"
            "</tr>"
        )
    rows.append("</tbody></table>")
    return "\n".join(rows)


def _format_value(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return str(value)
    return "" if value is None else str(value)


def _preview_text(value: Any, *, limit: int = 1000) -> str:
    text = "" if value is None else str(value).strip()
    if not text:
        return ""
    return text if len(text) <= limit else text[:limit] + "...<truncated>"


def _e(value: str) -> str:
    return html.escape(value, quote=True)
