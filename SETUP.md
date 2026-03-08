# LP Screener — Step-by-step setup

Follow these steps to run the LP Screener in your own Google Sheet.

## 1. Get the code

- **Option A**: Clone or download this repository. You only need the file **main_code_lp.gs**.
- **Option B**: Open **main_code_lp.gs** in the repo and copy its entire contents (Ctrl+A, Ctrl+C).

## 2. Create a Google Sheet

1. Go to [Google Sheets](https://sheets.google.com) and create a new spreadsheet.
2. (Optional) Rename the first sheet tab to **LP Screener**. If you use another name, you’ll set it in CONFIG later as `SHEET_NAME`.

## 3. Open Apps Script and paste the code

1. In the spreadsheet, go to **Extensions → Apps Script**.
2. If you see default code (e.g. `function myFunction() {}`), delete it.
3. Paste the full contents of **main_code_lp.gs** into the editor.
4. Click **File → Save** (or Ctrl+S) and give the project a name (e.g. “LP Screener”).

## 4. Configure CONFIG

The script will not work meaningfully until you set your own values. At the top of the pasted code you’ll see a `CONFIG` object.

1. **Safety filters** (required for filtering):
   - `MIN_ABSOLUTE_LIQUIDITY` — e.g. 50000 (minimum liquidity in USD).
   - `MIN_ABSOLUTE_VOLUME` — e.g. 50000 (minimum 24h volume in USD).
   - `MIN_ABSOLUTE_TRANSACTIONS` — e.g. 3000 (minimum 24h transaction count).

2. **Scoring** (used to compute the 0–100 score):
   - Set `GOOD_VOLUME_24H`, `GREAT_VOLUME_24H`, `GOOD_TVL`, `GREAT_TVL` to dollar values that match your idea of “good” and “great”.
   - Set `WEIGHT_POOL_QUALITY` and `WEIGHT_APR` (e.g. 0.6 and 0.4); they should sum to 1.0.

3. **Display**:
   - `MIN_SCORE_TO_SHOW` — e.g. 20 (only pools with score ≥ this appear).
   - `MIN_ADJUSTED_APR_TO_SHOW` — e.g. 30 (minimum APR % to show).
   - `MAX_RESULTS` — e.g. 20 (max rows in the sheet).

4. **Chains and tokens**:
   - `CHAINS` — e.g. `['solana', 'base']`.
   - `DEXSCREENER_SEARCH_TOKENS` — add the token symbols you want to screen per chain (e.g. SOL, USDC for Solana; WETH, USDC for Base). This drives which pools are fetched.

5. **Email (optional)**:
   - Set `EMAIL_ADDRESS` to your email, or leave it empty and set it later in **File → Project properties → Script properties** (key `EMAIL_ADDRESS`). Leave empty to disable alerts.
   - Set `EMAIL_MIN_FINAL_SCORE` and `EMAIL_MIN_APR` to the minimum score and APR for sending an email.

6. **Sheet name** (if different):
   - If your tab is not named “LP Screener”, set `SHEET_NAME` to your tab name.

Save the script again after editing CONFIG.

## 5. Run the screener once

1. In the Apps Script editor, open the function dropdown at the top and select **updateLPScreener**.
2. Click **Run**.
3. The first time, Google will ask you to authorize the script (view/edit the spreadsheet, send email if alerts are on). Approve the prompts.
4. When it finishes, switch back to your Google Sheet. You should see the **LP Screener** tab (or your `SHEET_NAME` tab) updated with pool data and a “Last Update” timestamp near the top.

If you see “Sheet not found”, make sure the sheet tab name matches `CONFIG.SHEET_NAME`.

## 6. (Optional) Set up automatic refresh

1. In the Apps Script editor, select the function **setupAutoRefresh** in the dropdown.
2. Click **Run** once.
3. This creates a time-based trigger that runs **updateLPScreener** every X minutes (X = `CONFIG.REFRESH_TIME`, e.g. 15).
4. To change the interval, edit `REFRESH_TIME` in CONFIG and run **setupAutoRefresh** again (you may need to remove the old trigger under **Edit → Current project’s triggers**).

## 7. Use the sheet

- **Manual run**: Extensions → Apps Script → select **updateLPScreener** → Run.
- **Manual run (convenience)**: Run **manualRefresh()** for a one-off update without touching triggers.
- **Automatic**: If you ran **setupAutoRefresh()**, the sheet will refresh on its own every `REFRESH_TIME` minutes.

You can sort and filter the sheet as needed. The script overwrites the data range each run; it does not keep history (that would require extra design).

## Troubleshooting

- **“Sheet not found”**: The tab name must match `CONFIG.SHEET_NAME` (default `'LP Screener'`).
- **No or few results**: Loosen CONFIG (lower minimum liquidity/volume/transactions) or add more tokens to `DEXSCREENER_SEARCH_TOKENS` for your chains.
- **Quota / rate limits**: GeckoTerminal has rate limits; the script uses delays. If you hit Google Apps Script quotas, reduce `REFRESH_TIME` or the number of chains/pages.
- **Email not sending**: Ensure `EMAIL_ADDRESS` is set (in CONFIG or Script properties) and that you’ve authorized the script to send email when prompted.

For more detail on CONFIG and behavior, see [README.md](README.md).
