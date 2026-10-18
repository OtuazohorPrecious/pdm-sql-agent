# check_readonly.py
import os
import psycopg
from dotenv import load_dotenv

load_dotenv()

with psycopg.connect(os.environ["READONLY_DB_URL"]) as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM failures")
        print("Read OK, failures rows:", cur.fetchone()[0])
        try:
            cur.execute("DELETE FROM failures")
            print("PROBLEM: delete was allowed!")
        except psycopg.Error as e:
            print("Write correctly blocked:", type(e).__name__)
