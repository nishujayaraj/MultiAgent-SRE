import time

from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from src.state.incident_state import IncidentState
from src.tools.mock_tools import create_jira_ticket
from src.tools.observability import agent_span

load_dotenv()
llm = ChatAnthropic(model="claude-haiku-4-5-20251001", temperature=0)

_SYSTEM = """You are an SRE writing a Jira incident ticket. Given a full incident report, write a concise but complete ticket description.

Structure it exactly as:
## Summary
One sentence.

## Impact
- Affected services: ...
- Users impacted: ...
- Blast radius: ...

## Root Cause
...

## Causal Chain
1. ...
2. ...

## Remediation Taken / Planned
List the steps with risk and time estimates.

## Human Decision
Note the on-call decision if one was made.

Be specific and professional. Use past tense for what happened, present tense for what is being done."""


def ticket_creator_node(state: IncidentState) -> dict:
    t0 = time.time()
    span = agent_span("ticket_creator", {
        "alert_id": state["alert_id"],
        "classification": state["classification"],
        "severity": state["severity"],
        "human_decision": state.get("human_decision"),
    })

    causal_chain_text = "\n".join(
        f"{i + 1}. {step}" for i, step in enumerate(state["causal_chain"])
    )
    remediation_text = "\n".join(
        f"- [{s.get('risk', '?').upper()} risk, {s.get('estimated_time', '?')}] {s.get('step', '')}"
        for s in state["remediation_steps"]
    )
    human_decision_text = (
        f"On-call decision: {state['human_decision'].upper()}"
        if state.get("human_decision")
        else "No human checkpoint triggered (auto-remediation path)."
    )

    response = llm.invoke([
        SystemMessage(content=_SYSTEM),
        HumanMessage(content=(
            f"Incident ID   : {state['alert_id']}\n"
            f"Service       : {state['service_name']} ({state['environment']})\n"
            f"Classification: {state['classification']}\n"
            f"Severity      : {state['severity']}\n"
            f"Alert         : {state['alert_message']}\n\n"
            f"Root Cause    : {state['root_cause']}\n"
            f"Confidence    : {state['confidence_score']:.0%}\n\n"
            f"Causal Chain  :\n{causal_chain_text}\n\n"
            f"Users Impacted: {state['estimated_users_impacted']:,}\n"
            f"Blast Radius  : {state['blast_radius']}\n"
            f"Affected Svcs : {', '.join(state['affected_services'])}\n\n"
            f"Remediation Steps:\n{remediation_text}\n\n"
            f"Human Decision: {human_decision_text}\n"
            f"Log Summary   : {state['log_summary']}"
        )),
    ])

    resolution_summary = response.content.strip()
    alert_num = state["alert_id"].replace("INC-", "").replace("inc-", "")
    ticket_id = f"INC-{alert_num}-{int(time.time())}"

    create_jira_ticket(
        title=f"[{state['severity'].upper()}] {state['service_name']}: {state['classification']} — {state['alert_id']}",
        description=resolution_summary,
        severity=state["severity"],
    )

    print(f"[TICKET] Created {ticket_id} for {state['alert_id']} ({state['service_name']})")

    output = {
        "ticket_id": ticket_id,
        "resolution_summary": resolution_summary,
        "status": "resolved",
        "messages": [f"[TICKET] Jira ticket {ticket_id} created for {state['alert_id']}"],
    }
    span.update(
        output={"ticket_id": ticket_id, "status": "resolved"},
        metadata={"duration_ms": int((time.time() - t0) * 1000)},
    )
    span.end()
    return output
