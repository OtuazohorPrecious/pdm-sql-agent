# guardrail.py
import re

FORBIDDEN = [
    "insert",
    "update",
    "delete",
    "merge",
    "drop",
    "alter",
    "create",
    "truncate",
    "grant",
    "revoke",
    "copy",
    "call",
    "do",
    "execute",
    "vacuum",
    "analyze",
    "lock",
    "set",
    "reset",
    "listen",
    "notify",
    "pg_sleep",
    "pg_read_file",
    "pg_terminate_backend",
    "dblink",
]
_FORBIDDEN_RE = re.compile(r"\b(" + "|".join(FORBIDDEN) + r")\b", re.IGNORECASE)


def _strip_comments(q: str) -> str:
    q = re.sub(r"/\*.*?\*/", " ", q, flags=re.DOTALL)  # /* block */
    q = re.sub(r"--[^\n]*", " ", q)  # -- line
    return q.strip()


def validate_sql(query: str) -> tuple[bool, str]:
    """Return (True, '') if the query looks safe, else (False, reason)."""
    q = _strip_comments(query).rstrip(";").strip()
    if not q:
        return False, "empty query"
    if ";" in q:
        return False, "only one statement is allowed"
    if not re.match(r"^(select|with)\b", q, re.IGNORECASE):
        return False, "query must start with SELECT or WITH"
    m = _FORBIDDEN_RE.search(q)
    if m:
        return False, f"forbidden keyword: {m.group(1).upper()}"
    if len(q) > 4000:
        return False, "query is too long"
    return True, ""
