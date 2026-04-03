# runtime/cryptodash_runner.py
#
# CLI entry point for CryptoDash.
# Orchestrates: load config → fetch prices → append history →
#               render dashboard → evaluate alerts → print alerts

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from runtime.jb_common import BASE_DIR

CONFIG_FILE = BASE_DIR / "data" / "cryptodash_config.json"


def _load_config() -> dict:
    if not CONFIG_FILE.exists():
        raise FileNotFoundError(
            f"Config not found: {CONFIG_FILE}\n"
            "Create it or run: python -m runtime.cryptodash_runner --init"
        )
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _print_alerts(alerts: list[dict]) -> None:
    if not alerts:
        return
    print("\n⚠️  ALERTS TRIGGERED:")
    for alert in alerts:
        coin = alert.get("coin_id", "?").upper()
        atype = alert.get("alert_type", "?")
        current = alert.get("current_value", 0)
        threshold = alert.get("threshold", 0)
        direction = alert.get("direction", "")
        ts = alert.get("triggered_at", "")

        if "pct" in atype:
            val_str = f"{current:+.2f}%"
            thr_str = f"{threshold:+.2f}%"
        else:
            val_str = f"${current:,.4f}"
            thr_str = f"${threshold:,.4f}"

        print(
            f"  [{coin}] {atype}: {val_str} is {direction} threshold {thr_str}  (at {ts})"
        )
    print()


def run_once(config: dict) -> dict:
    """Execute one full dashboard refresh cycle.

    Returns a RunResult dict summarising what happened.
    """
    result = {
        "coins_fetched": 0,
        "alerts_triggered": 0,
        "error": None,
    }

    try:
        from runtime.cryptodash_fetcher import fetch_prices
        from runtime.cryptodash_history import append_snapshots, load_history
        from runtime.cryptodash_renderer import render_dashboard
        from runtime.cryptodash_alerts import evaluate_alerts

        # 1. Fetch current prices
        snapshots = fetch_prices(config)
        result["coins_fetched"] = len(snapshots)

        if not snapshots:
            print("[cryptodash] No price data returned. Check coin IDs in config.")
            return result

        # 2. Append to history
        max_per_coin = int(config.get("max_snapshots_per_coin", 288))
        append_snapshots(snapshots, max_per_coin=max_per_coin)

        # 3. Load history for sparklines
        history = load_history()

        # 4. Render dashboard
        render_dashboard(snapshots, history, config)

        # 5. Evaluate alerts
        alerts = evaluate_alerts(snapshots, config)
        result["alerts_triggered"] = len(alerts)
        _print_alerts(alerts)

    except Exception as e:
        result["error"] = str(e)
        print(f"[cryptodash] ERROR: {e}", file=sys.stderr)

    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="CryptoDash — live crypto price terminal dashboard."
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Fetch and render once, then exit (default: loop).",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=None,
        help="Override refresh interval in seconds (default: from config).",
    )
    parser.add_argument(
        "--json",
        dest="output_json",
        action="store_true",
        help="Print RunResult as JSON after each cycle (useful for cron/agent runs).",
    )
    args = parser.parse_args()

    try:
        config = _load_config()
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)

    refresh_seconds: int = args.interval or int(config.get("refresh_seconds", 60))

    if args.once:
        result = run_once(config)
        if args.output_json:
            print(json.dumps(result, indent=2))
        if result.get("error"):
            sys.exit(1)
        return

    # Continuous loop mode
    print(f"[cryptodash] Starting — refreshing every {refresh_seconds}s. Ctrl+C to stop.")
    try:
        while True:
            result = run_once(config)
            if args.output_json:
                print(json.dumps(result, indent=2))
            time.sleep(refresh_seconds)
    except KeyboardInterrupt:
        print("\n[cryptodash] Stopped.")


if __name__ == "__main__":
    main()
