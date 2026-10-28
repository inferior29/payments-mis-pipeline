-- KPI views. GMV = amount of SUCCESS transactions. Refund rate = refund value / GMV.

CREATE OR REPLACE VIEW v_monthly_kpis AS
WITH monthly AS (
    SELECT date_trunc('month', txn_ts)::DATE                         AS month,
           COUNT(*)                                                  AS txn_count,
           COUNT(*) FILTER (WHERE status = 'SUCCESS')                AS success_count,
           COALESCE(SUM(amount) FILTER (WHERE status = 'SUCCESS'), 0) AS gmv,
           COALESCE(SUM(refund_amount), 0)                           AS refund_value
    FROM payments
    GROUP BY 1
), rates AS (
    SELECT *,
           success_count * 1.0 / txn_count                           AS success_rate,
           CASE WHEN gmv > 0 THEN refund_value / gmv END             AS refund_rate
    FROM monthly
)
SELECT month, txn_count, success_count, gmv, refund_value, success_rate, refund_rate,
       LAG(gmv) OVER (ORDER BY month)                                AS prev_gmv,
       gmv / NULLIF(LAG(gmv) OVER (ORDER BY month), 0) - 1           AS gmv_mom_growth,
       txn_count * 1.0 / NULLIF(LAG(txn_count) OVER (ORDER BY month), 0) - 1 AS txn_mom_growth
FROM rates;

CREATE OR REPLACE VIEW v_method_monthly AS
WITH m AS (
    SELECT date_trunc('month', txn_ts)::DATE AS month, payment_method,
           COUNT(*)                                                   AS txn_count,
           COUNT(*) FILTER (WHERE status = 'SUCCESS')                 AS success_count,
           COALESCE(SUM(amount) FILTER (WHERE status = 'SUCCESS'), 0) AS gmv
    FROM payments
    GROUP BY 1, 2
)
SELECT month, payment_method, txn_count, gmv,
       success_count * 1.0 / txn_count                AS success_rate,
       gmv / SUM(gmv) OVER (PARTITION BY month)       AS gmv_share
FROM m;

CREATE OR REPLACE VIEW v_top_merchants AS
WITH m AS (
    SELECT date_trunc('month', txn_ts)::DATE AS month, merchant_id,
           COALESCE(SUM(amount) FILTER (WHERE status = 'SUCCESS'), 0) AS gmv
    FROM payments
    GROUP BY 1, 2
), ranked AS (
    SELECT month, merchant_id, gmv,
           RANK() OVER (PARTITION BY month ORDER BY gmv DESC) AS gmv_rank,
           gmv / SUM(gmv) OVER (PARTITION BY month)           AS gmv_share
    FROM m
)
SELECT * FROM ranked WHERE gmv_rank <= 10;
