import pandas as pd
import pytest

from mis.checks import CHECKS, run_checks
from mis.kpis import monthly_kpis
from conftest import make_con, tiny


def test_monthly_kpis_match_hand_calculation(tiny_con):
    k = monthly_kpis(tiny_con).set_index(pd.to_datetime(monthly_kpis(tiny_con)["month"]).dt.strftime("%Y-%m"))
    oct_, nov = k.loc["2025-10"], k.loc["2025-11"]
    assert (oct_.txn_count, oct_.success_count, oct_.gmv, oct_.refund_value) == (4, 2, 300.0, 50.0)
    assert oct_.success_rate == 0.5 and oct_.refund_rate == pytest.approx(50 / 300)
    assert pd.isna(oct_.gmv_mom_growth)                               # no previous month
    assert (nov.txn_count, nov.gmv) == (2, 450.0)
    assert nov.gmv_mom_growth == pytest.approx(0.5)                   # 450 / 300 - 1
    assert nov.txn_mom_growth == pytest.approx(-0.5)                  # 2 / 4 - 1


def test_method_share_and_merchant_rank(tiny_con):
    m = tiny_con.execute("SELECT * FROM v_method_monthly WHERE month = DATE '2025-10-01'").fetchdf().set_index("payment_method")
    assert m.loc["UPI", "gmv_share"] == pytest.approx(100 / 300) and m.loc["CARD", "gmv_share"] == pytest.approx(200 / 300)
    assert m["gmv_share"].sum() == pytest.approx(1.0)
    top = tiny_con.execute("SELECT merchant_id, gmv_rank FROM v_top_merchants WHERE month = DATE '2025-10-01' ORDER BY gmv_rank").fetchall()
    assert top[0] == ("M1", 1)                                         # M1 has 300 GMV, M2 has 0 (all failed/pending)


def test_there_are_ten_checks_and_all_pass_on_clean_data(tiny_con):
    res = run_checks(tiny_con)
    assert len(res) == 10 == len(CHECKS)
    assert (res["status"] == "PASS").all()


CORRUPTIONS = {
    "txn_id present": "UPDATE payments SET txn_id = NULL WHERE txn_id = 'T1'",
    "txn_id unique": "UPDATE payments SET txn_id = 'T2' WHERE txn_id = 'T1'",
    "amount positive": "UPDATE payments SET amount = -5 WHERE txn_id = 'T1'",
    "status valid": "UPDATE payments SET status = 'DONE' WHERE txn_id = 'T1'",
    "payment method valid": "UPDATE payments SET payment_method = 'CHEQUE' WHERE txn_id = 'T1'",
    "refund within amount": "UPDATE payments SET refund_amount = 999 WHERE txn_id = 'T1'",
    "refund only on SUCCESS": "UPDATE payments SET refund_amount = 10 WHERE txn_id = 'T3'",
    "timestamps in window": "UPDATE payments SET txn_ts = TIMESTAMP '2027-01-01' WHERE txn_id = 'T1'",
}


@pytest.mark.parametrize("check,sql", CORRUPTIONS.items())
def test_each_data_check_catches_its_corruption(check, sql):
    con = make_con(tiny())
    con.execute(sql)
    res = run_checks(con).set_index("check")
    assert res.loc[check, "status"] == "FAIL", f"{check} did not fail"


def test_reconciliation_checks_catch_a_view_that_drops_a_month():
    con = make_con(tiny())
    # Simulate a buggy KPI layer: snapshot the view into a table, drop November, and point the view at the snapshot.
    con.execute("CREATE TABLE kpi_snapshot AS SELECT * FROM v_monthly_kpis WHERE month < DATE '2025-11-01'")
    con.execute("CREATE OR REPLACE VIEW v_monthly_kpis AS SELECT * FROM kpi_snapshot")
    res = run_checks(con).set_index("check")
    assert res.loc["KPI GMV reconciles to raw data", "status"] == "FAIL"
    assert res.loc["KPI transaction count reconciles", "status"] == "FAIL"


def test_sql_kpis_agree_with_an_independent_pandas_calculation(big_df):
    con = make_con(big_df)
    sql = monthly_kpis(con)
    d = big_df.assign(month=big_df["txn_ts"].dt.to_period("M").dt.to_timestamp())
    gmv = d[d.status == "SUCCESS"].groupby("month")["amount"].sum()
    cnt = d.groupby("month").size()
    for r in sql.itertuples():
        assert r.gmv == pytest.approx(gmv[pd.Timestamp(r.month)], rel=1e-9)
        assert r.txn_count == cnt[pd.Timestamp(r.month)]
