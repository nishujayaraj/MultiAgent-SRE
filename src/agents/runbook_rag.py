import time

from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic

from src.state.incident_state import IncidentState
from src.tools.observability import agent_span
from src.tools.runbook_loader import search_runbooks

load_dotenv()
# LLM initialized per spec (not used in this agent, but kept for consistency)
llm = ChatAnthropic(model="claude-haiku-4-5-20251001", temperature=0)


def runbook_rag_node(state: IncidentState) -> dict:
    t0 = time.time()
    span = agent_span("runbook_rag", {
        "query": state["alert_message"][:200],
        "service_name": state["service_name"],
    })

    query = state["alert_message"]
    results = search_runbooks(query, n_results=3)
    titles = [r["title"] for r in results]

    print(
        f"[RUNBOOK RAG] Matched {len(results)} runbook(s) for '{state['service_name']}' alert:\n"
        + "\n".join(f"             • {t}" for t in titles)
    )

    output = {
        "relevant_runbooks": results,
        "past_incidents": [],
        "messages": [
            f"[RUNBOOK RAG] Retrieved {len(results)} relevant runbook(s): "
            + ", ".join(f"'{t}'" for t in titles)
        ],
    }
    span.update(
        output={"matched_runbooks": titles, "count": len(results)},
        metadata={"duration_ms": int((time.time() - t0) * 1000)},
    )
    span.end()
    return output
