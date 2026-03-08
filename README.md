# LP Screener for Google Sheets

**LP Screener** is a Google Apps Script that automatically finds and scores liquidity pools (LPs) across multiple chains. It pulls data from DexScreener and GeckoTerminal, applies your own safety filters and scoring, and updates a Google Sheet. Optional email alerts notify you when high-score, high-APR opportunities appear.

## Features

- **Multi-chain**: Screen pools on Solana, Base, and other supported chains (configurable).
- **Filter-first search**: Fetches many pairs per chain, then filters by your minimum liquidity, volume, and transaction counts.
- **Scoring**: Combines pool quality (liquidity, volume, activity) and APR into a single score; you choose the weights.
- **Google Sheet output**: Top pools appear in a sheet with links, APR, volume, and score.
- **Optional email alerts**: Get emails when a pool exceeds your minimum score and APR thresholds.
- **Auto-refresh**: Run on a schedule (e.g. every 15 minutes) via a time-based trigger.

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

## Security

No secrets are stored in this repo. Configure your email and any API keys in Google Apps Script (script editor or **File → Project properties → Script properties**), not in committed code. See [SECURITY.md](SECURITY.md).

## Roadmap

- More chains and DEXs.
- Optional Telegram bot or notifications.
- Optional standalone script/config for power users.

## Files in this repo

| File | Purpose |
|------|---------|
| **main_code_lp.gs** | Single file to copy into Apps Script. Contains CONFIG and all logic. |
| **README.md** | This file — overview and how to run. |
| **SETUP.md** | Step-by-step setup and deployment. |
| **SECURITY.md** | How we handle secrets and configuration. |
| **METEORA_LINK_FIX.txt** | Optional note: if Meteora “Add Liquidity” links fail, use the DexScreener pair page instead. |
