# runtime/email_digest_gmail.py
#
# Gmail Connector for the email digest bot.
# Fetches unread emails since last_run_at, excluding already-processed IDs.

from __future__ import annotations

import json
import subprocess
from typing import Any

AppConfig = dict[str, Any]
RunState = dict[str, Any]
Email = dict[str, Any]


def fetch_emails(config: AppConfig, state: RunState) -> list[Email]:
    """Fetch unread emails from Gmail since last_run_at, excluding processed_ids.

    Uses the gog Gmail CLI (`gog gmail messages search`) to retrieve individual
    emails (not threads). Filters by UNREAD label and, if available, a date
    constraint derived from last_run_at.

    Args:
        config: AppConfig with fields gmail_account, filters, max_emails
        state:  RunState with last_run_at (ISO str | None) and processed_ids

    Returns:
        List of Email dicts with keys: id, from, subject, body_text,
        received_at, labels
    """
    account: str = config.get("gmail_account", "")
    max_results: int = int(config.get("max_emails", 50))
    extra_filters: list[str] = config.get("filters", [])
    last_run_at: str | None = state.get("last_run_at")
    processed_ids: set[str] = set(state.get("processed_ids", []))

    # Build Gmail search query
    query_parts = ["label:UNREAD"]
    if last_run_at:
        # Convert ISO timestamp to YYYY/MM/DD for Gmail query
        date_part = last_run_at[:10].replace("-", "/")
        query_parts.append(f"after:{date_part}")
    for f in extra_filters:
        query_parts.append(f)
    query = " ".join(query_parts)

    # Build gog command
    cmd = [
        "gog", "gmail", "messages", "search",
        query,
        "--max", str(max_results),
        "--json",
        "--no-input",
    ]
    if account:
        cmd += ["--account", account]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("gog gmail messages search timed out after 30s")
    except FileNotFoundError:
        raise RuntimeError(
            "gog CLI not found. Install via: brew install steipete/tap/gogcli"
        )

    if result.returncode != 0:
        raise RuntimeError(
            f"gog gmail messages search failed (exit {result.returncode}): "
            f"{result.stderr.strip()}"
        )

    raw = result.stdout.strip()
    if not raw:
        return []

    try:
        messages = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Failed to parse gog output as JSON: {e}\nOutput: {raw[:500]}")

    if not isinstance(messages, list):
        messages = [messages]

    emails: list[Email] = []
    for msg in messages:
        msg_id = msg.get("id") or msg.get("messageId") or ""
        if not msg_id or msg_id in processed_ids:
            continue

        email: Email = {
            "id": msg_id,
            "from": msg.get("from") or msg.get("sender") or "",
            "subject": msg.get("subject") or "(no subject)",
            "body_text": msg.get("body") or msg.get("snippet") or "",
            "received_at": msg.get("date") or msg.get("internalDate") or "",
            "labels": msg.get("labelIds") or msg.get("labels") or [],
        }
        emails.append(email)

    return emails
