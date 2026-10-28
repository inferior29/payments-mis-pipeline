from __future__ import annotations

from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "payments.duckdb"
OUT_DIR = ROOT / "outputs"

DATA_START = date(2025, 10, 1)       # first day of data
DATA_END = date(2026, 9, 30)         # last day of data (12 complete months)

STATUSES = ["SUCCESS", "FAILED", "PENDING"]
METHODS = ["UPI", "CARD", "NETBANKING", "WALLET"]
