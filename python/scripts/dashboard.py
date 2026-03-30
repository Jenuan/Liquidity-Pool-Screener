"""
LP Bot dashboard (Streamlit). Consumes only lpbot APIs: get_positions_live,
get_wallet_summary, get_events_table, get_pnl_evolution, get_wallet_evolution.

Test: from the lp-bot-python directory, run ``streamlit run scripts/dashboard.py``.
The main column uses ``st.fragment(run_every=...)`` so periodic updates rerun only
that block; sidebar/title reload on widget changes or initial page load (normal Streamlit).
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

# Ensure project root is on path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from lpbot.config_loader import load_env, load_risk_config
from lpbot.datasources.live_metrics import get_positions_live
from lpbot.analytics import (
    get_wallet_summary,
    get_events_table,
    get_pnl_evolution,
    get_wallet_evolution,
    compute_basic_metrics,
)

_CHAIN_NAMES: dict[int, str] = {1: "ethereum", 56: "bsc", 8453: "base"}


def _min_returns_for_sharpe() -> int:
    return 2


def _compute_sharpe(returns: list[float], periods_per_year: float = 365.0) -> float | None:
    if not returns or len(returns) < _min_returns_for_sharpe():
        return None
    import statistics
    mean_ret = statistics.mean(returns)
    std_ret = statistics.stdev(returns)
    if std_ret == 0:
        return None
    return (mean_ret / std_ret) * (periods_per_year ** 0.5)


def _compute_max_drawdown(values: list[float]) -> float | None:
    if not values or len(values) < 2:
        return None
    peak = values[0]
    max_dd = 0.0
    for v in values:
        if v > peak:
            peak = v
        dd = (peak - v) / peak if peak else 0.0
        if dd > max_dd:
            max_dd = dd
    return max_dd * 100.0  # percent


def main() -> None:
    load_env()

    st.set_page_config(page_title="LP Bot Dashboard", layout="wide")
    st.title("LP Bot Dashboard")

    refresh_interval = st.sidebar.number_input(
        "Atualizar a cada (segundos)",
        min_value=0,
        max_value=300,
        value=5,
        help="Intervalo de refresh automático do bloco central. 0 desativa — use «Atualizar agora».",
    )
    # Padrão desativado para evitar bloqueios no SQLite enquanto o bot está rodando.
    record_snapshot = st.sidebar.checkbox("Gravar snapshots ao atualizar", value=False)
    initial_capital = load_risk_config().initial_capital_usd

    # Wallet summary
    try:
        summary = get_wallet_summary()
    except Exception as e:
        summary = {}
        st.sidebar.error(f"Erro ao carregar carteira: {e}")

    if summary:
        st.sidebar.subheader("Carteira")
        st.sidebar.metric("Cash (USD)", f"{summary.get('cash_usd', 0):.2f}")
        st.sidebar.metric("Investido (USD)", f"{summary.get('invested_usd', 0):.2f}")
        st.sidebar.metric("Valor total (USD)", f"{summary.get('wallet_total_value_usd', 0):.2f}")
        st.sidebar.metric("PnL realizado (USD)", f"{summary.get('realized_pnl_usd', 0):.2f}")

    if refresh_interval > 0:
        st.sidebar.caption(f"Auto-refresh do painel central: {refresh_interval}s")
    else:
        st.sidebar.caption("Auto-refresh desligado — use «Atualizar agora» na área principal.")

    run_every = float(refresh_interval) if refresh_interval > 0 else None

    @st.fragment(run_every=run_every)
    def live_dashboard() -> None:
        if refresh_interval <= 0:
            st.button("Atualizar agora", type="primary")

        # Positions live
        try:
            positions = get_positions_live(
                refresh_interval_seconds=None,
                record_snapshot=record_snapshot,
            )
        except Exception as e:
            positions = []
            st.warning(f"Erro ao carregar posições: {e}")

        missing_rpc = sorted({
            str(p.get("unsupported_reason", "")).split(":", 1)[1].strip()
            for p in positions
            if str(p.get("unsupported_reason") or "").startswith("env_not_set:")
        })
        if missing_rpc:
            msg = (
                "Métricas live indisponíveis: defina no `.env` na raiz do projeto "
                + ", ".join(missing_rpc)
                + " e reinicie o Streamlit."
            )
            st.warning(msg)

        st.subheader("Posições ao vivo")
        if positions:
            import pandas as pd

            def _il_display(v):
                # Mantém tipo numérico na coluna do dataframe (None -> NaN).
                if v is None:
                    return None
                try:
                    return float(v)
                except (TypeError, ValueError):
                    return None

            def _network_display(p) -> str:
                n = p.get("network")
                if n:
                    return str(n).strip().lower()
                cid = p.get("chain_id")
                if isinstance(cid, int) and cid in _CHAIN_NAMES:
                    return _CHAIN_NAMES[cid]
                if cid is not None:
                    return f"evm ({cid})"
                return "—"

            def _price_pair_display(p) -> tuple:
                """Retorna (price0_usd, price1_usd) numéricos ou None quando indisponível."""
                if not p.get("supported"):
                    return None, None
                p0, p1 = p.get("price0_usd"), p.get("price1_usd")
                if p0 is None or p1 is None:
                    return None, None
                try:
                    f0, f1 = float(p0), float(p1)
                except (TypeError, ValueError):
                    return None, None
                if f0 == 0.0 and f1 == 0.0:
                    return None, None
                return f0, f1

            def _cell_price(v):
                if v is None:
                    return "—"
                try:
                    f = float(v)
                except (TypeError, ValueError):
                    return "—"
                return f

            def _cell_sym(s: str) -> str:
                t = (s or "").strip()
                return t if t else "—"

            def _fees_display(p):
                v = p.get("fees_accrued_usd")
                if v is None:
                    return None
                try:
                    return float(v)
                except (TypeError, ValueError):
                    return None

            def _metrics_source(p):
                src = (p.get("metrics_provenance") or "").strip()
                if src:
                    return src
                op = (p.get("outputs_provenance") or "").strip()
                if op:
                    return op
                if not p.get("supported") and p.get("unsupported_reason"):
                    return f"unsupported:{p['unsupported_reason']}"
                return "—"

            def _pnl_pct_display(p):
                if not p.get("supported"):
                    return None
                v = p.get("unrealized_pnl_pct", 0.0)
                try:
                    return float(v)
                except (TypeError, ValueError):
                    return None

            rows = []
            for p in positions:
                pr0, pr1 = _price_pair_display(p)
                p0_raw = p.get("price0_usd")
                p1_raw = p.get("price1_usd")
                rows.append({
                    "Par": p["pair"],
                    "DEX": p["dex"],
                    "Rede": _network_display(p),
                    "Live suportado": "Sim" if p.get("supported") else "Nao",
                    "Motivo sem live": p.get("unsupported_reason") or "—",
                    "Token0": _cell_sym(p.get("token0_symbol", "")),
                    "Token1": _cell_sym(p.get("token1_symbol", "")),
                    "Preço token0 (USD)": _cell_price(p0_raw) if pr0 is None else pr0,
                    "Preço token1 (USD)": _cell_price(p1_raw) if pr1 is None else pr1,
                    "Valor (USD)": p["value_usd"],
                    "PnL não realizado %": _pnl_pct_display(p),
                    "IL (USD)": _il_display(p.get("il_usd")),
                    "Fees (USD)": _fees_display(p),
                    "Fonte métricas": _metrics_source(p),
                    "Atualizado": p["timestamp_utc"].isoformat() if hasattr(p["timestamp_utc"], "isoformat") else str(p["timestamp_utc"]),
                })

            df = pd.DataFrame(rows)
            st.dataframe(df, width="stretch")
        else:
            st.info("Nenhuma posição aberta.")

        # Wallet evolution chart
        try:
            wallet_ev = get_wallet_evolution()
        except Exception:
            wallet_ev = []

        st.subheader("Evolução da carteira")
        if len(wallet_ev) >= 2:
            import pandas as pd
            df_ev = pd.DataFrame(wallet_ev)
            df_ev["timestamp"] = pd.to_datetime(df_ev["timestamp"])
            st.line_chart(df_ev.set_index("timestamp")[["wallet_total_value_usd", "cash_usd"]])
        else:
            st.info("Dados insuficientes para gráfico (precisa de pelo menos 2 snapshots).")

        # Indicators
        try:
            metrics = compute_basic_metrics()
            get_pnl_evolution()
            wallet_ev_list = get_wallet_evolution()
        except Exception:
            metrics = {}
            wallet_ev_list = []

        st.subheader("Indicadores")
        col1, col2, col3, col4 = st.columns(4)

        realized = metrics.get("realized_pnl_usd") or metrics.get("total_realized_pnl_usd") or 0.0
        profit_index = (realized / initial_capital * 100.0) if initial_capital else 0.0
        col1.metric("Índice de lucro (%)", f"{profit_index:.2f}", help="PnL realizado / capital inicial")

        values = [w["wallet_total_value_usd"] for w in wallet_ev_list]
        returns = []
        for i in range(1, len(values)):
            if values[i - 1] and values[i - 1] != 0:
                returns.append((values[i] - values[i - 1]) / values[i - 1])
        sharpe = _compute_sharpe(returns)
        col2.metric("Sharpe ratio", f"{sharpe:.2f}" if sharpe is not None else "N/A", help="Requer pelo menos 2 pontos de dados")

        max_dd = _compute_max_drawdown(values)
        col3.metric("Max drawdown (%)", f"{max_dd:.2f}" if max_dd is not None else "N/A")

        total_trades = metrics.get("total_trades", 0) or 0
        col4.metric("Nº de trades", f"{int(total_trades)}")

        try:
            events = get_events_table()
            close_events = [e for e in events if e.get("event_type") == "CLOSE_POSITION"]
            wins = sum(1 for e in close_events if (e.get("delta_realized_pnl_usd") or 0) > 0)
            win_rate = (wins / len(close_events) * 100.0) if close_events else None
        except Exception:
            win_rate = None
        st.metric("Win rate (fechamentos) %", f"{win_rate:.1f}" if win_rate is not None else "N/A")

        # Bot decisions (last N events)
        try:
            events = get_events_table()
            last_n = 15
            events_display = events[-last_n:] if len(events) > last_n else events
            events_display = list(reversed(events_display))
        except Exception:
            events_display = []

        st.subheader("Últimas decisões do bot")
        if events_display:
            import pandas as pd
            st.dataframe(pd.DataFrame(events_display), width="stretch")
        else:
            st.info("Nenhum evento registrado.")

    live_dashboard()


if __name__ == "__main__":
    main()
