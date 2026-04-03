# runtime/cryptodash_history.py
#
# History Store for CryptoDash.
# Appends and retrieves rolling price snapshots per coin.

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from runtime.jb_common import BASE_DIR

HISTORY_FILE = BASE_DIR / "data" / "cryptodash_history.json"
DEFAULT_MAX_SNAPSHOTS = 288  # 24h at 5-min intervals

PriceSnapshot = dict[str, Any]


def load_history() -> dict[str, list[PriceSnapshot]]:
    """Load the full price history from disk.

    Returns:
        dict mapping coin_id -> List[PriceSnapshot], oldest first.
    """
    if not HISTORY_FILE.exists():
        return {}
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {}
        return data
    except (json.JSONDecodeError, OSError):
        return {}


def _save_history(history: dict[str, list[PriceSnapshot]]) -> None:
    """Persist history dict to disk."""
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2)


def append_snapshots(
    snapshots: list[PriceSnapshot],
    max_per_coin: int = DEFAULT_MAX_SNAPSHOTS,
) -> None:
    """Append a batch of PriceSnapshots to the history, pruning old entries.

    Each snapshot is appended to its coin's rolling window. Entries beyond
    max_per_coin are dropped from the front (oldest first).

    Args:
        snapshots:    List of PriceSnapshot dicts (must have coin_id field)
        max_per_coin: Maximum snapshots to retain per coin (default 288)
    """
    history = load_history()

    for snapshot in snapshots:
        coin_id = snapshot.get("coin_id")
        if not coin_id:
            continue

        entries = history.get(coin_id, [])
        entries.append(snapshot)

        # Prune to rolling window
        if len(entries) > max_per_coin:
            entries = entries[-max_per_coin:]

        history[coin_id] = entries

    _save_history(history)


def get_coin_history(coin_id: str) -> list[PriceSnapshot]:
    """Return the stored price history for a single coin.

    Args:
        coin_id: CoinGecko coin ID (e.g. "bitcoin")

    Returns:
        List of PriceSnapshot dicts, oldest first. Empty list if not found.
    """
    history = load_history()
    return history.get(coin_id, [])
