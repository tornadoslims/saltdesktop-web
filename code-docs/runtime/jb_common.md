# runtime/jb_common.py

**Path:** `runtime/jb_common.py`
**Purpose:** Shared utilities for all JBCP runtime modules. Single source of truth for paths, timestamps, and JSON file storage.

## Imports

| Import | Used For |
|--------|----------|
| `json` | JSON serialization/deserialization in `JsonStore` |
| `datetime`, `timezone` | UTC timestamp generation and parsing |
| `Path` (pathlib) | File path handling |
| `Any` (typing) | Type annotations |

## Constants

| Constant | Value | Meaning |
|----------|-------|---------|
| `BASE_DIR` | `Path(__file__).resolve().parent.parent` | Project root directory (two levels up from this file) |
| `DATA_DIR` | `BASE_DIR / "data"` | Directory for all persistent data (JSON files, SQLite DB) |
| `LOG_DIR` | `BASE_DIR / "logs"` | Directory for log files and JSONL event streams |

## Functions

### `utc_now_iso() -> str`
Returns the current UTC time as an ISO 8601 string. Used everywhere as the standard timestamp format.

### `utc_now() -> datetime`
Returns the current UTC time as a `datetime` object. Used for time arithmetic.

### `parse_iso(ts: str | None) -> datetime | None`
Parses an ISO timestamp string into a `datetime` object. Returns `None` on failure or if input is `None`. Used by age calculations and relative time formatting.

### `age_seconds(ts: str | None) -> float`
Returns the age in seconds of an ISO timestamp relative to now. Returns `float("inf")` if the timestamp is missing or unparseable. Used by watchdog and staleness checks.

## Classes

### `JsonStore`
Simple JSON list file store. Handles ensure/load/save for any module.

**Constructor:** `__init__(self, file_path: Path, parent_dir: Path | None = None)`
- `file_path`: Path to the JSON file
- `parent_dir`: Optional parent directory (defaults to file's parent)

**Methods:**

- **`ensure() -> None`**: Creates parent directories and initializes the file with `[]` if it does not exist.
- **`load() -> list[dict[str, Any]]`**: Reads and returns the JSON list from disk. Calls `ensure()` first. Raises `ValueError` if the file does not contain a JSON list.
- **`save(data: list[dict[str, Any]]) -> None`**: Writes the JSON list to disk with 2-space indent. Calls `ensure()` first.

This class is used as a legacy persistence layer. The primary data store is now SQLite (`jb_database.py`), but `JsonStore` instances still exist in several modules for backward compatibility.
