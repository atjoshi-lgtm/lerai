query_LR_DP_old = """\
select PROJECT_NUMBER, status, replace(replace(dp_summary, '\r', ' '), '\n', ' ') as dp_summary, TARGET_DATE, TARGET_DATE_actual
from CMN_INT.AK_DEPLOYMENT_PROJECT
where dp_summary like '%Large Region%'
"""

query_LR_DP = """\
select distinct PROJECT_NUMBER, por_status, ticket_age, a.status status, status_age, replace(replace(dp_summary, '\r', ' '), '\n', ' ') as dp_summary, TARGET_DATE, TARGET_DATE_actual
from CMN_INT.AK_DEPLOYMENT_PROJECT a, CMN_INT.AK_ISSUE
where dp_summary like '%Large Region%' and PROJECT_NUMBER = DEPLOYMENT_PROJECT_NAME
"""
