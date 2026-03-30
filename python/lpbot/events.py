import pandas as pd
from lpbot.storage.log_store import load_all_events
from lpbot.models.portfolio import EventType

events = load_all_events()
trade_events = [
    e for e in events
    if e.event_type in {EventType.OPEN_POSITION, EventType.CLOSE_POSITION}
]

df_trades = pd.DataFrame([
    {
        "timestamp": e.timestamp,
        "event_type": e.event_type.value,
        "position_id": e.position_id,
        "description": e.description,
        "delta_cash_usd": e.delta_cash_usd,
        "delta_realized_pnl_usd": e.delta_realized_pnl_usd,
        "delta_unrealized_pnl_usd": e.delta_unrealized_pnl_usd,
        "delta_fees_usd": e.delta_fees_usd,
        "delta_il_usd": e.delta_il_usd,
    }
    for e in trade_events
])

