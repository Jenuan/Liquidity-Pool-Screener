# Security

**No secrets in this repo.** Do not commit API keys, tokens, passwords, or personal email addresses.

- **Email / alerts**: Configure your email in Google Apps Script (e.g. set `CONFIG.EMAIL_ADDRESS` in the script or via Project properties / Script properties). See README for setup.
- **API keys**: DexScreener and GeckoTerminal are used via public endpoints; no API keys are required. If you add other services, configure keys in Apps Script or environment, not in code.
- **Script properties**: Use `PropertiesService.getScriptProperties()` in Apps Script for sensitive values; they are stored in the script project, not in this repository.

When contributing or cloning, ensure you never commit `.env` files, `secrets/` contents, or hardcoded credentials.
