
from app.log_analyzer import analyze_logs


def test_detects_timeout_and_preserves_evidence():
    logs = """\
2026-10-19T10:15:01Z INFO checkout-api Server started
2026-10-19T10:15:12Z ERROR checkout-api Database connection timeout
2026-10-19T10:15:13Z ERROR checkout-api HTTP 500 returned
"""

    result = analyze_logs(logs)

    assert result["event_count"] == 3
    assert result["severity_counts"]["ERROR"] == 2
    assert result["findings"]
    assert result["findings"][0]["evidence"]
    assert any(
        "timeout" in evidence["message"].lower()
        for finding in result["findings"]
        for evidence in finding["evidence"]
    )


def test_handles_empty_and_malformed_logs():
    result = analyze_logs("not a valid structured log line")

    assert result["event_count"] == 0
    assert result["malformed_line_count"] == 1
    assert result["findings"] == []


def test_detects_memory_pressure():
    result = analyze_logs(
        "2026-10-19T10:20:00Z ERROR invoice-worker Out of memory"
    )

    assert any(
        finding["hypothesis"] == "Memory pressure"
        for finding in result["findings"]
    )
