# Email Digest Bot

Fetches unread Gmail messages every 15 minutes, summarizes them with an LLM, and posts a digest to Slack.

---

## Prerequisites

### 1. gog (Gmail CLI)

Install and authenticate the `gog` CLI:

```bash
brew install steipete/tap/gogcli
gog auth credentials /path/to/client_secret.json
gog auth add you@gmail.com --services gmail
gog auth list  # verify
```

Set your account as the default to avoid passing `--account` on every call:

```bash
export GOG_ACCOUNT=you@gmail.com
```

Add this to your shell profile (`~/.zshrc` or `~/.bashrc`) to persist it.

### 2. Slack Incoming Webhook

1. Go to [api.slack.com/apps](https://api.slack.com/apps) and create (or open) a Slack app.
2. Enable **Incoming Webhooks** and click **Add New Webhook to Workspace**.
3. Choose a channel and copy the webhook URL (starts with `https://hooks.slack.com/services/...`).
4. Paste it into `data/email_digest_config.json` as `slack_webhook_url`.

### 3. Python dependencies (optional but recommended)

```bash
pip install httpx   # faster Slack delivery; falls back to curl if missing
```

---

## Configuration

All configuration lives in `data/email_digest_config.json`.

| Field | Type | Default | Description |
|---|---|---|---|
| `gmail_account` | string | `""` | Gmail address to fetch from. Leave empty to use `GOG_ACCOUNT` env var. |
| `slack_webhook_url` | string | `""` | Slack incoming webhook URL. **Required to deliver digests.** |
| `filters` | array of strings | `[]` | Extra Gmail search terms appended to the query (e.g. `"-label:promotions"`). |
| `digest_style` | string | `"grouped"` | How emails are grouped in the summary. Currently `"grouped"` (by category). |
| `max_emails` | integer | `50` | Maximum emails to fetch per run. |

### Example config

```json
{
  "gmail_account": "you@gmail.com",
  "slack_webhook_url": "https://hooks.slack.com/services/XXX/YYY/ZZZ",
  "filters": ["-label:promotions", "-label:social"],
  "digest_style": "grouped",
  "max_emails": 50
}
```

---

## State file

Run state is persisted to `data/email_digest_state.json`:

```json
{
  "last_run_at": "2026-03-29T22:00:00+00:00",
  "processed_ids": ["msg-id-1", "msg-id-2"]
}
```

- **`last_run_at`** — timestamp of the last successful run; used to filter emails by date.
- **`processed_ids`** — list of Gmail message IDs already processed; prevents duplicates.

To reset and reprocess all unread mail, set `last_run_at` to `null` and `processed_ids` to `[]`.

---

## Dry-run (test without posting to Slack)

```bash
cd ~/.openclaw/workspace
python -m runtime.email_digest_runner --dry-run
```

This fetches emails, runs the LLM summarizer, and prints the digest to stdout — without POSTing to Slack or updating state.

---

## Manual trigger

To run one full cycle (fetch → summarize → post → save state):

```bash
cd ~/.openclaw/workspace
python -m runtime.email_digest_runner
```

---

## Cron job management

The bot is registered as an OpenClaw cron job (ID: `b89ec7f0-e468-4b62-9517-35c2393e7cca`) that fires every 15 minutes.

### Pause the bot

Ask OpenClaw (or use the cron tool):

```
Disable the email-digest-bot cron job
```

Or via the API: update the job with `enabled: false`.

### Resume the bot

```
Enable the email-digest-bot cron job
```

### Remove the bot permanently

```
Remove cron job b89ec7f0-e468-4b62-9517-35c2393e7cca
```

### Check next scheduled run

```
List cron jobs
```

---

## File layout

```
runtime/
  email_digest_runner.py     # CLI entry point / orchestrator
  email_digest_gmail.py      # Gmail Connector (fetch_emails)
  email_digest_summarizer.py # AI Summarizer (summarize_emails)
  email_digest_slack.py      # Slack Output (post_digest)
  email_digest_state.py      # State Store (load_state / save_state)
  EMAIL_DIGEST_README.md     # This file

data/
  email_digest_config.json   # Configuration (edit this)
  email_digest_state.json    # Run state (managed automatically)
```

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `gog CLI not found` | Install via `brew install steipete/tap/gogcli` |
| `gog gmail messages search failed` | Run `gog auth list` to verify auth; re-run `gog auth add` if expired |
| `slack_webhook_url is not configured` | Add your webhook URL to `data/email_digest_config.json` |
| `Slack delivery failed (HTTP 404)` | Webhook URL is invalid or revoked — regenerate in Slack app settings |
| `LLM returned empty response` | Check `claude` CLI is installed and authenticated |
| Duplicate emails in digest | State file may be corrupted; check `data/email_digest_state.json` |
