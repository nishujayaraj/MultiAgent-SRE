import operator
from enum import Enum
from typing import Annotated, List, Optional, TypedDict


class Severity(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class IncidentStatus(str, Enum):
    investigating = "investigating"
    root_cause_identified = "root_cause_identified"
    remediating = "remediating"
    resolved = "resolved"
    escalated = "escalated"


class IncidentState(TypedDict):
    # Alert input
    alert_id: str
    alert_message: str
    service_name: str
    environment: str
    raw_logs: str

    # Log Analyzer output
    error_patterns: List[str]
    anomalies: List[str]
    log_summary: str

    # Runbook RAG output
    relevant_runbooks: List[dict]
    past_incidents: List[str]

    # Impact output
    affected_services: List[str]
    estimated_users_impacted: int
    blast_radius: str

    # Root Cause output
    root_cause: str
    confidence_score: float
    causal_chain: List[str]

    # Remediation output
    remediation_steps: List[dict]
    recommended_action: str

    # Control
    status: str
    severity: str
    classification: str
    requires_human_approval: bool
    human_decision: Optional[str]

    # Final
    ticket_id: Optional[str]
    resolution_summary: Optional[str]

    # Messages — reducer concatenates lists from parallel branches
    messages: Annotated[List[str], operator.add]
