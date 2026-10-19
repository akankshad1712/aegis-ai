
import re
from collections import Counter
from typing import Any



LOG_PATTERN = re.compile(
    r"^(?P<timestamp>"
    r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}"
    r"(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?"
    r"|\S+"
    r")\s+"
    r"(?P<level>INFO|DEBUG|WARN|WARNING|ERROR|CRITICAL|FATAL)\s+"
    r"(?:(?P<service>[\w.-]+)\s+)?"
    r"(?P<message>.+)$",
    re.IGNORECASE,
)


ISSUE_RULES: list[dict[str, Any]] = [
    {
        "category": "dependency_failure",
        "hypothesis": "Dependency timeout or connection failure",
        "patterns": [
            r"\btime[\s-]?outs?\b",
            r"\bconnection refused\b",
            r"\bconnection reset\b",
            r"\bconnection unavailable\b",
        ],
        "recommended_checks": [
            "Check dependency health and connection pool saturation.",
            "Compare dependency latency with the incident time window.",
            "Inspect network and connection error logs.",
        ],
    },
    {
        "category": "application_errors",
        "hypothesis": "Application error spike",
        "patterns": [
            r"\bexception\b",
            r"\berror rate\b",
            r"\bhttp\s+500\b",
            r"\b5xx\b",
            r"\binternal server error\b",
            r"\bcrash(?:es|ed|ing)?\b",
        ],
        "recommended_checks": [
            "Group errors by exception type and endpoint.",
            "Compare error counts with a healthy baseline.",
            "Check whether failures started after a deployment.",
        ],
    },
    {
        "category": "latency",
        "hypothesis": "Elevated application latency",
        "patterns": [
            r"\blatency\b",
            r"\bslow(?:er|est)?\b",
            r"\bp95\b",
            r"\bresponse time\b",
            r"\bhigh response time\b",
        ],
        "recommended_checks": [
            "Compare p95 latency before and during the incident.",
            "Inspect slow endpoints and downstream dependencies.",
            "Check resource utilization during the affected time window.",
        ],
    },
    {
        "category": "memory_pressure",
        "hypothesis": "Memory pressure",
        "patterns": [
            r"\boom\b",
            r"\bout of memory\b",
            r"\bmemory pressure\b",
            r"\bmemory exhausted\b",
            r"\bheap\b",
        ],
        "recommended_checks": [
            "Inspect memory usage and restart history.",
            "Check for out-of-memory events and memory leaks.",
            "Review heap utilization and garbage-collection activity.",
        ],
    },
]


def _find_signals(message: str, patterns: list[str]) -> list[str]:
    """Return unique, word-boundary-aware signals from a log message."""
    signals: list[str] = []

    for pattern in patterns:
        for match in re.finditer(pattern, message, re.IGNORECASE):
            signal = match.group(0).lower()

            if signal not in signals:
                signals.append(signal)

    return signals


def _normalize_level(level: str) -> str:
    """Normalize common log-level aliases."""
    normalized = level.upper()

    if normalized == "WARN":
        return "WARNING"

    if normalized == "FATAL":
        return "CRITICAL"

    return normalized


def analyze_logs(log_text: str) -> dict[str, Any]:
    """
    Parse application logs and return evidence-backed heuristic findings.

    Findings are diagnostic hypotheses, not confirmed root causes.
    """
    events: list[dict[str, Any]] = []
    malformed_lines: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []

    # Parse each non-empty line while preserving its original line number.
    for line_number, raw_line in enumerate(
        log_text.splitlines(), start=1
    ):
        line = raw_line.strip()

        if not line:
            continue

        match = LOG_PATTERN.match(line)

        if not match:
            malformed_lines.append(
                {
                    "line_number": line_number,
                    "text": line[:500],
                }
            )
            continue

        event = match.groupdict()
        event["line_number"] = line_number
        event["level"] = _normalize_level(event["level"])
        event["service"] = event.get("service") or "unknown"

        events.append(event)

    severity_counts = Counter(
        event["level"] for event in events
    )

    # Evaluate issue patterns against parsed messages.
    for rule in ISSUE_RULES:
        evidence_events: list[dict[str, Any]] = []

        for event in events:
            signals = _find_signals(
                event["message"], rule["patterns"]
            )

            if signals:
                evidence_events.append(
                    {
                        "line_number": event["line_number"],
                        "timestamp": event["timestamp"],
                        "level": event["level"],
                        "service": event["service"],
                        "message": event["message"],
                        "matched_signals": signals,
                    }
                )

        if not evidence_events:
            continue

        # Ranking is based on the number of matching log lines.
        # This is not a calibrated probability or statistical confidence.
        score = min(
            0.95,
            round(0.60 + 0.10 * len(evidence_events), 2),
        )

        findings.append(
            {
                "category": rule["category"],
                "hypothesis": rule["hypothesis"],
                "score": score,
                "confidence_label": "Heuristic ranking",
                "evidence_count": len(evidence_events),
                "matched_signals": sorted(
                    {
                        signal
                        for event in evidence_events
                        for signal in event["matched_signals"]
                    }
                ),
                "evidence": evidence_events,
                "recommended_checks": list(
                    rule["recommended_checks"]
                ),
            }
        )

    findings.sort(
        key=lambda item: item["score"],
        reverse=True,
    )

    if findings:
        summary = (
            f"Found {len(findings)} possible issue categories "
            f"across {len(events)} parsed log events. "
            "These are heuristic hypotheses, not confirmed root causes."
        )
    else:
        summary = (
            "No known issue pattern was detected in the parsed logs. "
            "Review malformed lines and collect relevant logs, metrics, "
            "or traces if further investigation is needed."
        )

    return {
        "summary": summary,
        "event_count": len(events),
        "severity_counts": dict(severity_counts),
        "malformed_line_count": len(malformed_lines),
        "malformed_lines": malformed_lines,
        "events": events,
        "findings": findings,
        "analysis_method": "deterministic_log_rules",
        "root_cause_confirmed": False,
    }
