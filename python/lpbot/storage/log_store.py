"""
Persistência de eventos de portfólio em SQLite.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List

from lpbot.config_loader import PROJECT_ROOT
from lpbot.models.portfolio import PortfolioEvent, EventType


DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "lpbot.db"


def _ensure_db() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS portfolio_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            event_type TEXT NOT NULL,
            position_id TEXT,
            description TEXT NOT NULL,
            delta_cash_usd REAL NOT NULL,
            delta_realized_pnl_usd REAL NOT NULL,
            delta_unrealized_pnl_usd REAL NOT NULL,
            delta_fees_usd REAL NOT NULL,
            delta_il_usd REAL NOT NULL,
            metadata_json TEXT NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def append_events(events: List[PortfolioEvent]) -> None:
    if not events:
        return

    conn = _ensure_db()
    rows = []
    for ev in events:
        ts = ev.timestamp.isoformat()
        rows.append(
            (
                ts,
                ev.event_type.value if isinstance(ev.event_type, EventType) else str(ev.event_type),
                ev.position_id,
                ev.description,
                ev.delta_cash_usd,
                ev.delta_realized_pnl_usd,
                ev.delta_unrealized_pnl_usd,
                ev.delta_fees_usd,
                ev.delta_il_usd,
                json.dumps(ev.metadata or {}, default=str),
            )
        )

    conn.executemany(
        """
        INSERT INTO portfolio_events (
            timestamp,
            event_type,
            position_id,
            description,
            delta_cash_usd,
            delta_realized_pnl_usd,
            delta_unrealized_pnl_usd,
            delta_fees_usd,
            delta_il_usd,
            metadata_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()
    conn.close()


def load_all_events() -> List[PortfolioEvent]:
    conn = _ensure_db()
    cur = conn.execute(
        """
        SELECT timestamp,
               event_type,
               position_id,
               description,
               delta_cash_usd,
               delta_realized_pnl_usd,
               delta_unrealized_pnl_usd,
               delta_fees_usd,
               delta_il_usd,
               metadata_json
        FROM portfolio_events
        ORDER BY id ASC
        """
    )
    rows = cur.fetchall()
    conn.close()

    events: List[PortfolioEvent] = []
    for (
        ts_str,
        event_type_str,
        position_id,
        description,
        delta_cash_usd,
        delta_realized_pnl_usd,
        delta_unrealized_pnl_usd,
        delta_fees_usd,
        delta_il_usd,
        metadata_json,
    ) in rows:
        try:
            ts = datetime.fromisoformat(ts_str)
        except ValueError:
            ts = datetime.utcnow()
        try:
            ev_type = EventType(event_type_str)
        except ValueError:
            ev_type = EventType.MARK_TO_MARKET
        metadata = json.loads(metadata_json) if metadata_json else {}
        events.append(
            PortfolioEvent(
                timestamp=ts,
                event_type=ev_type,
                position_id=position_id,
                description=description,
                delta_cash_usd=delta_cash_usd,
                delta_realized_pnl_usd=delta_realized_pnl_usd,
                delta_unrealized_pnl_usd=delta_unrealized_pnl_usd,
                delta_fees_usd=delta_fees_usd,
                delta_il_usd=delta_il_usd,
                metadata=metadata,
            )
        )

    return events

