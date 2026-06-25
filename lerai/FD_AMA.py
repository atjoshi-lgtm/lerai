import os
import sys
import json
import requests

from openai_agent.openai_agent_client import chat_completion

BASE = os.environ.get("FOOTPRINT_API_BASE_URL")
cert_path = os.environ.get("CERT_PATH")
key_path = os.environ.get("KEY_PATH")
CERT_ARG = (cert_path, key_path)
VERIFY_ARG = True


OPENAI_FUNCTIONS = [
    {
        "name": "list_scheduled_metro_quarters",
        "description": "Lists all metros and quarters with scheduled footprint descriptors.",
        "parameters": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "get_scheduled_knee",
        "description": "Get knee data for a given metro, quarter, traffic_type, network, and maprule.",
        "parameters": {
            "type": "object",
            "properties": {
                "metro": {"type": "string"},
                "quarter": {"type": "string"},
                "maprule": {"type": "string"},
                "traffic_type": {
                    "type": "string",
                    "description": "traffic_type code (if omitted, defaults to 'LO')"
                },
                "network": {
                    "type": "string",
                    "description": "Network code (if omitted, defaults to 'f')"
                }
            },
            "required": ["metro", "quarter", "maprule"]
        }
    },
    {
        "name": "get_scheduled_knee_prediction",
        "description": "Get knee/traffic prediction for a metro, quarter, traffic_type, network, and maprule.",
        "parameters": {
            "type": "object",
            "properties": {
                "metro": {"type": "string"},
                "quarter": {"type": "string"},
                "maprule": {"type": "string"},
                "traffic_type": {
                    "type": "string",
                    "description": "traffic_type code (if omitted, defaults to 'LO')"
                },
                "network": {
                    "type": "string",
                    "description": "Network code (if omitted, defaults to 'f')"
                }
            },
            "required": ["metro", "quarter", "maprule"]
        }
    }
]

        
def list_scheduled_metro_quarters():
    url = BASE.rstrip("/") + "/api/v1/scheduled/metro_quarters/"
    resp = requests.get(url, cert=CERT_ARG, verify=VERIFY_ARG)
    resp.raise_for_status()
    return resp.json()

def get_scheduled_knee(metro, quarter, maprule, traffic_type=None, network=None):
    
    network = network or "f"
    traffic_type = traffic_type or "LO"

    url = (BASE.rstrip("/") +
           f"/api/v1/scheduled/knee/metro/{metro}/quarter/{quarter}/"
           f"content-type/{traffic_type}/network/{network}/maprule/{maprule}/")
    resp = requests.get(url, cert=CERT_ARG, verify=VERIFY_ARG)
    resp.raise_for_status()
    return resp.json()

def get_scheduled_knee_prediction(metro, quarter, maprule, traffic_type=None, network=None):
    network = network or "f"
    traffic_type = traffic_type or "LO"

    url = (BASE.rstrip("/") +
           f"/api/v1/scheduled/prediction/metro/{metro}/content-type/{traffic_type}/"
           f"network/{network}/maprule/{maprule}/begin-quarter/{quarter}")
    resp = requests.get(url, cert=CERT_ARG, verify=VERIFY_ARG)
    resp.raise_for_status()
    return resp.json()


# Mapping function names to actual local Python functions:
TOOL_MAP = {
    "list_scheduled_metro_quarters": list_scheduled_metro_quarters,
    "get_scheduled_knee": get_scheduled_knee,
    "get_scheduled_knee_prediction": get_scheduled_knee_prediction,
}



def answer_footprint_question_legacy(user_message, model="gpt-5.2"):
    messages = [
        {"role": "system", "content": "You are an expert in the footprint descriptor API. Return answers with context from called tools. If you call multiple tools, use their results to compose your answer."},
        {"role": "user", "content": user_message}
    ]
    functions = OPENAI_FUNCTIONS

    for _ in range(5):  # Allow up to 5 steps
        print (f"DEBUG: calling LLM with messages = {messages}")
        try:
            response = chat_completion(
                messages=messages,
                functions=functions,
                function_call="auto",
                model=model
            )
        except requests.HTTPError as e:
            print(e.response.text)
            raise    
            
        # response is a dict, not an object with attributes
        msg = response["choices"][0]["message"]
        print("DEBUG: LLM message:", msg)

        if msg.get("function_call"):
            fn = msg["function_call"]["name"]
            args_str = msg["function_call"]["arguments"]
            print("DEBUG: LLM requested function:", fn)
            print("DEBUG: Args:", args_str)
            args = json.loads(args_str) if args_str else {}

            if fn not in TOOL_MAP:
                print(f"Unknown function: {fn}")
                return f"Unknown function: {fn}"

            try:
                result = TOOL_MAP[fn](**args)
                print(f"DEBUG: FUNCTION {fn} result: {str(result)[:350]}{'...' if len(str(result))>350 else ''}")
            except Exception as e:
                result = f"Tool error: {e}"
                print(f"DEBUG: FUNCTION {fn} ERROR: {e}")

            # Pass function call and result back to LLM as a function message (per OpenAI format)
            clean_msg = {"role": "assistant", "content": msg.get("content"), "function_call": msg.get("function_call")}
            messages.append(clean_msg)
            #messages.append(msg)
            messages.append({"role": "function", "name": fn, "content": json.dumps(result)})
            continue

        # If LLM returns an assistant message with 'content', print and return it.
        if msg.get("content"):
            print("DEBUG: LLM final content:", msg["content"])
            return msg["content"]

    return "Sorry, couldn't answer after several tool calls."


def answer_footprint_question(user_message, model="gpt-5.2"):
    messages = [
        {"role": "system", "content": "You are an expert in the footprint descriptor API. Return answers with context from called tools. If you call multiple tools, use their results to compose your answer."},
        {"role": "user", "content": user_message}
    ]

    for _ in range(5):  # Allow up to 5 steps
        print(f"DEBUG: calling LLM with messages = {messages}")
        try:
            # We pass OPENAI_FUNCTIONS normally. The adapter script above 
            # will intercept this call and convert it to 'tools' silently.
            response = chat_completion(
                messages=messages,
                functions=OPENAI_FUNCTIONS,
                function_call="auto",
                model=model
            )
        except requests.HTTPError as e:
            print(e.response.text)
            raise    
            
        msg = response["choices"][0]["message"]
        print("DEBUG: LLM message:", msg)

        # Handle the modern tool response format returned by GPT-5.2
        if msg.get("tool_calls"):
            messages.append(msg) # Append assistant intent
            
            for tool_call in msg["tool_calls"]:
                fn = tool_call["function"]["name"]
                args_str = tool_call["function"]["arguments"]
                tool_call_id = tool_call["id"] 
                
                print("DEBUG: LLM requested function:", fn)
                args = json.loads(args_str) if args_str else {}

                if fn not in TOOL_MAP:
                    return f"Unknown function: {fn}"

                try:
                    result = TOOL_MAP[fn](**args)
                    print(f"DEBUG: FUNCTION {fn} result: {str(result)[:150]}...")
                except Exception as e:
                    result = f"Tool error: {e}"

                # Provide tool output linked via the required ID
                messages.append({
                    "role": "tool", 
                    "tool_call_id": tool_call_id, 
                    "content": json.dumps(result)
                })
            continue

        if msg.get("content"):
            print("DEBUG: LLM final content:", msg["content"])
            return msg["content"]

    return "Sorry, couldn't answer after several tool calls."

# ---- Example manual test ----
if __name__ == "__main__":
    # User can ask natural-language questions:
    q = "What quarters are available for AMS? What is the knee for AMS in 2025Q4 with maprule mm1, traffic type LO, and network f?"
    q="What are the quarters for which we have FDs for AMS? what is the most recent quarter for which we have an FD for mm2 map in AMS? what is the knee?" 
    print(answer_footprint_question(q))

