"""
Execution / Portfolio Agent.

Implementa um `run_once()` mínimo que:
- carrega env/config
- carrega estado
- lê candidatos do screener
- decide abrir/fechar posições
- persiste estado e eventos.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, List

from lpbot.config_loader import load_env, load_risk_config, get_dex_entry
from lpbot.datasources.screener_client import fetch_screener_rows
from lpbot.datasources.live_metrics import fetch_pool_metrics
from lpbot.datasources.solana_live_metrics import is_solana_pool_pubkey
from lpbot.models.portfolio import (
    EventType,
    PortfolioEvent,
    PortfolioState,
    Position,
    RiskLevel,
)
from lpbot.risk_strategy import _extract_apr, should_open_position, should_close_position
from lpbot.storage.log_store import append_events
from lpbot.storage.state_store import load_portfolio_state, save_portfolio_state


def _parse_optional_int(val: Any) -> int | None:
    if val is None or val == "":
        return None
    try:
        return int(float(str(val).strip()))
    except (TypeError, ValueError):
        return None


def _parse_range_full(val: Any) -> bool | None:
    if val is None or val == "":
        return None
    s = str(val).strip().lower()
    if s in ("yes", "true", "1", "full", "full range", "y"):
        return True
    if s in ("no", "false", "0", "narrow", "n"):
        return False
    return None


def _get_pool_metrics(position: Position) -> dict:
    """Fetch live pool metrics; fallback to safe defaults if DEX/RPC unsupported or fails."""
    try:
        return fetch_pool_metrics(position)
    except Exception:
        return {
            "apr_fees_24h": 0.0,
            "unrealized_pnl_pct": 0.0,
        }


def _candidate_passes_dex_execution_gates(candidate: dict) -> bool:
    """
    True se a linha do screener pode ser aberta pelo bot (DEX em dex_endpoints + id de pool válido).

    Importante: antes iterávamos só os primeiros N da folha; se o topo for só v4/base sem YAML,
    nunca se chegava a Pancake/Uniswap v2 — zero trades. Por isso filtramos e mantemos a ordem
    relativa só entre linhas executáveis.
    """
    dex = str(candidate.get("DEX") or candidate.get("dex") or "").strip()
    pool_id = str(candidate.get("PairAddress") or candidate.get("pool_id") or "").strip()
    base = str(candidate.get("Base") or candidate.get("token0_symbol") or "").strip()
    quote = str(candidate.get("Quote") or candidate.get("token1_symbol") or "").strip()
    if (
        not dex
        or dex.upper() == "UNKNOWN"
        or not pool_id
        or pool_id.upper() in {"UNKNOWN", "N/A", "NA"}
        or not base
        or not quote
        or base == "?"
        or quote == "?"
    ):
        return False
    dex_entry = get_dex_entry(dex)
    if not dex_entry:
        return False
    # live_metrics_mode: none (ex. Uniswap/Pancake V3 Base) ainda permite abertura:
    # fetch_pool_metrics usa DexScreener para preços/APR de entrada; sem on-chain V2 reserves.
    rpc_env = dex_entry.get("rpc_url_env")
    net = str(dex_entry.get("network") or "").strip().lower()
    if net == "solana":
        return bool(rpc_env and is_solana_pool_pubkey(pool_id))
    if not isinstance(dex_entry.get("chain_id"), int) or not rpc_env:
        return False
    return len(pool_id) == 42 and pool_id.startswith("0x")


def run_once() -> None:
    """
    Executa um ciclo do bot.
    """
    now = datetime.utcnow()

    load_env()
    risk_cfg = load_risk_config()

    portfolio: PortfolioState = load_portfolio_state()
    portfolio.timestamp = now

    candidates = fetch_screener_rows()
    events: List[PortfolioEvent] = []

    cap = risk_cfg.max_screener_candidates_per_cycle
    max_opens = risk_cfg.max_open_positions_per_cycle
    executable = [c for c in candidates if _candidate_passes_dex_execution_gates(c)]
    if candidates and not executable:
        sample = sorted(
            {str(c.get("DEX") or c.get("dex") or "").strip() for c in candidates[:20]}
        )[:6]
        print(
            "[lpbot] run_once: nenhuma linha executável (DEX/pool não cobertos por "
            f"dex_endpoints.yaml). Amostra de DEX na folha: {sample}",
            flush=True,
        )

    opened_this_run = 0
    for candidate in executable[:cap]:
        if opened_this_run >= max_opens:
            break
        should_open, reason, risk_level = should_open_position(
            portfolio=portfolio,
            candidate=candidate,
            risk_config=risk_cfg,
        )
        if not should_open:
            continue

        # Usar nomes das colunas da planilha (Pair, Base, Quote, DEX, PairAddress)
        dex = str(candidate.get("DEX") or candidate.get("dex") or "").strip()
        pool_id = str(candidate.get("PairAddress") or candidate.get("pool_id") or "").strip()
        base = str(candidate.get("Base") or candidate.get("token0_symbol") or "").strip()
        quote = str(candidate.get("Quote") or candidate.get("token1_symbol") or "").strip()
        pair_display = str(candidate.get("Pair") or f"{base}/{quote}").strip()

        dex_entry = get_dex_entry(dex)
        if not dex_entry:
            continue
        net = str(dex_entry.get("network") or "").strip().lower()
        if net == "solana":
            chain_id = None
        else:
            chain_id = int(dex_entry["chain_id"])

        entry_apr = _extract_apr(candidate)
        tick_lower = _parse_optional_int(candidate.get("TickLower") or candidate.get("tick_lower"))
        tick_upper = _parse_optional_int(candidate.get("TickUpper") or candidate.get("tick_upper"))
        range_full = _parse_range_full(
            candidate.get("FullRange") or candidate.get("full_range") or candidate.get("RangeFull")
        )

        position_id = f"{dex}::{pool_id}::{now.isoformat()}"
        pos = Position(
            id=position_id,
            dex=dex,
            pool_id=pool_id,
            token0_symbol=base,
            token1_symbol=quote,
            risk_level=risk_level if isinstance(risk_level, RiskLevel) else RiskLevel.MEDIUM,
            notional_usd=risk_cfg.position_size_usd,
            opened_at=now,
            entry_price_ratio=1.0,
            chain_id=chain_id,
            entry_apr_fees_24h=entry_apr,
            tick_lower=tick_lower,
            tick_upper=tick_upper,
            range_full=range_full,
        )
        portfolio.positions.append(pos)
        portfolio.cash_usd -= risk_cfg.position_size_usd

        events.append(
            PortfolioEvent(
                timestamp=now,
                event_type=EventType.OPEN_POSITION,
                position_id=pos.id,
                description=f"Opened position: {reason}",
                delta_cash_usd=-risk_cfg.position_size_usd,
                metadata={"candidate": candidate, "pair": pair_display},
            )
        )
        opened_this_run += 1

    remaining_positions: List[Position] = []
    for pos in portfolio.positions:
        metrics = _get_pool_metrics(pos)
        should_close, reason = should_close_position(
            portfolio=portfolio,
            position=pos,
            current_metrics=metrics,
            risk_config=risk_cfg,
        )
        if should_close:
            unrealized_pct = float(metrics.get("unrealized_pnl_pct", 0.0) or 0.0)
            pnl_usd = pos.notional_usd * (unrealized_pct / 100.0)

            # Atualiza a carteira: devolve capital + PnL (lucro ou perda) ao caixa
            portfolio.cash_usd += pos.notional_usd + pnl_usd
            portfolio.realized_pnl_usd += pnl_usd

            pair_display = f"{pos.token0_symbol}/{pos.token1_symbol}"
            events.append(
                PortfolioEvent(
                    timestamp=now,
                    event_type=EventType.CLOSE_POSITION,
                    position_id=pos.id,
                    description=f"Closed position: {reason}",
                    delta_cash_usd=pos.notional_usd + pnl_usd,
                    delta_realized_pnl_usd=pnl_usd,
                    metadata={"metrics": metrics, "pair": pair_display},
                )
            )
        else:
            remaining_positions.append(pos)

    portfolio.positions = remaining_positions

    # Persiste eventos e estado da carteira (caixa + PnL realizado atualizados)
    if events:
        append_events(events)
    save_portfolio_state(portfolio)

