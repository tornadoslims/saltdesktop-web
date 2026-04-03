# runtime/email_digest_gmail.py

**Path:** `runtime/email_digest_gmail.py`
**Purpose:** Gmail connector for the email digest bot. Fetches unread emails since last run, excluding already-processed IDs.

## Functions

### `fetch_emails(config: AppConfig, state: RunState) -> list[Email]`
Uses the `gog` Gmail CLI tool (`gog gmail messages search`) to retrieve individual unread emails. Filters by UNREAD label and optional date constraint from `last_run_at`.

**Config fields used:** `gmail_account`, `filters` (list of extra Gmail search terms), `max_emails` (default 50)

**State fields used:** `last_run_at` (ISO timestamp), `processed_ids` (set of already-processed email IDs)

**Returns:** List of Email dicts: `{id, from, subject, body_text, received_at, labels}`

Skips emails whose ID is already in `processed_ids`.
