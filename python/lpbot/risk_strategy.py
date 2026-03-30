"""
Risk & Strategy Agent.

Contém lógica mínima (ainda heurística) para decidir abrir/fechar posições.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, Tuple

from lpbot.config_loader import RiskConfig
from lpbot.models.portfolio import PortfolioState, Position, RiskLevel


def _resolve_risk_level(candidate: Dict) -> RiskLevel:
    """Determina o nível de risco a partir da linha do screener."""
    raw = str(candidate.get("risk_level", "MEDIUM")).upper()
    try:
        return RiskLevel(raw)
    except ValueError:
        return RiskLevel.MEDIUM


def _extract_apr(candidate: Dict) -> float:
    """
    Extrai o APR em fees a partir dos campos disponíveis na linha do screener.

    Prioridade:
    - apr_fees_24h (se existir)
    - AdjAPR
    - optimizedAPR
    - baseAPR
    """
    raw = (
        candidate.get("apr_fees_24h")
        or candidate.get("AdjAPR")
        or candidate.get("optimizedAPR")
        or candidate.get("baseAPR")
        or 0.0
    )
    if isinstance(raw, str):
        # Normaliza formato pt-BR (ex.: "1.234,56%" -> "1234.56")
        raw = raw.replace("%", "").strip()
        raw = raw.replace(".", "").replace(",", ".")
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


def should_open_position(
    portfolio: PortfolioState,
    candidate: Dict,
    risk_config: RiskConfig,
) -> Tuple[bool, str, RiskLevel]:
    """
    Decide se deve abrir uma nova posição para uma pool candidata.
    """
    risk_level = _resolve_risk_level(candidate)

    if len(portfolio.positions) >= risk_config.max_positions:
        return False, "Max positions reached", risk_level

    if portfolio.cash_usd < risk_config.position_size_usd:
        return False, "Not enough cash", risk_level

    apr = _extract_apr(candidate)
    threshold = risk_config.apr_thresholds_fees_24h.get(risk_level.value, 0.0)
    if apr < threshold:
        return (
            False,
            f"APR {apr:.2f}% below threshold {threshold:.2f}% for {risk_level.value}",
            risk_level,
        )

    return True, "APR above threshold and capacity available", risk_level


def should_close_position(
    portfolio: PortfolioState,
    position: Position,
    current_metrics: Dict,
    risk_config: RiskConfig,
) -> Tuple[bool, str]:
    """
    Decide se deve fechar uma posição existente.
    """
    min_hold_minutes = float(getattr(risk_config, "min_hold_minutes", 0.0) or 0.0)
    if min_hold_minutes > 0:
        # Evita “abre e fecha imediatamente” enquanto o provedor de APR/preço ainda
        # não estabilizou entre ciclos.
        opened_at = position.opened_at
        if isinstance(opened_at, datetime):
            age_minutes = (datetime.utcnow() - opened_at).total_seconds() / 60.0
            if age_minutes < min_hold_minutes:
                return False, (
                    f"Min hold not reached ({age_minutes:.1f}m/{min_hold_minutes:.0f}m)"
                )

    unrealized_pnl_pct = float(current_metrics.get("unrealized_pnl_pct", 0.0) or 0.0)
    apr_current = float(current_metrics.get("apr_fees_24h", 0.0) or 0.0)

    if unrealized_pnl_pct <= -risk_config.position_max_risk_pct:
        return True, (
            f"Unrealized PnL {unrealized_pnl_pct:.2f}% "
            f"<= -{risk_config.position_max_risk_pct:.2f}%"
        )

    threshold = risk_config.apr_thresholds_fees_24h.get(position.risk_level.value, 0.0)
    close_threshold = 0.5 * threshold
    if apr_current < close_threshold:
        return True, (
            f"APR {apr_current:.2f}% below close threshold {close_threshold:.2f}% "
            f"for {position.risk_level.value}"
        )

    return False, "Hold position"

