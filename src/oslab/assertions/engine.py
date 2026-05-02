"""Product-neutral assertion engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping


@dataclass(frozen=True)
class AssertionResult:
    """Serializable result for one scenario assertion."""

    id: str
    type: str
    passed: bool
    message: str
    failure_class: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "passed": self.passed,
            "message": self.message,
            "failureClass": self.failure_class,
            "details": self.details,
        }


@dataclass(frozen=True)
class AssertionSummary:
    """Aggregate assertion result."""

    results: list[AssertionResult]

    @property
    def passed(self) -> bool:
        return all(result.passed for result in self.results)

    @property
    def failed_count(self) -> int:
        return sum(1 for result in self.results if not result.passed)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "total": len(self.results),
            "failed": self.failed_count,
            "results": [result.to_dict() for result in self.results],
        }


def evaluate_assertions(
    assertions: Iterable[Mapping[str, Any]],
    canonical_result: Mapping[str, Any] | list[Any],
) -> AssertionSummary:
    """Evaluate scenario assertions against a canonical result payload."""

    records = _inventory_records(canonical_result)
    results: list[AssertionResult] = []
    for assertion in assertions:
        assertion_type = str(assertion.get("type") or "")
        if assertion_type == "inventory.contains":
            results.append(_evaluate_inventory_contains(assertion, records))
        elif assertion_type == "inventory.sourcePresent":
            results.append(_evaluate_inventory_source_present(assertion, records))
        elif assertion_type == "inventory.sourceAbsent":
            results.append(_evaluate_inventory_source_absent(assertion, records))
        elif assertion_type == "inventory.evidencePresent":
            results.append(_evaluate_inventory_evidence_present(assertion, records))
        elif assertion_type == "command.exitCode":
            results.append(_evaluate_command_exit_code(assertion, canonical_result))
        elif assertion_type == "command.stdoutContains":
            results.append(_evaluate_command_text_contains(assertion, canonical_result, stream="stdout"))
        elif assertion_type == "command.stderrContains":
            results.append(_evaluate_command_text_contains(assertion, canonical_result, stream="stderr"))
        elif assertion_type == "file.exists":
            results.append(_evaluate_path_state(assertion, canonical_result, collection_key="files", label="File", expected_exists=True))
        elif assertion_type == "file.notExists":
            results.append(_evaluate_path_state(assertion, canonical_result, collection_key="files", label="File", expected_exists=False))
        elif assertion_type == "directory.exists":
            results.append(
                _evaluate_path_state(assertion, canonical_result, collection_key="directories", label="Directory", expected_exists=True)
            )
        elif assertion_type == "process.exists":
            results.append(_evaluate_named_state(assertion, canonical_result, collection_key="processes", label="Process"))
        elif assertion_type == "service.exists":
            results.append(_evaluate_named_state(assertion, canonical_result, collection_key="services", label="Service"))
        elif assertion_type == "package.exists":
            results.append(_evaluate_named_state(assertion, canonical_result, collection_key="packages", label="Package"))
        else:
            results.append(
                _result(
                    assertion,
                    passed=False,
                    message=f"Unsupported assertion type: {assertion_type or '<missing>'}",
                    failure_class="unsupported_assertion",
                )
            )
    return AssertionSummary(results=results)


def _evaluate_inventory_contains(assertion: Mapping[str, Any], records: list[Mapping[str, Any]]) -> AssertionResult:
    expected_sources = _expected_sources(assertion)
    matching_records = _matching_records(records, assertion.get("match"))
    if not matching_records:
        return _result(
            assertion,
            passed=False,
            message="No inventory record matched the assertion",
            failure_class="assertion_failure",
            details={"match": assertion.get("match") or {}, "recordCount": len(records)},
        )

    if expected_sources:
        for record in matching_records:
            missing = _missing_sources(record, expected_sources)
            if not missing:
                return _result(
                    assertion,
                    passed=True,
                    message="Inventory record matched with required sources",
                    details={"record": _record_summary(record), "requiredSources": expected_sources},
                )
        return _result(
            assertion,
            passed=False,
            message="Inventory record matched, but required sources were missing",
            failure_class="assertion_failure",
            details={
                "requiredSources": expected_sources,
                "candidates": [_record_summary(record) for record in matching_records],
            },
        )

    return _result(
        assertion,
        passed=True,
        message="Inventory record matched",
        details={"record": _record_summary(matching_records[0])},
    )


def _evaluate_inventory_source_present(assertion: Mapping[str, Any], records: list[Mapping[str, Any]]) -> AssertionResult:
    expected_sources = _expected_sources(assertion)
    if not expected_sources:
        return _assertion_config_error(assertion, "`inventory.sourcePresent` requires `source`, `sources`, or `requiredSources`")

    matching_records = _matching_records(records, assertion.get("match"))
    for record in matching_records:
        missing = _missing_sources(record, expected_sources)
        if not missing:
            return _result(
                assertion,
                passed=True,
                message="Required inventory source was present",
                details={"record": _record_summary(record), "requiredSources": expected_sources},
            )

    return _result(
        assertion,
        passed=False,
        message="Required inventory source was not present",
        failure_class="assertion_failure",
        details={
            "requiredSources": expected_sources,
            "candidates": [_record_summary(record) for record in matching_records],
        },
    )


def _evaluate_inventory_source_absent(assertion: Mapping[str, Any], records: list[Mapping[str, Any]]) -> AssertionResult:
    expected_sources = _expected_sources(assertion)
    if not expected_sources:
        return _assertion_config_error(assertion, "`inventory.sourceAbsent` requires `source`, `sources`, or `requiredSources`")

    matching_records = _matching_records(records, assertion.get("match"))
    offenders: list[Mapping[str, Any]] = []
    for record in matching_records:
        record_sources = {_casefold(source) for source in _record_sources(record)}
        if any(_casefold(source) in record_sources for source in expected_sources):
            offenders.append(record)

    if offenders:
        return _result(
            assertion,
            passed=False,
            message="Forbidden inventory source was present",
            failure_class="assertion_failure",
            details={
                "forbiddenSources": expected_sources,
                "offenders": [_record_summary(record) for record in offenders],
            },
        )

    return _result(
        assertion,
        passed=True,
        message="Forbidden inventory source was absent",
        details={"forbiddenSources": expected_sources, "checkedRecords": len(matching_records)},
    )


def _evaluate_inventory_evidence_present(assertion: Mapping[str, Any], records: list[Mapping[str, Any]]) -> AssertionResult:
    matching_records = _matching_records(records, assertion.get("match"))
    if not matching_records:
        return _result(
            assertion,
            passed=False,
            message="No inventory record matched the evidence assertion",
            failure_class="assertion_failure",
            details={"match": assertion.get("match") or {}, "recordCount": len(records)},
        )

    evidence_filter = assertion.get("evidence")
    for record in matching_records:
        evidence_items = _record_evidence(record)
        if not isinstance(evidence_filter, Mapping):
            if evidence_items:
                return _result(
                    assertion,
                    passed=True,
                    message="Inventory evidence was present",
                    details={"record": _record_summary(record), "evidenceCount": len(evidence_items)},
                )
        else:
            for evidence in evidence_items:
                if _evidence_matches(evidence, evidence_filter):
                    return _result(
                        assertion,
                        passed=True,
                        message="Inventory evidence matched",
                        details={"record": _record_summary(record), "evidence": dict(evidence)},
                    )

    return _result(
        assertion,
        passed=False,
        message="Inventory evidence was not present",
        failure_class="assertion_failure",
        details={"candidates": [_record_summary(record) for record in matching_records]},
    )


def _evaluate_command_exit_code(assertion: Mapping[str, Any], canonical_result: Mapping[str, Any] | list[Any]) -> AssertionResult:
    if not isinstance(canonical_result, Mapping):
        return _result(
            assertion,
            passed=False,
            message="Command assertion requires a JSON object",
            failure_class="assertion_config_error",
        )
    expected = assertion.get("exitCode", assertion.get("expected"))
    if not isinstance(expected, int):
        return _assertion_config_error(assertion, "`command.exitCode` requires integer `exitCode`")

    actual = canonical_result.get("exitCode")
    if actual == expected:
        return _result(
            assertion,
            passed=True,
            message="Command exit code matched",
            details={"expected": expected, "actual": actual},
        )
    return _result(
        assertion,
        passed=False,
        message="Command exit code did not match",
        failure_class="assertion_failure",
        details={"expected": expected, "actual": actual},
    )


def _evaluate_command_text_contains(
    assertion: Mapping[str, Any],
    canonical_result: Mapping[str, Any] | list[Any],
    *,
    stream: str,
) -> AssertionResult:
    if not isinstance(canonical_result, Mapping):
        return _result(
            assertion,
            passed=False,
            message="Command assertion requires a JSON object",
            failure_class="assertion_config_error",
        )
    expected = assertion.get("text", assertion.get("contains"))
    if not isinstance(expected, str) or not expected:
        return _assertion_config_error(assertion, f"`command.{stream}Contains` requires non-empty `text`")

    actual = str(canonical_result.get(stream) or "")
    case_sensitive = bool(assertion.get("caseSensitive", True))
    haystack = actual if case_sensitive else actual.casefold()
    needle = expected if case_sensitive else expected.casefold()
    if needle in haystack:
        return _result(
            assertion,
            passed=True,
            message=f"Command {stream} contained expected text",
            details={"text": expected, "caseSensitive": case_sensitive},
        )
    return _result(
        assertion,
        passed=False,
        message=f"Command {stream} did not contain expected text",
        failure_class="assertion_failure",
        details={"text": expected, "caseSensitive": case_sensitive, f"{stream}Preview": actual[:500]},
    )


def _evaluate_path_state(
    assertion: Mapping[str, Any],
    canonical_result: Mapping[str, Any] | list[Any],
    *,
    collection_key: str,
    label: str,
    expected_exists: bool,
) -> AssertionResult:
    if not isinstance(canonical_result, Mapping):
        return _result(
            assertion,
            passed=False,
            message=f"{label} assertion requires a JSON object",
            failure_class="assertion_config_error",
        )

    expected_path = assertion.get("path")
    if not isinstance(expected_path, str) or not expected_path.strip():
        return _assertion_config_error(assertion, f"`{assertion.get('type')}` requires non-empty `path`")

    case_sensitive = bool(assertion.get("caseSensitive", False))
    items = _metadata_collection(canonical_result, collection_key)
    match = _find_path_state(items, expected_path, case_sensitive=case_sensitive)
    if match is None:
        return _result(
            assertion,
            passed=False,
            message=f"{label} state was not reported",
            failure_class="assertion_failure",
            details={"path": expected_path, "collection": collection_key},
        )

    exists = _state_exists(match, default=True)
    if exists is expected_exists:
        state = "exists" if expected_exists else "does not exist"
        return _result(
            assertion,
            passed=True,
            message=f"{label} {state}",
            details={"path": expected_path, "actual": _state_summary(match), "caseSensitive": case_sensitive},
        )

    state = "exist" if expected_exists else "be absent"
    return _result(
        assertion,
        passed=False,
        message=f"{label} did not {state}",
        failure_class="assertion_failure",
        details={
            "path": expected_path,
            "expectedExists": expected_exists,
            "actualExists": exists,
            "actual": _state_summary(match),
        },
    )


def _evaluate_named_state(
    assertion: Mapping[str, Any],
    canonical_result: Mapping[str, Any] | list[Any],
    *,
    collection_key: str,
    label: str,
) -> AssertionResult:
    if not isinstance(canonical_result, Mapping):
        return _result(
            assertion,
            passed=False,
            message=f"{label} assertion requires a JSON object",
            failure_class="assertion_config_error",
        )

    expected_name = assertion.get("name")
    expected_contains = assertion.get("nameContains")
    if not isinstance(expected_name, str) and not isinstance(expected_contains, str):
        return _assertion_config_error(assertion, f"`{assertion.get('type')}` requires `name` or `nameContains`")

    case_sensitive = bool(assertion.get("caseSensitive", False))
    items = _metadata_collection(canonical_result, collection_key)
    match = _find_named_state(
        items,
        expected_name if isinstance(expected_name, str) else None,
        expected_contains if isinstance(expected_contains, str) else None,
        case_sensitive=case_sensitive,
    )
    if match is None:
        return _result(
            assertion,
            passed=False,
            message=f"{label} state was not reported",
            failure_class="assertion_failure",
            details={"name": expected_name, "nameContains": expected_contains, "collection": collection_key},
        )

    exists = _state_exists(match, default=True)
    if exists:
        return _result(
            assertion,
            passed=True,
            message=f"{label} exists",
            details={"actual": _state_summary(match), "caseSensitive": case_sensitive},
        )

    return _result(
        assertion,
        passed=False,
        message=f"{label} did not exist",
        failure_class="assertion_failure",
        details={"expectedName": expected_name, "expectedNameContains": expected_contains, "actual": _state_summary(match)},
    )


def _inventory_records(canonical_result: Mapping[str, Any] | list[Any]) -> list[Mapping[str, Any]]:
    if isinstance(canonical_result, Mapping):
        records = canonical_result.get("records")
    else:
        records = canonical_result
    if not isinstance(records, list):
        return []
    return [record for record in records if isinstance(record, Mapping)]


def _matching_records(records: list[Mapping[str, Any]], match: object) -> list[Mapping[str, Any]]:
    if match is None:
        return list(records)
    if not isinstance(match, Mapping):
        return []
    return [record for record in records if _record_matches(record, match)]


def _record_matches(record: Mapping[str, Any], match: Mapping[str, Any]) -> bool:
    checks = {
        "name": lambda expected: _equals(record.get("name"), expected),
        "nameContains": lambda expected: _contains(record.get("name"), expected),
        "publisher": lambda expected: _equals(record.get("publisher"), expected),
        "publisherContains": lambda expected: _contains(record.get("publisher"), expected),
        "version": lambda expected: _equals(record.get("version"), expected),
        "source": lambda expected: _source_present(record, expected),
        "sourceContains": lambda expected: _source_contains(record, expected),
    }
    for key, expected in match.items():
        check = checks.get(str(key))
        if check is None or not check(expected):
            return False
    return True


def _expected_sources(assertion: Mapping[str, Any]) -> list[str]:
    if isinstance(assertion.get("source"), str):
        return [str(assertion["source"])]
    if isinstance(assertion.get("sources"), list):
        return [str(source) for source in assertion["sources"] if isinstance(source, str) and source.strip()]
    if isinstance(assertion.get("requiredSources"), list):
        return [str(source) for source in assertion["requiredSources"] if isinstance(source, str) and source.strip()]
    return []


def _missing_sources(record: Mapping[str, Any], expected_sources: list[str]) -> list[str]:
    record_sources = {_casefold(source) for source in _record_sources(record)}
    return [source for source in expected_sources if _casefold(source) not in record_sources]


def _record_sources(record: Mapping[str, Any]) -> list[str]:
    sources = record.get("sources")
    if isinstance(sources, list):
        return [str(source) for source in sources if isinstance(source, str)]
    source = record.get("source")
    if isinstance(source, str):
        return [source]
    return []


def _record_evidence(record: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    evidence = record.get("evidence")
    if not isinstance(evidence, list):
        return []
    return [item for item in evidence if isinstance(item, Mapping)]


def _evidence_matches(evidence: Mapping[str, Any], expected: Mapping[str, Any]) -> bool:
    checks = {
        "type": lambda value: _equals(evidence.get("type"), value),
        "source": lambda value: _equals(evidence.get("source"), value),
        "path": lambda value: _equals(evidence.get("path"), value),
        "pathContains": lambda value: _contains(evidence.get("path"), value),
    }
    for key, value in expected.items():
        check = checks.get(str(key))
        if check is None or not check(value):
            return False
    return True


def _source_present(record: Mapping[str, Any], expected: object) -> bool:
    if not isinstance(expected, str):
        return False
    return _casefold(expected) in {_casefold(source) for source in _record_sources(record)}


def _source_contains(record: Mapping[str, Any], expected: object) -> bool:
    if not isinstance(expected, str):
        return False
    needle = _casefold(expected)
    return any(needle in _casefold(source) for source in _record_sources(record))


def _equals(actual: object, expected: object) -> bool:
    if actual is None or expected is None:
        return False
    return _casefold(actual) == _casefold(expected)


def _contains(actual: object, expected: object) -> bool:
    if actual is None or expected is None:
        return False
    return _casefold(expected) in _casefold(actual)


def _casefold(value: object) -> str:
    return str(value).casefold()


def _metadata_collection(canonical_result: Mapping[str, Any], key: str) -> list[Any]:
    metadata = canonical_result.get("metadata")
    if not isinstance(metadata, Mapping):
        return []
    items = metadata.get(key)
    if not isinstance(items, list):
        return []
    return list(items)


def _find_path_state(items: list[Any], expected_path: str, *, case_sensitive: bool) -> Mapping[str, Any] | str | None:
    expected = _normalize_path_for_match(expected_path, case_sensitive=case_sensitive)
    for item in items:
        path = _state_text(item, "path")
        if path is None:
            continue
        if _normalize_path_for_match(path, case_sensitive=case_sensitive) == expected:
            return item
    return None


def _find_named_state(
    items: list[Any],
    expected_name: str | None,
    expected_contains: str | None,
    *,
    case_sensitive: bool,
) -> Mapping[str, Any] | str | None:
    expected = _normalize_text_for_match(expected_name, case_sensitive=case_sensitive) if expected_name else None
    contains = _normalize_text_for_match(expected_contains, case_sensitive=case_sensitive) if expected_contains else None
    for item in items:
        name = _state_text(item, "name")
        if name is None:
            continue
        actual = _normalize_text_for_match(name, case_sensitive=case_sensitive)
        if expected is not None and actual == expected:
            return item
        if contains is not None and contains in actual:
            return item
    return None


def _state_text(item: Any, key: str) -> str | None:
    if isinstance(item, str):
        return item
    if isinstance(item, Mapping):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def _state_exists(item: Mapping[str, Any] | str, *, default: bool) -> bool:
    if isinstance(item, Mapping) and isinstance(item.get("exists"), bool):
        return bool(item["exists"])
    return default


def _state_summary(item: Mapping[str, Any] | str) -> dict[str, Any]:
    if isinstance(item, Mapping):
        return dict(item)
    return {"value": item, "exists": True}


def _normalize_path_for_match(value: str, *, case_sensitive: bool) -> str:
    normalized = value.replace("\\", "/").rstrip("/")
    return normalized if case_sensitive else normalized.casefold()


def _normalize_text_for_match(value: str, *, case_sensitive: bool) -> str:
    return value if case_sensitive else value.casefold()


def _record_summary(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "name": record.get("name"),
        "version": record.get("version"),
        "publisher": record.get("publisher"),
        "sources": _record_sources(record),
    }


def _assertion_config_error(assertion: Mapping[str, Any], message: str) -> AssertionResult:
    return _result(assertion, passed=False, message=message, failure_class="assertion_config_error")


def _result(
    assertion: Mapping[str, Any],
    *,
    passed: bool,
    message: str,
    failure_class: str | None = None,
    details: dict[str, Any] | None = None,
) -> AssertionResult:
    return AssertionResult(
        id=str(assertion.get("id") or "<missing>"),
        type=str(assertion.get("type") or "<missing>"),
        passed=passed,
        message=message,
        failure_class=failure_class,
        details=details or {},
    )
