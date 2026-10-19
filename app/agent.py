"""AEGIS AI — LLM-powered incident investigation agent.

Uses the OpenAI Agents SDK to orchestrate existing, read-only
diagnostic tools. Recovery actions are never executed by this agent.
"""

import json
import os
from typing import Any

from agents import Agent, Runner, function_tool

from app.engine import investigate
from app.log_analyzer import analyze_logs


@function_tool
def investigate_incident_description(
    title: str,
    description: str,
) -> str:
    """Analyze an incident title and description using AEGIS diagnostic rules."""
    result = investigate(
        {
            "title": title,
            "description": description,
        }
    )
    return json.dumps(result, ensure_ascii=False)


@function_tool
def analyze_incident_logs(log_text: str) -> str:
    """Parse application logs and return evidence-backed heuristic findings."""
    result = analyze_logs(log_text)
    return json.dumps(result, ensure_ascii=False)


aegis_agent = Agent(
    name="AEGIS Reliability Investigation Agent",
    model=os.getenv("AEGIS_AGENT_MODEL", "gpt-4.1-mini"),
    instructions="""
You are the investigation assistant for AEGIS AI, a reliability
intelligence platform.

Your job is to investigate incidents using the provided diagnostic tools.

Rules:
1. Use investigate_incident_description to inspect the incident.
2. If log text is supplied, use analyze_incident_logs to inspect it.
3. Base conclusions on the returned evidence. Never invent metrics,
   log entries, deployments, infrastructure state, or tool results.
4. Distinguish observed evidence from hypotheses and recommendations.
5. Explain the leading hypothesis, supporting signals, alternative
   explanations, and recommended verification steps.
6. State clearly when evidence is insufficient.
7. Heuristic scores are ranking values, not calibrated probabilities.
8. Never claim that a root cause is confirmed unless the supplied
   evidence actually establishes it.
9. Never execute shell commands, modify databases, access external
   infrastructure, or perform recovery actions.
10. Return a concise, structured incident investigation report.
""",
    tools=[
        investigate_incident_description,
        analyze_incident_logs,
    ],
)


async def run_investigation_agent(
    incident: dict[str, Any],
    log_text: str = "",
) -> dict[str, Any]:
    """Run the LLM agent with access to AEGIS diagnostic tools."""

    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError(
            "OPENAI_API_KEY is not configured. "
            "Set it in your local .env file before using the AI agent."
        )

    incident_input = {
        "incident_id": incident.get("id"),
        "title": str(incident.get("title") or ""),
        "description": str(incident.get("description") or ""),
        "logs_provided": bool(log_text.strip()),
        "log_text": log_text,
    }

    prompt = (
        "Investigate this incident using your available diagnostic tools. "
        "Analyze the incident description and, when logs are provided, "
        "analyze those logs as well. Clearly separate evidence from "
        "hypotheses and recommendations.\n\n"
        "Incident input:\n"
        f"{json.dumps(incident_input, ensure_ascii=False)}"
    )

    result = await Runner.run(
        aegis_agent,
        input=prompt,
    )

    return {
        "agent": "AEGIS Reliability Investigation Agent",
        "mode": "llm_tool_using",
        "incident_id": incident.get("id"),
        "status": "completed",
        "report": result.final_output,
        "analysis_method": "openai_agents_sdk_with_deterministic_tools",
        "root_cause_confirmed": False,
        "recovery_executed": False,
    }
