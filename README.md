# MultiAgent-SRE

An AI-powered incident response pipeline that replaces the 3am pager dread with a coordinated multi-agent system — from raw alert to Jira ticket in under 60 seconds.

## The Problem

At 3am, a PagerDuty alert fires. A human engineer wakes up, opens five browser tabs — Datadog, Kubernetes dashboard, Jira, Confluence runbooks, and Slack — and spends the first 15 minutes just understanding what is happening. Is the database down or just slow? Which services are affected? What did the runbook say to do last time this happened? Every minute of confusion is thousands of failed transactions, frustrated users, and lost revenue. The cognitive load of context-switching between tools while half-asleep is where most of the incident resolution time goes — not the actual fix.

MultiAgent-SRE automates the *diagnostic and planning* layer of incident response. When an alert fires, a graph of specialized AI agents runs in parallel: one reads the logs, one searches the runbook library, one estimates the blast radius. They synthesize their findings into a root cause with a confidence score, generate a prioritized remediation plan with risk levels and kubectl/psql commands, and route to a human checkpoint only when the severity or uncertainty demands it. The on-call engineer arrives at a fully formed incident brief — not a blank screen.

---

## Architecture

```
                        +------------------+
                        |    SUPERVISOR    |
                        |  classifies alert|
                        |  sets severity   |
                        +--------+---------+
                                 |
             +-------------------+-------------------+
             |                   |                   |
             v                   v                   v
   +---------------+   +--------------+   +------------------+
   | LOG ANALYZER  |   | RUNBOOK RAG  |   | IMPACT ASSESSOR  |
   | error_patterns|   |  ChromaDB    |   | affected_services|
   | anomalies     |   |  vector      |   | users_impacted   |
   | log_summary   |   |  search      |   | blast_radius     |
   +-------+-------+   +------+-------+   +---------+--------+
           |                  |                     |
           +------------------+---------------------+
                              | (fan-in)
                              v
                     +------------------+
                     |   ROOT CAUSE     |
                     |  causal_chain    |
                     |  confidence_score|
                     +--------+---------+
                              |
                              v
                   +---------------------+
                   | REMEDIATION PLANNER |
                   |  3-5 steps          |
                   |  risk + eta per step|
                   +---------+-----------+
                             |
            +----------------+----------------+
            | severity=CRITICAL               |
            | OR confidence < 0.7             | (else: auto)
            v                                 v
   +------------------+             +------------------+
   | HUMAN CHECKPOINT |             |  TICKET CREATOR  |
   |  stdin decision  +------------>|  Jira + summary  |
   |  execute/escalate|             |  mock_tools call |
   +------------------+             +---------+--------+
                                              |
                                              v
                                            [END]
```

---

## Agents

| Agent | Inputs from State | LLM | Outputs to State |
|---|---|---|---|
| **Supervisor** | `alert_message`, `service_name`, `environment` | Yes | `classification`, `severity`, `status` |
| **Log Analyzer** | `raw_logs`, `alert_message` | Yes | `error_patterns`, `anomalies`, `log_summary` |
| **Runbook RAG** | `alert_message` | No (ChromaDB) | `relevant_runbooks` |
| **Impact Assessor** | `service_name`, `environment`, `alert_message` | Yes | `affected_services`, `estimated_users_impacted`, `blast_radius` |
| **Root Cause** | `log_summary`, `error_patterns`, `relevant_runbooks`, `blast_radius` | Yes | `root_cause`, `confidence_score`, `causal_chain` |
| **Remediation Planner** | `root_cause`, `relevant_runbooks`, `severity` | Yes | `remediation_steps`, `recommended_action` |
| **Human Checkpoint** | Full state | No (stdin) | `human_decision` |
| **Ticket Creator** | Full incident context | Yes | `ticket_id`, `resolution_summary` |

---

## Tech Stack

| Component | Tool / Library | Why |
|---|---|---|
| LLM | `claude-haiku-4-5-20251001` via Anthropic | Fast, cheap, strong reasoning — production SRE needs sub-second latency |
| Agent Orchestration | LangGraph `StateGraph` | Native parallel fan-out/fan-in, conditional routing, typed state |
| LLM Client | `langchain-anthropic` | Structured message formatting, clean tool integration |
| Vector Store | ChromaDB (persistent local) | Zero infrastructure — builds once from `.txt` runbooks, reuses forever |
| Embedding Model | `all-MiniLM-L6-v2` (sentence-transformers) | 80MB, fast, accurate enough for runbook similarity |
| Observability | Langfuse | Per-agent span tracing: inputs, outputs, and latency per run |
| State Schema | Python `TypedDict` + `Annotated` | Type-safe state with `operator.add` reducer for parallel message merges |
| Config | `python-dotenv` | `.env` file — zero hardcoded secrets anywhere |

---

## Quickstart

```bash
# 1. Clone
git clone https://github.com/yourusername/MultiAgent-SRE.git
cd MultiAgent-SRE

# 2. Create virtual environment
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure secrets
cp .env.example .env
# Edit .env — only ANTHROPIC_API_KEY is required.
# Langfuse keys are optional (tracing is silently skipped if not set).

# 5. Run
python main.py
```

You will be prompted to choose a scenario. On first run, ChromaDB will embed the 8 runbook files (~5 seconds). Subsequent runs load the persisted collection instantly.

---

## Sample Output (Scenario 1 — INC-001)

```
══════════════════════════════════════════════════════════════════
  MultiAgent SRE — AI-Powered Incident Response Pipeline
══════════════════════════════════════════════════════════════════

  Select a scenario:

  [1] INC-001 — DB connection pool pressure
      payments-service | prod | ~HIGH severity | auto path

  [2] INC-002 — OOMKilled memory leak, CrashLoopBackOff
      recommendation-service | prod | CRITICAL | ⚠ human checkpoint

  [3] INC-003 — Sustained high CPU at 94% for 8 minutes
      data-pipeline | staging | ~MEDIUM severity | auto path

  Enter scenario number (1/2/3): 1

[SUPERVISOR]   alert_id=INC-001 | classification=db_connection | severity=high
[IMPACT ASSESSOR] ~18,000 users impacted | 4 service(s) affected
[RUNBOOK RAG]  Matched 3 runbook(s): Db Connection Exhaustion, Network Latency, Disk Space
[LOG ANALYZER] Found 8 error pattern(s) and 4 anomaly(s) in payments-service logs
[ROOT CAUSE]   confidence=91% | human_approval=NO
               HikariCP pool exhaustion caused by idle-in-transaction connections...
[REMEDIATION]  5 step(s) planned | human_approval=NO
[TOOL]         Created Jira ticket INC-12345: [HIGH] payments-service: db_connection
[TICKET]       Created INC-001-1778003021 for INC-001

╔════════════════════════════════════════════════════════════════╗
║           INCIDENT REPORT — MultiAgent SRE                     ║
╚════════════════════════════════════════════════════════════════╝

  Ticket ID      : INC-001-1778003021
  Alert          : INC-001
  Service        : payments-service (prod)
  Status         : RESOLVED
  Severity       : HIGH
  Classification : db_connection
  Human Decision : N/A — AUTO PATH
  ...
```

---

## Why LangGraph?

**StateGraph over sequential chains.** A sequential LangChain chain would force every agent to wait for the previous one to finish. LangGraph's `StateGraph` declares nodes and edges explicitly — the full pipeline is visible as a graph, not hidden inside nested function calls. This makes the flow testable, debuggable, and easy to extend.

**Parallel fan-out/fan-in.** After the Supervisor classifies the alert, three agents run simultaneously: Log Analyzer reads the raw logs, Runbook RAG searches ChromaDB, and Impact Assessor estimates blast radius. In LangGraph this is just three `add_edge` calls from one source node. The runtime waits for all three to complete before Root Cause runs — reducing wall-clock time from ~15s sequential to ~5s parallel.

**Conditional edges.** The human checkpoint fires only when `requires_human_approval` is True — set when severity is `critical` or root cause confidence drops below 70%. This routing logic lives in a single `add_conditional_edges` call, not scattered across agent code. Changing the threshold is a one-line edit.

**State reducers.** Each parallel branch appends to the shared `messages` list independently. Without a reducer, parallel writes would overwrite each other. LangGraph's `Annotated[List[str], operator.add]` annotation tells the runtime to concatenate lists instead — all four agent messages arrive at Root Cause correctly merged, with zero extra coordination code.

**Type-safe state.** `IncidentState` as a `TypedDict` forces every field to be declared upfront. LangGraph validates keys at runtime, so a typo in an agent's return dict raises an error immediately rather than silently dropping data.

---

## Project Structure

```
MultiAgent-SRE/
├── src/
│   ├── agents/
│   │   ├── supervisor.py          # Alert classification + severity
│   │   ├── log_analyzer.py        # Error pattern extraction
│   │   ├── runbook_rag.py         # ChromaDB semantic search
│   │   ├── impact_assessor.py     # Blast radius estimation
│   │   ├── root_cause.py          # Causal chain synthesis
│   │   ├── remediation_planner.py # Step-by-step remediation
│   │   └── ticket_creator.py      # Jira ticket generation
│   ├── state/
│   │   └── incident_state.py      # TypedDict schema + Enums
│   ├── tools/
│   │   ├── mock_tools.py          # kubectl, Jira, PagerDuty stubs
│   │   ├── runbook_loader.py      # ChromaDB embed + search
│   │   └── observability.py       # Langfuse trace/span wrappers
│   └── data/runbooks/             # 8 .txt SRE runbooks
├── main.py                        # Graph definition + scenario runner
├── requirements.txt
├── .env.example
└── README.md
```

---

## Author

Built by **Nischitha S Jayaraja**
[LinkedIn](https://www.linkedin.com/in/nischithasjayaraja/) · [GitHub](https://github.com/nishujayaraj)
