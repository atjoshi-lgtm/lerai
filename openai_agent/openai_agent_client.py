import os


REQUIRED_AZURE_ENV_VARS = (
    "AZURE_OPENAI_URL",
    "AZURE_API_KEY",
    "AZURE_USER_ID",
    "AZURE_APP_NAME",
)

SUPPORTED_PAYLOAD_KWARGS = (
    "temperature",
    "top_p",
    "seed",
    "response_format",
    "metadata",
    "user",
    "parallel_tool_calls",
)


def _required_env(name):
    value = os.environ.get(name)
    if not value:
        raise ValueError(f"Missing required Azure OpenAI environment variable: {name}")
    return value


def _request_timeout(kwargs):
    timeout = kwargs.get("timeout", os.environ.get("AZURE_OPENAI_TIMEOUT", "30"))
    return float(timeout)


def _ssl_verify():
    return os.environ.get("AZURE_OPENAI_VERIFY_SSL", "true").lower() not in {"0", "false", "no"}


def _build_headers():
    return {
        "Content-Type": "application/json",
        "api-key": _required_env("AZURE_API_KEY"),
        "user-id": _required_env("AZURE_USER_ID"),
        "app-name": _required_env("AZURE_APP_NAME"),
    }


def _convert_function_call_to_tool_choice(function_call):
    if isinstance(function_call, dict) and "name" in function_call:
        return {"type": "function", "function": {"name": function_call["name"]}}
    return function_call


def _build_payload(messages, functions=None, model="GPT-5.2", **kwargs):
    payload = {
        "messages": messages,
        "max_completion_tokens": kwargs.get("max_completion_tokens", 6000),
    }

    if model:
        payload["model"] = model

    for param in SUPPORTED_PAYLOAD_KWARGS:
        if param in kwargs:
            payload[param] = kwargs[param]

    if functions:
        payload["tools"] = [{"type": "function", "function": fn} for fn in functions]
        tool_choice = kwargs.get("tool_choice", kwargs.get("function_call", "auto"))
        payload["tool_choice"] = _convert_function_call_to_tool_choice(tool_choice)

    return payload


def _load_requests():
    try:
        import requests
    except ModuleNotFoundError as exc:
        raise RuntimeError("Missing required dependency: requests") from exc
    return requests


def _raise_for_status(response, requests_module):
    try:
        response.raise_for_status()
    except requests_module.HTTPError as exc:
        status_code = getattr(response, "status_code", "unknown")
        detail = getattr(response, "text", "") or str(exc)
        raise requests_module.HTTPError(
            f"Azure OpenAI API error ({status_code}): {detail[:1000]}",
            response=response,
        ) from exc

def chat_completion(messages, functions=None, model="GPT-5.2", **kwargs):
    requests_module = _load_requests()
    response = requests_module.post(
        _required_env("AZURE_OPENAI_URL"),
        headers=_build_headers(),
        json=_build_payload(messages, functions=functions, model=model, **kwargs),
        timeout=_request_timeout(kwargs),
        verify=_ssl_verify(),
    )

    _raise_for_status(response, requests_module)
    return response.json()




def responses(messages, functions=None, model=None, **kwargs):
    return chat_completion(messages, functions=functions, model=model, **kwargs)
