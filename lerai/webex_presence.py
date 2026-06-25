"""
webex_presence.py

Handles all Webex presence/status checking and smart approver selection for
the LeRAI promotion workflow.

Responsibilities:
  - Check if a user is OOO via the Webex People API
  - Pick the first available (non-OOO) approver from a priority-ordered list
  - Send DMs to specific users
  - Detect whether a message came from a DM or a team space

Status values returned by the Webex People API:
  active       - active within the last 10 minutes
  inactive     - last activity more than 10 minutes ago
  call         - in a call
  meeting      - in a meeting
  DoNotDisturb - manually set DND
  OutOfOffice  - OOO (set by user or Hybrid Calendar integration)
  pending      - never logged in, status unknown

We treat only "OutOfOffice" as OOO. All other statuses (including unknown/missing)
are treated as available, so users with disabled status sharing are never silently skipped.
"""

import logging
from typing import List, Union
from dataclasses import dataclass


logger = logging.getLogger(__name__)

# The only status we treat as OOO
OOO_STATUS = "OutOfOffice"


# ─────────────────────────────────────────────────────────────────────────────
# Data classes
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ApproverSelection:
    """Result of pick_approver()."""
    found: bool
    email: str = ""                 # selected approver email
    skipped_ooo: List[str] = None   # emails skipped because they were OOO
    all_ooo: bool = False           # True if everyone was OOO

    def __post_init__(self):
        if self.skipped_ooo is None:
            self.skipped_ooo = []


# ─────────────────────────────────────────────────────────────────────────────
# Presence checking
# ─────────────────────────────────────────────────────────────────────────────

#def get_webex_status(webex_api, email: str) -> str | None:
def get_webex_status(webex_api, email: str) -> Union[str, None]:

    """
    Fetch the current Webex presence status for a user by email.

    Returns the status string (e.g. "active", "OutOfOffice") or None if
    the status could not be determined (user not in org, status sharing disabled, API error).
    """
    try:
        people = list(webex_api.people.list(email=email))
        if not people:
            logger.warning(f"No Webex user found for email: {email}")
            return None
        person = people[0]
        status = getattr(person, "status", None)
        logger.debug(f"Webex status for {email}: {status}")
        return status
    except Exception as e:
        logger.warning(f"Could not fetch Webex status for {email}: {e}")
        return None


def is_ooo(webex_api, email: str) -> bool:
    """
    Returns True if the user is confirmed OOO, False otherwise.
    Defaults to False (available) if status cannot be determined.
    """
    status = get_webex_status(webex_api, email)
    if status is None:
        # Can't determine — assume available so they're not silently skipped
        logger.info(f"{email}: status unknown, assuming available")
        return False
    ooo = status == OOO_STATUS
    if ooo:
        logger.info(f"{email}: is OOO (status={status})")
    return ooo


# ─────────────────────────────────────────────────────────────────────────────
# Approver selection
# ─────────────────────────────────────────────────────────────────────────────

def pick_approver(
    webex_api,
    approved_users: List[str],
    requester: str,
) -> ApproverSelection:
    """
    Pick the first available approver from the priority-ordered approved_users list.

    Rules:
      - Skip the requester (can't self-approve)
      - Skip anyone who is OOO
      - Try the next person if the current one is unavailable
      - Return all_ooo=True if no one is available

    Args:
        webex_api:      WebexTeamsAPI instance
        approved_users: Priority-ordered list of approved approver emails
        requester:      Email of the person requesting promotion (excluded)

    Returns:
        ApproverSelection with .found and .email
    """
    skipped_ooo = []
    requester_lower = requester.lower().strip()

    candidates = [u for u in approved_users if u.lower().strip() != requester_lower]

    if not candidates:
        logger.warning("No candidates after excluding requester from approved list.")
        return ApproverSelection(found=False, all_ooo=False)

    for email in candidates:
        if is_ooo(webex_api, email):
            skipped_ooo.append(email)
            logger.info(f"Skipping {email} — OOO")
            continue
        # Found an available approver
        logger.info(f"Selected approver: {email} (skipped OOO: {skipped_ooo})")
        return ApproverSelection(found=True, email=email, skipped_ooo=skipped_ooo)

    # Everyone was OOO
    logger.warning(f"All eligible approvers are OOO: {skipped_ooo}")
    return ApproverSelection(found=False, skipped_ooo=skipped_ooo, all_ooo=True)


# ─────────────────────────────────────────────────────────────────────────────
# DM helpers
# ─────────────────────────────────────────────────────────────────────────────

def send_dm(webex_api, to_email: str, message: str) -> bool:
    """
    Send a direct message to a user by email.
    Returns True on success, False on failure.
    """
    try:
        webex_api.messages.create(toPersonEmail=to_email, markdown=message)
        logger.info(f"DM sent to {to_email}")
        return True
    except Exception as e:
        logger.error(f"Failed to send DM to {to_email}: {e}")
        return False


def send_space_message(webex_api, room_id: str, message: str) -> bool:
    """
    Post a message to a Webex space/room.
    Returns True on success, False on failure.
    """
    try:
        webex_api.messages.create(roomId=room_id, markdown=message)
        logger.info(f"Message posted to room {room_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to post to room {room_id}: {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Context detection
# ─────────────────────────────────────────────────────────────────────────────

def is_direct_message(activity: dict) -> bool:
    """
    Detect whether the incoming Webex activity is a DM (direct/1:1 space)
    or a group team space.

    The webex_bot framework passes the activity dict from the Webex API.
    The roomType field is "direct" for DMs and "group" for team spaces.
    """
    room_type = activity.get("target", {}).get("roomType", "")
    if not room_type:
        # Fallback: check the space object
        room_type = activity.get("space", {}).get("type", "")
    return room_type.lower() == "direct"


def get_room_id(activity: dict) -> str:
    """Extract the room/space ID from a webex_bot activity dict."""
    return (
        activity.get("target", {}).get("id")
        or activity.get("space", {}).get("id")
        or ""
    )

def get_space_id(activity: dict) ->  Union[str, None]:
    target = activity.get("target", {})
    if "ONE_ON_ONE" not in target.get("tags", []):
        return target.get("id")
    return ""

def get_sender_email(activity: dict) -> str:
    """Extract the sender's email from a webex_bot activity dict."""
    return activity.get("actor", {}).get("emailAddress", "")
