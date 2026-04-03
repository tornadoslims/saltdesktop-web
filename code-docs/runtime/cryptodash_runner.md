# runtime/cryptodash_runner.py

**Path:** `runtime/cryptodash_runner.py`
**Purpose:** CLI entry point for CryptoDash. Orchestrates the full pipeline: load config, fetch prices, append history, render dashboard, evaluate alerts.

## Functions

### `run_once(config) -> dict`
Executes one full dashboard refresh cycle:
1. `fetch_prices(config)` -- get current prices from CoinGecko
2. `append_snapshots(snapshots)` -- add to rolling history
3. `load_history()` -- load full history for sparklines
4. `render_dashboard(snapshots, history, config)` -- print Rich table
5. `evaluate_alerts(snapshots, config)` -- check thresholds

Returns: `{coins_fetched, alerts_triggered, error}`

### `main()`
CLI with `--once` (single pass) or continuous loop (default). `--interval` overrides refresh seconds. `--json` prints RunResult as JSON after each cycle.

## CLI

```bash
python -m runtime.cryptodash_runner --once           # Single fetch + render
python -m runtime.cryptodash_runner --interval 30    # Loop every 30s
python -m runtime.cryptodash_runner --once --json    # JSON output for cron
```
