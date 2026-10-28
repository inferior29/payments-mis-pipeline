"""Ten automated data-accuracy checks. Each counts violations (0 = pass).

The report is not published unless all ten pass.
"""
from __future__ import annotations

import duckdb
import pandas as pd

from .config import DATA_END, DATA_START, METHODS, STATUSES

_q = lambda items: ", ".join(f"'{i}'" for i in items)
GMV_TOLERANCE = 0.01  # INR; float summation order can differ in the last decimals

CHECKS: list[tuple[str, str, str]] = [
    ("txn_id present", "Every transaction has an id",
     "SELECT COUNT(*) FROM payments WHERE txn_id IS NULL"),
    ("txn_id unique", "No transaction is loaded twice",
     "SELECT COUNT(*) FROM (SELECT txn_id FROM payments GROUP BY txn_id HAVING COUNT(*) > 1)"),
    ("amount positive", "Amount is present and greater than zero",
     "SELECT COUNT(*) FROM payments WHERE amount IS NULL OR amount <= 0"),
    ("status valid", f"Status is one of {STATUSES}",
     f"SELECT COUNT(*) FROM payments WHERE status IS NULL OR status NOT IN ({_q(STATUSES)})"),
    ("payment method valid", f"Payment method is one of {METHODS}",
     f"SELECT COUNT(*) FROM payments WHERE payment_method IS NULL OR payment_method NOT IN ({_q(METHODS)})"),
    ("refund within amount", "Refund is not negative and does not exceed the transaction amount",
     "SELECT COUNT(*) FROM payments WHERE refund_amount < 0 OR refund_amount > amount"),
    ("refund only on SUCCESS", "Only successful transactions carry a refund",
     "SELECT COUNT(*) FROM payments WHERE refund_amount > 0 AND status <> 'SUCCESS'"),
    ("timestamps in window", f"Every timestamp falls between {DATA_START} and {DATA_END}",
     f"SELECT COUNT(*) FROM payments WHERE txn_ts IS NULL OR txn_ts < TIMESTAMP '{DATA_START}' "
     f"OR txn_ts >= TIMESTAMP '{DATA_END}' + INTERVAL 1 DAY"),
    ("KPI GMV reconciles to raw data", "Sum of monthly GMV in the KPI view equals SUM(amount) of SUCCESS rows in the table",
     f"SELECT CASE WHEN ABS(COALESCE((SELECT SUM(gmv) FROM v_monthly_kpis), 0) - "
     f"COALESCE((SELECT SUM(amount) FROM payments WHERE status = 'SUCCESS'), 0)) > {GMV_TOLERANCE} THEN 1 ELSE 0 END"),
    ("KPI transaction count reconciles", "Sum of monthly transaction counts in the KPI view equals the table row count",
     "SELECT CASE WHEN COALESCE((SELECT SUM(txn_count) FROM v_monthly_kpis), 0) <> (SELECT COUNT(*) FROM payments) THEN 1 ELSE 0 END"),
]
assert len(CHECKS) == 10


def run_checks(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    rows = []
    for name, description, sql in CHECKS:
        violations = int(con.execute(sql).fetchone()[0])
        rows.append({"check": name, "description": description, "violations": violations,
                     "status": "PASS" if violations == 0 else "FAIL"})
    return pd.DataFrame(rows)
