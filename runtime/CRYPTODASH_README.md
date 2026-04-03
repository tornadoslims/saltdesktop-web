# CryptoDash

A live crypto price terminal dashboard. Fetches prices from CoinGecko every minute, renders a Rich table with sparklines, and fires alerts when configured thresholds are crossed.

---

## Setup

### 1. Python dependencies

```bash
pip install rich httpx
```

- **rich** — terminal table and color rendering (required for full dashboard; falls back to plain text if missing)
- **httpx** — faster HTTP for CoinGecko API (falls back to `curl` if missing)

### 2. Config file

Edit `data/cryptodash_config.json` with your coins and preferences (see [Config Fields](#config-fields) below).

### 3. Run it

```bash
cd ~/.openclaw/workspace

# Single refresh and exit
python -m runtime.cryptodash_runner --once

# Continuous loop (refreshes every N seconds from config)
python -m runtime.cryptodash_runner

# Override refresh interval
python -m runtime.cryptodash_runner --interval 30
```

---

## CoinGecko Coin IDs

CryptoDash uses [CoinGecko](https://www.coingecko.com) IDs — these are lowercase slugs, not ticker symbols.

| Coin | CoinGecko ID |
|---|---|
| Bitcoin | `bitcoin` |
| Ethereum | `ethereum` |
| Solana | `solana` |
| BNB | `binancecoin` |
| XRP | `ripple` |
| Cardano | `cardano` |
| Avalanche | `avalanche-2` |
| Dogecoin | `dogecoin` |
| Polkadot | `polkadot` |
| Chainlink | `chainlink` |
| Uniswap | `uniswap` |
| Litecoin | `litecoin` |

To find any coin's ID: search at [api.coingecko.com/api/v3/coins/list](https://api.coingecko.com/api/v3/coins/list) or browse [coingecko.com](https://www.coingecko.com) and copy the slug from the URL.

---

## Config Fields

All configuration lives in `data/cryptodash_config.json`.

| Field | Type | Default | Description |
|---|---|---|---|
| `coins` | array of strings | `["bitcoin", "ethereum", "solana"]` | CoinGecko IDs to track. |
| `currency` | string | `"usd"` | Display currency. Any CoinGecko-supported currency (e.g. `eur`, `gbp`, `btc`). |
| `refresh_seconds` | integer | `60` | How often to refresh in continuous loop mode. |
| `show_sparkline` | boolean | `true` | Show a mini price sparkline chart per coin. |
| `alert_thresholds` | object | `{}` | Per-coin alert rules (see [Alert Thresholds](#alert-thresholds)). |
| `max_snapshots_per_coin` | integer | `288` | History entries to retain per coin (288 = 24h at 1-min intervals). |
| `cooldown_minutes` | integer | `30` | Minimum minutes between repeated alerts for the same coin/type. |
| `title` | string | `"CryptoDash"` | Dashboard header title. |

### Example config

```json
{
  "coins": ["bitcoin", "ethereum", "solana"],
  "currency": "usd",
  "refresh_seconds": 60,
  "show_sparkline": true,
  "alert_thresholds": {
    "bitcoin": {
      "price_above": 100000,
      "price_below": 80000,
      "change_24h_pct_above": 10,
      "change_24h_pct_below": -10
    },
    "ethereum": {
      "price_above": 5000,
      "change_24h_pct_below": -15
    }
  },
  "max_snapshots_per_coin": 288,
  "cooldown_minutes": 30,
  "title": "CryptoDash"
}
```

---

## Alert Thresholds

Alerts are defined per coin in `config.alert_thresholds`. Four threshold types are supported:

| Key | Triggers when… |
|---|---|
| `price_above` | Current price **exceeds** this value |
| `price_below` | Current price **falls below** this value |
| `change_24h_pct_above` | 24h % change **exceeds** this value (e.g. `10` = +10%) |
| `change_24h_pct_below` | 24h % change **falls below** this value (e.g. `-10` = −10%) |

Alerts respect a **cooldown** (default 30 minutes) to suppress repeated firing. Alert state is stored in `data/cryptodash_alerts.json`.

To reset all alert cooldowns, delete or clear `data/cryptodash_alerts.json`.

---

## Adding or Removing Coins

1. Open `data/cryptodash_config.json`.
2. Edit the `coins` array — add or remove CoinGecko ID strings.
3. Optionally add alert thresholds for new coins in `alert_thresholds`.
4. Save the file. The next run picks up the change automatically.

**Example — add Dogecoin:**

```json
"coins": ["bitcoin", "ethereum", "solana", "dogecoin"]
```

**Example — remove Solana:**

```json
"coins": ["bitcoin", "ethereum"]
```

No restart needed for cron mode — config is loaded fresh each run.

---

## Running Interactively vs Cron

### Interactive (loop mode)

```bash
python -m runtime.cryptodash_runner
```

Refreshes the terminal table every `refresh_seconds`. Press `Ctrl+C` to stop.

```bash
python -m runtime.cryptodash_runner --interval 30   # refresh every 30s
```

### Single-shot (for cron or agent dispatch)

```bash
python -m runtime.cryptodash_runner --once
python -m runtime.cryptodash_runner --once --json   # print RunResult as JSON
```

---

## Cron Job Management

CryptoDash is registered as an OpenClaw cron job (ID: `d273c223-d618-4548-9e17-abecbc32ac32`) that fires every 60 seconds.

### Pause

```
Disable the cryptodash cron job
```

Or update the job with `enabled: false`.

### Resume

```
Enable the cryptodash cron job
```

### Remove permanently

```
Remove cron job d273c223-d618-4548-9e17-abecbc32ac32
```

### List all cron jobs

```
List cron jobs
```

---

## File Layout

```
runtime/
  cryptodash_runner.py    # CLI entry point / orchestrator
  cryptodash_fetcher.py   # Price Fetcher (CoinGecko API)
  cryptodash_history.py   # History Store (rolling snapshots)
  cryptodash_renderer.py  # Dashboard Renderer (Rich table + sparklines)
  cryptodash_alerts.py    # Alert Evaluator (threshold checks + cooldown)
  CRYPTODASH_README.md    # This file

data/
  cryptodash_config.json  # Configuration (edit this)
  cryptodash_history.json # Rolling price history (managed automatically)
  cryptodash_alerts.json  # Alert cooldown state (managed automatically)
```

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `ModuleNotFoundError: rich` | `pip install rich` |
| `ModuleNotFoundError: httpx` | `pip install httpx` (or ensure `curl` is available) |
| All prices show `0` | Check coin IDs are valid CoinGecko slugs |
| `Config not found` | Create `data/cryptodash_config.json` (see example above) |
| Sparkline shows `—` | Not enough history yet — run a few more cycles |
| Alerts not firing | Check `alert_thresholds` in config; verify cooldown hasn't suppressed them |
| CoinGecko rate limit (429) | Reduce refresh frequency or add a delay; free tier allows ~30 req/min |
