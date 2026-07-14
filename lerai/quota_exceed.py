import os
import ast
import json
import ssl
import urllib.parse
import urllib.request

RUN_QUERY2_URL = os.environ.get("RUN_QUERY2_URL")

cert_path = os.environ.get("CERT_PATH")
key_path = os.environ.get("KEY_PATH")

QUOTA_EXCEED_HEADER = ['physregion', 'fp_config_name', 'objcount_max', 'objectlimit', 'objcount', 'objcount_quota']


def _load_query2_rows(resp_str: str, check_name: str):
    try:
        data = json.loads(resp_str)
    except json.JSONDecodeError as e:
        return None, f"{check_name}: Invalid JSON response: {e}"

    if not isinstance(data, dict):
        return None, f"{check_name}: Response JSON must be an object"

    stderr = data.get("stderr", "")
    if stderr is None:
        stderr = ""
    if not isinstance(stderr, str):
        return None, f"{check_name}: stderr must be a string"
    if stderr.strip():
        return None, f"{check_name}: {stderr.strip()}"

    returncode = data.get("returncode")
    if returncode != 0:
        return None, f"{check_name}: Non-zero return code: {returncode}"

    stdout = data.get("stdout", "")
    if stdout is None:
        stdout = ""
    if not isinstance(stdout, str):
        return None, f"{check_name}: stdout must be a string"

    try:
        rows = ast.literal_eval(stdout.strip())
    except Exception as e:
        return None, f"{check_name}: Failed to parse stdout: {e}"

    if not isinstance(rows, list):
        return None, f"{check_name}: stdout must parse to a list"
    if not rows:
        return None, f"{check_name}: Empty result set"
    if not isinstance(rows[0], list):
        return None, f"{check_name}: Header row must be a list"

    return rows, None


def _to_int(value, row, field_name):
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError(f"invalid {field_name} value {value!r} in row {row}")


def handle_response(resp_str: str, silent: bool = True) -> str:
    check_name = "LR quota exceed check"
    rows, error = _load_query2_rows(resp_str, check_name)
    if error:
        return error

    # Case 1: only header row
    if len(rows) == 1 and rows[0] == QUOTA_EXCEED_HEADER:
        if not silent:
            return("LR quota exceed check: No issues.")
        else:
            return ""

    # Case 2: multiple rows
    if len(rows) > 1:
        ret = ["The following fp-configs are exceeding their quota limits or are over machine's objlimit:\n"]
        for row in rows[1:]:  # skip header
            if not isinstance(row, list) or len(row) < 6:
                return f"{check_name}: Invalid row format: {row}"
            region = row[0]
            fp_config_name = row[1]
            try:
                objcount_max = _to_int(row[2], row, "objcount_max")
                objectlimit = _to_int(row[3], row, "objectlimit")
                objcount = _to_int(row[4], row, "objcount")
                objcount_quota = _to_int(row[5], row, "objcount_quota")
            except ValueError as e:
                return f"{check_name}: {e}"

            if (objcount_max > objectlimit):
                if fp_config_name == "all-fps-together":                    
                    ret.append(f" * LR {region}: some machines have total object count larger than the entire machine's object limit! {int(objcount_max):,} > {int(objectlimit):,}")
                else:
                    ret.append(f" * LR {region}: some machines have {fp_config_name}'s object count larger than the entire machine's object limit! {int(objcount_max):,} > {int(objectlimit):,}")
            elif objcount > objcount_quota: 
                ret.append(f" * LR {region}: {fp_config_name} object count of the whole region is larger than its count quota. {int(objcount):,} > {int(objcount_quota):,}")
        return "\n".join(ret)

    return f"{check_name}: Unexpected result format"
            
            
def check_query2_for_quota_exceed (silent: bool = True) -> str:
    ssl_context = ssl.create_default_context()
    ssl_context.load_cert_chain(certfile=cert_path, keyfile=key_path)

    agg = "freeflow.devbl.query.akadns.net"
    q3 = """ \
select physregion, fp_config_name, objcount_max, objectlimit, objcount, objcount_quota
from footprint_stats_rv a, MCM_RegionAttributes b, 
     (select region, avg(serviceinfo_objectlimit) objectlimit
      from ghostvars_popular_ffdevbl_rv a, mcm_machines b
      where a.ghostip = b.ip 
      group by region ) c 
WHERE attribute = 'regionUsedFor' and value like 'LR_%' and a.physregion = b.physicalregion and a.physregion = c.region and ( objcount_max > objectlimit or ( objcount_quota > 0 and objcount > objcount_quota*1.02 ) )  and fp_config_name not like 'rdc-edge-%'
union all 
select region, 'all-fps-together' fp_config_name, avg(serviceinfo_objectcount) objcount_max, avg(serviceinfo_objectlimit) objectlimit, 0, 0
from ghostvars_popular_ffdevbl_rv a, mcm_machines b, MCM_RegionAttributes c
where a.ghostip = b.ip and 
      attribute = 'regionUsedFor' and 
      value like 'LR_%' and 
      b.region = c.physicalregion 
group by region
having objcount_max  > objectlimit
""" 
    
    params = {
    "query": q3,
    "agg": agg,
}
        
    req = urllib.request.Request(
        RUN_QUERY2_URL + "?" + urllib.parse.urlencode(params),
        headers={
            "User-Agent": "LeRAI/1.0",
            "Accept": "text/plain,*/*",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=300, context=ssl_context) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            body = resp.read().decode(charset, errors="replace")
            return handle_response(resp_str=body,silent=silent)
    except urllib.error.HTTPError as e:
        # e.code, e.read() often contain useful details
        detail = ""
        try:
            detail = e.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        raise RuntimeError(f"Quota Exceed: HTTP error {e.code} fetching query2 result: {detail[:500]}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Quota Exceed: Network error fetching query2 result: {e}")
        


    
