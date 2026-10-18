# test_guardrail.py
from guardrail import validate_sql

cases = {
    "SELECT machine_id, count(*) FROM failures GROUP BY machine_id": True,
    "with t as (select 1) select * from t": True,
    "SELECT update_time FROM x": True,  # whole-word check
    "DELETE FROM failures": False,
    "SELECT 1; DROP TABLE failures": False,
    "SELECT pg_sleep(30)": False,
    "/* sneaky */ UPDATE machines SET age = 0": False,
}
for q, expected in cases.items():
    ok, reason = validate_sql(q)
    status = "PASS" if ok == expected else "FAIL"
    print(f"{status}  ok={ok!s:5}  {reason:35}  {q}")
