"""
Live pool metrics for Solana CLMM pools (Raydium CLMM-compatible PoolState layout).

On-chain: JSON-RPC getAccountInfo for the pool + token vaults (SPL token balances).
USD prices: DexScreener public API (aggregated DEX quotes on Solana) — not an oracle;
documented as estimates. This dashboard provides `il_usd` as a proxy (mark-to-market delta vs initial capital).

Layout matches raydium-io/raydium-clmm `PoolState` (Anchor account + #[repr(C, packed)] body).
Other programs that fork the same account layout can be allowlisted via dex_endpoints.yaml.
"""

from __future__ import annotations

import base64
import os
from datetime import datetime
from typing import Any, Dict, List

import base58
import requests

from lpbot.config_loader import load_env, rpc_url_needs_real_endpoint
from lpbot.models.portfolio import Position

# SPL Token (classic) account: amount u64 at offset 64.
_SPL_AMOUNT_OFFSET = 64

# After 8-byte Anchor discriminator, packed PoolState offsets (see raydium-clmm pool.rs).
_OFF_BUMP = 8
_OFF_MINT_0 = 8 + 1 + 32 * 2  # 73
_OFF_MINT_1 = _OFF_MINT_0 + 32  # 105
_OFF_VAULT_0 = _OFF_MINT_1 + 32  # 137
_OFF_VAULT_1 = _OFF_VAULT_0 + 32  # 169
_OFF_DEC_0 = 8 + 1 + 32 * 7  # 233
_OFF_DEC_1 = 234
_OFF_SQRT = 8 + 1 + 32 * 7 + 1 + 1 + 2 + 16  # 253 → sqrt_price_x64 (u128)
_OFF_TICK_CURRENT = _OFF_SQRT + 16  # 269 → tick_current (i32)

_MIN_POOL_DATA_LEN = _OFF_TICK_CURRENT + 4

# Default Raydium CLMM program (add forks / Pancake Solana IDs in yaml).
_DEFAULT_CLMM_PROGRAM_IDS = frozenset({"CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK"})

# Common Solana USD-stable mints → 1.0 USD (on-chain names; still approximate).
_STABLE_MINT_USD = {
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": 1.0,  # USDC
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB": 1.0,  # USDT
}

_DEXSCREENER_TOKENS_URL = "https://api.dexscreener.com/latest/dex/tokens/{mint}"


def is_solana_pool_pubkey(pool_id: str) -> bool:
    """True if `pool_id` is a valid base58-encoded 32-byte Solana public key (not EVM 0x)."""
    s = (pool_id or "").strip()
    if not s or s.startswith("0x"):
        return False
    try:
        raw = base58.b58decode(s)
    except Exception:
        return False
    return len(raw) == 32


def _rpc_call(rpc_url: str, method: str, params: List[Any], timeout: float = 30.0) -> Any:
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    r = requests.post(rpc_url, json=payload, timeout=timeout)
    r.raise_for_status()
    body = r.json()
    if "error" in body and body["error"]:
        raise RuntimeError(str(body["error"]))
    return body.get("result")


def _account_data_b64(rpc_url: str, address: str) -> tuple[str, str] | None:
    """Returns (owner, base64_data) or None if missing."""
    res = _rpc_call(
        rpc_url,
        "getAccountInfo",
        [address, {"encoding": "base64"}],
    )
    if not res or not res.get("value"):
        return None
    val = res["value"]
    owner = val.get("owner") or ""
    data = val.get("data")
    if not data or not isinstance(data, list) or not data[0]:
        return None
    return owner, str(data[0])


def _read_pubkey(data: bytes, offset: int) -> str:
    return base58.b58encode(data[offset : offset + 32]).decode("ascii")


def _read_u64(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset : offset + 8], "little")


def _read_u128(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset : offset + 16], "little")


def _read_i32_le(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset : offset + 4], "little", signed=True)


def _spl_token_amount(rpc_url: str, vault_address: str) -> int | None:
    row = _account_data_b64(rpc_url, vault_address)
    if not row:
        return None
    _owner, b64 = row
    raw = base64.b64decode(b64)
    if len(raw) < _SPL_AMOUNT_OFFSET + 8:
        return None
    return _read_u64(raw, _SPL_AMOUNT_OFFSET)


def _dexscreener_usd_for_mint(mint_b58: str, timeout: float = 15.0) -> float | None:
    """
    Best-effort USD price from DexScreener (highest-liquidity Solana pair).
    Returns None if no Solana route / parse failure.
    """
    if mint_b58 in _STABLE_MINT_USD:
        return float(_STABLE_MINT_USD[mint_b58])
    url = _DEXSCREENER_TOKENS_URL.format(mint=mint_b58)
    try:
        r = requests.get(url, timeout=timeout)
        r.raise_for_status()
        pairs = (r.json() or {}).get("pairs") or []
    except Exception:
        return None
    sol_pairs = [p for p in pairs if p.get("chainId") == "solana" and p.get("priceUsd")]
    if not sol_pairs:
        return None

    def _liq_usd(p: dict) -> float:
        liq = p.get("liquidity") or {}
        try:
            return float(liq.get("usd") or 0.0)
        except (TypeError, ValueError):
            return 0.0

    best = max(sol_pairs, key=_liq_usd)
    try:
        return float(best["priceUsd"])
    except (TypeError, ValueError, KeyError):
        return None


def _clmm_program_allowlist(dex_entry: Dict[str, Any]) -> frozenset[str]:
    raw = dex_entry.get("clmm_program_ids")
    if isinstance(raw, list) and raw:
        return frozenset(str(x).strip() for x in raw if str(x).strip())
    return _DEFAULT_CLMM_PROGRAM_IDS


def fetch_solana_clmm_pool_metrics(
    position: Position,
    dex_entry: Dict[str, Any],
    fallback: Dict[str, Any],
    entry_pool_value_cache: Dict[str, float],
) -> Dict[str, Any]:
    """
    Returns the same shape as `fetch_pool_metrics` EVM path, plus:
    - il_usd: proxy (value_usd - position.notional_usd)
    - metrics_provenance: short string for UI/logs
    """
    load_env()
    rpc_env = dex_entry.get("rpc_url_env")
    if not rpc_env:
        return {**fallback, "unsupported_reason": "solana_rpc_url_env_missing"}
    rpc_url = os.getenv(str(rpc_env))
    if not rpc_url or rpc_url_needs_real_endpoint(rpc_url):
        return {**fallback, "unsupported_reason": f"env_not_set:{rpc_env}"}

    pool_id = (position.pool_id or "").strip()
    if not is_solana_pool_pubkey(pool_id):
        return {**fallback, "unsupported_reason": "invalid_solana_pool_pubkey"}

    allow = _clmm_program_allowlist(dex_entry)
    try:
        acc = _account_data_b64(rpc_url, pool_id)
        if not acc:
            return {**fallback, "unsupported_reason": "solana_pool_account_missing"}
        owner, b64 = acc
        if owner not in allow:
            return {
                **fallback,
                "unsupported_reason": f"program_owner_not_allowed:{owner}",
            }
        data = base64.b64decode(b64)
        if len(data) < _MIN_POOL_DATA_LEN:
            return {**fallback, "unsupported_reason": "solana_pool_data_too_short"}

        mint0 = _read_pubkey(data, _OFF_MINT_0)
        mint1 = _read_pubkey(data, _OFF_MINT_1)
        vault0 = _read_pubkey(data, _OFF_VAULT_0)
        vault1 = _read_pubkey(data, _OFF_VAULT_1)
        dec0 = data[_OFF_DEC_0]
        dec1 = data[_OFF_DEC_1]
        sqrt_x64 = _read_u128(data, _OFF_SQRT)
        tick_current = _read_i32_le(data, _OFF_TICK_CURRENT)

        bal0 = _spl_token_amount(rpc_url, vault0)
        bal1 = _spl_token_amount(rpc_url, vault1)
        if bal0 is None or bal1 is None:
            return {**fallback, "unsupported_reason": "solana_vault_read_failed"}

        p0 = _dexscreener_usd_for_mint(mint0)
        p1 = _dexscreener_usd_for_mint(mint1)
        if p0 is None or p1 is None or p0 <= 0 or p1 <= 0:
            return {**fallback, "unsupported_reason": "usd_price_unavailable"}

        human0 = bal0 / (10**dec0)
        human1 = bal1 / (10**dec1)
        pool_value_usd = human0 * p0 + human1 * p1

        apr_fees_24h = 0.0

        # Mid ratio (token1 per token0, human units) from Q64.64 sqrt — informational only.
        if sqrt_x64 > 0:
            sqrt_f = sqrt_x64 / (2**64)
            ratio_raw = sqrt_f * sqrt_f
            mid_token1_per_token0 = ratio_raw * (10 ** (dec0 - dec1))
        else:
            mid_token1_per_token0 = 0.0

        entry_pool_value = entry_pool_value_cache.get(position.id)
        if entry_pool_value is None or entry_pool_value <= 0:
            entry_pool_value = pool_value_usd if pool_value_usd > 0 else position.notional_usd
            entry_pool_value_cache[position.id] = entry_pool_value

        if entry_pool_value and entry_pool_value > 0:
            value_usd = position.notional_usd * (pool_value_usd / entry_pool_value)
        else:
            value_usd = position.notional_usd

        notional = position.notional_usd
        unrealized_pnl_pct = ((value_usd - notional) / notional * 100.0) if notional else 0.0
        il_usd_proxy = float(value_usd - position.notional_usd)

        return {
            "apr_fees_24h": apr_fees_24h,
            "unrealized_pnl_pct": unrealized_pnl_pct,
            "price0_usd": float(p0),
            "price1_usd": float(p1),
            "value_usd": value_usd,
            "reserve0": bal0,
            "reserve1": bal1,
            "total_supply": 0,
            "pool_value_usd": pool_value_usd,
            "entry_pool_value_usd": entry_pool_value,
            "timestamp_utc": datetime.utcnow(),
            "supported": True,
            "il_usd": il_usd_proxy,
            "metrics_provenance": (
                "onchain:solana_rpc+clmm_vault_balances; usd:DexScreener(solana); "
                f"mid_token1_per_token0_est={mid_token1_per_token0:.8g}"
            ),
            "tick_current": tick_current,
        }
    except Exception as exc:
        return {
            **fallback,
            "unsupported_reason": f"solana_rpc_error:{exc!s}"[:200],
        }
