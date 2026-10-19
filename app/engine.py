
import re
from typing import Any


# These are deterministic diagnostic rules, not an LLM.
# Scores are heuristic ranking values, not calibrated probabilities.

RULES: list[dict[str, Any]] = [
    {
        "category": "latency",
        "hypothesis": "Dependency latency or request timeout",
        "score": 0.86,
        "patterns": [
            r"\btime[\s-]?outs?\b",
            r"\blatency\b",
            r"\bslow(?:er|est)?\b",
            r"\bp95\b",
        ],
        "recommended_checks": [
            "Inspect dependency response times",
            "Compare p95 latency by endpoint",
            "Check connection pools and timeout settings",
        ],
    },
    {
        "category": "application_errors",
        "hypothesis": "Application error spike",
        "score": 0.82,
        "patterns": [
            r"\b5xx\b",
            r"\b500\b",
            r"\berror rate\b",
            r"\bcrash(?:es|ed|ing)?\b",
            r"\bexceptions?\b",
        ],
        "recommended_checks": [
            "Group logs by exception type",
            "Compare errors across application versions",
            "Inspect affected endpoints and error rates",
        ],
    },
    {
        "category": "deployment",
        "hypothesis": "Recent deployment regression",
        "score": 0.78,
        "patterns": [
            r"\bdeploy(?:ment|ed|ing)?\b",
            r"\brelease\b",
            r"\brollback\b",
            r"\bversion\b",
        ],
        "recommended_checks": [
            "Review the deployment timeline",
            "Compare configuration and release changes",
            "Check whether errors began after deployment",
        ],
    },
    {
        "category": "memory",
        "hypothesis": "Memory pressure",
        "score": 0.80,
        "patterns": [
            r"\bmemory\b",
            r"\boom\b",
            r"\bout of memory\b",
            r"\bheap\b",
        ],
        "recommended_checks": [
            "Inspect memory usage over time",
            "Check restart and out-of-memory events",
            "Review heap usage and garbage-collection activity",
        ],
    },
]


def _matched_signals(
    text: str, patterns: list[str]
) -> list[str]:
    """Return unique signal phrases found in the incident text."""
    matches: list[str] = []

    for pattern in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            signal = match.group(0).lower()

            if signal not in matches:
                matches.append(signal)

    return matches


def investigate(
    incident: dict[str, Any],
) -> dict[str, Any]:
    """
    Analyze incident text using deterministic diagnostic rules.

    Findings are hypotheses, not confirmed root causes.
    Scores rank findings heuristically and are not probabilities.
    """
    title = str(incident.get("title") or "")
    description = str(incident.get("description") or "")
    text = f"{title} {description}".lower()

    findings: list[dict[str, Any]] = []

    for rule in RULES:
        signals = _matched_signals(text, rule["patterns"])

        if not signals:
            continue

        findings.append(
            {
                "category": rule["category"],
                "hypothesis": rule["hypothesis"],
                "score": rule["score"],
                "confidence_label": "Heuristic ranking",
                "matched_signals": signals,
                "evidence": [
                    f"Matched incident text signals: "
                    f"{', '.join(signals)}.",
                    (
                        "These text matches support investigating this "
                        "hypothesis; they do not confirm the root cause."
                    ),
                ],
                "recommended_checks": list(
                    rule["recommended_checks"]
                ),
            }
        )

    if not findings:
        findings.append(
            {
                "category": "unknown",
                "hypothesis": (
                    "Insufficient evidence to rank a root cause"
                ),
                "score": 0.25,
                "confidence_label": "Insufficient evidence",
                "matched_signals": [],
                "evidence": [
                    (
                        "The incident title and description did not "
                        "match the available diagnostic rules."
                    ),
                    (
                        "A root cause cannot be confirmed without "
                        "supporting logs, metrics, traces, or "
                        "deployment data."
                    ),
                ],
                "recommended_checks": [
                    "Attach relevant application logs",
                    "Provide the incident time range",
                    "Identify affected endpoints and services",
                    "Review recent deployments and configuration changes",
                ],
            }
        )

    findings.sort(
        key=lambda item: item["score"],
        reverse=True,
    )

    top = findings[0]

    summary = (
        f"Leading hypothesis: {top['hypothesis']}. "
        "This is a heuristic lead, not a confirmed root cause. "
        "Review the matched signals and perform the recommended checks."
    )

    return {
        "summary": summary,
        "findings": findings,
        "analysis_method": "deterministic_rules",
        "root_cause_confirmed": False,
    }
