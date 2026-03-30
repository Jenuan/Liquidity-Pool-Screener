"""
Persistência do estado do portfólio em SQLite.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, fields
from datetime import datetime
from pathlib import Path
from typing import Any, List

from lpbot.config_loader import PROJECT_ROOT, load_risk_config
from lpbot.models.portfolio import PortfolioState, Position


DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "lpbot.db"


def _ensure_db() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS portfolio_state_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            cash_usd REAL NOT NULL,
            realized_pnl_usd REAL NOT NULL,
            unrealized_pnl_usd REAL NOT NULL,
            cumulative_fees_usd REAL NOT NULL,
            cumulative_il_usd REAL NOT NULL,
            positions_json TEXT NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def _serialize_positions(positions: list[Position]) -> str:
    return json.dumps([asdict(p) for p in positions], default=str)


def _deserialize_positions(data: str) -> list[Position]:
    if not data:
        return []

    from lpbot.models.portfolio import Position, RiskLevel

    valid = {f.name for f in fields(Position)}
    raw_list: list[dict[str, Any]] = json.loads(data)
    positions: list[Position] = []
    for item in raw_list:
        clean = {k: v for k, v in item.items() if k in valid}
        risk_level = clean.get("risk_level", "MEDIUM")
        if isinstance(risk_level, str):
            try:
                clean["risk_level"] = RiskLevel(risk_level)
            except ValueError:
                clean["risk_level"] = RiskLevel.MEDIUM
        opened_at = clean.get("opened_at")
        if isinstance(opened_at, str):
            try:
                clean["opened_at"] = datetime.fromisoformat(opened_at)
            except ValueError:
                clean["opened_at"] = datetime.utcnow()
        positions.append(Position(**clean))
    return positions


def load_portfolio_state() -> PortfolioState:
    conn = _ensure_db()
    cur = conn.execute(
        """
        SELECT timestamp, cash_usd, realized_pnl_usd, unrealized_pnl_usd,
               cumulative_fees_usd, cumulative_il_usd, positions_json
        FROM portfolio_state_snapshots
        ORDER BY id DESC
        LIMIT 1
        """
    )
    row = cur.fetchone()
    conn.close()

    if row is None:
        risk_cfg = load_risk_config()
        return PortfolioState(
            timestamp=datetime.utcnow(),
            cash_usd=risk_cfg.initial_capital_usd,
            positions=[],
            realized_pnl_usd=0.0,
            unrealized_pnl_usd=0.0,
            cumulative_fees_usd=0.0,
            cumulative_il_usd=0.0,
        )

    ts_str, cash_usd, realized_pnl, unrealized_pnl, cum_fees, cum_il, positions_json = row
    try:
        ts = datetime.fromisoformat(ts_str)
    except ValueError:
        ts = datetime.utcnow()

    positions = _deserialize_positions(positions_json)

    return PortfolioState(
        timestamp=ts,
        cash_usd=cash_usd,
        positions=positions,
        realized_pnl_usd=realized_pnl,
        unrealized_pnl_usd=unrealized_pnl,
        cumulative_fees_usd=cum_fees,
        cumulative_il_usd=cum_il,
    )


def save_portfolio_state(state: PortfolioState) -> None:
    conn = _ensure_db()
    positions_json = _serialize_positions(state.positions)
    ts = state.timestamp.isoformat()
    conn.execute(
        """
        INSERT INTO portfolio_state_snapshots (
            timestamp,
            cash_usd,
            realized_pnl_usd,
            unrealized_pnl_usd,
            cumulative_fees_usd,
            cumulative_il_usd,
            positions_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ts,
            state.cash_usd,
            state.realized_pnl_usd,
            state.unrealized_pnl_usd,
            state.cumulative_fees_usd,
            state.cumulative_il_usd,
            positions_json,
        ),
    )
    conn.commit()
    conn.close()


def load_all_state_snapshots() -> List[dict]:
    """
    Load all portfolio_state_snapshots ordered by id ASC for time series.
    Each dict has timestamp, cash_usd, invested_usd (sum of position notionals), wallet_total_value_usd.
    """
    conn = _ensure_db()
    cur = conn.execute(
        """
        SELECT timestamp, cash_usd, realized_pnl_usd, positions_json
        FROM portfolio_state_snapshots
        ORDER BY id ASC
        """
    )
    rows = cur.fetchall()
    conn.close()

    result = []
    for row in rows:
        ts_str, cash_usd, _realized_pnl, positions_json = row
        try:
            ts = datetime.fromisoformat(ts_str)
        except ValueError:
            ts = datetime.utcnow()
        positions = _deserialize_positions(positions_json or "[]")
        invested_usd = sum(float(p.notional_usd) for p in positions)
        result.append({
            "timestamp": ts,
            "cash_usd": cash_usd,
            "invested_usd": invested_usd,
            "wallet_total_value_usd": cash_usd + invested_usd,
        })
    return result

