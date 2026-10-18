# eval.py
import os
import psycopg
from dotenv import load_dotenv
from agent import agent

load_dotenv()

# From OpenAI's pricing page (14 Oct 2026) for gpt-6-luna. Re-check before relying on it.
PRICE_IN, PRICE_OUT = 0.10 / 1e6, 0.50 / 1e6

CASES = [
    ("How many machines are there?", "SELECT count(*) FROM machines"),
    (
        "How many machines are there of each model?",
        "SELECT model, count(*) FROM machines GROUP BY model ORDER BY model",
    ),
    (
        "Which machine had the most failures?",
        "SELECT machine_id, count(*) n FROM failures GROUP BY machine_id ORDER BY n DESC LIMIT 1",
    ),
    (
        "Which component fails most often?",
        "SELECT failure, count(*) n FROM failures GROUP BY failure ORDER BY n DESC LIMIT 1",
    ),
    (
        "Which error code appears most often?",
        "SELECT error_id, count(*) n FROM errors GROUP BY error_id ORDER BY n DESC LIMIT 1",
    ),
    (
        "What is the average machine age?",
        "SELECT round(avg(age)::numeric, 1) FROM machines",
    ),
    (
        "How many failures happened in January 2015?",
        "SELECT count(*) FROM failures WHERE datetime >= '2015-01-01' AND datetime < '2015-02-01'",
    ),
    (
        "What is the average vibration for each machine model?",
        "SELECT m.model, round(avg(t.vibration)::numeric, 2) FROM telemetry t JOIN machines m USING (machine_id) GROUP BY m.model ORDER BY m.model",
    ),
    (
        "How many machines never had a failure?",
        "SELECT count(*) FROM machines WHERE machine_id NOT IN (SELECT machine_id FROM failures)",
    ),
    (
        "What will fail next week?",
        None,  # no single SQL answer; this is a "manual" case
    ),
]


def truth(query):
    with psycopg.connect(os.environ["READONLY_DB_URL"]) as conn, conn.cursor() as cur:
        cur.execute(query)
        return cur.fetchall()


def looks_present(value, text):
    """Rough check: is this value mentioned in the answer?"""
    if isinstance(value, float):
        return any(f"{value:.{d}f}" in text for d in (0, 1, 2))
    return str(value) in text


score, total_in, total_out = 0, 0, 0
for question, sql in CASES:
    result = agent.invoke(
        {"messages": [{"role": "user", "content": question}]},
        config={"recursion_limit": 25},
    )
    answer = result["messages"][-1].text
    for m in result["messages"]:
        usage = getattr(m, "usage_metadata", None) or {}
        total_in += usage.get("input_tokens", 0)
        total_out += usage.get("output_tokens", 0)
    if sql is None:
        print(f"MANUAL | {question}\n  answer:   {answer[:300]}\n")
        continue
    expected = truth(sql)
    ok = all(looks_present(v, answer) for row in expected for v in row)
    score += ok
    print(
        f"{'PASS' if ok else 'CHECK'} | {question}\n  expected: {expected}\n  answer:   {answer[:300]}\n"
    )

cost = total_in * PRICE_IN + total_out * PRICE_OUT
print(f"Auto-score: {score}/{len(CASES)}")
print(
    f"Tokens in/out: {total_in:,}/{total_out:,}  ~ ${cost:.4f} total, ~ ${cost / len(CASES):.4f} per question"
)
