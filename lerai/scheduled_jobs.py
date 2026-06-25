import os
import time
from webexteamssdk import WebexTeamsAPI
from csv_env_diff import compare_offline_vs_production
from log_error_summary import get_airflow_error_summary
from expected_observed_comparison import run_offload_analysis_workflow
from query2_variance_addition import check_query2_for_variance_addition
from quota_exceed import check_query2_for_quota_exceed


# ── Bot setup ─────────────────────────────────────────────────────────────
webex_token = os.environ.get("WEBEX_ACCESS_TOKEN", "default_value")
space_id  = os.environ.get("WEBEX_SPACE_ID")
offload_space_id  = os.environ.get("LR_OFFLOAD_WEBEX_SPACE_ID")


def send_daily_csv_diff_report():
    """
    Scheduled job: runs once a day inside the bot process.
    - Checks if offline CSVs are stale (>36h).
    - If stale: posts a 'stale data' message.
    - If fresh: runs full CSV comparison.
    - In both cases: also collects and summarizes Airflow ERROR logs and appends to the message.
    """

    #print(f"\n\n\ntoken = {webex_token}, space_id = {space_id}\n\n\n")
    if not webex_token or not space_id:
        print("Daily job: WEBEX_ACCESS_TOKEN or WEBEX_SPACE_ID not set; skipping.")
        return

    api = WebexTeamsAPI(access_token=webex_token)

    # ---- Part 1: CSV diff (with staleness check) ----
    csv_section = ""
    try:
        csv_summary = compare_offline_vs_production(check_staleness_only=False,stale_hours=36)
        csv_section = (
            "✅ **CSV comparison**\n\n"
            "Daily offline vs production CSV comparison completed.\n\n"
            f"{csv_summary}\n"
        )
    except Exception as e:
        csv_section = (
            "❌ **CSV comparison**\n\n"
            f"Failed to run daily CSV comparison.\n\n"
            f"Error: `{e}`\n"
        )
        print(f"Daily CSV job error: {e}")

    # Avoid OpenAI rate limit, sleep for 2s
    time.sleep(2)  
    # ---- Part 2: Airflow log error summary ----
    try:
        airflow_summary = get_airflow_error_summary()
        airflow_section = (
            "🧩 **Airflow ERROR log summary (last 12 hours)**\n\n"
            f"{airflow_summary}\n"
        )
    except Exception as e:
        airflow_section = (
            "❌ **Airflow ERROR log summary**\n\n"
            f"Failed to collect or summarize Airflow logs.\n\n"
            f"Error: `{e}`\n"
        )
        print(f"Daily Airflow log job error: {e}")

    # ---- Combine sections and send one message ----
    full_message = (
        "📅 **Daily report**\n\n"
        f"{csv_section}\n"
        f"{airflow_section}"
    )

    api.messages.create(roomId=space_id, markdown=full_message)

def send_daily_offload_report():
    """
    Scheduled job: runs once a day inside the bot process.
    - just calls run_offload_analysis_workflow, which provides a GPT summary of expected/observed offload diff
    - If not null, sends it to the LR offload watch webex space
    """
    print(f"\n\n\ntoken = {webex_token}, space_id = {offload_space_id}\n\n\n")
    if not webex_token or not offload_space_id:
        print("Daily job: WEBEX_ACCESS_TOKEN or WEBEX_OFFLOAD_SPACE_ID not set; skipping.")
        return

    api = WebexTeamsAPI(access_token=webex_token)

    # ---- Part 1: Offload summary
    section = ""
    try:
        offload_summary = run_offload_analysis_workflow()
        section = (
                    "✅ **LR offload watch**\n\n"
                    "Daily expected-observed offload comparison completed.\n\n"
                    f"{offload_summary}"
                )
    except Exception as e:
        section = (
            "❌ **LR offload watch**\n\n"
            f"Failed to run daily expected-observed offload comparison.\n\n"
            f"Error: `{e}`\n"
        )
        print(f"Daily offload job error: {e}")

    api.messages.create(roomId=offload_space_id, markdown=section)

    
def send_daily_query2_variance_report():
    """
    Scheduled job: runs once a day inside the bot process.
    - just calls the query2 variance function, which provides a  summary of regions in need of variance
    - If not null, sends it to the LR OPs webex space
    """
    print ("Running daily variance job")
    if not webex_token or not space_id:
        print("Daily Query2 Variance check job: WEBEX_ACCESS_TOKEN or WEBEX_OFFLOAD_SPACE_ID not set; skipping.")
        return

    section = ""
    try:
        variance_summary = check_query2_for_variance_addition()
        if not variance_summary:
            return 
        section = (
                    "✅ **Query2 Variance Watch**\n\n"
                    f"{variance_summary}"
                )
    except Exception as e:
        section = (
            "❌ **Query2 Variance Watch**\n\n"
            f"Error: `{e}`\n"
        )
        print(f"Daily query2 variance jpb error: {e}")

    api = WebexTeamsAPI(access_token=webex_token)
    api.messages.create(roomId=offload_space_id, markdown=section)

    
def send_daily_quota_exceed_report():
    """
    Scheduled job: runs once a day inside the bot process.
    - just calls the query2 variance function, which provides a summary of regions where quotas are exceeded
    - If not null, sends it to the LR OPs webex space
    """
    print ("Running daily quota exceed job")
    if not webex_token or not space_id:
        print("Daily Quota exceed check job: WEBEX_ACCESS_TOKEN or WEBEX_OFFLOAD_SPACE_ID not set; skipping.")
        return

    section = ""
    try:
        summary = check_query2_for_quota_exceed()
        if not summary:
            return 
        section = ( "📅 **Exceeding Quotas watch**\n\n"
                    f"{summary}"
                )
    except Exception as e:
        section = (
            "❌ **Exceeding Quotas watch**\n\n"
            f"Failed to run daily exceeding quotas check.\n\n"
            f"Error: `{e}`\n"
        )
        print(f"Daily exceeding quotas error: {e}")

    api = WebexTeamsAPI(access_token=webex_token)
    api.messages.create(roomId=offload_space_id, markdown=section)
    
