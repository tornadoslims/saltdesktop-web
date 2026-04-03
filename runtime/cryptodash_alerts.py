# runtime/cryptodash_alerts.py
#
# Alert Evaluator for CryptoDash.
# Checks price and 24h% thresholds per coin, respects a cooldown window.

from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from runtime.jb_common import BASE_DIR, utc_now_iso

ALERT_STATE_FILE = BASE_DIR / "data" / "cryptodash_alerts.json"
DEFAULT_COOLDOWN_MINUTES = 30

DashConfig = dict[str, Any]
PriceSnapshot = dict[str, Any]
Alert = dict[str, Any]


# ---------------------------------------------------------------------------
# Alert state persistence
# ---------------------------------------------------------------------------

def _load_alert_state() -> dict[str, str]:
    """Load last-alerted timestamps keyed by '{coin_id}:{alert_type}'."""
    if not ALERT_STATE_FILE.exists():
        return {}
    try:
        with open(ALERT_STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _save_alert_state(state: dict[str, str]) -> None:
    ALERT_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(ALERT_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


# ---------------------------------------------------------------------------
# Cooldown check
# ---------------------------------------------------------------------------

def _is_on_cooldown(
    state: dict[str, str],
    key: str,
    cooldown_minutes: int,
) -> bool:
    """Return True if the alert key fired within the cooldown window."""
    last_str = state.get(key)
    if not last_str:
        return False
    try:
        last_dt = datetime.fromisoformat(last_str)
        if last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - last_dt < timedelta(minutes=cooldown_minutes)
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def evaluate_alerts(
    snapshots: list[PriceSnapshot],
    config: DashConfig,
) -> list[Alert]:
    """Evaluate price snapshots against configured thresholds.

    Supported threshold types per coin (set in config.alert_thresholds):
      - price_above:          float  — alert when price > value
      - price_below:          float  — alert when price < value
      - change_24h_pct_above: float  — alert when 24h change % > value
      - change_24h_pct_below: float  — alert when 24h change % < value (e.g. -5)

    Respects a per-alert cooldown to suppress duplicate alerts.

    Args:
        snapshots: Current PriceSnapshot list from Price Fetcher
        config:    DashConfig with alert_thresholds and optional cooldown_minutes

    Returns:
        List of Alert dicts for triggered thresholds. Empty if none triggered.
    """
    thresholds: dict[str, dict] = config.get("alert_thresholds", {})
    cooldown_minutes: int = int(config.get("cooldown_minutes", DEFAULT_COOLDOWN_MINUTES))

    if not thresholds:
        return []

    alert_state = _load_alert_state()
    now = utc_now_iso()
    alerts: list[Alert] = []

    for snap in snapshots:
        coin_id: str = snap.get("coin_id", "")
        symbol: str = snap.get("symbol", coin_id)
        price: float = float(snap.get("price", 0))
        change_pct: float = float(snap.get("change_24h_pct", 0))

        coin_thresholds = thresholds.get(coin_id, {})
        if not coin_thresholds:
            continue

        checks: list[tuple[str, float, float, str]] = []
        # (alert_type, current_value, threshold_value, direction)

        if "price_above" in coin_thresholds:
            checks.append(("price_above", price, float(coin_thresholds["price_above"]), "above"))
        if "price_below" in coin_thresholds:
            checks.append(("price_below", price, float(coin_thresholds["price_below"]), "below"))
        if "change_24h_pct_above" in coin_thresholds:
            checks.append(("change_24h_pct_above", change_pct, float(coin_thresholds["change_24h_pct_above"]), "above"))
        if "change_24h_pct_below" in coin_thresholds:
            checks.append(("change_24h_pct_below", change_pct, float(coin_thresholds["change_24h_pct_below"]), "below"))

        for alert_type, current_value, threshold_value, direction in checks:
            triggered = (
                (direction == "above" and current_value > threshold_value) or
                (direction == "below" and current_value < threshold_value)
            )
            if not triggered:
                continue

            key = f"{coin_id}:{alert_type}"
            if _is_on_cooldown(alert_state, key, cooldown_minutes):
                continue

            alerts.append({
                "coin_id": coin_id,
                "symbol": symbol,
                "alert_type": alert_type,
                "current_value": current_value,
                "threshold": threshold_value,
                "direction": direction,
                "triggered_at": now,
            })
            alert_state[key] = now

    if alerts:
        _save_alert_state(alert_state)

    return alerts
