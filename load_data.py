# load_data.py  (version 2: small batches, each committed, with automatic retries)
import os
import time

import psycopg
from dotenv import load_dotenv

load_dotenv()
DB_URL = os.environ["ADMIN_DB_URL"]

BATCH_ROWS = 50_000  # rows sent per batch; lower it to 20_000 on a weak connection
MAX_TRIES = 4  # attempts per batch before giving up

DDL = """
DROP TABLE IF EXISTS telemetry, errors, maintenance, failures, machines;

CREATE TABLE machines (
    machine_id INTEGER PRIMARY KEY,
    model      TEXT    NOT NULL,
    age        INTEGER NOT NULL
);

CREATE TABLE telemetry (
    datetime   TIMESTAMP NOT NULL,
    machine_id INTEGER   NOT NULL REFERENCES machines(machine_id),
    volt       DOUBLE PRECISION,
    rotate     DOUBLE PRECISION,
    pressure   DOUBLE PRECISION,
    vibration  DOUBLE PRECISION
);

CREATE TABLE errors (
    datetime   TIMESTAMP NOT NULL,
    machine_id INTEGER   NOT NULL REFERENCES machines(machine_id),
    error_id   TEXT      NOT NULL
);

CREATE TABLE maintenance (
    datetime   TIMESTAMP NOT NULL,
    machine_id INTEGER   NOT NULL REFERENCES machines(machine_id),
    component  TEXT      NOT NULL
);

CREATE TABLE failures (
    datetime   TIMESTAMP NOT NULL,
    machine_id INTEGER   NOT NULL REFERENCES machines(machine_id),
    failure    TEXT      NOT NULL
);
"""

INDEXES = """
CREATE INDEX ON telemetry   (machine_id, datetime);
CREATE INDEX ON errors      (machine_id, datetime);
CREATE INDEX ON maintenance (machine_id, datetime);
CREATE INDEX ON failures    (machine_id, datetime);
"""

COMMENTS = """
COMMENT ON TABLE machines    IS 'One row per machine: its model type and age in years';
COMMENT ON TABLE telemetry   IS 'Hourly average sensor readings per machine during 2015';
COMMENT ON TABLE errors      IS 'Non-breaking errors logged while a machine was running';
COMMENT ON TABLE maintenance IS 'Component replacements, scheduled or unscheduled';
COMMENT ON TABLE failures    IS 'Component replacements caused by a failure';
COMMENT ON COLUMN telemetry.volt        IS 'Voltage, hourly average';
COMMENT ON COLUMN telemetry.rotate      IS 'Rotation speed, hourly average';
COMMENT ON COLUMN telemetry.pressure    IS 'Pressure, hourly average';
COMMENT ON COLUMN telemetry.vibration   IS 'Vibration, hourly average';
COMMENT ON COLUMN errors.error_id       IS 'Error code, e.g. error1 to error5';
COMMENT ON COLUMN maintenance.component IS 'Component replaced, e.g. comp1 to comp4';
COMMENT ON COLUMN failures.failure      IS 'Component that failed, e.g. comp1 to comp4';
"""

# (table name, CSV file, columns in the SAME order as the CSV header)
FILES = [
    ("machines", "PdM_machines.csv", "machine_id, model, age"),
    (
        "telemetry",
        "PdM_telemetry.csv",
        "datetime, machine_id, volt, rotate, pressure, vibration",
    ),
    ("errors", "PdM_errors.csv", "datetime, machine_id, error_id"),
    ("maintenance", "PdM_maint.csv", "datetime, machine_id, component"),
    ("failures", "PdM_failures.csv", "datetime, machine_id, failure"),
]


def connect():
    # keepalives make the connection send small "still here" signals,
    # so a quiet network link is less likely to be dropped.
    return psycopg.connect(
        DB_URL,
        connect_timeout=20,
        keepalives=1,
        keepalives_idle=30,
        keepalives_interval=10,
        keepalives_count=5,
    )


def read_batches(path):
    """Yield the CSV's data lines (header skipped) in chunks of BATCH_ROWS lines."""
    with open(path, "r", encoding="utf-8", newline="") as f:
        f.readline()  # skip the header line
        batch = []
        for line in f:
            if not line.strip():
                continue
            batch.append(line if line.endswith("\n") else line + "\n")
            if len(batch) >= BATCH_ROWS:
                yield batch
                batch = []
        if batch:
            yield batch


def load_table(table, fname, cols):
    copy_sql = f"COPY {table} ({cols}) FROM STDIN WITH (FORMAT csv)"
    expected = 0
    for n, batch in enumerate(read_batches(os.path.join("data", fname)), start=1):
        for attempt in range(1, MAX_TRIES + 1):
            try:
                with connect() as conn, conn.cursor() as cur:
                    with cur.copy(copy_sql) as copy:
                        copy.write("".join(batch))
                # Leaving the 'with connect()' block commits this batch only.
                break
            except psycopg.OperationalError as e:
                if attempt == MAX_TRIES:
                    raise
                wait = 5 * attempt
                print(
                    f"\n  batch {n} failed ({str(e).splitlines()[0]}); retry {attempt} in {wait}s"
                )
                time.sleep(wait)
        expected += len(batch)
        print(f"  {table}: {expected:,} rows sent", end="\r", flush=True)
    print()
    return expected


with connect() as conn:
    conn.execute(DDL)
print("Tables created.")

expected_counts = {}
for table, fname, cols in FILES:
    expected_counts[table] = load_table(table, fname, cols)

with connect() as conn:
    conn.execute(INDEXES)
    conn.execute(COMMENTS)
    print("Indexes and comments added.\n")
    print(f"{'table':12} {'in CSV':>10} {'in database':>12}")
    for table, expected in expected_counts.items():
        actual = conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        flag = "" if actual == expected else "   <-- MISMATCH"
        print(f"{table:12} {expected:>10,} {actual:>12,}{flag}")
print("\nDone.")
