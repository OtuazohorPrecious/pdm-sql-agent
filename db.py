# db.py
import os
import psycopg
from dotenv import load_dotenv

load_dotenv()  # reads .env on your laptop; on Streamlit Cloud the secrets are already set
DB_URL = os.environ["READONLY_DB_URL"]


def run_sql(query: str, max_rows: int = 50):
    """Run one query as agent_ro. Return (column names, at most max_rows rows)."""
    with psycopg.connect(DB_URL) as conn, conn.cursor() as cur:
        cur.execute(query)
        cols = [d.name for d in cur.description] if cur.description else []
        return cols, cur.fetchmany(max_rows)
