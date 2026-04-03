# runtime/email_digest_runner.py

**Path:** `runtime/email_digest_runner.py`
**Purpose:** Runner / CLI entry point for the email digest bot. Orchestrates the full pipeline.

## Functions

### `run(dry_run=False) -> dict`
Executes one full digest pipeline run:
1. Load config from `data/email_digest_config.json`
2. Load state (last_run_at, processed_ids)
3. Fetch emails via `email_digest_gmail.fetch_emails()`
4. Summarize via `email_digest_summarizer.summarize_emails()`
5. Post to Slack via `email_digest_slack.post_digest()` (unless dry_run)
6. Save updated state with new processed_ids

Returns: `{run_id, emails_processed, delivered, error}`

### `main()`
CLI with `--dry-run` flag.

## CLI

```bash
python -m runtime.email_digest_runner              # Full run
python -m runtime.email_digest_runner --dry-run    # Fetch + summarize only
```
