# runtime/email_digest_state.py
#
# State persistence for the email digest bot.
# Tracks last_run_at and processed_ids across runs.

from __future__ import annotations

from pathlib import Path
from typing import Any

from runtime.jb_common import BASE_DIR, JsonStore

STATE_FILE = BASE_DIR / "data" / "email_digest_state.json"
_store = JsonStore(STATE_FILE)

RunState = dict[str, Any]


def load_state() -> RunState:
    """Load and return the current run state.

    Returns a dict with:
      - last_run_at: str | None  — ISO timestamp of the last successful run
      - processed_ids: list[str] — email IDs already processed
    """
    records = _store.load()

    # State file is a single-record list; initialize defaults if empty
    if not records:
        return {"last_run_at": None, "processed_ids": []}

    state = records[0]
    return {
        "last_run_at": state.get("last_run_at"),
        "processed_ids": state.get("processed_ids", []),
    }


def save_state(state: RunState) -> None:
    """Persist the given run state.

    Args:
        state: dict with last_run_at (str | None) and processed_ids (list[str])
    """
    normalized = {
        "last_run_at": state.get("last_run_at"),
        "processed_ids": list(state.get("processed_ids", [])),
    }
    _store.save([normalized])
