# runtime/cryptodash_alerts.py

**Path:** `runtime/cryptodash_alerts.py`
**Purpose:** Alert evaluator for CryptoDash. Checks price and 24h% thresholds per coin, respects a cooldown window to suppress duplicate alerts.

## Constants

- `ALERT_STATE_FILE`: `BASE_DIR / "data" / "cryptodash_alerts.json"` -- persists last-alerted timestamps
- `DEFAULT_COOLDOWN_MINUTES`: 30

## Functions

### `evaluate_alerts(snapshots, config) -> list[Alert]`
Evaluates price snapshots against configured thresholds. Supported threshold types per coin:
- `price_above`: alert when price > value
- `price_below`: alert when price < value
- `change_24h_pct_above`: alert when 24h change % > value
- `change_24h_pct_below`: alert when 24h change % < value

Respects a per-alert cooldown (keyed by `{coin_id}:{alert_type}`). State is persisted to JSON.

Returns list of Alert dicts: `{coin_id, symbol, alert_type, current_value, threshold, direction, triggered_at}`

### Internal helpers:
- `_load_alert_state()` / `_save_alert_state(state)`: JSON persistence for cooldown tracking
- `_is_on_cooldown(state, key, cooldown_minutes)`: Checks if an alert has fired within the cooldown window
