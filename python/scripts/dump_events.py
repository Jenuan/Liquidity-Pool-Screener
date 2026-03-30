"""
Utility script to inspect portfolio events stored in SQLite.

Usage (from project root, with venv active):

    python scripts/dump_events.py          # show all events
    python scripts/dump_events.py 10       # show last 10 events
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

from lpbot.config_loader import PROJECT_ROOT


def dump_events(limit: int | None = None) -> None:
    db_path = PROJECT_ROOT / "data" / "lpbot.db"
    if not db_path.exists():
        print(f"No database found at {db_path}")
        return

    conn = sqlite3.connect(db_path)
    try:
        base_query = """
            SELECT id,
                   timestamp,
                   event_type,
                   position_id,
                   description,
                   delta_cash_usd,
                   delta_realized_pnl_usd,
                   delta_unrealized_pnl_usd,
                   delta_fees_usd,
                   delta_il_usd
            FROM portfolio_events
            ORDER BY id ASC
        """
        if limit is not None and limit > 0:
            # Use a subquery to get the last N rows while preserving ascending order
            query = f"SELECT * FROM ({base_query}) ORDER BY id DESC LIMIT {limit}"
        else:
            query = base_query

        cur = conn.execute(query)
        rows = cur.fetchall()
    finally:
        conn.close()

    if not rows:
        print("No events found.")
        return

    print("=== Portfolio Events ===")
    for row in rows:
        (
            ev_id,
            ts,
            ev_type,
            position_id,
            description,
            delta_cash,
            delta_realized,
            delta_unrealized,
            delta_fees,
            delta_il,
        ) = row
        print("-" * 80)
        print(f"id: {ev_id}")
        print(f"timestamp: {ts}")
        print(f"event_type: {ev_type}")
        print(f"position_id: {position_id}")
        print(f"description: {description}")
        print(f"delta_cash_usd: {delta_cash}")
        print(f"delta_realized_pnl_usd: {delta_realized}")
        print(f"delta_unrealized_pnl_usd: {delta_unrealized}")
        print(f"delta_fees_usd: {delta_fees}")
        print(f"delta_il_usd: {delta_il}")


def main() -> None:
    limit: int | None = None
    if len(sys.argv) >= 2:
        try:
            limit = int(sys.argv[1])
        except ValueError:
            print(f"Invalid limit value: {sys.argv[1]!r}. Ignoring and dumping all events.")
    dump_events(limit)


if __name__ == "__main__":
    main()

