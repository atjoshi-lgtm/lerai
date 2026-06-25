import os
import pymysql
import pymysql.cursors
from pathlib import Path

def run_mysql_query(sql: str, timeout: int = 60) -> str:
    
    host = os.environ.get("MYSQL_HOST")
    user = os.environ.get("MYSQL_USER")
    database = os.environ.get("MYSQL_DATABASE")
    password = os.environ.get("MYSQL_PASSWORD")

    if not all([host, user, database, password]):
        raise ValueError("Missing one or more required MySQL environment variables (MYSQL_HOST, MYSQL_USER, MYSQL_DATABASE, MYSQL_PASSWORD)")

    try:
        conn = pymysql.connect(host=host,user=user,database=database,password=password,connect_timeout=timeout,cursorclass=pymysql.cursors.DictCursor)
    except pymysql.MySQLError as e:
        raise ConnectionError(f"Failed to connect to MySQL: {e}") from e
    
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql)
            rows = cursor.fetchall()
        if not rows:
            return ""
        headers = ",".join(rows[0].keys())
        lines = [headers] + [",".join(str(v) for v in row.values()) for row in rows]
        return "\n".join(lines)
    finally:
        conn.close()

def save_mysql_query_to_csv_file(sql: str, output_path: str, timeout: int = 300) -> str:
    csv_text = run_mysql_query(sql, timeout=timeout)
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(csv_text + "\n", encoding="utf-8")
    return str(path)
