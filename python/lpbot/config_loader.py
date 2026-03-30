"""
Configuration loading utilities for the LP bot.

Responsável por:
- Carregar variáveis de ambiente do `.env`.
- Ler arquivos YAML em `config/`.
- Expor objetos de configuração tipados.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict
from urllib.parse import urlparse

import yaml
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = PROJECT_ROOT / "config"
RISK_CONFIG_PATH = CONFIG_DIR / "risk_config.yaml"
DEX_ENDPOINTS_PATH = CONFIG_DIR / "dex_endpoints.yaml"


@dataclass
class RiskConfig:
    """Configuração de risco e estratégia carregada de `risk_config.yaml`."""

    initial_capital_usd: float
    max_positions: int
    position_size_usd: float
    daily_portfolio_risk_pct: float
    daily_portfolio_target_pct: float
    position_max_risk_pct: float
    min_hold_minutes: float
    apr_thresholds_fees_24h: Dict[str, float]
    strategy: Dict[str, Any]
    max_screener_candidates_per_cycle: int
    max_open_positions_per_cycle: int


@dataclass
class DexConfig:
    """Configuração de endpoints de DEX e datasource do screener."""

    dexes: Dict[str, Any]
    datasources: Dict[str, Any]


def load_env(dotenv_path: Path | None = None) -> None:
    """
    Carrega variáveis de ambiente do `.env` na raiz do projeto.
    """
    if dotenv_path is None:
        dotenv_path = PROJECT_ROOT / ".env"
    load_dotenv(dotenv_path, override=False)


_PLACEHOLDER_MARKERS = (
    "seu_rpc",
    "your_rpc",
    "sua_chave",
    "your_api_key",
    "changeme",
    "placeholder",
    "replace_me",
    "example.com",
    "api-key-here",
)


def rpc_url_needs_real_endpoint(url: str | None) -> bool:
    """
    True if the value is empty or is clearly a documentation placeholder, not a
    reachable JSON-RPC URL. Used so the UI shows env_not_set-style hints instead
    of long DNS / eth_chainId errors.
    """
    if url is None:
        return True
    s = str(url).strip()
    if not s:
        return True
    low = s.lower()
    if any(m in low for m in _PLACEHOLDER_MARKERS):
        return True
    try:
        parsed = urlparse(s)
    except Exception:
        return True
    host = (parsed.hostname or "").strip().lower()
    if not host:
        return True
    if host == "localhost" or host.startswith("127.0.0.1"):
        return False
    if re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", host):
        return False
    if "." not in host:
        return True
    return False


def _load_yaml(path: Path) -> Dict[str, Any]:
    """Helper interno para ler YAML como dict."""
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def load_risk_config() -> RiskConfig:
    """
    Lê `config/risk_config.yaml` e devolve um `RiskConfig`.

    Modo paper relaxado (thresholds mais baixos, mais candidatos/aberturas por ciclo):
    - `paper_trading.relaxed: true` no YAML, ou
    - variável de ambiente `LPBOT_PAPER_RELAXED=1` (equivalente, sem editar o ficheiro).

    Desativar: `relaxed: false` e não definir a env (ou `LPBOT_PAPER_RELAXED=0`).
    """
    data = _load_yaml(RISK_CONFIG_PATH)

    portfolio = data.get("portfolio", {})
    risk_limits = data.get("risk_limits", {})
    apr_thresholds: Dict[str, float] = dict(data.get("apr_thresholds_fees_24h", {}) or {})
    strategy = dict(data.get("strategy", {}) or {})
    paper = data.get("paper_trading") or {}
    if not isinstance(paper, dict):
        paper = {}

    min_hold = float(strategy.get("min_hold_minutes", 0.0) or 0.0)
    max_candidates = 5
    max_opens = 1

    paper_relaxed = bool(paper.get("relaxed", False)) or _env_truthy("LPBOT_PAPER_RELAXED")
    if paper_relaxed:
        po = paper.get("apr_thresholds_fees_24h")
        if isinstance(po, dict) and po:
            for k, v in po.items():
                apr_thresholds[str(k)] = float(v)
        elif apr_thresholds:
            apr_thresholds = {
                str(k): max(0.01, float(v) * 0.1) for k, v in apr_thresholds.items()
            }
        min_hold = float(paper.get("min_hold_minutes", min_hold) or min_hold)
        max_candidates = int(paper.get("max_screener_candidates_per_cycle", 20) or 20)
        max_opens = int(paper.get("max_open_positions_per_cycle", 3) or 3)
        max_candidates = max(1, max_candidates)
        max_opens = max(1, max_opens)

    return RiskConfig(
        initial_capital_usd=portfolio.get("initial_capital_usd", 100.0),
        max_positions=portfolio.get("max_positions", 5),
        position_size_usd=portfolio.get("position_size_usd", 20.0),
        daily_portfolio_risk_pct=risk_limits.get("daily_portfolio_risk_pct", 5.0),
        daily_portfolio_target_pct=risk_limits.get("daily_portfolio_target_pct", 5.0),
        position_max_risk_pct=risk_limits.get("position_max_risk_pct", 20.0),
        min_hold_minutes=min_hold,
        apr_thresholds_fees_24h=apr_thresholds,
        strategy=strategy,
        max_screener_candidates_per_cycle=max_candidates,
        max_open_positions_per_cycle=max_opens,
    )


def load_dex_config() -> DexConfig:
    """Lê `config/dex_endpoints.yaml` e devolve um `DexConfig`."""
    data = _load_yaml(DEX_ENDPOINTS_PATH)
    return DexConfig(
        dexes=data.get("dexes", {}),
        datasources=data.get("datasources", {}),
    )


# Normalize sheet DEX labels to config keys (uniswap_v2 / pancakeswap_v2).
_DEX_NORMALIZE: Dict[str, str] = {
    "uniswap": "uniswap_v2",
    "uniswap v2": "uniswap_v2",
    "uni": "uniswap_v2",
    "pancakeswap": "pancakeswap_v2",
    "pancake": "pancakeswap_v2",
    "cake": "pancakeswap_v2",
    "pancakeswap-v3-solana": "pancakeswap_v3_solana",
    "pancakeswap v3 solana": "pancakeswap_v3_solana",
    "pancakeswap_v3_solana": "pancakeswap_v3_solana",
    "uniswap-v3-base": "uniswap_v3_base",
    "uniswap v3 base": "uniswap_v3_base",
    "uniswap_v3_base": "uniswap_v3_base",
    "pancakeswap-v3-base": "pancakeswap_v3_base",
    "pancakeswap v3 base": "pancakeswap_v3_base",
    "pancakeswap_v3_base": "pancakeswap_v3_base",
}


def normalize_dex_key(dex_label: str) -> str:
    """
    Map DEX label from the sheet (e.g. 'PancakeSwap', 'Uniswap V2') to config key.
    Returns the config key (e.g. 'pancakeswap_v2', 'uniswap_v2') or the original
    value lowercased/stripped if no mapping exists.
    """
    key = (dex_label or "").strip().lower()
    return _DEX_NORMALIZE.get(key, key.replace(" ", "_") if key else "unknown")


def get_dex_entry(dex_label: str) -> Dict[str, Any] | None:
    """
    Resolve DEX config entry by sheet label. Returns the dex block from
    dex_endpoints.yaml (chain_id, rpc_url_env, factory_address, etc.) or None.
    """
    cfg = load_dex_config()
    config_key = normalize_dex_key(dex_label)
    return cfg.dexes.get(config_key)

