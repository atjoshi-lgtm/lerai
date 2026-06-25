import requests
import os
import urllib3



AZURE_OPENAI_URL = os.environ.get("AZURE_OPENAI_URL")
AZURE_API_KEY = os.environ.get("AZURE_API_KEY")
AZURE_USER_ID = os.environ.get("AZURE_USER_ID")
AZURE_APP_NAME = os.environ.get("AZURE_APP_NAME")

if not all([AZURE_OPENAI_URL, AZURE_API_KEY, AZURE_USER_ID, AZURE_APP_NAME]):
    raise ValueError("Missing one or more required Azure OpenAI environment variables (AZURE_OPENAI_URL, AZURE_API_KEY, AZURE_USER_ID, AZURE_APP_NAME)")

# 1. Keep a backup of the real requests.post function
_original_requests_post = requests.post

# 2. Create an interceptor function
def gpt5_payload_adapter(url, *args, **kwargs):
    # Check if the payload contains the legacy functions block
    if "json" in kwargs and "functions" in kwargs["json"]:
        payload = kwargs["json"]
        
        print("DEBUG [Adapter]: Intercepted legacy payload. Converting to GPT-5.2 tools standard...")
        
        # Pull out the legacy list and transform it into a modern tool array
        legacy_functions = payload.pop("functions")
        payload["tools"] = [{"type": "function", "function": fn} for fn in legacy_functions]
        
        # Swap out function_call for tool_choice
        payload.pop("function_call", None)
        payload["tool_choice"] = "auto"

    # Forward the modified payload out to the network via the original requests mechanism
    return _original_requests_post(url, *args, **kwargs)

# 3. Overwrite requests.post in this module's scope with our adapter
requests.post = gpt5_payload_adapter

def chat_completion(messages, functions=None, model="GPT-5.2", **kwargs):
    headers = {
        "Content-Type": "application/json",
        "api-key": AZURE_API_KEY,
        "user-id": AZURE_USER_ID,
        "app-name": AZURE_APP_NAME
    }
    payload = {
        "messages": messages,
        "max_completion_tokens": 6000
    }
    if functions:
        payload["functions"] = functions
        payload["function_call"] = kwargs.get("function_call", "auto")

    #print ("here's the request")
    #print (headers)
    #print (payload)
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    response = requests.post(AZURE_OPENAI_URL, headers=headers, json=payload, verify=False)
    result = response.json()
    #print(result)

    response.raise_for_status()
    return response.json()




def responses(messages, functions=None, model=None, **kwargs):
    return chat_completion(messages, functions=functions, model=model, **kwargs)
