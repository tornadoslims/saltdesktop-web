# runtime/cryptodash_fetcher.py

**Path:** `runtime/cryptodash_fetcher.py`
**Purpose:** Price fetcher for CryptoDash. Fetches current prices and market data from the CoinGecko public API.

## Functions

### `fetch_prices(config: DashConfig) -> list[PriceSnapshot]`
Calls CoinGecko `/simple/price` with market data fields (24h change, market cap, volume). Uses `subprocess` to call `curl` rather than a Python HTTP library.

**Parameters (from config):**
- `coins`: list of CoinGecko IDs (e.g., ["bitcoin", "ethereum"])
- `currency`: fiat currency (default "usd")
- `timeout_seconds`: request timeout (default 10)
- `api_base_url`: CoinGecko base URL (overridable for testing)

**Returns:** List of PriceSnapshot dicts with: `coin_id, symbol, name, price, change_24h_pct, market_cap, volume_24h, fetched_at`
