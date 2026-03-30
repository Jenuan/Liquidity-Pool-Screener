"""
Persistence of position snapshots (value, PnL, fees, IL) for time series and dashboard.
Uses the same SQLite DB as log_store and state_store.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from lpbot.config_loader import PROJECT_ROOT


DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "lpbot.db"


def _ensure_db() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS position_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            position_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            value_usd REAL NOT NULL,
            unrealized_pnl_usd REAL NOT NULL,
            unrealized_pnl_pct REAL NOT NULL,
            fees_accrued_usd REAL NOT NULL,
            il_usd REAL NOT NULL,
            apr_snapshot REAL NOT NULL,
            pool_value_usd REAL
        )
        """
    )
    conn.commit()
    return conn


def append_position_snapshots(snapshots: List[Dict[str, Any]]) -> None:
    """Append one or more position snapshots. Each dict must have position_id, timestamp, value_usd, etc."""
    if not snapshots:
        return

    conn = _ensure_db()
    rows = []
    for s in snapshots:
        ts = s.get("timestamp")
        if isinstance(ts, datetime):
            ts = ts.isoformat()
        rows.append(
            (
                str(s.get("position_id", "")),
                str(ts),
                float(s.get("value_usd", 0.0)),
                float(s.get("unrealized_pnl_usd", 0.0)),
                float(s.get("unrealized_pnl_pct", 0.0)),
                float(s.get("fees_accrued_usd", 0.0)),
                float(s.get("il_usd", 0.0)),
                float(s.get("apr_snapshot", 0.0)),
                s.get("pool_value_usd") if s.get("pool_value_usd") is not None else None,
            )
        )
    conn.executemany(
        """
        INSERT INTO position_snapshots (
            position_id, timestamp, value_usd, unrealized_pnl_usd, unrealized_pnl_pct,
            fees_accrued_usd, il_usd, apr_snapshot, pool_value_usd
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()
    conn.close()


def load_position_snapshots(
    position_id: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> List[Dict[str, Any]]:
    """
    Load position snapshots, optionally filtered by position_id and time range.
    Returns list of dicts with keys position_id, timestamp, value_usd, unrealized_pnl_usd, etc.
    """
    conn = _ensure_db()
    query = "SELECT position_id, timestamp, value_usd, unrealized_pnl_usd, unrealized_pnl_pct, fees_accrued_usd, il_usd, apr_snapshot, pool_value_usd FROM position_snapshots WHERE 1=1"
    params: List[Any] = []

    if position_id is not None:
        query += " AND position_id = ?"
        params.append(position_id)
    if since is not None:
        query += " AND timestamp >= ?"
        params.append(since.isoformat())
    if until is not None:
        query += " AND timestamp <= ?"
        params.append(until.isoformat())

    query += " ORDER BY id ASC"
    cur = conn.execute(query, params)
    rows = cur.fetchall()
    conn.close()

    result = []
    for row in rows:
        pos_id, ts_str, value_usd, unrealized_pnl_usd, unrealized_pnl_pct, fees_accrued_usd, il_usd, apr_snapshot, pool_value_usd = row
        try:
            ts = datetime.fromisoformat(ts_str)
        except ValueError:
            ts = datetime.utcnow()
        result.append({
            "position_id": pos_id,
            "timestamp": ts,
            "value_usd": value_usd,
            "unrealized_pnl_usd": unrealized_pnl_usd,
            "unrealized_pnl_pct": unrealized_pnl_pct,
            "fees_accrued_usd": fees_accrued_usd,
            "il_usd": il_usd,
            "apr_snapshot": apr_snapshot,
            "pool_value_usd": pool_value_usd,
        })
    return result
