
import hashlib
import json
import random
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "refunds.db"


def connect_db(read_only=False):
    """Open the project database, optionally in read-only mode."""
    if read_only:
        connection = sqlite3.connect(
            f"{DB_PATH.resolve().as_uri()}?mode=ro",
            uri=True,
        )
        connection.execute("PRAGMA query_only = ON")
        return connection

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(DB_PATH)


def initialize_database(seed=42, row_count=300):
    """Create reproducible sample orders and refunds."""
    rng = random.Random(seed)

    with connect_db() as conn:
        conn.executescript("""
            DROP TABLE IF EXISTS refunds;
            DROP TABLE IF EXISTS orders;

            CREATE TABLE orders (
                order_id INTEGER PRIMARY KEY,
                seller_id INTEGER NOT NULL,
                zone TEXT NOT NULL,
                pincode_tier INTEGER NOT NULL,
                payment_mode TEXT NOT NULL,
                order_date TEXT NOT NULL
            );

            CREATE TABLE refunds (
                refund_id INTEGER PRIMARY KEY,
                order_id INTEGER NOT NULL,
                refund_reason TEXT,
                refund_status TEXT NOT NULL,
                refund_amount REAL,
                request_date TEXT NOT NULL,
                FOREIGN KEY(order_id) REFERENCES orders(order_id)
            );
        """)

        reasons = [
            "damaged item",
            "late delivery",
            "wrong item",
            "customer cancellation",
            "payment issue",
        ]
        statuses = ["requested", "approved", "rejected", "processed"]
        modes = ["UPI", "card", "COD"]
        zones = ["North", "South", "East", "West"]

        for order_id in range(1, row_count + 1):
            tier = rng.choices([1, 2, 3], weights=[3, 4, 6])[0]
            seller_id = rng.choice([40218, 40219, 40220, 40221])
            payment = rng.choice(modes)
            zone = rng.choice(zones)
            order_date = f"2026-{rng.randint(1, 10):02d}-{rng.randint(1, 28):02d}"

            conn.execute(
                """INSERT INTO orders
                   (order_id, seller_id, zone, pincode_tier,
                    payment_mode, order_date)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (order_id, seller_id, zone, tier, payment, order_date),
            )

            # Preserve occasional missing fields as SQL NULL.
            reason = None if order_id % 37 == 0 else rng.choice(reasons)
            amount = None if order_id % 41 == 0 else round(
                rng.uniform(150, 5000), 2
            )
            conn.execute(
                """INSERT INTO refunds
                   (order_id, refund_reason, refund_status,
                    refund_amount, request_date)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    order_id,
                    reason,
                    rng.choice(statuses),
                    amount,
                    order_date,
                ),
            )

    return DB_PATH


def run_sql(read_only_query):
    """Run one read-only SQL statement and return evidence metadata."""
    query = read_only_query.strip()

    if not query:
        raise ValueError("SQL query cannot be empty")

    # The SQLite read-only connection and query_only setting are the
    # actual security controls; this check also rejects multiple statements.
    if ";" in query.rstrip(";"):
        raise ValueError("Only one SQL statement is allowed")

    with connect_db(read_only=True) as conn:
        cursor = conn.execute(query)
        if cursor.description is None:
            raise ValueError("Query must return rows")

        columns = [column[0] for column in cursor.description]
        rows = cursor.fetchall()

    canonical = json.dumps(
        {"columns": columns, "rows": rows},
        sort_keys=True,
        default=str,
        separators=(",", ":"),
    )
    result_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    return {
        "sql": query,
        "columns": columns,
        "rows": rows,
        "row_count": len(rows),
        "sha256": result_hash,
    }


if __name__ == "__main__":
    path = initialize_database()
    print(f"Database created: {path}")
    print(run_sql(
        "SELECT pincode_tier, COUNT(*) AS order_count "
        "FROM orders GROUP BY pincode_tier ORDER BY pincode_tier"
    ))
