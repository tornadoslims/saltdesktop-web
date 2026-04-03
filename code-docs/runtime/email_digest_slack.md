# runtime/email_digest_slack.py

**Path:** `runtime/email_digest_slack.py`
**Purpose:** Slack output for the email digest bot. Formats a DigestSummary as Slack Block Kit and POSTs to an incoming webhook.

## Constants

- `CATEGORY_LABELS`: Maps category names to display labels with emoji

## Functions

### `post_digest(summary, config) -> DeliveryReceipt`
Formats summary as Slack blocks (header, dividers, category sections, individual items, footer) and POSTs to the webhook URL. Tries `httpx` first, falls back to `curl`.

**Config fields:** `slack_webhook_url` (required), `username` (default "Email Digest Bot"), `icon_emoji` (default ":email:")

**Returns:** `{status: "ok"|"error", delivered_at, http_status}`

### `_format_digest(summary, username, icon_emoji) -> dict`
Builds the Slack webhook payload with Block Kit blocks: header with email count, dividers, category sections with bold subjects and italic senders, context footer with timestamp.

### `_post_with_httpx(url, payload_json) -> int | None`
Attempts POST via httpx library. Returns HTTP status or None if httpx is not installed.

### `_post_with_curl(url, payload_json) -> int`
Fallback POST via curl subprocess.
