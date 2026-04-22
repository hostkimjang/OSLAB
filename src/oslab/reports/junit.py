"""JUnit XML report writer."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal


JUnitStatus = Literal["passed", "failed", "error", "skipped"]


@dataclass(frozen=True)
class JUnitCase:
    name: str
    classname: str
    status: JUnitStatus
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)


def write_junit(path: Path, *, suite_name: str, cases: list[JUnitCase], elapsed_seconds: float = 0.0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    testsuite = ET.Element(
        "testsuite",
        {
            "name": suite_name,
            "tests": str(len(cases)),
            "failures": str(sum(1 for case in cases if case.status == "failed")),
            "errors": str(sum(1 for case in cases if case.status == "error")),
            "skipped": str(sum(1 for case in cases if case.status == "skipped")),
            "time": f"{elapsed_seconds:.3f}",
        },
    )
    for case in cases:
        testcase = ET.SubElement(
            testsuite,
            "testcase",
            {
                "name": case.name,
                "classname": case.classname,
                "time": "0.000",
            },
        )
        if case.status == "failed":
            failure = ET.SubElement(testcase, "failure", {"message": case.message})
            failure.text = _details_text(case)
        elif case.status == "error":
            error = ET.SubElement(testcase, "error", {"message": case.message})
            error.text = _details_text(case)
        elif case.status == "skipped":
            skipped = ET.SubElement(testcase, "skipped", {"message": case.message})
            skipped.text = _details_text(case)

    tree = ET.ElementTree(testsuite)
    ET.indent(tree, space="  ")
    tree.write(path, encoding="utf-8", xml_declaration=True)


def _details_text(case: JUnitCase) -> str:
    if not case.details:
        return case.message
    return json.dumps(case.details, ensure_ascii=False, indent=2, sort_keys=True)
