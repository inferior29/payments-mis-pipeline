"""Synthetic payments dataset loaded into DuckDB (500,000 transactions by default)."""
from __future__ import annotations

import argparse
import calendar
from datetime import datetime
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from .config import DATA_START, DB_PATH, METHODS

BASE_SUCCESS = {"UPI": 0.965, "CARD": 0.93, "NETBANKING": 0.90, "WALLET": 0.95}
AMOUNT_MEDIAN = {"UPI": 900, "CARD": 2600, "NETBANKING": 3800, "WALLET": 600}
METHOD_P = [0.62, 0.22, 0.08, 0.08]


def generate(n: int = 500_000, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    months = [(DATA_START.year + (DATA_START.month - 1 + k) // 12, (DATA_START.month - 1 + k) % 12 + 1) for k in range(12)]
    growth = 1.045 ** np.arange(12)                                  # volume grows ~4.5% a month
    month_p = growth / growth.sum()
    month_idx = rng.choice(12, size=n, p=month_p)

    days_in = np.array([calendar.monthrange(y, m)[1] for y, m in months])
    day = (rng.random(n) * days_in[month_idx]).astype(int)           # 0-based day of month
    seconds = rng.integers(0, 86_400, n)
    starts = np.array([np.datetime64(datetime(y, m, 1), "s") for y, m in months])
    ts = starts[month_idx] + day.astype("timedelta64[D]") + seconds.astype("timedelta64[s]")

    method_i = rng.choice(len(METHODS), size=n, p=METHOD_P)
    method = np.array(METHODS)[method_i]
    p_success = np.array([BASE_SUCCESS[m] for m in METHODS])[method_i] + rng.normal(0, 0.004, n) + 0.0015 * month_idx
    success = rng.random(n) < np.clip(p_success, 0, 1)
    status = np.where(success, "SUCCESS", np.where(rng.random(n) < 0.9, "FAILED", "PENDING"))

    median = np.array([AMOUNT_MEDIAN[m] for m in METHODS])[method_i]
    amount = np.clip(rng.lognormal(np.log(median), 0.9), 10, 500_000).round(2)

    ranks = np.arange(1, 401)
    merchant_p = (1 / ranks**0.8) / (1 / ranks**0.8).sum()
    merchant = np.array([f"M{i:04d}" for i in ranks])[rng.choice(400, size=n, p=merchant_p)]

    refund = np.where(success & (rng.random(n) < 0.025), (amount * rng.uniform(0.2, 1.0, n)).round(2), 0.0)

    df = pd.DataFrame({"txn_ts": ts, "merchant_id": merchant, "payment_method": method,
                       "status": status, "amount": amount, "refund_amount": refund})
    df = df.sort_values("txn_ts", kind="stable").reset_index(drop=True)
    df.insert(0, "txn_id", [f"TXN{i:09d}" for i in range(1, n + 1)])
    return df


def load_duckdb(df: pd.DataFrame, path: Path = DB_PATH) -> duckdb.DuckDBPyConnection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    con = duckdb.connect(str(path))
    con.register("df_in", df)
    con.execute("CREATE TABLE payments AS SELECT * FROM df_in")
    con.unregister("df_in")
    return con


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rows", type=int, default=500_000)
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    con = load_duckdb(generate(a.rows, a.seed))
    print(f"loaded {con.execute('SELECT COUNT(*) FROM payments').fetchone()[0]:,} transactions into {DB_PATH}")


if __name__ == "__main__":
    main()
