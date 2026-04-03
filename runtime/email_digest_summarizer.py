# runtime/email_digest_summarizer.py
#
# Email Summarizer for the email digest bot.
# Categorizes and summarizes emails using an LLM via the Claude CLI.

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from typing import Any

AppConfig = dict[str, Any]
Email = dict[str, Any]
DigestCategory = dict[str, Any]
DigestSummary = dict[str, Any]

CATEGORIES = ["action_items", "newsletters", "fyi"]

SYSTEM_PROMPT = """You are an email digest assistant. Your job is to categorize and summarize a list of emails into three groups:

1. action_items — emails that require a response or action from the user
2. newsletters — bulk mail, marketing, subscriptions, digests
3. fyi — informational emails that need no action (receipts, confirmations, notifications)

Respond with ONLY a valid JSON object in this exact format (no markdown, no explanation):
{
  "action_items": [
    {"from": "sender", "subject": "subject line", "summary": "one sentence summary"}
  ],
  "newsletters": [
    {"from": "sender", "subject": "subject line", "summary": "one sentence summary"}
  ],
  "fyi": [
    {"from": "sender", "subject": "subject line", "summary": "one sentence summary"}
  ]
}"""


def _build_prompt(emails: list[Email], digest_style: str) -> str:
    lines = [f"Categorize and summarize these {len(emails)} emails:\n"]
    for i, email in enumerate(emails, 1):
        lines.append(f"{i}. From: {email.get('from', 'unknown')}")
        lines.append(f"   Subject: {email.get('subject', '(no subject)')}")
        body = email.get("body_text", "").strip()
        if body:
            # Truncate long bodies to keep prompt manageable
            snippet = body[:300] + ("..." if len(body) > 300 else "")
            lines.append(f"   Body: {snippet}")
        lines.append("")
    return "\n".join(lines)


def summarize_emails(emails: list[Email], config: AppConfig) -> DigestSummary:
    """Categorize and summarize emails into a structured DigestSummary.

    Calls the Claude CLI (`claude`) with a structured prompt to produce
    JSON-formatted categories: action_items, newsletters, and fyi.

    Args:
        emails: List of Email dicts from the Gmail Connector
        config: AppConfig with model, max_tokens, digest_style fields

    Returns:
        DigestSummary dict with keys:
          - categories: List[DigestCategory] — each with name, items list
          - total_emails: int
          - generated_at: str (ISO timestamp)
    """
    if not emails:
        return {
            "categories": [
                {"name": cat, "items": []} for cat in CATEGORIES
            ],
            "total_emails": 0,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    digest_style: str = config.get("digest_style", "grouped")
    model: str = config.get("model", "claude-sonnet-4-5")
    max_tokens: int = int(config.get("max_tokens", 1024))

    user_prompt = _build_prompt(emails, digest_style)
    full_prompt = f"{SYSTEM_PROMPT}\n\n{user_prompt}"

    cmd = [
        "claude",
        "--print",
        "--permission-mode", "bypassPermissions",
        "--model", model,
        "--max-tokens", str(max_tokens),
        full_prompt,
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("LLM call timed out after 120s")
    except FileNotFoundError:
        raise RuntimeError(
            "claude CLI not found. Ensure Claude Code is installed."
        )

    if result.returncode != 0:
        raise RuntimeError(
            f"claude CLI failed (exit {result.returncode}): "
            f"{result.stderr.strip()}"
        )

    raw = result.stdout.strip()
    if not raw:
        raise RuntimeError("LLM returned empty response")

    # Strip markdown code fences if present
    if raw.startswith("```"):
        lines = raw.splitlines()
        raw = "\n".join(
            line for line in lines
            if not line.startswith("```")
        ).strip()

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"Failed to parse LLM response as JSON: {e}\nResponse: {raw[:500]}"
        )

    categories: list[DigestCategory] = []
    for cat in CATEGORIES:
        items = parsed.get(cat, [])
        if not isinstance(items, list):
            items = []
        categories.append({"name": cat, "items": items})

    return {
        "categories": categories,
        "total_emails": len(emails),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
