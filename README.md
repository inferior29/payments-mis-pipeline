# Automated Payments MIS Reporting Pipeline

Turns a 500,000-transaction payments table into a formatted Excel MIS report, with two gates that stop a bad report
from going out. **All data is synthetic.**

```
payments (DuckDB) ─► SQL views (CTEs, window functions) ─► 10 data-accuracy checks ──► any FAIL = no report
                              │                                                         
                              └─► KPI context ─► commentary (Claude | template) ─► figure gate ──► any unmatched number = no report
                                                                                              │
                                                                          Excel MIS workbook (6 sheets, chart, formats)
```

## What it does

- **Models the data in SQL.** `src/mis/sql/views.sql` defines monthly KPIs (GMV, success rate, refund rate, month-on-month growth via `LAG`), payment-method mix (share of GMV via `SUM() OVER (PARTITION BY month)`) and top merchants (`RANK() OVER`).
- **Runs 10 automated data-accuracy checks before publishing:** id present and unique, amount positive, valid status, valid payment method, refund within amount, refund only on successful payments, timestamps inside the reporting window, KPI GMV reconciles to the raw table, KPI transaction count reconciles to the row count. Each check has a test that breaks the data and confirms it fails.
- **Writes the commentary from computed KPIs.** Claude receives the formatted KPI table and returns structured JSON (`headline`, `bullets[]`) through a forced tool call. An offline template writer produces the same shape for runs without an API key.
- **Blocks the report if any figure does not match.** Every number in the commentary must appear in the KPI context exactly as displayed. A wrong, invented or re-rounded figure raises `CommentaryMismatch`, the run exits with code 1 and no workbook is written.
- **Publishes an Excel MIS** with real numeric cells and number formats, a GMV chart, method and merchant tables, and the data-check results.
- **Runs weekly on GitHub Actions** (`.github/workflows/weekly_mis.yml`): Mondays 02:30 UTC, also runnable by hand. It runs the tests, builds the report and uploads the workbook as an artifact. If the `ANTHROPIC_API_KEY` repository secret exists it uses Claude for the commentary, otherwise the template.

## Run it

```bash
pip install -r requirements.txt
export PYTHONPATH=src                                   # or: pip install -e .
python -m mis.run --regen                               # generates 500,000 transactions and builds outputs/payments_mis_2026-09.xlsx
pytest -q                                               # 26 tests

export ANTHROPIC_API_KEY=...                            # optional, read from the environment only
python -m mis.run --commentary claude
```

## Sample output (latest month, September 2026)

GMV INR 11.09 crore, up 5.3% on August; 52,369 transactions; success rate 96.7%; refunds 1.40% of GMV.
The checked-in `outputs/payments_mis_2026-09.xlsx` was written with the template commentary.

## Status of each claim

| Piece | Status |
|---|---|
| SQL views, 10 checks, figure gate, Excel report | Built; covered by 26 tests; verified against an independent pandas calculation |
| Claude commentary | Unit-tested against a fake client (forced tool call, structure, gate). **Not yet run against the live API** |
| Weekly GitHub Actions schedule | Workflow is written; it has not run until the repo is pushed and a run appears in the Actions tab |

## What the figure gate does not catch

It verifies numbers, not meaning. A correct figure placed in a misleading sentence (for example describing a decline as
growth) would pass. Keep a human read of the commentary before it is sent. The data is synthetic and one month of
commentary is generated per run.

## Layout

```
src/mis/  config.py  generate_data.py  sql/views.sql  checks.py  kpis.py  commentary.py  excel_report.py  run.py
tests/    SQL vs hand calculation and pandas, every check broken on purpose, gate cases, Excel contents, blocked runs
.github/workflows/weekly_mis.yml
```
