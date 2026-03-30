# Security

**No secrets in this repo.** Do not commit API keys, tokens, passwords, or personal email addresses.

- **Email / alerts**: Configure your email in Google Apps Script (e.g. set `CONFIG.EMAIL_ADDRESS` in the script or via Project properties / Script properties). See README for setup.
- **API keys**: DexScreener and GeckoTerminal are used via public endpoints; no API keys are required. If you add other services, configure keys in Apps Script or environment, not in code.
- **Script properties**: Use `PropertiesService.getScriptProperties()` in Apps Script for sensitive values; they are stored in the script project, not in this repository.

When contributing or cloning, ensure you never commit `.env` files, `secrets/` contents, or hardcoded credentials.

## Python bot (`python/`)

The optional Python companion uses environment variables and may reference a **Google service account JSON key file** on your machine.

- **Never commit** `python/.env`, `.env.*`, RPC URLs with real API keys baked in, or any `*.json` key export from Google Cloud.
- Copy `python/.env.example` to `python/.env` locally and set `GOOGLE_SERVICE_ACCOUNT_JSON` to an **absolute or relative path outside this repository** (for example a path under your user profile or a secrets manager).
- Use dedicated RPC providers (Alchemy, Infura, QuickNode, Helius, etc.) with keys you rotate if exposed.
- GitHub can scan pushes for known secret patterns; see [Secret scanning](https://docs.github.com/code-security/secret-scanning/about-secret-scanning).
