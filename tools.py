# tools.py
from langchain.tools import tool
from db import run_sql

MAX_CHARS = 4000  # never send more than this many characters back to the model


def _public_tables() -> list[str]:
    _, rows = run_sql(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_type = 'BASE TABLE' "
        "ORDER BY table_name",
        max_rows=100,
    )
    return [r[0] for r in rows]


@tool
def sql_db_list_tables() -> str:
    """Input is an empty string, output is a comma-separated list of tables in the database."""
    return ", ".join(_public_tables())


@tool
def sql_db_schema(table_names: str) -> str:
    """Input to this tool is a comma-separated list of tables, output is the schema and sample rows for those tables.
    Be sure that the tables actually exist by calling sql_db_list_tables first!
    Example Input: table1, table2, table3"""
    valid = set(_public_tables())
    out = []
    for name in [t.strip() for t in table_names.split(",") if t.strip()]:
        if name not in valid:
            out.append(f"Error: table {name!r} not found in database")
            continue
        # Safe to interpolate: name came from the database's own table list.
        _, r = run_sql(f"SELECT obj_description('public.{name}'::regclass, 'pg_class')")
        table_comment = (r[0][0] if r else None) or ""
        _, cols = run_sql(
            "SELECT column_name, data_type, "
            f"col_description('public.{name}'::regclass, ordinal_position) "
            "FROM information_schema.columns "
            f"WHERE table_schema = 'public' AND table_name = '{name}' "
            "ORDER BY ordinal_position",
            max_rows=100,
        )
        _, sample = run_sql(f'SELECT * FROM "{name}" LIMIT 3')
        lines = [f"TABLE {name}  -- {table_comment}"]
        for col, dtype, comment in cols:
            lines.append(f"  {col} {dtype}" + (f"  -- {comment}" if comment else ""))
        lines.append("/* 3 sample rows:")
        lines.extend("   " + " | ".join(str(v) for v in row) for row in sample)
        lines.append("*/")
        out.append("\n".join(lines))
    return "\n\n".join(out)


@tool
def sql_db_query(query: str) -> str:
    """Input to this tool is a detailed and correct SQL query, output is a result from the database.
    If the query is not correct, an error message will be returned.
    If an error is returned, rewrite the query, check the query, and try again.
    If you encounter an issue with an unknown column, use sql_db_schema to query the correct table fields."""
    try:
        cols, rows = run_sql(query)
        text = str(cols) + "\n" + "\n".join(str(r) for r in rows)
        return text[:MAX_CHARS]
    except Exception as e:
        return f"Error: {e}"


tools = [sql_db_list_tables, sql_db_schema, sql_db_query]
