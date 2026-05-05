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

_SYSTEM = """You are an SRE blast-radius and impact assessment expert. Given an incident on a production service, estimate:

1. affected_services: List of service names likely impacted (include the primary service and plausible downstream dependents based on its name)
2. estimated_users_impacted: Integer — your best estimate of concurrent users affected right now
3. blast_radius: A single concise string describing the scope of impact (e.g., "All payment transactions on prod — checkout flow fully degraded")

Base your assessment on the service name, environment, and alert details. For a payment service in prod, assume high user counts.

Return ONLY valid JSON — no markdown, no explanation:
{
  "affected_services": ["service-a", "service-b"],
  "estimated_users_impacted": 12345,
  "blast_radius": "..."
}"""


def _parse_json(content: str) -> dict:
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise


def impact_assessor_node(state: IncidentState) -> dict:
    t0 = time.time()
    span = agent_span("impact_assessor", {
        "service_name": state["service_name"],
        "environment": state["environment"],
        "alert_message": state["alert_message"][:200],
    })

    response = llm.invoke([
        SystemMessage(content=_SYSTEM),
        HumanMessage(content=(
            f"Service: {state['service_name']}\n"
            f"Environment: {state['environment']}\n"
            f"Alert: {state['alert_message']}"
        )),
    ])

    try:
        result = _parse_json(response.content)
    except Exception:
        result = {
            "affected_services": [state["service_name"]],
            "estimated_users_impacted": 0,
            "blast_radius": "Unknown — parse error",
        }

    affected_services = result.get("affected_services", [state["service_name"]])
    estimated_users = result.get("estimated_users_impacted", 0)
    blast_radius = result.get("blast_radius", "")

    print(
        f"[IMPACT ASSESSOR] ~{estimated_users:,} users impacted | "
        f"{len(affected_services)} service(s) affected\n"
        f"                  blast_radius: {blast_radius}"
    )

    output = {
        "affected_services": affected_services,
        "estimated_users_impacted": estimated_users,
        "blast_radius": blast_radius,
        "messages": [
            f"[IMPACT ASSESSOR] Estimated {estimated_users:,} users impacted across "
            f"{len(affected_services)} service(s) — {blast_radius}"
        ],
    }
    span.update(
        output={
            "estimated_users_impacted": estimated_users,
            "affected_services_count": len(affected_services),
            "blast_radius": blast_radius[:200],
        },
        metadata={"duration_ms": int((time.time() - t0) * 1000)},
    )
    span.end()
    return output
