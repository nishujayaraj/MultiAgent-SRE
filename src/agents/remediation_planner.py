import json
import re
import time

from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from src.state.incident_state import IncidentState
from src.tools.observability import agent_span

load_dotenv()
llm = ChatAnthropic(model="claude-haiku-4-5-20251001", temperature=0)

_SYSTEM = """You are an SRE remediation planner. Given a confirmed root cause and matched runbooks, produce a prioritized remediation plan.

Rules:
- 3–5 steps, ordered by urgency (most critical first)
- Each step must be specific and actionable — include the actual command or tool where applicable
- risk must be exactly one of: "low", "medium", "high"
- estimated_time is a human-readable string like "2 minutes", "15 minutes", "1 hour"
- recommended_action is the single most important thing to do RIGHT NOW (copied or summarized from step 1)

Return ONLY valid JSON — no markdown, no explanation:
{
  "remediation_steps": [
    {"step": "...", "risk": "low|medium|high", "estimated_time": "..."},
    ...
  ],
  "recommended_action": "..."
}"""


def _extract_remediation_section(content: str) -> str:
    """Pull just the Remediation bullet points from a runbook."""
    in_section = False
    lines = []
    for line in content.split("\n"):
        stripped = line.strip().lower()
        if stripped.startswith("remediation:"):
            in_section = True
            continue
        if in_section and stripped and any(
            stripped.startswith(h)
            for h in ("escalation:", "runbook:", "symptoms:", "common causes:", "diagnostic steps:")
        ):
            break
        if in_section:
            lines.append(line)
    return "\n".join(lines).strip()


def _parse_json(content: str) -> dict:
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise


def remediation_planner_node(state: IncidentState) -> dict:
    t0 = time.time()
    span = agent_span("remediation_planner", {
        "root_cause": state["root_cause"][:300],
        "severity": state["severity"],
        "runbooks_count": len(state["relevant_runbooks"]),
    })

    runbook_sections = []
    for r in state["relevant_runbooks"]:
        section = _extract_remediation_section(r["content"])
        if section:
            runbook_sections.append(f"=== {r['title']} ===\n{section}")
    runbook_context = "\n\n".join(runbook_sections) or "No runbook remediation sections available."

    response = llm.invoke([
        SystemMessage(content=_SYSTEM),
        HumanMessage(content=(
            f"Service: {state['service_name']} ({state['environment']})\n"
            f"Severity: {state['severity']}\n"
            f"Root Cause: {state['root_cause']}\n\n"
            f"Runbook Remediation Guidance:\n{runbook_context}"
        )),
    ])

    try:
        result = _parse_json(response.content)
    except Exception:
        result = {
            "remediation_steps": [
                {"step": "Manual investigation required — parse error", "risk": "high", "estimated_time": "unknown"}
            ],
            "recommended_action": "Escalate to on-call engineer",
        }

    remediation_steps = result.get("remediation_steps", [])
    recommended_action = result.get("recommended_action", "")

    # Approve if critical severity OR root cause agent already flagged low confidence
    requires_human_approval = (state["severity"] == "critical") or state["requires_human_approval"]

    print(
        f"[REMEDIATION] {len(remediation_steps)} step(s) planned | "
        f"human_approval={'YES (severity=critical)' if state['severity'] == 'critical' else 'YES (low confidence)' if state['requires_human_approval'] else 'NO'}\n"
        f"              recommended: {recommended_action}"
    )

    output = {
        "remediation_steps": remediation_steps,
        "recommended_action": recommended_action,
        "requires_human_approval": requires_human_approval,
        "status": "remediating",
        "messages": [
            f"[REMEDIATION] {len(remediation_steps)} step(s) planned. "
            f"Recommended: {recommended_action}"
        ],
    }
    span.update(
        output={
            "steps_count": len(remediation_steps),
            "recommended_action": recommended_action[:300],
            "requires_human_approval": requires_human_approval,
        },
        metadata={"duration_ms": int((time.time() - t0) * 1000)},
    )
    span.end()
    return output
