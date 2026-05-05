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

_SYSTEM = """You are an SRE incident classifier. Given an alert, classify it and determine severity.

Classification options (pick exactly one):
- high_cpu        : CPU utilization spike or saturation
- memory_leak     : Memory exhaustion, OOM, or leak
- db_connection   : Database connection pool exhaustion or DB unreachable
- network         : Network latency, packet loss, or connectivity failure
- deployment      : Pod crash, CrashLoopBackOff, or failed rollout
- unknown         : Cannot determine from available information

Severity options (pick exactly one):
- low      : No user-facing impact, informational
- medium   : Partial degradation, subset of users affected
- high     : Significant degradation, many users affected
- critical : Full or near-full outage, widespread user impact

Return ONLY valid JSON — no markdown, no explanation:
{"classification": "<type>", "severity": "<level>", "reasoning": "<one concise sentence>"}"""


def _parse_json(content: str) -> dict:
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise


def supervisor_node(state: IncidentState) -> dict:
    t0 = time.time()
    span = agent_span("supervisor", {
        "alert_id": state["alert_id"],
        "alert_message": state["alert_message"][:200],
        "service_name": state["service_name"],
        "environment": state["environment"],
    })

    response = llm.invoke([
        SystemMessage(content=_SYSTEM),
        HumanMessage(content=(
            f"Alert: {state['alert_message']}\n"
            f"Service: {state['service_name']}\n"
            f"Environment: {state['environment']}"
        )),
    ])

    try:
        result = _parse_json(response.content)
    except Exception:
        result = {"classification": "unknown", "severity": "medium", "reasoning": "Parse error"}

    classification = result.get("classification", "unknown")
    severity = result.get("severity", "medium")
    reasoning = result.get("reasoning", "")

    print(
        f"[SUPERVISOR] alert_id={state['alert_id']} | "
        f"classification={classification} | severity={severity}\n"
        f"             reasoning: {reasoning}"
    )

    output = {
        "classification": classification,
        "severity": severity,
        "status": "investigating",
        "messages": [
            f"[SUPERVISOR] {state['alert_id']} classified as '{classification}' "
            f"(severity={severity}) on {state['service_name']}/{state['environment']}"
        ],
    }
    span.update(
        output={"classification": classification, "severity": severity},
        metadata={"duration_ms": int((time.time() - t0) * 1000)},
    )
    span.end()
    return output
