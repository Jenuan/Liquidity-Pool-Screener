"""
lpbot package.

Core logic for the LP simulation bot:
- configuration loading
- risk & strategy
- execution/portfolio
- analytics
"""

from lpbot.analytics import (
    compute_basic_metrics,
    get_events_table,
    get_wallet_summary,
)

__all__ = [
    "compute_basic_metrics",
    "get_events_table",
    "get_wallet_summary",
]