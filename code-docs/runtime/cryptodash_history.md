# runtime/cryptodash_history.py

**Path:** `runtime/cryptodash_history.py`
**Purpose:** History store for CryptoDash. Appends and retrieves rolling price snapshots per coin.

## Constants

- `HISTORY_FILE`: `BASE_DIR / "data" / "cryptodash_history.json"`
- `DEFAULT_MAX_SNAPSHOTS`: 288 (24h at 5-minute intervals)

## Functions

### `load_history() -> dict[str, list[PriceSnapshot]]`
Loads full price history from disk. Returns dict mapping coin_id to list of snapshots (oldest first).

### `append_snapshots(snapshots, max_per_coin=288) -> None`
Appends a batch of PriceSnapshots to history. Prunes old entries beyond `max_per_coin` (drops from front/oldest).

### `get_coin_history(coin_id) -> list[PriceSnapshot]`
Returns stored price history for a single coin (oldest first). Empty list if not found.
