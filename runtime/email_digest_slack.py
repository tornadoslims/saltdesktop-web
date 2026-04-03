# runtime/email_digest_slack.py
#
# Slack Output for the email digest bot.
# Formats a DigestSummary as Slack markdown and POSTs to an incoming webhook.

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from typing import Any

AppConfig = dict[str, Any]
DigestSummary = dict[str, Any]
DeliveryReceipt = dict[str, Any]

CATEGORY_LABELS = {
    "action_items": "🔴 Action Items",
    "newsletters": "📰 Newsletters",
    "fyi": "ℹ️ FYI",
}


def _format_digest(summary: DigestSummary, username: str, icon_emoji: str) -> dict[str, Any]:
    """Build a Slack webhook payload from a DigestSummary."""
    total = summary.get("total_emails", 0)
    generated_at = summary.get("generated_at", "")
    categories = summary.get("categories", [])

    # Header
    blocks: list[dict] = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"{icon_emoji} Email Digest — {total} new email{'s' if total != 1 else ''}",
                "emoji": True,
            },
        },
        {"type": "divider"},
    ]

    has_content = False
    for category in categories:
        name = category.get("name", "")
        items = category.get("items", [])
        if not items:
            continue

        has_content = True
        label = CATEGORY_LABELS.get(name, name.replace("_", " ").title())

        # Section header
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*{label}* ({len(items)})",
            },
        })

        # Individual items
        for item in items:
            sender = item.get("from", "unknown")
            subject = item.get("subject", "(no subject)")
            summary_text = item.get("summary", "")
            text = f"• *{subject}* — _{sender}_"
            if summary_text:
                text += f"\n  {summary_text}"
            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": text},
            })

        blocks.append({"type": "divider"})

    if not has_content:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": "_No new emails to report._"},
        })

    # Footer
    if generated_at:
        try:
            dt = datetime.fromisoformat(generated_at)
            time_str = dt.strftime("%b %d, %Y at %H:%M UTC")
        except ValueError:
            time_str = generated_at
        blocks.append({
            "type": "context",
            "elements": [
                {"type": "mrkdwn", "text": f"Generated {time_str}"}
            ],
        })

    return {
        "username": username,
        "icon_emoji": icon_emoji,
        "blocks": blocks,
    }


def post_digest(summary: DigestSummary, config: AppConfig) -> DeliveryReceipt:
    """Format a DigestSummary and POST it to the configured Slack webhook URL.

    Uses httpx (via python -m httpx is not standard; uses subprocess curl as
    fallback) or the httpx Python library if available.

    Args:
        summary: DigestSummary dict from Email Summarizer
        config:  AppConfig with slack_webhook_url, and optional username/icon_emoji

    Returns:
        DeliveryReceipt dict with status, delivered_at, and http_status
    """
    webhook_url: str = config.get("slack_webhook_url", "")
    if not webhook_url:
        raise ValueError(
            "slack_webhook_url is not configured. "
            "Set it in data/email_digest_config.json."
        )

    username: str = config.get("username", "Email Digest Bot")
    icon_emoji: str = config.get("icon_emoji", ":email:")

    payload = _format_digest(summary, username, icon_emoji)
    payload_json = json.dumps(payload)

    delivered_at = datetime.now(timezone.utc).isoformat()

    # Try httpx first, fall back to curl
    http_status = _post_with_httpx(webhook_url, payload_json)
    if http_status is None:
        http_status = _post_with_curl(webhook_url, payload_json)

    status = "ok" if http_status == 200 else "error"

    return {
        "status": status,
        "delivered_at": delivered_at,
        "http_status": http_status,
    }


def _post_with_httpx(url: str, payload_json: str) -> int | None:
    """Attempt to POST using the httpx library. Returns HTTP status or None."""
    try:
        import httpx  # type: ignore
        response = httpx.post(
            url,
            content=payload_json,
            headers={"Content-Type": "application/json"},
            timeout=15,
        )
        return response.status_code
    except ImportError:
        return None
    except Exception as e:
        raise RuntimeError(f"httpx POST failed: {e}")


def _post_with_curl(url: str, payload_json: str) -> int:
    """POST using curl subprocess. Returns HTTP status code."""
    cmd = [
        "curl",
        "-s",
        "-o", "/dev/null",
        "-w", "%{http_code}",
        "-X", "POST",
        "-H", "Content-Type: application/json",
        "-d", payload_json,
        url,
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("curl POST to Slack timed out after 15s")
    except FileNotFoundError:
        raise RuntimeError(
            "Neither httpx nor curl is available. "
            "Install httpx: pip install httpx"
        )

    if result.returncode != 0:
        raise RuntimeError(
            f"curl failed (exit {result.returncode}): {result.stderr.strip()}"
        )

    try:
        return int(result.stdout.strip())
    except ValueError:
        raise RuntimeError(f"Unexpected curl output: {result.stdout.strip()!r}")
