# LP Screener for Google Sheets

**LP Screener** is a Google Apps Script that automatically finds and scores liquidity pools (LPs) across multiple chains. It pulls data from DexScreener and GeckoTerminal, applies your own safety filters and scoring, and updates a Google Sheet. Optional email alerts notify you when high-score, high-APR opportunities appear.

## Python companion bot (`python/`)

This repo also includes an optional **Python** stack: it reads the same Google Sheet, applies LP / risk logic, and can run a **Streamlit dashboard** with live-style metrics (RPCs, DexScreener, on-chain reads where supported). Setup, env vars, and metric limitations are documented in **[python/README.md](python/README.md)**.

**Typical flow:** Apps Script fills the sheet → configure a Google **service account** + Sheet ID in `python/.env` (never commit that file or JSON keys) → run scripts from the `python/` directory. See **[SECURITY.md](SECURITY.md)** for what must stay local.

## Project status

| Component | Stage | Notes |
|-----------|--------|--------|
| **Apps Script screener** (`main_code_lp.gs`) | **Configurable community tool** | You own all thresholds, filters, and scoring in `CONFIG`. Output quality depends entirely on your settings. |
| **Python companion** (`python/`) | **Experimental / early** | Sheet integration, risk/executor flow, and Streamlit dashboard; **live metrics are partial** (RPC + public APIs, DEX/pool coverage gaps). See **[python/README.md](python/README.md)** for limitations (fees on live table, V3 vs V2, Solana CLMM assumptions, etc.). |

**Not financial advice** (DYOR). The Python side is **not** presented as production-ready execution software; use it for **monitoring and research**, validate every figure before any on-chain action, and expect breaking changes.

This status should be updated in the same commit whenever capabilities materially change.

## Features

- **Multi-chain**: Screen pools on Solana, Base, and other supported chains (configurable).
- **Filter-first search**: Fetches many pairs per chain, then filters by your minimum liquidity, volume, and transaction counts.
- **Scoring**: Combines pool quality (liquidity, volume, activity) and APR into a single score; you choose the weights.
- **Google Sheet output**: Top pools appear in a sheet with links, APR, volume, and score.
- **Optional email alerts**: Get emails when a pool exceeds your minimum score and APR thresholds.
- **Auto-refresh**: Run on a schedule (e.g. every 15 minutes) via a time-based trigger.

## Screenshots

**Sheet output** — The script fills the sheet from row 4 and writes the "Last Update" timestamp in row 2. The header row is created automatically on first run (see [Sheet layout](#sheet-layout) below).

Example header row (row 1):

| Chain | Pair | Base | Quote | DEX | Pool Score | Grade | AdjAPR | Range | Safety |
|-------|------|------|-------|-----|------------|-------|--------|-------|--------|
| Duration | Link | PairAddress | BaseAddr | QuoteAddr | volume24h | tvl | volumeTvlRatio | feeTier*100 | baseAPR |
| optimizedAPR | riskLevel | marketCa | pairAge | liquidityChange24h | priceChange1h | finalScore | status | notes | |

**Email alert** — When email alerts are enabled, you get one email per qualifying pool (subject and body like below).

<img src="docs/email-example.png" alt="Example email alert for a high-score pool" width="480" style="border-radius: 12px;">

Example email body:

```
🔥 HIGH-QUALITY OPPORTUNITY DETECTED! 🔥

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PAIR: WAR/SOL
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Chain: Solana
DEX: pumpswap

🏆 QUALITY GRADE: A/S
📊 FINAL SCORE: 86.2/100

📋 CONTRACT ADDRESSES:
• Pair Contract: D8gczSF4uYxWt5FJEfdRUWNYdBW1LoNUYDJ8GspakwUJ
• WAR Contract: DeVVwq85BuiRPhxiSxw97AogQ8ensFC1mr4NZ4GA5PGD
• SOL Contract: So11111111111111111111111111111111111111112

📊 APR BREAKDOWN:
• Base APR (Full Range): 19331.5%
• Optimized APR (Concentrated): 19331.5%
• Adjusted APR (Risk-Adjusted): 19331.5% ⭐

🎯 RANGE SETUP:
• Recommended Range: Full Range
• Safety Score: 0/100
• Expected Duration: N/A
• Risk Level: EXTREME

💰 POOL METRICS:
• 24h Volume: $15.153.279,7
• TVL: $114.046,182
• Volume/TVL Ratio: 132.87x
• Market Cap: $71.595,742

📈 ACTIVITY INDICATORS:
💰 High volume
🔥 Very recent volume
🚀 Strong acceleration
💎 Very active
⚡ High efficiency

⚠️ RISK FACTORS:
• Price Change 1h: 6.6%
• Liquidity Change 24h: 0.0%
• Pair Age: 3.7 hours

🔗 QUICK LINKS:
DexScreener: https://dexscreener.com/solana/D8gczSF4uYxWt5FJEfdRUWNYdBW1LoNUYDJ8GspakwUJ

📋 ADD LIQUIDITY:
Solana Pool: D8gczSF4uYxWt5FJEfdRUWNYdBW1LoNUYDJ8GspakwUJ

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

This is an automated alert from your LP Screener. Always DYOR!
```

## How to run

1. Open your Google Sheet (the one bound to the script).
2. Go to **Extensions → Apps Script**.
3. **One-time run**: Select the function `updateLPScreener` and click **Run**. This fetches pools, applies your filters, and updates the sheet.
4. **Automatic refresh**: Run `setupAutoRefresh()` once (select it and click Run). It creates a time-based trigger so `updateLPScreener` runs every X minutes (set in `CONFIG.REFRESH_TIME`).
5. **Manual refresh anytime**: You can also run `manualRefresh()` for a single update without changing triggers.

## Setup (quick)

1. Create a Google Sheet and (optionally) name a tab **LP Screener** (or set `CONFIG.SHEET_NAME` in the script).
2. **Extensions → Apps Script**: create a new script bound to that spreadsheet.
3. Copy the contents of **main_code_lp.gs** into the script editor (replace any default code).
4. Edit the **CONFIG** object at the top of the script: set your minimum liquidity, volume, transactions, scoring thresholds, token lists per chain, and (optionally) email. The repo ships with placeholders (e.g. `0`); you must choose values that match your strategy.
5. Save, run `updateLPScreener` once to test, then run `setupAutoRefresh()` if you want automatic updates.

For a **step-by-step guide** (clone → paste → configure → deploy), see **[SETUP.md](SETUP.md)**.

The script **creates the sheet header row automatically on first run**. Ensure the sheet tab exists and is named as in `CONFIG.SHEET_NAME`; then run `updateLPScreener` once.

## Sheet layout

Row 1 is the header row (written by the script if empty). Row 2 column A is overwritten with "Last Update: …". Data starts at row 4. Column order:

| # | Column | # | Column | # | Column |
|---|--------|---|--------|---|--------|
| 1 | Chain | 11 | Duration | 21 | optimizedAPR |
| 2 | Pair | 12 | Link | 22 | riskLevel |
| 3 | Base | 13 | PairAddress | 23 | marketCa |
| 4 | Quote | 14 | BaseAddr | 24 | pairAge |
| 5 | DEX | 15 | QuoteAddr | 25 | liquidityChange24h |
| 6 | Pool Score | 16 | volume24h | 26 | priceChange1h |
| 7 | Grade | 17 | tvl | 27 | finalScore |
| 8 | AdjAPR | 18 | volumeTvlRatio | 28 | status |
| 9 | Range | 19 | feeTier*100 | 29 | notes |
| 10 | Safety | 20 | baseAPR | | |

## Config overview

All settings live in the **CONFIG** object at the top of **main_code_lp.gs**:

| Area | What to set |
|------|-------------|
| **Safety filters** | `MIN_ABSOLUTE_LIQUIDITY`, `MIN_ABSOLUTE_VOLUME`, `MIN_ABSOLUTE_TRANSACTIONS` — pools below these are excluded. |
| **Scoring** | `GOOD_VOLUME_24H`, `GREAT_VOLUME_24H`, `GOOD_TVL`, `GREAT_TVL` — used for score calculation. `WEIGHT_POOL_QUALITY` and `WEIGHT_APR` — how much pool quality vs APR matters (e.g. 0.6 and 0.4). |
| **Display** | `MIN_SCORE_TO_SHOW`, `MIN_ADJUSTED_APR_TO_SHOW`, `MAX_RESULTS` — which pools appear in the sheet. |
| **Chains & tokens** | `CHAINS`, `DEXSCREENER_SEARCH_TOKENS` — which chains and token symbols to search. Customize token lists per chain for the pools you care about. |
| **Email alerts** | `EMAIL_ADDRESS` (or set in Apps Script Project/Script properties), `EMAIL_MIN_FINAL_SCORE`, `EMAIL_MIN_APR`. Leave email empty to disable. |
| **Refresh** | `REFRESH_TIME` — interval in minutes for the auto-refresh trigger. |

The repository ships with **placeholder values** (e.g. `0`). You must set your own numbers and token lists; the best pools depend on your strategy.

## License

This project is licensed under the [MIT License](LICENSE). You may use, modify, and distribute it under the terms of that license.

## Security

No secrets are stored in this repo. Configure your email and any API keys in Google Apps Script (script editor or **File → Project properties → Script properties**), not in committed code. See [SECURITY.md](SECURITY.md).

## Roadmap

- More chains and DEXs.
- Optional Telegram bot or notifications.
- Richer strategy tooling (the Python bot in `python/` is a starting point for automation and monitoring).

## Contributing & help wanted

We welcome issues and pull requests, especially:

- **Strategy & risk:** Scoring, filters, and position sizing ideas grounded in real LP experience (this is not financial advice; always DYOR).
- **Accessibility:** Clearer docs for non-developers, fewer manual steps, and plain-language explanations.
- **Internationalization:** Portuguese/English improvements across READMEs and UI copy.

## Files in this repo

| File | Purpose |
|------|---------|
| **main_code_lp.gs** | Single file to copy into Apps Script. Contains CONFIG and all logic. |
| **README.md** | This file — overview and how to run. |
| **SETUP.md** | Step-by-step setup and deployment. |
| **SECURITY.md** | How we handle secrets and configuration. |
| **LICENSE** | MIT License — use, modify, and distribute with attribution. |
| **docs/** | Screenshot: `email-example.png` (email alert example, used in this README). |
| **METEORA_LINK_FIX.txt** | Optional note: if Meteora “Add Liquidity” links fail, use the DexScreener pair page instead. |
| **python/** | Optional Python bot: sheet integration, risk/executor logic, Streamlit dashboard. See [python/README.md](python/README.md). |


### Keywords
Defi, cripto, liquidity, pools, pancakeswap, uniswap, meteora, memecoins, usdc, solana, bitcoin
