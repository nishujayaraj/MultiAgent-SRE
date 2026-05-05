def execute_kubectl_rollback(service: str, version: str) -> dict:
    print(f"[TOOL] kubectl rollout undo deployment/{service} --to-revision={version}")
    return {"status": "success", "service": service, "rolled_back_to": version}


def scale_deployment(service: str, replicas: int) -> dict:
    print(f"[TOOL] kubectl scale deployment/{service} --replicas={replicas}")
    return {"status": "success", "service": service, "replicas": replicas}


def kill_process(pid: int, reason: str) -> dict:
    print(f"[TOOL] kill -9 {pid}  # reason: {reason}")
    return {"status": "success", "pid": pid, "reason": reason}


def create_jira_ticket(title: str, description: str, severity: str) -> dict:
    ticket_id = "INC-" + str(abs(hash(title)) % 100000)
    print(f"[TOOL] Created Jira ticket {ticket_id}: [{severity.upper()}] {title}")
    return {"status": "success", "ticket_id": ticket_id, "severity": severity}


def page_oncall(team: str, message: str) -> dict:
    print(f"[TOOL] PagerDuty → {team}: {message}")
    return {"status": "success", "team": team, "acknowledged": False}


def query_metrics(service: str, metric_name: str, time_range: str) -> dict:
    print(f"[TOOL] Datadog query: {metric_name}{{service:{service}}} over {time_range}")
    return {
        "status": "success",
        "service": service,
        "metric": metric_name,
        "time_range": time_range,
        "result": {"avg": 87.3, "max": 99.1, "min": 12.0},
    }
