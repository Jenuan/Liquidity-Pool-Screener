"""
Live pool metrics: EVM Uniswap V2 / PancakeSwap V2 (web3 + eth_defi) and
Solana CLMM pools (JSON-RPC + Raydium-compatible PoolState; USD via DexScreener).
"""

from __future__ import annotations

import os
import time
from datetime import datetime
from typing import Any, Dict, List

from lpbot.config_loader import load_env, get_dex_entry, normalize_dex_key, rpc_url_needs_real_endpoint
from lpbot.datasources.dexscreener_pair import fetch_pair_stats_for_position
from lpbot.datasources.solana_live_metrics import fetch_solana_clmm_pool_metrics
from lpbot.models.portfolio import Position
from lpbot.storage.state_store import load_portfolio_state
from lpbot.storage.position_history import append_position_snapshots

# In-memory cache: position_id -> entry_pool_value_usd (first successful fetch).
_entry_pool_value_cache: Dict[str, float] = {}

# Cache for last get_positions_live result and timestamp (for refresh_interval_seconds).
_last_positions_live: List[Dict[str, Any]] | None = None
_last_positions_live_ts: float = 0.0

# Known stablecoin symbols (USD-pegged).
_STABLES = frozenset({
    "usdc",
    "usdt",
    "busd",
    "dai",
    "usdc.e",
    "usdt.e",
    "usdbc",  # legacy Base bridged USDC naming
    "lusd",
    "crvusd",
})

# Reference pair per chain for native asset USD price (pair address).
# Ethereum: WETH/USDC; BSC: WBNB/BUSD; Base: Uniswap V2 WETH/USDC. Used when the valued
# pair has no stable leg.
_REFERENCE_PAIRS: Dict[int, str] = {
    1: "0xB4e16d0168e52d35CaCD2c6185b44281Ec28C9Dc",   # Uniswap V2 WETH/USDC
    56: "0x58F876857a02D6762E0101bb5C46A8c1ED44Dc16",  # PancakeSwap WBNB/BUSD
    8453: "0x88A43bbDF9D098eEC7bCEda4e2494615dfD9bB9C",  # Uniswap V2 WETH/USDC (Base)
}


def _get_web3(chain_id: int, rpc_url_env: str) -> Any:
    """Build Web3 instance for the given chain. Uses process-local cache per chain_id."""
    load_env()
    rpc_url = os.getenv(rpc_url_env)
    if not rpc_url:
        raise ValueError(f"RPC URL not set: set {rpc_url_env} in .env")
    from web3 import Web3  # type: ignore[import-not-found]
    from eth_defi.chain import install_chain_middleware  # type: ignore[import-not-found]

    provider = Web3.HTTPProvider(rpc_url)
    w3 = Web3(provider)
    install_chain_middleware(w3)
    return w3


# Simple cache: chain_id -> Web3 (no expiry; process lifetime).
_web3_cache: Dict[int, Any] = {}


def _web3_for_chain(chain_id: int, rpc_url_env: str) -> Any:
    if chain_id not in _web3_cache:
        _web3_cache[chain_id] = _get_web3(chain_id, rpc_url_env)
    return _web3_cache[chain_id]


def _is_stable(symbol: str) -> bool:
    return (symbol or "").strip().lower() in _STABLES


def _get_reference_price_usd(web3: Any, chain_id: int) -> float:
    """Get native asset (WETH/WBNB) price in USD from reference pair. Returns 0.0 on failure."""
    pair_address = _REFERENCE_PAIRS.get(chain_id)
    if not pair_address:
        return 0.0
    try:
        from eth_defi.uniswap_v2.pair import fetch_pair_details  # type: ignore[import-not-found]
        pair = fetch_pair_details(web3, pair_address, reverse_token_order=False)
        price = pair.get_current_mid_price()
        return float(price)
    except Exception:
        return 0.0


def _token_price_usd_from_pair(pair: Any, chain_id: int, reference_price_usd: float) -> tuple[float, float]:
    """
    Derive USD price for token0 and token1 using pair's mid price (quote/base) and stable/reference.
    PairDetails: get_current_mid_price() returns quote/base in human form. When quote is stable, base price in USD = mid.
    """
    base = pair.get_base_token()
    quote = pair.get_quote_token()
    base_sym = (base.symbol or "").strip().lower()
    quote_sym = (quote.symbol or "").strip().lower()
    try:
        mid = pair.get_current_mid_price()
        mid_f = float(mid)
    except Exception:
        mid_f = 0.0

    # mid = quote per base. If quote is stable (USD): price_base_usd = mid, price_quote_usd = 1.
    # If base is stable: price_base_usd = 1, price_quote_usd = 1/mid.
    if _is_stable(quote_sym):
        price_base_usd = mid_f
        price_quote_usd = 1.0
    elif _is_stable(base_sym):
        price_base_usd = 1.0
        price_quote_usd = (1.0 / mid_f) if mid_f else 0.0
    else:
        price_base_usd = reference_price_usd if base_sym in ("weth", "eth", "wbnb", "bnb") else 0.0
        price_quote_usd = reference_price_usd if quote_sym in ("weth", "eth", "wbnb", "bnb") else 0.0

    # reverse_token_order: if True, token0=quote, token1=base; else token0=base, token1=quote.
    if pair.reverse_token_order:
        price0_usd, price1_usd = price_quote_usd, price_base_usd
    else:
        price0_usd, price1_usd = price_base_usd, price_quote_usd

    return price0_usd, price1_usd


def _metrics_fallback_base(position: Position) -> Dict[str, Any]:
    """Template merged into Solana failures; prices None so UI does not show fake zeros."""
    return {
        "apr_fees_24h": 0.0,
        "unrealized_pnl_pct": 0.0,
        "price0_usd": None,
        "price1_usd": None,
        "value_usd": position.notional_usd,
        "reserve0": 0,
        "reserve1": 0,
        "total_supply": 0,
        "pool_value_usd": 0.0,
        "timestamp_utc": datetime.utcnow(),
        "supported": False,
        "unsupported_reason": "unsupported_dex_or_pool",
    }


def _unsupported_pool_metrics(position: Position, reason: str) -> Dict[str, Any]:
    m = {**_metrics_fallback_base(position), "unsupported_reason": reason}
    m["metrics_provenance"] = f"unsupported:{reason}"
    return _merge_entry_apr_into_metrics(position, m)


def _merge_entry_apr_into_metrics(position: Position, metrics: Dict[str, Any]) -> Dict[str, Any]:
    """If on-chain APR is zero, use APR gravado na abertura (screener) para estratégia / saídas."""
    m = dict(metrics)
    if "tick_current" not in m:
        m["tick_current"] = None
    if position.entry_apr_fees_24h is not None:
        try:
            e = float(position.entry_apr_fees_24h)
        except (TypeError, ValueError):
            e = None
        if e is not None and float(m.get("apr_fees_24h") or 0) == 0:
            m["apr_fees_24h"] = e
            m["apr_fees_24h_fill"] = "entry_screener"
    return m


def _dexscreener_provenance(source: str, stage: str, detail: str, tail: str = "") -> str:
    """source: v2_pool_fallback | live_metrics_mode_none"""
    if source == "v2_pool_fallback":
        return f"fallback:dexscreener_{stage} (pool_not_v2_pair:{detail}{tail})"
    return f"dexscreener_only:live_metrics_mode_none:{stage} ({detail}{tail})"


def _dexscreener_evm_price_only_payload(
    *,
    position: Position,
    chain_id: int,
    pool_id: str,
    source: str,
    detail: str,
) -> Dict[str, Any]:
    """
    Populate USD token prices from DexScreener only (no on-chain reserves).
    source: v2_pool_fallback | live_metrics_mode_none; detail: reason/cfg_key for provenance.
    """
    stats, ds_reason = fetch_pair_stats_for_position(
        network=None,
        chain_id=chain_id,
        pool_id=pool_id,
    )
    if not stats:
        metrics: Dict[str, Any] = {
            "apr_fees_24h": 0.0,
            "unrealized_pnl_pct": 0.0,
            "price0_usd": None,
            "price1_usd": None,
            "value_usd": position.notional_usd,
            "reserve0": 0,
            "reserve1": 0,
            "total_supply": 0,
            "pool_value_usd": 0.0,
            "entry_pool_value_usd": position.notional_usd,
            "timestamp_utc": datetime.utcnow(),
            "supported": True,
            "metrics_provenance": _dexscreener_provenance(
                source,
                "unavailable_evm_value_only",
                detail,
                tail=f":{ds_reason or 'no_stats'}",
            ),
            "tick_current": None,
        }
        return _merge_entry_apr_into_metrics(position, metrics)

    price_usd = stats.get("price_usd")
    base_sym = (stats.get("base_token_symbol") or "").strip().lower()
    quote_sym = (stats.get("quote_token_symbol") or "").strip().lower()
    price_native = stats.get("price_native")
    if price_usd is None:
        metrics: Dict[str, Any] = {
            "apr_fees_24h": 0.0,
            "unrealized_pnl_pct": 0.0,
            "price0_usd": None,
            "price1_usd": None,
            "value_usd": position.notional_usd,
            "reserve0": 0,
            "reserve1": 0,
            "total_supply": 0,
            "pool_value_usd": 0.0,
            "entry_pool_value_usd": position.notional_usd,
            "timestamp_utc": datetime.utcnow(),
            "supported": True,
            "metrics_provenance": _dexscreener_provenance(
                source, "no_price_evm_value_only", detail
            ),
            "tick_current": None,
        }
        return _merge_entry_apr_into_metrics(position, metrics)

    try:
        price_base_usd = float(price_usd)
    except (TypeError, ValueError):
        metrics: Dict[str, Any] = {
            "apr_fees_24h": 0.0,
            "unrealized_pnl_pct": 0.0,
            "price0_usd": None,
            "price1_usd": None,
            "value_usd": position.notional_usd,
            "reserve0": 0,
            "reserve1": 0,
            "total_supply": 0,
            "pool_value_usd": 0.0,
            "entry_pool_value_usd": position.notional_usd,
            "timestamp_utc": datetime.utcnow(),
            "supported": True,
            "metrics_provenance": _dexscreener_provenance(
                source, "invalid_price_evm_value_only", detail
            ),
            "tick_current": None,
        }
        return _merge_entry_apr_into_metrics(position, metrics)

    # DexScreener `priceUsd` is the USD price of `baseToken`. We infer the other leg when
    # one side is stable; if base is stable but priceUsd≈1, use `priceNative` (quote per base)
    # when the quote is the volatile symbol.
    price_quote_usd: float | None
    if quote_sym and _is_stable(quote_sym):
        price_quote_usd = 1.0
    elif base_sym and _is_stable(base_sym):
        price_base_usd = 1.0
        try:
            native_f = float(price_native) if price_native is not None else 0.0
        except (TypeError, ValueError):
            native_f = 0.0
        # Stable base ~ $1: priceNative is typically quote amount per 1 base → quote USD ≈ 1/native.
        if native_f and native_f > 0:
            price_quote_usd = 1.0 / native_f
        else:
            try:
                pu = float(price_usd)
            except (TypeError, ValueError):
                pu = 0.0
            price_quote_usd = (1.0 / pu) if pu else None
    else:
        price_quote_usd = None

    t0 = (position.token0_symbol or "").strip().lower()
    t1 = (position.token1_symbol or "").strip().lower()

    price0_usd: float | None = None
    price1_usd: float | None = None

    if base_sym and t0 == base_sym:
        price0_usd = price_base_usd
    elif quote_sym and t0 == quote_sym:
        price0_usd = price_quote_usd

    if base_sym and t1 == base_sym:
        price1_usd = price_base_usd
    elif quote_sym and t1 == quote_sym:
        price1_usd = price_quote_usd

    metrics: Dict[str, Any] = {
        "apr_fees_24h": 0.0,
        "unrealized_pnl_pct": 0.0,
        "price0_usd": price0_usd,
        "price1_usd": price1_usd,
        "value_usd": position.notional_usd,
        "reserve0": 0,
        "reserve1": 0,
        "total_supply": 0,
        "pool_value_usd": 0.0,
        "entry_pool_value_usd": position.notional_usd,
        "timestamp_utc": datetime.utcnow(),
        "supported": True,
        "metrics_provenance": _dexscreener_provenance(source, "evm_pair_price_usd", detail),
        "tick_current": None,
    }
    return _merge_entry_apr_into_metrics(position, metrics)


def _fallback_v2_pool_metrics_from_dexscreener(
    *,
    position: Position,
    chain_id: int,
    pool_id: str,
    unavailable_reason: str,
) -> Dict[str, Any]:
    """
    Conservative fallback when V2 on-chain decoding fails (e.g. `pool_not_v2_pair`).
    """
    return _dexscreener_evm_price_only_payload(
        position=position,
        chain_id=chain_id,
        pool_id=pool_id,
        source="v2_pool_fallback",
        detail=unavailable_reason,
    )


def _enrich_outputs_for_row(
    pos: Position,
    metrics: Dict[str, Any],
    chain_id: int | None,
    network: Any,
) -> Dict[str, Any]:
    """
    DexScreener (par), tipo de range, fees estimadas, tick in-range (Solana CLMM).
    """
    net = str(network or "").strip().lower() if network else ""
    out: Dict[str, Any] = {}

    if net == "solana":
        if pos.range_full is True:
            out["range_type"] = "full_range"
            out["range_mode"] = "clmm_full_range"
            out["position_tick_in_range"] = True
        elif pos.tick_lower is not None and pos.tick_upper is not None:
            out["range_type"] = "short_range"
            out["range_mode"] = "clmm_short_range"
            lo, hi = int(pos.tick_lower), int(pos.tick_upper)
            if lo > hi:
                lo, hi = hi, lo
            out["tick_lower"] = lo
            out["tick_upper"] = hi
            tick_cur = metrics.get("tick_current")
            if tick_cur is not None:
                out["position_tick_in_range"] = lo <= int(tick_cur) <= hi
            else:
                out["position_tick_in_range"] = None
        else:
            out["range_type"] = "unknown"
            out["range_mode"] = "clmm_unknown"
            out["range_unavailable_reason"] = "missing_ticks_or_full_flag_in_position"
    else:
        out["range_type"] = "amm_v2_curve"
        out["range_mode"] = "constant_product_v2"
        out["range_note"] = "AMM x*y=k (sem ticks); liquidez ao longo da curva"

    stats, ds_reason = fetch_pair_stats_for_position(
        network=net if net else None,
        chain_id=chain_id,
        pool_id=pos.pool_id,
    )
    if stats:
        out["price_change_h24_pct"] = stats.get("price_change_h24_pct")
        out["price_change_m5_pct"] = stats.get("price_change_m5_pct")
        out["price_change_h1_pct"] = stats.get("price_change_h1_pct")
        out["price_change_h6_pct"] = stats.get("price_change_h6_pct")
        out["price_change_source"] = stats.get("price_change_source")
        out["pair_url"] = stats.get("pair_url")
        out["dexscreener_volume_h24_usd"] = stats.get("volume_h24_usd")
        out["dexscreener_liquidity_usd"] = stats.get("liquidity_usd")
        out["price_change_unavailable_reason"] = None
    else:
        out["price_change_h24_pct"] = None
        out["price_change_m5_pct"] = None
        out["price_change_h1_pct"] = None
        out["price_change_h6_pct"] = None
        out["price_change_source"] = None
        out["price_change_unavailable_reason"] = ds_reason

    supported = bool(metrics.get("supported"))
    # Não expor estimativa linear de fees (dias fracionários faziam o valor mudar a cada poll).
    out["fees_model"] = "not_tracked_live"
    out["fees_accrued_usd_est"] = None
    out["fees_accrued_usd_linear_est"] = None
    if not supported:
        out["fees_notes"] = "Sem métricas live suportadas — fees não mostradas ao vivo."
        out["outputs_provenance"] = (
            "price_change:DexScreener pair API when applicable; range:position+network; "
            "fees:not_tracked"
        )
        return out

    out["fees_notes"] = (
        "Fees LP não são calculadas neste painel ao vivo; use eventos OPEN/CLOSE quando existirem."
    )
    out["outputs_provenance"] = (
        "price_change:DexScreener pair API; range:position+network; fees:not_tracked"
    )

    return out


def fetch_pool_metrics(position: Position) -> Dict[str, Any]:
    """
    Fetch live metrics for one position. Returns dict compatible with risk_strategy
    (apr_fees_24h, unrealized_pnl_pct) plus value_usd, pool_value_usd, reserves, etc.
    On unsupported DEX or RPC failure returns fallback dict with unrealized_pnl_pct=0, apr_fees_24h=0.
    """
    global _entry_pool_value_cache

    fb = _metrics_fallback_base(position)

    dex_entry = get_dex_entry(position.dex)
    if not dex_entry:
        return _unsupported_pool_metrics(position, "unknown_dex")

    network = str(dex_entry.get("network") or "").strip().lower()
    if network == "solana":
        sol = fetch_solana_clmm_pool_metrics(
            position, dex_entry, fb, _entry_pool_value_cache
        )
        out = _merge_entry_apr_into_metrics(position, sol)
        if not out.get("supported"):
            r = str(out.get("unsupported_reason") or "")
            if not out.get("metrics_provenance"):
                out["metrics_provenance"] = f"unsupported:{r}" if r else "unsupported:solana"
            out["price0_usd"] = None
            out["price1_usd"] = None
        return out

    live_mode = str(dex_entry.get("live_metrics_mode") or "uniswap_v2_pair").strip().lower()
    if live_mode == "none":
        cfg_key = normalize_dex_key(position.dex)
        if not isinstance(dex_entry.get("chain_id"), int):
            return _unsupported_pool_metrics(
                position, f"live_metrics_not_implemented_for_dex:{cfg_key}"
            )
        chain_id_none = int(dex_entry["chain_id"])
        pool_id_none = (position.pool_id or "").strip()
        if not pool_id_none or len(pool_id_none) != 42 or not pool_id_none.startswith("0x"):
            return _unsupported_pool_metrics(
                position, f"live_metrics_not_implemented_for_dex:{cfg_key}"
            )
        return _dexscreener_evm_price_only_payload(
            position=position,
            chain_id=chain_id_none,
            pool_id=pool_id_none,
            source="live_metrics_mode_none",
            detail=cfg_key,
        )

    if not isinstance(dex_entry.get("chain_id"), int):
        return _unsupported_pool_metrics(position, "dex_missing_chain_or_rpc")

    chain_id = int(dex_entry["chain_id"])
    rpc_env = dex_entry.get("rpc_url_env")
    if not rpc_env:
        return _unsupported_pool_metrics(position, "dex_missing_chain_or_rpc")

    pool_id = (position.pool_id or "").strip()
    if not pool_id or len(pool_id) != 42 or not pool_id.startswith("0x"):
        return _unsupported_pool_metrics(position, "invalid_evm_pool_address")

    load_env()
    rpc_env_s = str(rpc_env)
    rpc_url = os.getenv(rpc_env_s)
    if not rpc_url or rpc_url_needs_real_endpoint(rpc_url):
        return _unsupported_pool_metrics(position, f"env_not_set:{rpc_env_s}")

    try:
        web3 = _web3_for_chain(chain_id, rpc_env_s)
    except ValueError as e:
        msg = str(e).lower()
        if "not set" in msg and rpc_env_s.lower() in msg:
            return _unsupported_pool_metrics(position, f"env_not_set:{rpc_env_s}")
        return _unsupported_pool_metrics(position, f"evm_rpc_error:{e!s}"[:200])
    except Exception as e:
        return _unsupported_pool_metrics(position, f"evm_rpc_error:{e!s}"[:200])

    try:
        from eth_defi.uniswap_v2.pair import fetch_pair_details  # type: ignore[import-not-found]
        pair = fetch_pair_details(web3, pool_id, reverse_token_order=False)
    except Exception:
        return _fallback_v2_pool_metrics_from_dexscreener(
            position=position,
            chain_id=chain_id,
            pool_id=pool_id,
            unavailable_reason="pool_not_v2_pair(fetch_pair_details)",
        )

    try:
        reserves = pair.contract.functions.getReserves().call()
        total_supply = pair.contract.functions.totalSupply().call()
    except Exception:
        return _fallback_v2_pool_metrics_from_dexscreener(
            position=position,
            chain_id=chain_id,
            pool_id=pool_id,
            unavailable_reason="pool_not_v2_pair(getReserves/totalSupply)",
        )

    reserve0, reserve1 = int(reserves[0]), int(reserves[1])
    ref_price = _get_reference_price_usd(web3, chain_id)
    price0_usd, price1_usd = _token_price_usd_from_pair(pair, chain_id, ref_price)

    dec0 = getattr(pair.token0, "decimals", 18) or 18
    dec1 = getattr(pair.token1, "decimals", 18) or 18
    r0_human = reserve0 / (10**dec0)
    r1_human = reserve1 / (10**dec1)
    pool_value_usd = r0_human * price0_usd + r1_human * price1_usd

    # APR: not provided by chain; use 0. TODO: optional feed from screener or other source.
    apr_fees_24h = 0.0

    # Position value: use entry_pool_value from cache on first successful fetch.
    entry_pool_value = _entry_pool_value_cache.get(position.id)
    if entry_pool_value is None or entry_pool_value <= 0:
        entry_pool_value = pool_value_usd if pool_value_usd > 0 else position.notional_usd
        _entry_pool_value_cache[position.id] = entry_pool_value

    if entry_pool_value and entry_pool_value > 0:
        value_usd = position.notional_usd * (pool_value_usd / entry_pool_value)
    else:
        value_usd = position.notional_usd

    notional = position.notional_usd
    unrealized_pnl_pct = ((value_usd - notional) / notional * 100.0) if notional else 0.0

    return _merge_entry_apr_into_metrics(
        position,
        {
            "apr_fees_24h": apr_fees_24h,
            "unrealized_pnl_pct": unrealized_pnl_pct,
            # Proxy: diferença entre valor atual (mark-to-market) e capital inicial.
            # (Neste dashboard, fees ao vivo não são modeladas; então IL aqui funciona
            # como um sinal consistente com o PnL não realizado em USD.)
            "il_usd": float(value_usd - position.notional_usd),
            "price0_usd": float(price0_usd or 0.0),
            "price1_usd": float(price1_usd or 0.0),
            "value_usd": value_usd,
            "reserve0": reserve0,
            "reserve1": reserve1,
            "total_supply": total_supply,
            "pool_value_usd": pool_value_usd,
            "entry_pool_value_usd": entry_pool_value,
            "timestamp_utc": datetime.utcnow(),
            "supported": True,
            "metrics_provenance": (
                "onchain:evm_uniswap_v2_style_pair(getReserves); usd:pair_mid+stables/reference_v2_pair"
            ),
        },
    )


def get_positions_live(
    refresh_interval_seconds: float | None = None,
    record_snapshot: bool = False,
) -> List[Dict[str, Any]]:
    """
    Load current positions and return live metrics for each. Optionally use cached
    result if refresh_interval_seconds is set and last call was within that interval.
    record_snapshot: if True, append to position_snapshots (Phase 2); no-op until storage exists.
    """
    global _last_positions_live, _last_positions_live_ts

    if refresh_interval_seconds is not None and refresh_interval_seconds > 0:
        now = time.monotonic()
        if _last_positions_live is not None and (now - _last_positions_live_ts) < refresh_interval_seconds:
            return _last_positions_live

    state = load_portfolio_state()
    result: List[Dict[str, Any]] = []

    for pos in state.positions:
        metrics = fetch_pool_metrics(pos)
        dex_entry = get_dex_entry(pos.dex)
        chain_id: int | None = dex_entry.get("chain_id") if dex_entry else None
        if chain_id is not None and not isinstance(chain_id, int):
            chain_id = None
        network = (dex_entry or {}).get("network")

        unrealized_usd = (metrics.get("value_usd") or pos.notional_usd) - pos.notional_usd

        if "il_usd" in metrics:
            il_cell = metrics.get("il_usd")
        else:
            il_cell = 0.0 if metrics.get("supported", False) else None

        extra = _enrich_outputs_for_row(pos, metrics, chain_id, network)
        fees_cell = None

        sup = bool(metrics.get("supported"))
        raw0, raw1 = metrics.get("price0_usd"), metrics.get("price1_usd")
        if sup:
            price0_cell = float(raw0) if raw0 is not None else 0.0
            price1_cell = float(raw1) if raw1 is not None else 0.0
        else:
            price0_cell, price1_cell = None, None

        prov = metrics.get("metrics_provenance")
        if not prov and not sup:
            ur = metrics.get("unsupported_reason")
            prov = f"unsupported:{ur}" if ur else None

        row = {
            "pair": f"{pos.token0_symbol}/{pos.token1_symbol}",
            "dex": pos.dex,
            "chain_id": chain_id,
            "network": network,
            "position_id": pos.id,
            "token0_symbol": pos.token0_symbol,
            "token1_symbol": pos.token1_symbol,
            "value_usd": metrics.get("value_usd", pos.notional_usd),
            "unrealized_pnl_usd": unrealized_usd,
            "unrealized_pnl_pct": metrics.get("unrealized_pnl_pct", 0.0),
            "fees_accrued_usd": fees_cell,
            "fees_accrued_usd_est": fees_cell,
            "il_usd": il_cell,
            "price0_usd": price0_cell,
            "price1_usd": price1_cell,
            "timestamp_utc": metrics.get("timestamp_utc", datetime.utcnow()),
            "supported": sup,
            "unsupported_reason": metrics.get("unsupported_reason"),
            "metrics_provenance": prov,
            "apr_fees_24h": float(metrics.get("apr_fees_24h") or 0.0),
            "apr_fees_24h_fill": metrics.get("apr_fees_24h_fill"),
            "entry_apr_fees_24h": pos.entry_apr_fees_24h,
            "tick_lower": pos.tick_lower,
            "tick_upper": pos.tick_upper,
            "tick_current": metrics.get("tick_current"),
            "range_full": pos.range_full,
        }
        row.update(extra)
        # Garantir que enrich nunca repõe fees variáveis nem campos internos na linha API/UI.
        row["fees_accrued_usd"] = fees_cell
        row["fees_accrued_usd_est"] = fees_cell
        row.pop("fees_accrued_usd_linear_est", None)
        if not row.get("metrics_provenance"):
            op = (row.get("outputs_provenance") or "").strip()
            row["metrics_provenance"] = op if op else None
        result.append(row)

        if record_snapshot:
            il_snap = row["il_usd"]
            if il_snap is None:
                il_snap = 0.0
            fees_snap = row["fees_accrued_usd"]
            if fees_snap is None:
                fees_snap = 0.0
            append_position_snapshots([{
                "position_id": pos.id,
                "timestamp": row["timestamp_utc"],
                "value_usd": row["value_usd"],
                "unrealized_pnl_usd": row["unrealized_pnl_usd"],
                "unrealized_pnl_pct": row["unrealized_pnl_pct"],
                "fees_accrued_usd": fees_snap,
                "il_usd": il_snap,
                "apr_snapshot": float(row.get("apr_fees_24h") or 0.0),
                "pool_value_usd": metrics.get("pool_value_usd"),
            }])

    _last_positions_live = result
    _last_positions_live_ts = time.monotonic()
    return result
