import logging

from lerai.cplex_agent.graph import get_compiled_graph
from lerai.leroy_overrides_writer import (
    _get_api,
    _extract_thread_id,
    _extract_last_ai_markdown,
    _send_threaded_webex_reply,
)

logger = logging.getLogger(__name__)


def run_cplex_agent(user_question: str, webex_message=None, webex_api=None) -> str | None:
    app = get_compiled_graph()
    api = _get_api(webex_api)
    thread_id = _extract_thread_id(webex_message, webex_api=api) if webex_message is not None else "local-cli"
    config = {"configurable": {"thread_id": thread_id}}

    logger.info("Invoking CPLEX agent", extra={"thread_id": thread_id, "question": user_question})

    graph_result = app.invoke({"messages": [("user", user_question)]}, config=config)
    final_response = _extract_last_ai_markdown(graph_result)

    if webex_message is not None:
        _send_threaded_webex_reply(final_response, thread_id, webex_message, api)
        return None

    return final_response
