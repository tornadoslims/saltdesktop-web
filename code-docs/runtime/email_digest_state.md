# runtime/email_digest_state.py

**Path:** `runtime/email_digest_state.py`
**Purpose:** State persistence for the email digest bot. Tracks `last_run_at` and `processed_ids` across runs using the JsonStore.

## Functions

### `load_state() -> RunState`
Loads run state from `data/email_digest_state.json`. Returns `{last_run_at: str | None, processed_ids: list[str]}`. Defaults to empty state if file is missing.

### `save_state(state: RunState) -> None`
Persists state as a single-record JSON list. Normalizes fields before saving.
