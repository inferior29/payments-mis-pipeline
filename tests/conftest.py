from pathlib import Path

import duckdb
import pandas as pd
import pytest

from mis.generate_data import generate

VIEWS = Path(__file__).resolve().parents[1] / "src" / "mis" / "sql" / "views.sql"


def make_con(df: pd.DataFrame) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.register("df_in", df)
    con.execute("CREATE TABLE payments AS SELECT * FROM df_in")
    con.unregister("df_in")
    con.execute(VIEWS.read_text())
    return con


def tiny() -> pd.DataFrame:
    """Two months with hand-calculated KPIs (see test_views.py)."""
    rows = [
        ("T1", "2025-10-05 10:00", "M1", "UPI", "SUCCESS", 100.0, 0.0),
        ("T2", "2025-10-09 11:00", "M1", "CARD", "SUCCESS", 200.0, 50.0),
        ("T3", "2025-10-12 12:00", "M2", "UPI", "FAILED", 300.0, 0.0),
        ("T4", "2025-10-20 13:00", "M2", "WALLET", "PENDING", 400.0, 0.0),
        ("T5", "2025-11-03 09:00", "M1", "UPI", "SUCCESS", 450.0, 0.0),
        ("T6", "2025-11-14 15:00", "M2", "NETBANKING", "FAILED", 150.0, 0.0),
    ]
    df = pd.DataFrame(rows, columns=["txn_id", "txn_ts", "merchant_id", "payment_method", "status", "amount", "refund_amount"])
    df["txn_ts"] = pd.to_datetime(df["txn_ts"])
    return df


@pytest.fixture
def tiny_con():
    return make_con(tiny())


@pytest.fixture(scope="session")
def big_df():
    return generate(n=40_000, seed=5)
