"""KPI extraction and the one place where numbers are formatted for people (and for the AI)."""
from __future__ import annotations

import duckdb
import pandas as pd


def fmt_cr(x: float) -> str:
    return f"₹{x / 1e7:,.2f} Cr"


def fmt_pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def fmt_pct2(x: float) -> str:
    return f"{x * 100:.2f}%"


def fmt_growth(x) -> str:
    return "n/a" if pd.isna(x) else f"{x * 100:+.1f}%"


def month_label(d) -> str:
    return pd.Timestamp(d).strftime("%b %Y")


def monthly_kpis(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return con.execute("SELECT * FROM v_monthly_kpis ORDER BY month").fetchdf()


def build_context(con: duckdb.DuckDBPyConnection, n_months: int = 4) -> dict:
    """Everything the commentary is allowed to quote, already formatted exactly as it should appear."""
    kpis = monthly_kpis(con)
    latest = kpis["month"].max()
    methods = con.execute("SELECT * FROM v_method_monthly WHERE month = ? ORDER BY gmv DESC", [latest]).fetchdf()
    merchants = con.execute("SELECT * FROM v_top_merchants WHERE month = ? AND gmv_rank <= 3 ORDER BY gmv_rank", [latest]).fetchdf()
    return {
        "currency": "INR; Cr means crore (ten million)",
        "latest_month": month_label(latest),
        "months": [
            {"month": month_label(r.month), "gmv": fmt_cr(r.gmv), "transactions": f"{int(r.txn_count):,}",
             "success_rate": fmt_pct(r.success_rate), "refund_rate": fmt_pct2(r.refund_rate),
             "gmv_mom_growth": fmt_growth(r.gmv_mom_growth)}
            for r in kpis.tail(n_months).itertuples()
        ],
        "payment_methods_latest_month": [
            {"method": r.payment_method, "gmv_share": fmt_pct(r.gmv_share), "success_rate": fmt_pct(r.success_rate)}
            for r in methods.itertuples()
        ],
        "top_merchants_latest_month": [
            {"merchant": r.merchant_id, "gmv_share": fmt_pct(r.gmv_share)} for r in merchants.itertuples()
        ],
    }
