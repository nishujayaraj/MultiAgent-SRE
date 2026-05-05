import os

from dotenv import load_dotenv

load_dotenv()

_langfuse = None
_current_trace = None  # top-level LangfuseAgent observation for the active incident


class _NoopSpan:
    """Returned when Langfuse is not configured — every call silently does nothing."""
    def update(self, **kwargs) -> None:
        pass

    def end(self, **kwargs) -> None:
        pass


def _init():
    global _langfuse
    try:
        from langfuse import Langfuse
        pk = os.getenv("LANGFUSE_PUBLIC_KEY")
        sk = os.getenv("LANGFUSE_SECRET_KEY")
        if pk and sk:
            _langfuse = Langfuse(
                public_key=pk,
                secret_key=sk,
                host=os.getenv("LANGFUSE_BASE_URL", os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")),
            )
    except Exception:
        _langfuse = None


_init()


def start_trace(alert_id: str, service_name: str, alert_message: str) -> None:
    """Open one top-level trace per incident (Langfuse v4 API). Call before graph.invoke()."""
    global _current_trace
    if _langfuse is None:
        return
    # In Langfuse v4, start_observation() on the client creates the root trace node
    _current_trace = _langfuse.start_observation(
        name=alert_id,
        as_type="agent",
        input={
            "alert_id": alert_id,
            "service_name": service_name,
            "alert_message": alert_message[:300],
        },
        metadata={"project": "MultiAgent-SRE"},
    )


def agent_span(name: str, inputs: dict):
    """Create a child span on the active trace. Returns _NoopSpan when tracing is off."""
    if _langfuse is None or _current_trace is None:
        return _NoopSpan()
    # Child spans are created by calling start_observation on the parent trace object
    return _current_trace.start_observation(
        name=name,
        as_type="span",
        input=inputs,
    )


def flush_trace() -> None:
    """End the root trace and flush all pending events to Langfuse."""
    global _current_trace
    if _current_trace is not None:
        _current_trace.end()
    if _langfuse is not None:
        _langfuse.flush()
    _current_trace = None
