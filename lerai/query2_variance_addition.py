import os
import ast
import ssl
import urllib.request


#from sql2_query import run_sql2_query

RUN_QUERY2_URL = os.environ.get("RUN_QUERY2_URL")

cert_path = os.environ.get("CERT_PATH")
key_path = os.environ.get("KEY_PATH")


import json
import ast

def handle_response(resp_str: str, silent: bool = True) -> str:
    data = json.loads(resp_str)

    returncode = data.get("returncode")
    stdout = data.get("stdout", "")
    stderr = data.get("stderr", "")

    # If stderr has content → print it and stop
    if stderr.strip():
        return("Query2 vsize variance check" + stderr.strip())
        

    if returncode != 0:
        return(f"Query2 vsize variance check: Non-zero return code: {returncode}")
        

    # Parse stdout safely (it's a string representation of a Python list)
    try:
        rows = ast.literal_eval(stdout.strip())
    except Exception as e:
        return(f"Query2 vsize variance check: Failed to parse stdout: {e}")

    # Case 1: only header row
    if len(rows) == 1 and rows[0] == ['region', 'regionname', 'vsize_limit']:
        if not silent:
            return("LRs in query2 variance: All regions are upto date")
        else:
            return ""

    # Case 2: multiple rows
    if len(rows) > 1:
        ret = "The folowing LR(s) need to get added to the query2 vsize variance:\n"
        for row in rows[1:]:  # skip header
            region = row[0]
            region_name = row[1]
            ret = ret + (f"- {region} ({region_name})\n")
        return ret
            
            
def check_query2_for_variance_addition (silent: bool = True) -> str:
    ssl_context = ssl.create_default_context()
    ssl_context.load_cert_chain(certfile=cert_path, keyfile=key_path)

    agg = "freeflow.devbl.query.akadns.net"
    q3 = """ \
select region, regionname, avg(vsize_limit) vsize_limit
from procnothread a, mcm_machines b, MCM_RegionAttributes c
where command = 'query2' and a.ip = b.ip and 
      b.hardwaretype like '%Carib%' and 
      attribute = 'regionUsedFor' and 
      value like 'LR%' and 
      value not like 'LR_Mixed%' and 
      region = physicalregion 
group by region, regionname
having vsize_limit < 2516582400
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
        raise RuntimeError(f"HTTP error {e.code} fetching query2 result: {detail[:500]}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Network error fetching query2 result: {e}")
        


    
