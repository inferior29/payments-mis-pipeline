"""Pipeline: load data -> SQL views -> 10 checks -> commentary -> figure gate -> Excel MIS.

    python -m mis.run                          # offline template commentary
    ANTHROPIC_API_KEY=... python -m mis.run --commentary claude
    python -m mis.run --commentary auto        # Claude if a key is set, else template (used by GitHub Actions)

Exit code 1 (and no Excel file) if any data check fails or any commentary figure does not match the KPIs.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb

from .checks import run_checks
from .commentary import CommentaryMismatch, approve, pick_backend
from .config import DB_PATH, OUT_DIR
from .excel_report import write_excel
from .generate_data import generate, load_duckdb
from .kpis import build_context, monthly_kpis

VIEWS_SQL = Path(__file__).parent / "sql" / "views.sql"


def build_report(con: duckdb.DuckDBPyConnection, backend, out_dir: Path) -> Path:
    """Returns the workbook path, or raises (data checks failed / commentary figure mismatch). Nothing is written then."""
    con.execute(VIEWS_SQL.read_text())
    checks = run_checks(con)
    failed = checks[checks["status"] == "FAIL"]
    if len(failed):
        raise RuntimeError("Data checks failed, report not published: " + "; ".join(
            f"{r.check} ({r.violations} violations)" for r in failed.itertuples()))

    ctx = build_context(con)
    commentary = approve(backend.write(ctx), ctx)  # raises CommentaryMismatch on any unmatched figure

    kpis = monthly_kpis(con)
    latest = kpis["month"].max()
    methods = con.execute("SELECT * FROM v_method_monthly WHERE month = ? ORDER BY gmv DESC", [latest]).fetchdf()
    merchants = con.execute("SELECT * FROM v_top_merchants WHERE month = ? ORDER BY gmv_rank", [latest]).fetchdf()
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"payments_mis_{latest:%Y-%m}.xlsx"
    write_excel(path, kpis, methods, merchants, checks, commentary, backend.name, ctx["latest_month"])
    return path


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rows", type=int, default=500_000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--regen", action="store_true", help="rebuild the database even if it exists")
    ap.add_argument("--commentary", choices=["template", "claude", "auto"], default="template")
    ap.add_argument("--out", default=str(OUT_DIR))
    a = ap.parse_args()

    if a.regen or not Path(DB_PATH).exists():
        con = load_duckdb(generate(a.rows, a.seed))
    else:
        con = duckdb.connect(str(DB_PATH))
    try:
        path = build_report(con, pick_backend(a.commentary), Path(a.out))
    except (RuntimeError, CommentaryMismatch) as err:
        print(f"BLOCKED: {err}", file=sys.stderr)
        sys.exit(1)
    rows = con.execute("SELECT COUNT(*) FROM payments").fetchone()[0]
    print(f"Published {path} from {rows:,} transactions; 10/10 checks passed; commentary figures verified.")


if __name__ == "__main__":
    main()
