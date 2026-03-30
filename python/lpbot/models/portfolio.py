"""
Modelos de portfólio e posições para o bot de LP.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict


class RiskLevel(str, Enum):
    """Níveis de risco usados pela estratégia."""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class EventType(str, Enum):
    """Tipos de eventos no ciclo de vida do portfólio."""

    OPEN_POSITION = "OPEN_POSITION"
    CLOSE_POSITION = "CLOSE_POSITION"
    REBALANCE = "REBALANCE"
    FEE_ACCRUAL = "FEE_ACCRUAL"
    MARK_TO_MARKET = "MARK_TO_MARKET"


@dataclass
class Position:
    """Representa uma posição LP simulada em uma pool específica."""

    id: str
    dex: str
    pool_id: str
    token0_symbol: str
    token1_symbol: str
    risk_level: RiskLevel
    notional_usd: float
    opened_at: datetime
    entry_price_ratio: float
    chain_id: Optional[int] = None
    # Screener / entrada (opcional): APR em % fees 24h gravado na abertura
    entry_apr_fees_24h: Optional[float] = None
    # CLMM (opcional): ticks da posição; range_full=True ignora limites numéricos na UI
    tick_lower: Optional[int] = None
    tick_upper: Optional[int] = None
    range_full: Optional[bool] = None


@dataclass
class PortfolioState:
    """Estado agregado do portfólio em um instante."""

    timestamp: datetime
    cash_usd: float
    positions: List[Position] = field(default_factory=list)
    realized_pnl_usd: float = 0.0
    unrealized_pnl_usd: float = 0.0
    cumulative_fees_usd: float = 0.0
    cumulative_il_usd: float = 0.0


@dataclass
class PortfolioEvent:
    """Evento de portfólio, usado para logging/analytics."""

    timestamp: datetime
    event_type: EventType
    position_id: Optional[str]
    description: str
    delta_cash_usd: float = 0.0
    delta_realized_pnl_usd: float = 0.0
    delta_unrealized_pnl_usd: float = 0.0
    delta_fees_usd: float = 0.0
    delta_il_usd: float = 0.0
    metadata: Dict = field(default_factory=dict)

