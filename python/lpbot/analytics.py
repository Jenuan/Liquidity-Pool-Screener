"""
Analytics & Backtest Agent (mínimo).
"""

from __future__ import annotations

from typing import Any, Dict, List

from lpbot.models.portfolio import EventType
from lpbot.storage.log_store import load_all_events
from lpbot.storage.state_store import load_portfolio_state, load_all_state_snapshots


def get_wallet_summary() -> Dict[str, float]:
    """
    Resumo da carteira atual (atualizado com saídas dos trades: lucros e perdas).
    Use no notebook para exibir: caixa, investido, PnL realizado, valor total.
    """
    state = load_portfolio_state()
    cash = state.cash_usd
    invested = sum(float(p.notional_usd) for p in state.positions)
    return {
        "cash_usd": cash,
        "invested_usd": invested,
        "realized_pnl_usd": state.realized_pnl_usd,
        "wallet_total_value_usd": cash + invested,
        "open_positions": float(len(state.positions)),
    }


def _event_pair_display(metadata: dict | None) -> str:
    """Extrai o nome do par para exibição a partir do metadata do evento."""
    if not metadata:
        return ""
    if metadata.get("pair"):
        return str(metadata["pair"])
    cand = metadata.get("candidate") or {}
    if isinstance(cand, dict):
        if cand.get("Pair"):
            return str(cand["Pair"])
        b, q = cand.get("Base") or "?", cand.get("Quote") or "?"
        return f"{b}/{q}"
    return ""


def get_events_table() -> List[Dict[str, Any]]:
    """
    Retorna os eventos em formato de lista de dicionários, com coluna 'pair'
    para exibir no Jupyter: pd.DataFrame(lpbot.analytics.get_events_table()).
    """
    events = load_all_events()
    rows = []
    for e in events:
        rows.append({
            "timestamp": e.timestamp.isoformat(),
            "event_type": e.event_type.value if isinstance(e.event_type, EventType) else str(e.event_type),
            "position_id": e.position_id,
            "pair": _event_pair_display(e.metadata),
            "description": e.description,
            "delta_cash_usd": e.delta_cash_usd,
            "delta_realized_pnl_usd": e.delta_realized_pnl_usd,
        })
    return rows


def compute_basic_metrics() -> Dict[str, float]:
    """
    Calcula um conjunto mínimo de métricas a partir dos eventos e do último estado.
    """
    events = load_all_events()

    total_events = len(events)
    total_trades = sum(
        1
        for e in events
        if e.event_type in {EventType.OPEN_POSITION, EventType.CLOSE_POSITION}
    )
    total_realized_pnl_usd = sum(e.delta_realized_pnl_usd for e in events)
    total_fees_usd = sum(e.delta_fees_usd for e in events)
    total_il_usd = sum(e.delta_il_usd for e in events)

    # Lê o último snapshot (atualizado com saídas dos trades: caixa + PnL realizado)
    state = load_portfolio_state()
    cash_available_usd = state.cash_usd
    open_positions = len(state.positions)
    invested_usd = sum(float(p.notional_usd) for p in state.positions)
    # Valor total da carteira = caixa + capital em posições abertas
    wallet_total_value_usd = cash_available_usd + invested_usd
    # PnL realizado acumulado (do estado persistido, reflete saídas com lucro/perda)
    realized_pnl_from_state = state.realized_pnl_usd

    return {
        "total_events": float(total_events),
        "total_trades": float(total_trades),
        "total_realized_pnl_usd": float(total_realized_pnl_usd),
        "realized_pnl_usd": float(realized_pnl_from_state),
        "total_fees_usd": float(total_fees_usd),
        "total_il_usd": float(total_il_usd),
        "cash_available_usd": float(cash_available_usd),
        "invested_usd": float(invested_usd),
        "wallet_total_value_usd": float(wallet_total_value_usd),
        "open_positions": float(open_positions),
    }


def get_pnl_evolution() -> List[Dict[str, Any]]:
    """
    Time series of cumulative realized PnL. Built from portfolio_events ordered by timestamp.
    Returns list of dicts with timestamp, realized_pnl_cumulative_usd.
    """
    events = load_all_events()
    sorted_events = sorted(events, key=lambda e: e.timestamp)
    cumulative = 0.0
    result = []
    for e in sorted_events:
        cumulative += e.delta_realized_pnl_usd
        result.append({
            "timestamp": e.timestamp,
            "realized_pnl_cumulative_usd": cumulative,
        })
    return result


def get_wallet_evolution() -> List[Dict[str, Any]]:
    """
    Time series of total wallet value (cash + positions). Built from portfolio_state_snapshots.
    Returns list of dicts with timestamp, wallet_total_value_usd, optionally cash_usd, positions_value_usd.
    """
    snapshots = load_all_state_snapshots()
    return [
        {
            "timestamp": s["timestamp"],
            "wallet_total_value_usd": s["wallet_total_value_usd"],
            "cash_usd": s["cash_usd"],
            "positions_value_usd": s["invested_usd"],
        }
        for s in snapshots
    ]

