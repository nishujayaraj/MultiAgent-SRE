import textwrap

from langgraph.graph import END, StateGraph

from src.agents.impact_assessor import impact_assessor_node
from src.agents.log_analyzer import log_analyzer_node
from src.agents.remediation_planner import remediation_planner_node
from src.agents.root_cause import root_cause_node
from src.agents.runbook_rag import runbook_rag_node
from src.agents.supervisor import supervisor_node
from src.agents.ticket_creator import ticket_creator_node
from src.state.incident_state import IncidentState
from src.tools.observability import flush_trace, start_trace

# ── Scenario definitions ────────────────────────────────────────────────────

_INC001_LOGS = """\
2024-01-15 14:23:01.543 WARN  c.z.h.pool.HikariPool - HikariPool-1 - Connection acquisition slower than usual: 8,240ms (threshold: 5,000ms)
2024-01-15 14:23:02.112 WARN  c.z.h.pool.HikariPool - HikariPool-1 - Pool utilization: 85/100 connections active, 0 idle
2024-01-15 14:23:03.334 ERROR c.z.h.pool.HikariPool - HikariPool-1 - Connection is not available, request timed out after 30000ms.
2024-01-15 14:23:03.445 ERROR c.p.s.PaymentService - Failed to process payment txn_id=TXN-847362: PSQLException: connection timeout
2024-01-15 14:23:04.001 WARN  c.z.h.pool.HikariPool - HikariPool-1 - 12 threads waiting for connection (waiting > 5s)
2024-01-15 14:23:05.112 INFO  c.p.s.PaymentService - 86% of payment requests completing successfully (degraded)
2024-01-15 14:23:06.334 ERROR org.postgresql.Driver - FATAL: remaining connection slots are reserved — current: 90/100
2024-01-15 14:23:07.445 WARN  c.p.r.PaymentRepository - Connection pool wait queue growing: 15 pending requests
2024-01-15 14:23:08.001 ERROR c.p.s.PaymentService - Transaction TXN-847370 failed: could not acquire connection within SLA
2024-01-15 14:23:09.334 INFO  c.p.s.PaymentService - Retry succeeded for TXN-847371 after 11,000ms wait
2024-01-15 14:23:10.112 WARN  c.z.h.pool.HikariPool - HikariPool-1 - Pool utilization: 91/100 connections, trend: increasing
2024-01-15 14:23:12.001 WARN  c.p.s.PaymentService - 503 error rate elevated to 8% on /api/checkout — service degraded\
"""

_INC002_LOGS = """\
2024-01-15 15:42:01.123 INFO  k8s - Pod recommendation-service-7d9f8b6c4-xk2p9: Running (memory: 1820MB/2048MB)
2024-01-15 15:42:15.445 WARN  c.r.s.RecommendationEngine - Heap at 89% (1820MB/2048MB) — Full GC triggered
2024-01-15 15:42:16.001 WARN  c.r.s.RecommendationEngine - GC pause: 4,240ms — application frozen during collection
2024-01-15 15:42:18.334 ERROR c.r.cache.ModelCache - Cache eviction failed — unbounded cache size: 847MB, no eviction policy set
2024-01-15 15:42:19.112 ERROR c.r.s.RecommendationService - java.lang.OutOfMemoryError: Java heap space
2024-01-15 15:42:19.113 ERROR c.r.s.RecommendationService - at com.rec.cache.ModelCache.store(ModelCache.java:243)
2024-01-15 15:42:19.445 INFO  k8s - OOMKilled: container recommendation-service (exit code 137, limit: 2Gi)
2024-01-15 15:42:20.001 INFO  k8s - Pod restarting... (RESTARTS: 6)
2024-01-15 15:42:28.334 WARN  c.r.s.RecommendationEngine - Heap at 76% on restart — unbounded cache reloading from disk
2024-01-15 15:42:44.112 ERROR c.r.s.RecommendationService - java.lang.OutOfMemoryError: Java heap space
2024-01-15 15:42:44.334 INFO  k8s - OOMKilled: container recommendation-service (exit code 137). RESTARTS: 7
2024-01-15 15:42:46.001 WARN  k8s - Back-off restarting failed container recommendation-service
2024-01-15 15:42:47.445 INFO  k8s - Pod STATUS: CrashLoopBackOff (RESTARTS: 8)
2024-01-15 15:42:50.001 ERROR c.r.api.RecommendationController - No healthy pods available — service completely unavailable
2024-01-15 15:42:51.334 ERROR c.r.api.RecommendationController - Returning 503 to all clients — recommendation feature offline\
"""

_INC003_LOGS = """\
2024-01-15 16:10:01.001 INFO  c.d.pipeline.DataPipelineWorker - Batch job batch-20240115-1610 started (records: 2.4M)
2024-01-15 16:10:02.445 WARN  c.d.pipeline.DataPipelineWorker - CPU usage: 94.2% — sustained for 2 minutes
2024-01-15 16:10:05.112 WARN  c.d.pipeline.DataPipelineWorker - Thread pool saturated: 48/48 active threads, 0 idle
2024-01-15 16:10:07.334 WARN  c.d.pipeline.DataPipelineWorker - Throughput degraded: 15,000 rec/s → 3,200 rec/s
2024-01-15 16:10:08.001 WARN  c.d.transform.JsonTransformer - Slow record processing: avg 340ms per record (baseline: 45ms)
2024-01-15 16:10:10.445 INFO  k8s.hpa - HPA scale-up triggered: data-pipeline 2 → 4 replicas
2024-01-15 16:10:12.334 WARN  c.d.transform.JsonTransformer - GC overhead: 18% of CPU in garbage collection (threshold: 5%)
2024-01-15 16:10:15.112 INFO  k8s - New pods starting but not yet ready — CPU still at 93%
2024-01-15 16:10:30.445 WARN  c.d.pipeline.DataPipelineWorker - Batch ETA: 47 minutes (was 8 minutes)
2024-01-15 16:11:01.001 WARN  c.d.transform.JsonTransformer - Nested JSON deserialization suspected: O(n^2) operation on large record payloads
2024-01-15 16:11:08.334 WARN  c.d.pipeline.DataPipelineWorker - CPU: 94.1% — all 4 replicas active, no throughput improvement
2024-01-15 16:11:15.001 INFO  c.d.pipeline.DataPipelineWorker - No user-facing errors yet — SLA breach threshold in ~15 minutes\
"""

SCENARIOS: list[IncidentState] = [
    {   # ── Scenario 1: DB connection pressure ─────────────────────────────
        "alert_id": "INC-001",
        "alert_message": (
            "WARNING: Database connection pool under pressure on payments-service. "
            "HikariPool-1 utilization at 91%, wait time averaging 8,000ms. "
            "503 error rate at 8% on /api/checkout and rising."
        ),
        "service_name": "payments-service",
        "environment": "prod",
        "raw_logs": _INC001_LOGS,
        "error_patterns": [], "anomalies": [], "log_summary": "",
        "relevant_runbooks": [], "past_incidents": [],
        "affected_services": [], "estimated_users_impacted": 0, "blast_radius": "",
        "root_cause": "", "confidence_score": 0.0, "causal_chain": [],
        "remediation_steps": [], "recommended_action": "",
        "status": "open", "severity": "", "classification": "",
        "requires_human_approval": False, "human_decision": None,
        "ticket_id": None, "resolution_summary": None, "messages": [],
    },
    {   # ── Scenario 2: OOMKilled memory leak ──────────────────────────────
        "alert_id": "INC-002",
        "alert_message": (
            "CRITICAL: recommendation-service pods OOMKilled and in CrashLoopBackOff. "
            "All 3 production replicas terminated with exit code 137. "
            "java.lang.OutOfMemoryError: Java heap space. Service completely unavailable. "
            "8 restarts in the last 30 minutes."
        ),
        "service_name": "recommendation-service",
        "environment": "prod",
        "raw_logs": _INC002_LOGS,
        "error_patterns": [], "anomalies": [], "log_summary": "",
        "relevant_runbooks": [], "past_incidents": [],
        "affected_services": [], "estimated_users_impacted": 0, "blast_radius": "",
        "root_cause": "", "confidence_score": 0.0, "causal_chain": [],
        "remediation_steps": [], "recommended_action": "",
        "status": "open", "severity": "", "classification": "",
        "requires_human_approval": False, "human_decision": None,
        "ticket_id": None, "resolution_summary": None, "messages": [],
    },
    {   # ── Scenario 3: Sustained high CPU ─────────────────────────────────
        "alert_id": "INC-003",
        "alert_message": (
            "WARNING: Sustained high CPU on data-pipeline service — 94% for 8 consecutive minutes. "
            "Processing throughput degraded by 73% (15,000 rec/s → 3,200 rec/s). "
            "HPA scale-out triggered but not resolving. No user-facing errors yet."
        ),
        "service_name": "data-pipeline",
        "environment": "staging",
        "raw_logs": _INC003_LOGS,
        "error_patterns": [], "anomalies": [], "log_summary": "",
        "relevant_runbooks": [], "past_incidents": [],
        "affected_services": [], "estimated_users_impacted": 0, "blast_radius": "",
        "root_cause": "", "confidence_score": 0.0, "causal_chain": [],
        "remediation_steps": [], "recommended_action": "",
        "status": "open", "severity": "", "classification": "",
        "requires_human_approval": False, "human_decision": None,
        "ticket_id": None, "resolution_summary": None, "messages": [],
    },
]


# ── Human checkpoint (no LLM — pure logic + stdin) ─────────────────────────

def human_checkpoint_node(state: IncidentState) -> dict:
    steps = state["remediation_steps"]
    sep = "─" * 62

    print(f"\n{sep}")
    print("  ⚠  HUMAN APPROVAL REQUIRED")
    print(sep)
    print(f"  Incident       : {state['alert_id']}")
    print(f"  Service        : {state['service_name']} ({state['environment']})")
    print(f"  Classification : {state['classification']}")
    print(f"  Severity       : {state['severity'].upper()}")
    print(f"  Users at risk  : {state['estimated_users_impacted']:,}")
    print()
    _wrap_print("  Root Cause", state["root_cause"])
    print(f"  Confidence     : {state['confidence_score']:.0%}")
    print()
    _wrap_print("  Blast Radius", state["blast_radius"])
    print()
    print("  Remediation Steps:")
    for i, s in enumerate(steps, 1):
        risk = s.get("risk", "?").upper()
        eta = s.get("estimated_time", "?")
        print(f"    {i}. [{risk} | {eta}]")
        for ln in textwrap.wrap(s.get("step", ""), width=70):
            print(f"       {ln}")
    print()
    _wrap_print("  Recommended", state["recommended_action"])
    print()

    while True:
        decision = input("  Execute recommended fix or Escalate? (execute/escalate): ").strip().lower()
        if decision in ("execute", "escalate"):
            break
        print("  Please enter 'execute' or 'escalate'.")

    print(f"\n[HUMAN CHECKPOINT] Decision recorded: {decision.upper()}")
    return {
        "human_decision": decision,
        "messages": [f"[HUMAN CHECKPOINT] On-call decision: {decision.upper()}"],
    }


# ── Routing and helpers ─────────────────────────────────────────────────────

def _route_after_remediation(state: IncidentState) -> str:
    return "human_checkpoint" if state["requires_human_approval"] else "ticket_creator"


def _wrap_print(label: str, text: str, width: int = 55) -> None:
    lines = textwrap.wrap(text, width=width)
    if not lines:
        print(f"{label:<18}: —")
        return
    print(f"{label:<18}: {lines[0]}")
    for ln in lines[1:]:
        print(f"{'':21}{ln}")


# ── Graph builder ───────────────────────────────────────────────────────────

def build_graph():
    workflow = StateGraph(IncidentState)

    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("log_analyzer", log_analyzer_node)
    workflow.add_node("runbook_rag", runbook_rag_node)
    workflow.add_node("impact_assessor", impact_assessor_node)
    workflow.add_node("root_cause", root_cause_node)
    workflow.add_node("remediation_planner", remediation_planner_node)
    workflow.add_node("human_checkpoint", human_checkpoint_node)
    workflow.add_node("ticket_creator", ticket_creator_node)

    workflow.set_entry_point("supervisor")

    # Parallel fan-out
    workflow.add_edge("supervisor", "log_analyzer")
    workflow.add_edge("supervisor", "runbook_rag")
    workflow.add_edge("supervisor", "impact_assessor")

    # Parallel fan-in → reasoning chain
    workflow.add_edge("log_analyzer", "root_cause")
    workflow.add_edge("runbook_rag", "root_cause")
    workflow.add_edge("impact_assessor", "root_cause")

    workflow.add_edge("root_cause", "remediation_planner")

    # Conditional: critical severity or low confidence → human checkpoint
    workflow.add_conditional_edges(
        "remediation_planner",
        _route_after_remediation,
        {"human_checkpoint": "human_checkpoint", "ticket_creator": "ticket_creator"},
    )

    workflow.add_edge("human_checkpoint", "ticket_creator")
    workflow.add_edge("ticket_creator", END)

    return workflow.compile()


# ── Final incident report ───────────────────────────────────────────────────

def _print_incident_report(s: IncidentState) -> None:
    W = 64
    bar = "━" * W

    print(f"\n╔{'═' * W}╗")
    print(f"║{'  INCIDENT REPORT — MultiAgent SRE':^{W}}║")
    print(f"╚{'═' * W}╝")

    print(f"\n  Ticket ID      : {s['ticket_id'] or 'N/A'}")
    print(f"  Alert          : {s['alert_id']}")
    print(f"  Service        : {s['service_name']} ({s['environment']})")
    print(f"  Status         : {s['status'].upper()}")
    print(f"  Severity       : {s['severity'].upper()}")
    print(f"  Classification : {s['classification']}")
    print(f"  Human Decision : {(s.get('human_decision') or 'N/A — auto path').upper()}")

    print(f"\n{bar}")
    print("  IMPACT")
    print(bar)
    print(f"  Users Affected : {s['estimated_users_impacted']:,}")
    _wrap_print("  Blast Radius", s["blast_radius"])
    print(f"  Affected Svcs  : {', '.join(s['affected_services'])}")

    print(f"\n{bar}")
    print(f"  ROOT CAUSE  (confidence: {s['confidence_score']:.0%})")
    print(bar)
    _wrap_print("  Cause", s["root_cause"])
    if s["causal_chain"]:
        print()
        print("  Causal Chain:")
        for i, step in enumerate(s["causal_chain"], 1):
            for j, ln in enumerate(textwrap.wrap(step, width=60)):
                if j == 0:
                    print(f"    {i}. {ln}")
                else:
                    print(f"       {ln}")

    print(f"\n{bar}")
    print(f"  REMEDIATION  ({len(s['remediation_steps'])} step(s))")
    print(bar)
    _wrap_print("  Recommended", s["recommended_action"])
    if s["remediation_steps"]:
        print()
        for i, step in enumerate(s["remediation_steps"], 1):
            risk = step.get("risk", "?").upper()
            eta = step.get("estimated_time", "?")
            print(f"    {i}. [{risk} | {eta}]")
            for ln in textwrap.wrap(step.get("step", ""), width=60):
                print(f"       {ln}")

    print(f"\n{bar}")
    print(f"  AGENT PIPELINE  ({len(s['messages'])} message(s))")
    print(bar)
    for msg in s["messages"]:
        for j, ln in enumerate(textwrap.wrap(msg, width=60)):
            prefix = "  • " if j == 0 else "    "
            print(f"{prefix}{ln}")

    print()


# ── Scenario selection ──────────────────────────────────────────────────────

def _select_scenario() -> IncidentState:
    print("  Select a scenario:\n")
    print("  [1] INC-001 — DB connection pool pressure")
    print("      payments-service | prod | ~HIGH severity | auto path")
    print()
    print("  [2] INC-002 — OOMKilled memory leak, CrashLoopBackOff")
    print("      recommendation-service | prod | CRITICAL | ⚠ human checkpoint")
    print()
    print("  [3] INC-003 — Sustained high CPU at 94% for 8 minutes")
    print("      data-pipeline | staging | ~MEDIUM severity | auto path")
    print()
    while True:
        choice = input("  Enter scenario number (1/2/3): ").strip()
        if choice in ("1", "2", "3"):
            return SCENARIOS[int(choice) - 1]
        print("  Please enter 1, 2, or 3.\n")


# ── Entry point ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("═" * 66)
    print("  MultiAgent SRE — AI-Powered Incident Response Pipeline")
    print("═" * 66 + "\n")

    state = _select_scenario()

    start_trace(
        alert_id=state["alert_id"],
        service_name=state["service_name"],
        alert_message=state["alert_message"],
    )

    print(f"\n{'─' * 66}")
    print(f"  Starting pipeline for {state['alert_id']}")
    print(f"  Service  : {state['service_name']} ({state['environment']})")
    print(f"  Alert    : {state['alert_message'][:80]}...")
    print(f"{'─' * 66}\n")

    app = build_graph()
    final_state = app.invoke(state)

    flush_trace()

    _print_incident_report(final_state)
