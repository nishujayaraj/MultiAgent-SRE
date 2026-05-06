"""
Runs all 3 scenarios through the full LangGraph pipeline.
Prints confidence_score from the root cause agent and
explains why requires_human_approval was True or False.

Human checkpoint is auto-answered with 'execute' so this
script runs without any stdin interaction.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from langgraph.graph import END, StateGraph

from src.agents.impact_assessor import impact_assessor_node
from src.agents.log_analyzer import log_analyzer_node
from src.agents.remediation_planner import remediation_planner_node
from src.agents.root_cause import root_cause_node
from src.agents.runbook_rag import runbook_rag_node
from src.agents.supervisor import supervisor_node
from src.agents.ticket_creator import ticket_creator_node
from src.state.incident_state import IncidentState
from main import SCENARIOS, _route_after_remediation


def _auto_human_checkpoint(state: IncidentState) -> dict:
    """Non-interactive replacement: always answers 'execute'."""
    print("[HUMAN CHECKPOINT] auto-answered: EXECUTE")
    return {
        "human_decision": "execute",
        "messages": ["[HUMAN CHECKPOINT] On-call decision: EXECUTE (auto)"],
    }


def build_graph():
    workflow = StateGraph(IncidentState)
    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("log_analyzer", log_analyzer_node)
    workflow.add_node("runbook_rag", runbook_rag_node)
    workflow.add_node("impact_assessor", impact_assessor_node)
    workflow.add_node("root_cause", root_cause_node)
    workflow.add_node("remediation_planner", remediation_planner_node)
    workflow.add_node("human_checkpoint", _auto_human_checkpoint)
    workflow.add_node("ticket_creator", ticket_creator_node)

    workflow.set_entry_point("supervisor")
    workflow.add_edge("supervisor", "log_analyzer")
    workflow.add_edge("supervisor", "runbook_rag")
    workflow.add_edge("supervisor", "impact_assessor")
    workflow.add_edge("log_analyzer", "root_cause")
    workflow.add_edge("runbook_rag", "root_cause")
    workflow.add_edge("impact_assessor", "root_cause")
    workflow.add_edge("root_cause", "remediation_planner")
    workflow.add_conditional_edges(
        "remediation_planner",
        _route_after_remediation,
        {"human_checkpoint": "human_checkpoint", "ticket_creator": "ticket_creator"},
    )
    workflow.add_edge("human_checkpoint", "ticket_creator")
    workflow.add_edge("ticket_creator", END)
    return workflow.compile()


def _explain_approval(state: IncidentState) -> str:
    """Build a human-readable explanation of why approval was or wasn't required."""
    confidence = state["confidence_score"]
    severity   = state["severity"]
    low_conf   = confidence < 0.7
    is_critical = severity == "critical"

    if not state["requires_human_approval"]:
        return f"confidence {confidence:.0%} ≥ 70% and severity={severity} (not critical)"

    reasons = []
    if is_critical:
        reasons.append(f"severity={severity} (CRITICAL override)")
    if low_conf:
        reasons.append(f"confidence {confidence:.0%} < 70%")
    return " + ".join(reasons) if reasons else "unknown"


def run():
    app = build_graph()

    sep  = "═" * 66
    thin = "─" * 66

    print(f"\n{sep}")
    print("  CONFIDENCE & HUMAN APPROVAL PROBE — All 3 Scenarios")
    print(f"{sep}\n")

    results = []
    for scenario in SCENARIOS:
        alert_id = scenario["alert_id"]
        print(f"{thin}")
        print(f"  Running {alert_id}: {scenario['service_name']} ({scenario['environment']})")
        print(f"{thin}")

        final: IncidentState = app.invoke(scenario)

        results.append({
            "alert_id":               alert_id,
            "service":                scenario["service_name"],
            "severity":               final["severity"],
            "confidence_score":       final["confidence_score"],
            "requires_human":         final["requires_human_approval"],
            "human_decision":         final.get("human_decision"),
            "explanation":            _explain_approval(final),
        })
        print()

    # ── Summary table ──────────────────────────────────────────────────────
    print(f"\n{sep}")
    print("  SUMMARY")
    print(sep)
    print(f"  {'Scenario':<10}  {'Service':<26}  {'Sev':<8}  {'Conf':>6}  {'Human?':<6}  Why")
    print(f"  {'─'*8}  {'─'*24}  {'─'*8}  {'─'*6}  {'─'*6}  {'─'*35}")
    for r in results:
        conf_str   = f"{r['confidence_score']:.0%}"
        human_flag = "YES" if r["requires_human"] else "NO "
        print(
            f"  {r['alert_id']:<10}  {r['service']:<26}  {r['severity']:<8}  "
            f"{conf_str:>6}  {human_flag:<6}  {r['explanation']}"
        )

    print(f"\n{sep}")
    print("  DETAIL")
    print(sep)
    for r in results:
        print(f"\n  {r['alert_id']} — {r['service']}")
        print(f"    Severity           : {r['severity'].upper()}")
        print(f"    Confidence Score   : {r['confidence_score']:.2f}  ({r['confidence_score']:.0%})")
        print(f"    Requires Approval  : {'YES' if r['requires_human'] else 'NO'}")
        if r["requires_human"]:
            print(f"    Reason             : {r['explanation']}")
            if r["human_decision"]:
                print(f"    Human Decision     : {r['human_decision'].upper()}")
        else:
            print(f"    Reason (no approval): {r['explanation']}")

    print(f"\n{sep}\n")


if __name__ == "__main__":
    run()
