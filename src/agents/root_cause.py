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

_SYSTEM = """You are a senior SRE performing root cause analysis on a production incident.

You will be given:
- A log summary from the affected service
- Error patterns extracted from logs
- Relevant runbook titles that were matched
- The assessed blast radius

Your job is to synthesize a clear causal chain — the sequence of events that led to this incident — and identify the single root cause.

Rules:
- causal_chain must have 3–5 items, each a concise past-tense sentence describing one sequential event
- root_cause is one clear sentence naming the fundamental cause (not a symptom)
- confidence_score is 0.0–1.0: how certain you are given the available evidence
  - 0.9–1.0 : unambiguous, strong direct evidence
  - 0.7–0.89: likely cause with good supporting evidence
  - 0.5–0.69: probable but notable uncertainty
  - 0.0–0.49: insufficient information

Return ONLY valid JSON — no markdown, no explanation:
{
  "root_cause": "...",
  "confidence_score": 0.87,
  "causal_chain": ["Step 1: ...", "Step 2: ...", "Step 3: ...", "Step 4: ..."]
}"""


def _parse_json(content: str) -> dict:
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise


def root_cause_node(state: IncidentState) -> dict:
    t0 = time.time()
    runbook_titles = [r["title"] for r in state["relevant_runbooks"]]
    span = agent_span("root_cause", {
        "service_name": state["service_name"],
        "error_patterns_count": len(state["error_patterns"]),
        "runbooks_matched": runbook_titles,
        "log_summary": state["log_summary"][:300],
    })

    response = llm.invoke([
        SystemMessage(content=_SYSTEM),
        HumanMessage(content=(
            f"Service: {state['service_name']} ({state['environment']})\n"
            f"Alert: {state['alert_message']}\n\n"
            f"Log Summary:\n{state['log_summary']}\n\n"
            f"Error Patterns:\n" + "\n".join(f"- {p}" for p in state["error_patterns"]) + "\n\n"
            f"Matched Runbooks: {', '.join(runbook_titles)}\n\n"
            f"Blast Radius: {state['blast_radius']}"
        )),
    ])

    try:
        result = _parse_json(response.content)
    except Exception:
        result = {
            "root_cause": "Unable to determine root cause — parse error",
            "confidence_score": 0.0,
            "causal_chain": [],
        }

    root_cause = result.get("root_cause", "Unknown")
    confidence_score = float(result.get("confidence_score", 0.0))
    causal_chain = result.get("causal_chain", [])
    requires_human_approval = confidence_score < 0.7

    print(
        f"[ROOT CAUSE] confidence={confidence_score:.0%} | "
        f"human_approval={'YES' if requires_human_approval else 'NO'}\n"
        f"             {root_cause}"
    )
    for step in causal_chain:
        print(f"               → {step}")

    output = {
        "root_cause": root_cause,
        "confidence_score": confidence_score,
        "causal_chain": causal_chain,
        "requires_human_approval": requires_human_approval,
        "status": "root_cause_identified",
        "messages": [f"[ROOT CAUSE] {root_cause} (confidence={confidence_score:.0%})"],
    }
    span.update(
        output={
            "root_cause": root_cause[:300],
            "confidence_score": confidence_score,
            "causal_chain_steps": len(causal_chain),
            "requires_human_approval": requires_human_approval,
        },
        metadata={"duration_ms": int((time.time() - t0) * 1000)},
    )
    span.end()
    return output
