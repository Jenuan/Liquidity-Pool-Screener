# lp-bot-python

This directory is **`python/`** in the [Liquidity_pool_screener](https://github.com/Jenuan/Liquidity_pool_screener) repo. The bot expects **`.env` beside this README** (i.e. `python/.env`). Copy from `.env.example`; do not commit secrets.

## Status

This code is **experimental**: live PnL, IL, and fee figures may be **approximate or incomplete** depending on chain, pool type, and what is read from the sheet vs on-chain. It is meant for **developers** already using the LP Screener sheet. Do not treat the dashboard as audited financial or execution software.

## Variáveis de ambiente (`.env`)

| Variável | Uso |
|----------|-----|
| `ETHEREUM_RPC_URL` | RPC HTTP Ethereum (Uniswap V2 / métricas EVM) |
| `BSC_RPC_URL` | RPC HTTP BSC (PancakeSwap V2) |
| `BASE_RPC_URL` | RPC HTTP Base (apenas se usar entradas `*_v3_base` em `dex_endpoints.yaml`; leitor live V3 ainda não implementado) |
| `SOLANA_RPC_URL` | **Obrigatório** para live metrics de `pancakeswap_v3_solana` (JSON-RPC Solana; ver `config/dex_endpoints.yaml`) |

### Mapeamento DEX → `rpc_url_env` (`config/dex_endpoints.yaml`)

| Chave em `dexes:` | `rpc_url_env` |
|-------------------|---------------|
| `uniswap_v2` | `ETHEREUM_RPC_URL` |
| `pancakeswap_v2` | `BSC_RPC_URL` |
| `uniswap_v3_base`, `pancakeswap_v3_base` | `BASE_RPC_URL` |
| `pancakeswap_v3_solana` | `SOLANA_RPC_URL` |

Substitua os placeholders em `.env` pelos endpoints HTTPS do vosso fornecedor (Alchemy, Infura, QuickNode, etc.); veja também `.env.example`.

**Dashboard Streamlit:** após alterar RPCs no `.env`, reinicie o Streamlit (`streamlit run scripts/dashboard.py`).

**Métricas live de facto:** valores como `https://SEU_RPC_ETHEREUM` são *placeholders* — o código não consegue falar com a chain até substituíres por URLs JSON-RPC **reais** (domínio com ponto, tipicamente com API key no path ou query). Exemplos de fornecedores: Alchemy, Infura, QuickNode, Ankr, Helius ou outro RPC Solana. Para **Ethereum e BSC** costuma ser obrigatório ter conta num destes serviços. Para **Solana**, podes testar com o endpoint público (limitado): `https://api.mainnet-beta.solana.com` — em produção prefere um RPC com quota dedicada.

Credenciais Google Sheets / outras variáveis do projeto continuam como já configuradas.

### Solana (métricas ao vivo)

- **`pancakeswap_v3_solana`:** sem `SOLANA_RPC_URL` no `.env`, as linhas Solana aparecem como live não suportado (`env_not_set:SOLANA_RPC_URL`); o dashboard avisa na sidebar. Defina o RPC na raiz do projeto (mesmo ficheiro `.env` que as variáveis EVM).
- O endereço da pool na planilha deve ser **base58** (32 bytes), não `0x…`.
- A conta da pool deve ser **CLMM compatível com o layout `PoolState` do Raydium**; o **owner** do programa deve estar em `clmm_program_ids` no YAML (por padrão inclui o programa Raydium CLMM).
- **Preços em USD** vêm da API pública **DexScreener** (melhor par `chainId: solana` por liquidez): são **estimativas agregadas**, não cotação on-chain.
- **IL (USD)**: no dashboard, `il_usd` é exibido como proxy de mark-to-market (valor atual - capital inicial). Não é necessariamente o IL matemático vs hodl.

### Saídas agregadas (`get_positions_live`)

- **Variação de preço (% m5/h1/h6/h24)**: API **DexScreener** por par (`/latest/dex/pairs/{chain}/{pairAddress}`). Não é o mesmo motor do site oficial do DEX; pode faltar par ou haver divergência.
- **APR (`apr_fees_24h`)**: quando a pool não devolve APR on-chain (0), o valor vem do **APR da linha do screener na abertura** (`entry_apr_fees_24h`), se existir. Campo opcional `apr_fees_24h_fill` = `entry_screener`.
- **Fees (`fees_accrued_usd`) na tabela ao vivo**: coluna **`—`** — fees LP não são estimadas por poll (evita valores que mudavam a cada refresh). Fees reais via eventos (`OPEN`/`CLOSE` / `delta_fees_usd`) quando esse fluxo existir. `fees_model` = `not_tracked_live`.
- **EVM live**: só pools estilo **Uniswap V2** (`getReserves`). Endereços V3 noutra chain ou contratos incompatíveis devolvem motivos como `pool_not_v2_pair` ou `dex_missing_chain_or_rpc`. Rótulos explícitos Base V3 (`uniswap-v3-base`, `pancakeswap-v3-base` → YAML com `live_metrics_mode: none`) não abrem posição até existir leitor; caso contrário use DEX/pool V2 na rede configurada.
- **Range (simulação)**:
  - EVM V2: `range_type` = `amm_v2_curve` (curva x·y=k; sem ticks).
  - Solana CLMM: opcional via planilha — `FullRange` / `TickLower` / `TickUpper` (ver abertura no `executor`). Com ticks + métricas on-chain, `tick_current` e `position_tick_in_range` indicam se o preço está dentro do range.
- **Limitações**: ticks “reais” de uma NFT on-chain não são lidos; só o que for guardado na abertura ou inferido acima.

### Colunas opcionais na planilha (abertura de posição)

| Coluna | Uso |
|--------|-----|
| `TickLower` / `tick_lower` | Tick inferior (CLMM), opcional |
| `TickUpper` / `tick_upper` | Tick superior (CLMM), opcional |
| `FullRange` / `full_range` / `RangeFull` | `yes`/`true`/`full` = range completo; `no`/`narrow` = range curto (usa ticks se existirem) |

O APR de entrada continua a ser lido dos campos já suportados (`AdjAPR`, `optimizedAPR`, `baseAPR`, etc.) como em `risk_strategy._extract_apr`.
