"""
DexScreener HTTP API: pair-level stats (price change %, volume, URL).

Used for "live" pair metrics similar to DEX landing pages (24h change, etc.).
Not an on-chain oracle; see README for limitations.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import requests

_PAIR_URL = "https://api.dexscreener.com/latest/dex/pairs/{chain_slug}/{pair_address}"

# chain_id (EVM) -> DexScreener chain slug (path segment)
CHAIN_ID_TO_DEXSCREENER_SLUG: Dict[int, str] = {
    1: "ethereum",
    56: "bsc",
    137: "polygon",
    42161: "arbitrum",
    10: "optimism",
    8453: "base",
    43114: "avalanche",
    250: "fantom",
}


def _float_or_none(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _str_or_none(v: Any) -> Optional[str]:
    if v is None:
        return None
    try:
        s = str(v).strip()
    except Exception:
        return None
    return s or None


def fetch_pair_stats(chain_slug: str, pair_address: str, timeout: float = 20.0) -> Optional[Dict[str, Any]]:
    """
    GET /latest/dex/pairs/{chain_slug}/{pair_address}

    Returns a dict with normalized fields, or None on HTTP/parse failure or empty pairs.
    """
    url = _PAIR_URL.format(chain_slug=chain_slug, pair_address=pair_address.strip())
    try:
        r = requests.get(url, timeout=timeout)
        r.raise_for_status()
        body = r.json() or {}
    except Exception:
        return None

    pairs = body.get("pairs")
    if not isinstance(pairs, list) or not pairs:
        return None

    def _liq_usd(p: dict) -> float:
        liq = p.get("liquidity") or {}
        try:
            return float(liq.get("usd") or 0.0)
        except (TypeError, ValueError):
            return 0.0

    best = max(pairs, key=_liq_usd)
    pc = best.get("priceChange") or {}
    vol = best.get("volume") or {}

    return {
        "price_change_source": "dexscreener",
        "pair_url": best.get("url"),
        "price_usd": _float_or_none(best.get("priceUsd")),
        "price_native": _float_or_none(best.get("priceNative")),
        "base_token_symbol": _str_or_none((best.get("baseToken") or {}).get("symbol")),
        "quote_token_symbol": _str_or_none((best.get("quoteToken") or {}).get("symbol")),
        "price_change_m5_pct": _float_or_none(pc.get("m5")),
        "price_change_h1_pct": _float_or_none(pc.get("h1")),
        "price_change_h6_pct": _float_or_none(pc.get("h6")),
        "price_change_h24_pct": _float_or_none(pc.get("h24")),
        "volume_h24_usd": _float_or_none(vol.get("h24")),
        "liquidity_usd": _float_or_none((best.get("liquidity") or {}).get("usd")),
        "dex_id": best.get("dexId"),
        "pair_address": best.get("pairAddress"),
    }


def fetch_pair_stats_for_position(
    *,
    network: Optional[str],
    chain_id: Optional[int],
    pool_id: str,
) -> tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Resolve DexScreener slug from network/chain and fetch pair stats.

    Returns (stats_dict_or_none, unavailable_reason_or_none).
    """
    net = (network or "").strip().lower()
    pid = (pool_id or "").strip()

    if net == "solana":
        if not pid or pid.startswith("0x"):
            return None, "invalid_pool_for_solana"
        return fetch_pair_stats("solana", pid), None

    if not pid.startswith("0x") or len(pid) != 42:
        return None, "invalid_evm_pool_address"

    if chain_id is None:
        return None, "missing_chain_id"

    slug = CHAIN_ID_TO_DEXSCREENER_SLUG.get(int(chain_id))
    if not slug:
        return None, f"unsupported_chain_id:{chain_id}"

    stats = fetch_pair_stats(slug, pid)
    if stats is None:
        return None, "dexscreener_no_pair_or_error"

    return stats, None
