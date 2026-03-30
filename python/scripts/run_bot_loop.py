"""
Loop script to run the LP bot continuously every N seconds.

Usage (from project root, with venv active):

    python scripts/run_bot_loop.py
"""

from __future__ import annotations

import sys
import time
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from lpbot.executor import run_once


# Valor normal ~900 (15 min). Durante teste paper, pode usar 60–120 para ver o dashboard atualizar mais vezes.
INTERVAL_SECONDS = 900
# INTERVAL_SECONDS = 120  # descomentar só durante validação paper


def main() -> None:
    print(f"[run_bot_loop] Starting loop at {datetime.utcnow().isoformat()} UTC")
    print(f"[run_bot_loop] Interval: {INTERVAL_SECONDS} seconds (~{INTERVAL_SECONDS / 60:.1f} min)")
    while True:
        started_at = datetime.utcnow()
        print(f"[run_bot_loop] Running cycle at {started_at.isoformat()} UTC")
        try:
            run_once()
            print("[run_bot_loop] Cycle completed successfully.")
        except Exception as exc:  # noqa: BLE001
            # Log the exception to stdout so you can see failures in the terminal
            print(f"[run_bot_loop] ERROR during run_once(): {exc!r}")

        print(f"[run_bot_loop] Sleeping for {INTERVAL_SECONDS} seconds...")
        time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    main()

