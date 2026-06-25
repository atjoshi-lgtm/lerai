import requests
import logging
import ssl
from webexteamssdk import WebexTeamsAPI
from lerai.webex_presence import send_dm, get_sender_email, get_room_id, get_space_id, send_space_message
from openai_agent.openai_agent_client import chat_completion



def create_approval_token(sender_email, approver_email, webex_space, original_token):
    """Combines 4 fields into a single reversible token."""
    timestamp = str(int(time.time()))
    # Join with a separator that unlikely to be in emails
    raw_data = f"{sender_email}|{approver_email}|{webex_space}|{original_token}|{timestamp}"
    
    # Encode to Base64 to make it a single string
    token_bytes = raw_data.encode('utf-8')
    encoded_token = base64.urlsafe_b64encode(token_bytes).decode('utf-8')
    
    return encoded_token.rstrip('=')  # Remove padding for a cleaner look

def decode_approval_token(token):
    """Decodes the token back into the 5 original fields."""
    try:
        # Add padding back if necessary
        missing_padding = len(token) % 4
        if missing_padding:
            token += '=' * (4 - missing_padding)
            
        decoded_bytes = base64.urlsafe_b64decode(token)
        decoded_str = decoded_bytes.decode('utf-8')
        
        # Split back into parts
        parts = decoded_str.split('|')
        if len(parts) == 5:
            return {
                "sender": parts[0],
                "approver": parts[1],
                "webex_space": parts[2],
                "original_token": parts[3],
                "timestamp": parts[4]
            }
    except Exception as e:
        print(f"Error decoding token: {e}")
        
    return None


def handle_promotion_request(message, activity):
    """
    Main logic for processing a promotion request.
    Extracts approver/token and notifies the approver.
    """
    # 1. Setup & Authorization
    approved_users_raw = os.environ.get("APPROVED_USERS", {})
    if isinstance(approved_users_raw, str):
        try:
            approved_map = json.loads(approved_users_raw)
        except json.JSONDecodeError:
            return "❌ Error: APPROVED_USERS is not valid JSON."
    else:
        approved_map = approved_users_raw
    webex_token = os.environ.get("WEBEX_ACCESS_TOKEN")
    api = WebexTeamsAPI(access_token=webex_token)
    
    sender_email = get_sender_email(activity)
    webex_space = get_space_id(activity)

    if sender_email not in approved_map.values():
        authorized_names = sorted(set(name for name in approved_map.keys() if "@" not in name))
        list_str = "\n".join([f"- {name}" for name in authorized_names])
        return (f"❌ Access Denied.\n\n**Authorized Requesters:**\n{list_str}")

    # 2. Extract Data using AI
    valid_names = ", ".join([name for name in approved_map.keys() if "@" not in name])
    prompt = (
        f"Analyze this message: '{message}'\n"
        f"1. Identify the requested approver. Valid choices: {valid_names}.\n"
        f"2. Identify the promotion token.\n"
        "Return a JSON object with keys 'approver' and 'token'. Set to null if missing."
    )

    try:
        llm_resp = chat_completion(
            messages=[{"role": "system", "content": "You are a precise technical analyst."},
                      {"role": "user", "content": prompt}]
        ) #
        
        # Clean potential markdown from LLM output before parsing
        raw_content = llm_resp["choices"][0]["message"]["content"].replace("```json", "").replace("```", "").strip()
        extracted = json.loads(raw_content)
        approver_input = extracted.get("approver")
        token = extracted.get("token")
    except Exception as e:
        return f"❌ AI Parsing Error: {e}"

    if not approver_input or not token:
        return "⚠️ Could not identify the approver or token. Please say something like: '/promote... ask Bruce, token XYZ'"

    # 3. Resolve & Notify
    target_email = approved_map.get(approver_input)
    if not target_email:
        return f"❌ `{approver_input}` is not an authorized approver."

    new_token = create_approval_token(sender_email, target_email, webex_space, token)

    if webex_space:
        dm_body = (
            f"🔔 **Promotion Request**\n\n"
            f"**Requester:** {sender_email}\n"
            f"**Approver:** <@personEmail:{target_email}>\n"
            f"Before approving, you may want to ask me to show you the latest offline-prod diff, verify that it's safe, and that the token matches {token}.\n"
            f"Once sure, to approve, reply to me with `/approve {new_token}` (DM or in the LeROY ops space)."
        )
        return dm_body
    else:
        dm_body = (
            f"🔔 **Promotion Request**\n\n"
            f"**Requester:** {sender_email}\n"
            f"**Approver:** {target_email}\n"
            f"Before approving, you may want to ask me to show you the latest offline-prod diff, verify that it's safe, and that the token matches {token}.\n"
            f"Once sure, to approve, reply to me with `/approve {new_token}` (DM or in the LeROY ops space)."
        )
        if send_dm(api, target_email, dm_body): #
            return f"✅ Request sent to **{approver_input}**. Awaiting approval."
        else:
            return f"❌ Failed to notify {target_email}."


def handle_approval_request(message, activity):

    #token_to_process = message.strip()
    token_to_process = message.strip().split()[-1]
    if not token_to_process:
            return "❌ Missing token. Usage: `/approve <token>`"

    # 1. Decode
    print (token_to_process)
    data = decode_approval_token(token_to_process)
    if not data:
        return "❌ Invalid or corrupted approval token."

    sender_email = get_sender_email(activity) #

    promotion_requester = data['sender']
    requested_approver = data['approver']
    original_token = data['original_token']
    webex_space = data['webex_space']
    
    # 2. Authorization Check
    if sender_email != requested_approver:
        return f"❌ Error: Approval messages come from {sender_email}, but original requester {promotion_requester} had asked {requested_approver} to approve the promotion. Approval message ignored."

    # 3. Request to LeROY Agent
    BASE = os.environ.get("FOOTPRINT_API_BASE_URL")
    cert_path = os.environ.get("CERT_PATH")
    key_path = os.environ.get("KEY_PATH")

    url = os.environ.get("LEROY_AGENT_PROMOTE_URL")
    params = {'token': original_token}

    webex_token = os.environ.get("WEBEX_ACCESS_TOKEN")
    api = WebexTeamsAPI(access_token=webex_token)

    try:
        response = requests.get(url, params=params, timeout=60, cert=(cert_path,key_path))        
        if response.status_code == 200:
            # 1. Parse the JSON body into a dictionary
            data = response.json() 
    
            # 2. Extract the stdout and stderr
            std_out = data.get("stdout")
            std_err = data.get("stderr")
    
            # 3. Print them to your console/logs for debugging
            print(f"STDOUT: {std_out}")
            print(f"STDERR: {std_err}")
            
            # Who Am I responding to? 
            # 1. If request and approval both happened on the same space, reply once to that space (i.e. return the message with mentions). 
            # 2. If request and approval both happened on different spaces, reply once to each space (i.e. one space message, one return). 
            # 3. If request on space, and approver replied by DM, reply to the space and approver (i.e. one space message, one return)
            # 4. If request by DM, and approver replied to space, reply just once to the space (i.e. return the message with mentions). 
            # 5. If everything was on DM, reply to the approver and copy to requester by DM 

            current_webex_space = get_space_id(activity)
            msg_w_mention = (f"🚀 **Promotion Successful!**\n\n"
                   f"**Requester:** <@personEmail:{promotion_requester}>\n"
                   f"**Approver:** <@personEmail:{requested_approver}>\n"
                   f"**Promotion details:** {std_out}\n{std_err}")
            msg = (f"🚀 **Promotion Successful!**\n\n"
                   f"**Requester:** {promotion_requester}\n"
                   f"**Approver:** {requested_approver}\n"
                   f"**Promotion details:** {std_out}\n{std_err}")

            print (f"current webex space = {current_webex_space}")
            print (f"Webex space in token = {webex_space}")
            # 1. 
            if current_webex_space and webex_space and current_webex_space == webex_space:
                return msg_w_mention
            # 2. Reply to the leroy ops space and copy to approver
            if webex_space and current_webex_space and webex_space != current_webex_space:
                send_space_message(api, webex_space, msg_w_mention)
                return msg_w_mention
            # 3. Request on space, approval on DM
            if webex_space and not current_webex_space:
                send_space_message(api, webex_space, msg_w_mention)
                return msg
            # 4. Request on DM, approval on space
            if not webex_space and current_webex_space:
                return msg_w_mention
            # 5. Fully DM communication
            else:                
                if send_dm(api, promotion_requester, msg): 
                    msg = f"{msg} cc: {promotion_requester}."            
                    return msg
        else:
            msg = f"⚠️ Agent returned error ({response.status_code}): {response.text}"
            if send_dm(api, promotion_requester, msg): 
                msg = f"{msg} Informed promotion requester {promotion_requester}."
            return msg          
            
    except Exception as e:
        print(f"Promotion connection error: {e}")
        return f"🔥 Connection to LeROY Agent failed: `{str(e)}`"