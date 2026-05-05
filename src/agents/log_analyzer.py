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

_SYSTEM = """You are an expert SRE log analyst. Analyze the provided service logs and extract:

1. error_patterns: 5–10 distinct error message patterns (the repeating error signatures, not individual lines)
2. anomalies: 3–5 anomalous behaviors or conditions observed across the logs
3. log_summary: A plain-English paragraph (3–5 sentences) summarizing what the logs reveal about the incident

Return ONLY valid JSON — no markdown, no explanation:
{
  "error_patterns": ["pattern1", "pattern2"],
  "anomalies": ["anomaly1", "anomaly2"],
  "log_summary": "..."
}"""


def _parse_json(content: str) -> dict:
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise


def log_analyzer_node(state: IncidentState) -> dict:
    t0 = time.time()
    span = agent_span("log_analyzer", {
        "service_name": state["service_name"],
        "log_chars": len(state["raw_logs"]),
        "alert_message": state["alert_message"][:200],
    })

    response = llm.invoke([
        SystemMessage(content=_SYSTEM),
        HumanMessage(content=(
            f"Service: {state['service_name']}\n"
            f"Alert: {state['alert_message']}\n\n"
            f"Logs:\n{state['raw_logs']}"
        )),
    ])

    try:
        result = _parse_json(response.content)
    except Exception:
        result = {
            "error_patterns": ["parse error — raw LLM response stored in log_summary"],
            "anomalies": [],
            "log_summary": response.content,
        }

    error_patterns = result.get("error_patterns", [])
    anomalies = result.get("anomalies", [])
    log_summary = result.get("log_summary", "")

    print(
        f"[LOG ANALYZER] Found {len(error_patterns)} error pattern(s) "
        f"and {len(anomalies)} anomaly(s) in {state['service_name']} logs"
    )

    output = {
        "error_patterns": error_patterns,
        "anomalies": anomalies,
        "log_summary": log_summary,
        "messages": [
            f"[LOG ANALYZER] Extracted {len(error_patterns)} error patterns "
            f"and {len(anomalies)} anomalies from {state['service_name']} logs"
        ],
    }
    span.update(
        output={
            "error_patterns_count": len(error_patterns),
            "anomalies_count": len(anomalies),
            "log_summary": log_summary[:300],
        },
        metadata={"duration_ms": int((time.time() - t0) * 1000)},
    )
    span.end()
    return output
