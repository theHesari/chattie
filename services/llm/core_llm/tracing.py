from langchain_core.runnables import RunnableConfig

_handler = None


def _get_handler():
    global _handler
    if _handler is None:
        from langfuse.langchain import CallbackHandler
        _handler = CallbackHandler()
    return _handler


def run_config(
    session_id: str,
    run_name: str,
    user_id: str | None = None,
    tags: list[str] | None = None,
) -> RunnableConfig:
    """Graph config shared by every endpoint: thread memory + Langfuse tracing."""
    return {
        "configurable": {"thread_id": session_id},
        "callbacks": [_get_handler()],
        "run_name": run_name,
        "metadata": {
            "langfuse_session_id": session_id,
            "langfuse_user_id": user_id or "anonymous",
            "langfuse_tags": ["api", *(tags or [])],
        },
    }
