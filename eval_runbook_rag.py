"""
Runbook RAG retrieval accuracy evaluation.
Runs 5 alert messages through search_runbooks() and checks
whether the top-1 retrieved runbook matches the expected one.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.tools.runbook_loader import search_runbooks

# (alert_message, expected_top_runbook_filename_stem)
TEST_CASES = [
    (
        "CRITICAL: HikariPool connection pool exhausted on payments-service. "
        "Active connections at max (50/50). Queries timing out with "
        "HikariPool-1 connection is not available. Request queue depth: 847.",
        "db_connection_exhaustion",
    ),
    (
        "ALERT: recommendation-service pod restarting repeatedly — "
        "OOMKilled, CrashLoopBackOff. Container exceeded memory limit of 512Mi. "
        "kubectl get pods shows 7 restarts in the last 10 minutes.",
        "memory_leak",
    ),
    (
        "WARNING: data-pipeline node CPU usage at 94% for the last 8 minutes. "
        "Load average: 15.2. Slow response times detected on all endpoints.",
        "high_cpu",
    ),
    (
        "ALERT: Redis NOAUTH Authentication required errors spiking. "
        "Cache hit rate dropped from 91% to 12%. Latency p99 jumped to 4200ms. "
        "Connection timeouts to Redis cluster on port 6379.",
        "redis_timeout",
    ),
    (
        "CRITICAL: Deployment of user-service v2.4.1 failing. "
        "Rollout stuck: 0/3 new pods ready. ImagePullBackOff on 2 replicas, "
        "CrashLoopBackOff on 1. Previous stable version v2.4.0 still running on 1 pod.",
        "deployment_failure",
    ),
]

RUNBOOK_DISPLAY = {
    "db_connection_exhaustion": "Db Connection Exhaustion",
    "memory_leak":              "Memory Leak",
    "high_cpu":                 "High Cpu",
    "redis_timeout":            "Redis Timeout",
    "deployment_failure":       "Deployment Failure",
    "pod_crashloop":            "Pod Crashloop",
    "disk_space":               "Disk Space",
    "network_latency":          "Network Latency",
}


def stem_from_title(title: str) -> str:
    """Convert a ChromaDB title back to a filename stem for comparison."""
    return title.lower().replace(" ", "_")


def run_evaluation():
    print("\n" + "=" * 70)
    print("  RUNBOOK RAG — RETRIEVAL ACCURACY EVALUATION")
    print("=" * 70)

    correct = 0

    for i, (alert, expected_stem) in enumerate(TEST_CASES, 1):
        results = search_runbooks(alert, n_results=3)
        top = results[0] if results else None

        top_stem   = stem_from_title(top["title"]) if top else "none"
        top_title  = top["title"] if top else "N/A"
        top_score  = top["similarity_score"] if top else 0.0
        is_correct = top_stem == expected_stem
        correct   += int(is_correct)

        status = "✓ CORRECT" if is_correct else "✗ WRONG  "
        expected_display = RUNBOOK_DISPLAY.get(expected_stem, expected_stem)

        print(f"\n  Test {i}: {status}")
        print(f"    Alert     : {alert[:80]}...")
        print(f"    Expected  : {expected_display}")
        print(f"    Retrieved : {top_title}  (similarity={top_score:.4f})")
        if not is_correct:
            print(f"    All top-3 : {[r['title'] for r in results]}")

    accuracy = correct / len(TEST_CASES) * 100
    print("\n" + "=" * 70)
    print(f"  RESULT: {correct}/{len(TEST_CASES)} correct  →  Retrieval Accuracy: {accuracy:.0f}%")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    run_evaluation()
