from __future__ import annotations

import xml.etree.ElementTree as ET

from oslab.reports.junit import JUnitCase, write_junit


def test_write_junit_maps_failures_errors_and_skips(tmp_path) -> None:
    output = tmp_path / "reports" / "result.junit.xml"

    write_junit(
        output,
        suite_name="fake.suite",
        cases=[
            JUnitCase(name="passed", classname="oslab.fake", status="passed"),
            JUnitCase(name="failed", classname="oslab.fake", status="failed", message="assertion failed"),
            JUnitCase(name="error", classname="oslab.fake", status="error", message="provider failed"),
            JUnitCase(name="skipped", classname="oslab.fake", status="skipped", message="not applicable"),
        ],
    )

    root = ET.parse(output).getroot()
    assert root.attrib["name"] == "fake.suite"
    assert root.attrib["tests"] == "4"
    assert root.attrib["failures"] == "1"
    assert root.attrib["errors"] == "1"
    assert root.attrib["skipped"] == "1"
    assert root.find("./testcase[@name='passed']/failure") is None
    assert root.find("./testcase[@name='failed']/failure") is not None
    assert root.find("./testcase[@name='error']/error") is not None
    assert root.find("./testcase[@name='skipped']/skipped") is not None


def test_write_junit_keeps_unicode_details_readable(tmp_path) -> None:
    output = tmp_path / "reports" / "unicode.junit.xml"

    write_junit(
        output,
        suite_name="unicode.suite",
        cases=[
            JUnitCase(
                name="fixture.demo",
                classname="oslab.demo",
                status="error",
                message="Fixture command failed",
                details={"stderr": "위치 C:\\Oslab\\fixture.ps1:10 문자:3"},
            )
        ],
    )

    content = output.read_text(encoding="utf-8")
    assert "위치" in content
    assert "문자:3" in content
    assert "\\uc704\\uce58" not in content
