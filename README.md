# MultiAgent-SRE

> An AI system that handles the first 15 minutes of any production incident, so you don't have to do it half-asleep at 3am.

---

## The Problem It Solves

Picture this: it's 3am, PagerDuty wakes you up. You open five tabs — Datadog, Kubernetes dashboard, Jira, Confluence, Slack — and spend the next 15 minutes just trying to understand *what is happening*. Is the database down or just slow? Which services are affected? What was the fix last time this happened? By the time you've connected the dots, real users have already had a bad experience.

Here's the thing, the actual fix usually takes only 5 minutes. The *diagnosis* is what eats your time.

**MultiAgent-SRE automates that diagnosis.** The moment an alert fires, a team of AI agents springs into action: one reads your logs, one searches your runbook library, one estimates how many users are affected. They work simultaneously, share their findings, and hand you a complete incident brief. Root cause identified, remediation steps ranked by risk, Jira ticket drafted. You arrive at a decision, not a blank screen.

---

## How It Works

Here's the journey an alert takes through the system:

1. **Alert comes in** → The Supervisor agent reads it, classifies the incident type, and sets the severity level
2. **Three agents work in parallel** → Log Analyzer digs through raw logs, Runbook RAG searches your runbook library using semantic search, Impact Assessor estimates affected users and services
3. **Root Cause synthesized** → A dedicated agent takes all three outputs and builds a causal chain with a confidence score
4. **Remediation planned** → Another agent generates 3–5 prioritized steps with real commands (kubectl, psql, etc.) and risk levels
5. **Human decision point** → If the incident is CRITICAL or the AI isn't confident enough, it pauses and asks you: *execute or escalate?*
6. **Ticket created** → A structured Jira ticket with the full incident report is generated automatically

Total time from alert to brief: **under 60 seconds.**

---

## Architecture

The pipeline is a LangGraph `StateGraph` — not a sequential chain, but a real graph with parallel branches and conditional routing.

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
                         (all 3 merge here)
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
                   |  3-5 ranked steps   |
                   |  risk + time per step|
                   +---------+-----------+
                             |
            +----------------+----------------+
            |  CRITICAL severity              |
            |  OR confidence < 70%            |  (otherwise auto)
            v                                 v
   +------------------+             +------------------+
   | HUMAN CHECKPOINT |             |  TICKET CREATOR  |
   | execute/escalate +------------>|  Jira + summary  |
   +------------------+             +---------+--------+
                                              |
                                              v
                                            [END]
```

The three middle agents (Log Analyzer, Runbook RAG, Impact Assessor) run **in parallel**, LangGraph fans out after the Supervisor and fans back in before Root Cause. This cuts diagnosis time from ~15s sequential to ~5s.

---

## The Agents

Each agent has one job. It reads what it needs from shared state, does its work, and writes its output back.

| Agent | What it does | Uses LLM? | Key outputs |
|---|---|---|---|
| **Supervisor** | Reads the alert, picks the incident type, sets severity | Yes | `classification`, `severity` |
| **Log Analyzer** | Finds error patterns and anomalies in raw logs | Yes | `error_patterns`, `anomalies`, `log_summary` |
| **Runbook RAG** | Semantic search over your runbook library (ChromaDB) | No | `relevant_runbooks` |
| **Impact Assessor** | Estimates affected services and user count | Yes | `blast_radius`, `estimated_users_impacted` |
| **Root Cause** | Synthesizes everything into a causal chain + confidence score | Yes | `root_cause`, `confidence_score`, `causal_chain` |
| **Remediation Planner** | Generates ranked steps with real commands and risk levels | Yes | `remediation_steps`, `recommended_action` |
| **Human Checkpoint** | Asks the on-call engineer to decide: execute or escalate | No (stdin) | `human_decision` |
| **Ticket Creator** | Writes a structured Jira incident ticket | Yes | `ticket_id`, `resolution_summary` |

---

## Tech Stack

| What | Tool | Why this one |
|---|---|---|
| LLM | Claude Haiku 4.5 (`claude-haiku-4-5-20251001`) | Fast and cheap — important when every second of an incident counts |
| Agent Orchestration | LangGraph `StateGraph` | Handles parallel execution and conditional routing out of the box |
| LLM Client | `langchain-anthropic` | Clean message formatting, easy to swap models |
| Runbook Search | ChromaDB + `all-MiniLM-L6-v2` | Runs locally, no external service needed, persists between runs |
| Observability | Langfuse | See exactly what each agent received, returned, and how long it took |
| State | Python `TypedDict` + `Annotated` | Type-safe, catches mistakes at runtime before they cause silent bugs |
| Config | `python-dotenv` | Secrets in `.env`, never hardcoded |

---

## Getting Started

You only need an Anthropic API key to run this. Langfuse is optional.

```bash
# 1. Clone the repo
git clone https://github.com/nishujayaraj/MultiAgent-SRE.git
cd MultiAgent-SRE

# 2. Create a virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set up your API key
cp .env.example .env
# Open .env and add your ANTHROPIC_API_KEY
# Langfuse keys are optional — the system works fine without them

# 5. Run it
python main.py
```

On first run, ChromaDB will embed the 8 runbook files (takes ~5 seconds). Every run after that loads the saved collection instantly.

---

## Try It — Three Built-in Scenarios

When you run `python main.py`, you pick one of three pre-built incidents:

```
  [1] INC-001 — DB connection pool pressure
      payments-service | prod | HIGH severity | no human checkpoint

  [2] INC-002 — OOMKilled memory leak, CrashLoopBackOff
      recommendation-service | prod | CRITICAL | ⚠ asks for your decision

  [3] INC-003 — Sustained high CPU at 94% for 8 minutes
      data-pipeline | staging | MEDIUM severity | no human checkpoint
```

Scenario 2 is the interesting one, it fires the human checkpoint, shows you the full brief, and waits for you to type `execute` or `escalate`.

### Sample output (Scenario 1)

```
[SUPERVISOR]       classification=db_connection | severity=high
[IMPACT ASSESSOR]  ~45,000 users impacted | 4 service(s) affected
[RUNBOOK RAG]      Matched: Db Connection Exhaustion, High Cpu, Redis Timeout
[LOG ANALYZER]     8 error patterns, 5 anomalies found
[ROOT CAUSE]       confidence=78% | auto path (no human needed)
[REMEDIATION]      5 steps planned
[TICKET]           Created INC-001-1778003021

╔════════════════════════════════════════════════════════════════╗
║              INCIDENT REPORT — MultiAgent SRE                  ║
╚════════════════════════════════════════════════════════════════╝

  Ticket ID      : INC-001-1778003021
  Service        : payments-service (prod)
  Severity       : HIGH
  Classification : db_connection
  Human Decision : N/A — AUTO PATH

  Root Cause     : HikariPool exhausted due to idle-in-transaction
                   connections piling up after a traffic spike.

  Recommended    : SELECT pg_terminate_backend(pid) FROM
                   pg_stat_activity WHERE state = 'idle in transaction'
                   AND now() - query_start > interval '2 minutes';
```

---

## Why LangGraph and Not Just a Script?

You could wire these agents together with plain Python, call one function, pass the result to the next, done. But this project needs three things a script can't easily give you:

**Parallel execution.** Log analysis, runbook search, and impact assessment have nothing to do with each other, there's no reason to run them one at a time. LangGraph fans them out after the Supervisor and waits for all three before continuing. With a script, you'd have to manage `asyncio` or threads yourself.

**Conditional routing.** The human checkpoint only fires under certain conditions (CRITICAL severity or low confidence). In LangGraph, this is one `add_conditional_edges` call. In a script, it's `if/else` branches that get tangled as the system grows.

**Safe parallel state merges.** All three parallel agents append messages to the same shared list. Without a reducer, the last writer would silently overwrite the others. LangGraph's `Annotated[List[str], operator.add]` annotation tells the runtime to concatenate instead no coordination code needed.

**Visibility.** The graph is declared explicitly: nodes, edges, conditions. You can see the full pipeline at a glance, add a new agent by adding a node and two edges, and test any agent in isolation.

---

## Project Structure

```
MultiAgent-SRE/
├── src/
│   ├── agents/
│   │   ├── supervisor.py           # Classifies alert, sets severity
│   │   ├── log_analyzer.py         # Extracts error patterns from logs
│   │   ├── runbook_rag.py          # Searches runbooks via ChromaDB
│   │   ├── impact_assessor.py      # Estimates blast radius + user impact
│   │   ├── root_cause.py           # Builds causal chain + confidence score
│   │   ├── remediation_planner.py  # Generates ranked remediation steps
│   │   └── ticket_creator.py       # Writes the Jira incident ticket
│   ├── state/
│   │   └── incident_state.py       # Shared TypedDict state + Enums
│   ├── tools/
│   │   ├── mock_tools.py           # Stub tools: kubectl, Jira, PagerDuty
│   │   ├── runbook_loader.py       # Embeds runbooks into ChromaDB
│   │   └── observability.py        # Langfuse trace/span wrappers
│   └── data/runbooks/              # 8 realistic SRE runbook .txt files
├── main.py                         # Graph definition + scenario runner
├── requirements.txt
├── .env.example
└── README.md
```

---

## Author

Built by **Nischitha S Jayaraja**
[LinkedIn](https://www.linkedin.com/in/nischithasjayaraja/) · [GitHub](https://github.com/nishujayaraj)
