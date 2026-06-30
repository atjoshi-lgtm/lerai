import os
import re
import logging
from webex_bot.models.command import Command
from csv_env_diff import compare_offline_vs_production
from log_error_summary import get_airflow_error_summary
from expected_observed_comparison import run_offload_analysis_workflow
from DP_AMA import summarize_dps, create_dp_candiate_answer, verify_dp_candiate_answer, fetch_dp_info
from FD_AMA import answer_footprint_question
from scheduled_jobs import send_daily_csv_diff_report, send_daily_offload_report
from query2_variance_addition import check_query2_for_variance_addition
from quota_exceed import check_query2_for_quota_exceed
from promote import handle_promotion_request, handle_approval_request
from leroy_overrides_writer import write_toml
from lerai.logging_utils import log_user_request, redact_value


logger = logging.getLogger(__name__)


class CompareCsvEnvsCommand(Command):
    def __init__(self):
        super().__init__(
            command_keyword="diff_offline_prod",  # command the user types in Webex
            exact_command_keyword_match=True,
            help_message=(
                "Compare offline vs production"
            ),
            card=None,
        )

    def pre_execute(self, message, attachment_actions, activity):
        # This runs immediately so the user gets quick feedback
        log_user_request(logger, self.command_keyword, message, activity)
        return "🔍 Comparing offline and production CSVs... this may take a few seconds."

    def execute(self, message, attachment_actions, activity):
        # You could later parse arguments from `message` if needed
        try:
            summary = compare_offline_vs_production()
            return summary
        except Exception as e:
            # Surface errors so you can debug from Webex
            return f"Error while comparing CSVs: {e}"

class AirflowErrorSummaryCommand(Command):
    """
    Usage in Webex:
      airflow_errors
    """

    def __init__(self):
        super().__init__(
            command_keyword="airflow_errors",
            exact_command_keyword_match=True,
            help_message=(
                "Airflow Errors"
            ),
            card=None,
        )

    def pre_execute(self, message, attachment_actions, activity):
        log_user_request(logger, self.command_keyword, message, activity)
        return "🔍 Collecting and summarizing Airflow ERROR logs... please wait."

    def execute(self, message, attachment_actions, activity):
        try:
            summary = get_airflow_error_summary()
            return summary
        except Exception as e:
            return f"Error while collecting or summarizing Airflow logs: {e}"

class ExpectedObservedDiffCommand(Command):
    """
    Usage in Webex:
      airflow_errors
    """

    def __init__(self):
        super().__init__(
            command_keyword="expected_observed_diff",
            exact_command_keyword_match=True,            
            help_message=(
                "Compare expected and obserevd offload"
            ),
            card=None,
        )

    def pre_execute(self, message, attachment_actions, activity):
        log_user_request(logger, self.command_keyword, message, activity)
        return "🔍 Collecting and summarizing expected and observed offload... please wait."

    def execute(self, message, attachment_actions, activity):
        try:
            summary = run_offload_analysis_workflow()
            return summary
        except Exception as e:
            return f"Error while collecting or summarizing expected and observed offload: {e}"



class LRDPDevCommand(Command):
    """
    Usage in Webex:
      lrdpdev
    """

    def __init__(self):
        super().__init__(
            command_keyword="/lrdp",
            help_message=(
                "LR DP AMA Dev"
            ),
            card=None,
        )

    def pre_execute(self, message, attachment_actions, activity):
        log_user_request(logger, self.command_keyword, message, activity)
        return "🔍 Running query... please wait."

    def execute(self, message, attachment_actions, activity):
        try:

            full_text = message
            dpinfo = fetch_dp_info()
            candidate_answer = create_dp_candiate_answer(full_text, dpinfo=dpinfo)
            verification = verify_dp_candiate_answer(full_text, candidate_answer, dpinfo=dpinfo)
            a = f"{candidate_answer}\n{verification}"
            verdict_match = re.search(r'<verdict>(.*?)</verdict>',a, re.DOTALL)
            answer_match = re.search(r'<answer>(.*?)</answer>', a, re.DOTALL)    
            verdict = verdict_match.group(1).strip() if verdict_match else "No verdict found"
            answer = answer_match.group(1).strip() if answer_match else "No answer found"
            return f"{answer}\nVerdict = {verdict}"
        except Exception as e:
            return f"Error while getting data from netarch or chatgpt: {e}"

class LRDPCommand(Command):
    """
    Usage in Webex:
      lrdp 
    """

    def __init__(self):
        super().__init__(
            command_keyword="/dp",
            help_message=(
                "LR DP AMA"
            ),
            card=None,
        )

    def pre_execute(self, message, attachment_actions, activity):
        log_user_request(logger, self.command_keyword, message, activity)
        return "🔍 Running query... please wait."

    def execute(self, message, attachment_actions, activity):
        try:

            full_text = message
            ans = summarize_dps(full_text)
            return ans
        except Exception as e:
            return f"Error while getting data from netarch or chatgpt: {e}"

class footprintCommand(Command):
    """
    Usage in Webex:
      fd
    """

    def __init__(self):
        super().__init__(
            command_keyword="/fd",
            help_message=(
                "FD AMA"
            ),
            card=None,
        )

    def pre_execute(self, message, attachment_actions, activity):
        log_user_request(logger, self.command_keyword, message, activity)
        return "🔍 Running query... please wait."

    def execute(self, message, attachment_actions, activity):
        try:

            full_text = message
            return (answer_footprint_question(full_text))
        except Exception as e:
            return f"Error while getting data from footprint-archive or chatGPT: {e}"


class PromoteCommand(Command):
    """
    Usage: promote
    Triggers a manual promotion request. Requires a second approved user to 'approve'.
    """
    def __init__(self):
        super().__init__(
            command_keyword="/promote",
            help_message="Request offline to production promotion",
            card=None,
        )

    def pre_execute(self, message, attachment_actions, activity):
        log_user_request(logger, self.command_keyword, message, activity)
        return "🔍 Running safety evaluation before opening promotion request... please wait."

    def execute(self, message, attachment_actions, activity):
        # Simply delegate to the dedicated handler
        return handle_promotion_request(message, activity)

class ApproveCommand(Command):
    """
    Usage: approve
    Approves a pending promotion request opened by another staff member.
    """
    def __init__(self):
        super().__init__(
            command_keyword="/approve",
            help_message="Approve a pending promotion",
            card=None,
        )

    def pre_execute(self, message, attachment_actions, activity):
        log_user_request(logger, self.command_keyword, message, activity)
        return "✅ Processing your approval... please wait."

    def execute(self, message, attachment_actions, activity):
        # Simply delegate to the dedicated handler
        return handle_approval_request(message, activity)

class QueryVarianceCommand(Command):
    def __init__(self):
        super().__init__(
            command_keyword="query_variance",
            exact_command_keyword_match=True,
            help_message="Query Variance Addition",
            card=None,
        )

    def pre_execute(self, message, attachment_actions, activity):
        log_user_request(logger, self.command_keyword, message, activity)
        return "✅ Checking for large regions in need of query2 variance... please wait."

    def execute(self, message, attachment_actions, activity):
        x = check_query2_for_variance_addition(silent=False)
        return x

class QuotaExceedCommand(Command):
    def __init__(self):
        super().__init__(
            command_keyword="quota_exceed",
            exact_command_keyword_match=True,
            help_message="Check quota exceeded",
            card=None,
        )

    def pre_execute(self, message, attachment_actions, activity):
        log_user_request(logger, self.command_keyword, message, activity)
        return "✅ Checking for large regions where quota is exceeded... please wait."

    def execute(self, message, attachment_actions, activity):
        x = check_query2_for_quota_exceed(silent=False)
        return x

    
class LeroyOverrideWriterCommand(Command):
    def __init__(self):
        super().__init__(
            command_keyword="/write_override",
            exact_command_keyword_match=False,
            help_message="Write leroy overrides",
            card=None,
        )

    def pre_execute(self, message, attachment_actions, activity):
        logger.info(
            "Override writer request received",
            extra={
                "request_message": redact_value(message),
                "attachment_actions": redact_value(attachment_actions),
                "activity": redact_value(activity),
            },
        )
        return "✅ Writing... please wait."

    def execute(self, message, attachment_actions, activity):
        x = write_toml(message)
        return x
    

    
class SimulateDailyReport(Command):
    def __init__(self):
        super().__init__(
            command_keyword="simulate_daily",  # command the user types in Webex
            exact_command_keyword_match=True,
            help_message=(
                "Simulate Daily report"
            ),
            card=None,
        )

    def pre_execute(self, message, attachment_actions, activity):
        # This runs immediately so the user gets quick feedback
        log_user_request(logger, self.command_keyword, message, activity)
        return "🔍 Simulating daily report"

    def execute(self, message, attachment_actions, activity):
        # You could later parse arguments from `message` if needed
        try:
            send_daily_csv_diff_report()
            return "✅ Done, check the leroyops space."
        except Exception as e:
            # Surface errors so you can debug from Webex
            return f"❌ Error: {e}"

class SimulateDailyOffloadReport(Command):
    def __init__(self):
        super().__init__(
            command_keyword="daily_offload_simulate",  # command the user types in Webex
            exact_command_keyword_match=True,
            help_message=(
                "Simulate Daily Offload report"
            ),
            card=None,
        )

    def pre_execute(self, message, attachment_actions, activity):
        # This runs immediately so the user gets quick feedback
        log_user_request(logger, self.command_keyword, message, activity)
        return "🔍 Simulating daily offload report"

    def execute(self, message, attachment_actions, activity):
        # You could later parse arguments from `message` if needed
        try:
            send_daily_offload_report()
            return "✅ Done, check the leroyops space."
        except Exception as e:
            # Surface errors so you can debug from Webex
            return f"❌ Error: {e}"

