from io import StringIO

from oslab.console import Console, format_detail_value, redact_value


def test_redact_value_masks_short_values() -> None:
    assert redact_value("short") == "<redacted>"


def test_redact_value_keeps_small_prefix_and_suffix() -> None:
    assert redact_value("root@pam!oslab") == "root@pam...slab"


def test_redact_value_handles_empty_values() -> None:
    assert redact_value("") == "<empty>"


def test_format_detail_value_keeps_korean_text_readable() -> None:
    formatted = format_detail_value({"error": "[WinError 10060] 연결하지 못했습니다"})

    assert "연결하지 못했습니다" in formatted
    assert "\\uc5f0" not in formatted


def test_console_detail_formats_structured_korean_details() -> None:
    stream = StringIO()
    console = Console(stream=stream)

    console.detail("details", {"error": "위치 C:\\Oslab\\script.ps1:15 문자:3"})

    output = stream.getvalue()
    assert "details: {" in output
    assert "위치" in output
    assert "문자:3" in output
    assert "\\uc704\\uce58" not in output
