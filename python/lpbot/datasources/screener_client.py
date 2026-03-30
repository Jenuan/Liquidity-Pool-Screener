"""
Cliente do LP Screener.

Versão mínima: lê dados do Google Sheets usando `gspread` e devolve
uma lista de dicionários (linhas normalizadas).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import gspread

from lpbot.config_loader import PROJECT_ROOT, load_env, load_dex_config


def _get_service_account_client() -> gspread.Client:
    """Cria um client do gspread usando o JSON da service account."""
    import os

    json_path = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not json_path:
        raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON não definido no .env")

    resolved = Path(json_path)
    if not resolved.is_absolute():
        resolved = PROJECT_ROOT / resolved

    if not resolved.exists():
        raise FileNotFoundError(f"Service account JSON não encontrado em: {resolved}")

    return gspread.service_account(filename=str(resolved))


def _non_empty_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _is_valid_screener_row(data: Dict[str, Any]) -> bool:
    """
    Descarta linhas que não são pares reais da planilha.

    O Apps Script escreve os pares a partir de DATA_START_ROW (ex.: 4), mas o intervalo
    A1:Z500 inclui linhas 2–3 (ex.: "Last Update" em A2) e células vazias alinhadas às
    colunas de métricas — isso gerava candidatos com APR preenchido por dados antigos
    e DEX/PairAddress/Base/Quote vazios, levando a UNKNOWN no bot.
    """
    chain = _non_empty_str(data.get("Chain")).lower()
    if chain.startswith("last update"):
        return False

    dex = _non_empty_str(data.get("DEX") or data.get("dex"))
    pool_id = _non_empty_str(data.get("PairAddress") or data.get("pool_id"))
    base = _non_empty_str(data.get("Base") or data.get("token0_symbol"))
    quote = _non_empty_str(data.get("Quote") or data.get("token1_symbol"))

    if not dex or not pool_id or not base or not quote:
        return False
    if pool_id.upper() in {"N/A", "NA", "-", "NONE"}:
        return False
    if base in {"?", "-"} or quote in {"?", "-"}:
        return False

    return True


def _enrich_screener_row(data: Dict[str, Any]) -> None:
    """
    Preenche Base/Quote a partir da coluna Pair (ex.: WIF/USDT) quando vazias.
    Mantém compatibilidade com a planilha do Apps Script.
    """
    base = _non_empty_str(data.get("Base") or data.get("token0_symbol"))
    quote = _non_empty_str(data.get("Quote") or data.get("token1_symbol"))
    if base and quote:
        return
    pair_text = _non_empty_str(data.get("Pair"))
    if not pair_text or "/" not in pair_text:
        return
    parts = [p.strip() for p in pair_text.split("/", 1)]
    if len(parts) != 2:
        return
    b, q = parts[0], parts[1]
    if not b or not q:
        return
    if not base:
        data["Base"] = b
    if not quote:
        data["Quote"] = q


def fetch_screener_rows() -> List[Dict[str, Any]]:
    """
    Busca as linhas atuais do LP Screener no Google Sheets.
    """
    import os

    load_env()
    dex_cfg = load_dex_config()
    screener_cfg = dex_cfg.datasources.get("screener", {})

    sheet_id_env = os.getenv("GOOGLE_SHEET_ID")
    sheet_id_cfg = screener_cfg.get("sheet_id")
    sheet_id = sheet_id_env or sheet_id_cfg
    if not sheet_id:
        raise RuntimeError(
            "Nenhum Google Sheet ID configurado (GOOGLE_SHEET_ID ou datasources.screener.sheet_id)."
        )

    range_a1 = screener_cfg.get("range", "LPs!A1:Z500")

    # Separar nome da aba e intervalo A1 (para evitar duplicar o nome da aba)
    if "!" in range_a1:
        sheet_name, a1_range = range_a1.split("!", 1)
    else:
        sheet_name, a1_range = range_a1, "A1:Z500"

    client = _get_service_account_client()
    sheet = client.open_by_key(sheet_id)
    worksheet = sheet.worksheet(sheet_name)
    values = worksheet.get(a1_range)
    if not values:
        return []

    header, *rows = values
    header = [str(c).strip() for c in header]

    # Pula linhas “meta” logo abaixo do header (ex.: A2 Last Update, linha 3 vazia)
    # quando o screener grava pares só a partir de DATA_START_ROW (p.ex. 4).
    skip_leading = int(screener_cfg.get("skip_leading_rows_after_header", 0) or 0)
    if skip_leading > 0:
        rows = rows[skip_leading:]

    result: List[Dict[str, Any]] = []
    for row in rows:
        row = (row + [""] * len(header))[: len(header)]
        data = dict(zip(header, row))

        if "apr_fees_24h" in data:
            # Trata formato pt-BR vindo da planilha (ex.: "202,22" ou "1.234,56")
            raw = str(data["apr_fees_24h"]).replace("%", "").strip()
            raw = raw.replace(".", "").replace(",", ".")
            try:
                data["apr_fees_24h"] = float(raw)
            except ValueError:
                data["apr_fees_24h"] = 0.0

        # Planilha do screener (Apps Script) usa coluna "riskLevel"; o bot espera "risk_level"
        if not data.get("risk_level") and data.get("riskLevel") is not None:
            rl = _non_empty_str(data.get("riskLevel"))
            data["risk_level"] = rl.upper() if rl else "MEDIUM"
        if not data.get("risk_level"):
            data["risk_level"] = "MEDIUM"

        _enrich_screener_row(data)

        if not _is_valid_screener_row(data):
            continue

        result.append(data)

    return result

