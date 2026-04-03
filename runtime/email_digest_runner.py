# runtime/email_digest_runner.py
#
# Runner / CLI entry point for the email digest bot.
# Orchestrates: load config → load state → fetch emails → summarize →
#               post to Slack → save state → print RunResult

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from uuid import uuid4

from runtime.jb_common import BASE_DIR, utc_now_iso

CONFIG_FILE = BASE_DIR / "data" / "email_digest_config.json"


def _load_config() -> dict:
    if not CONFIG_FILE.exists():
        raise FileNotFoundError(
            f"Config file not found: {CONFIG_FILE}\n"
            "Create it with the required fields (see EMAIL_DIGEST_README.md)."
        )
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def run(dry_run: bool = False) -> dict:
    """Execute one full digest pipeline run.

    Args:
        dry_run: If True, fetch and summarize but do not POST to Slack.

    Returns:
        RunResult dict with run_id, emails_processed, delivered, error.
    """
    run_id = str(uuid4())
    result: dict = {
        "run_id": run_id,
        "emails_processed": 0,
        "delivered": False,
        "error": None,
    }

    try:
        # --- Load config ---
        config = _load_config()

        # --- Load state ---
        from runtime.email_digest_state import load_state, save_state
        state = load_state()

        # --- Fetch emails ---
        from runtime.email_digest_gmail import fetch_emails
        emails = fetch_emails(config, state)

        if not emails:
            print(f"[{run_id}] No new emails. Skipping pipeline.")
            return result

        result["emails_processed"] = len(emails)
        print(f"[{run_id}] Fetched {len(emails)} new email(s).")

        # --- Summarize ---
        from runtime.email_digest_summarizer import summarize_emails
        summary = summarize_emails(emails, config)
        print(f"[{run_id}] Summary generated at {summary.get('generated_at')}.")

        # --- Post to Slack ---
        if dry_run:
            print(f"[{run_id}] DRY RUN — skipping Slack delivery.")
            print(json.dumps(summary, indent=2))
        else:
            from runtime.email_digest_slack import post_digest
            receipt = post_digest(summary, config)
            http_status = receipt.get("http_status")
            if receipt.get("status") != "ok":
                raise RuntimeError(
                    f"Slack delivery failed (HTTP {http_status}). "
                    "Check your slack_webhook_url in config."
                )
            result["delivered"] = True
            print(
                f"[{run_id}] Delivered to Slack "
                f"(HTTP {http_status}) at {receipt.get('delivered_at')}."
            )

        # --- Save state ---
        new_ids = list(
            set(state.get("processed_ids", [])) | {e["id"] for e in emails}
        )
        save_state({
            "last_run_at": utc_now_iso(),
            "processed_ids": new_ids,
        })
        print(f"[{run_id}] State saved. Total processed IDs: {len(new_ids)}.")

    except Exception as e:
        result["error"] = str(e)
        print(f"[{run_id}] ERROR: {e}", file=sys.stderr)

    return result


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Email Digest Bot — fetch Gmail, summarize, post to Slack."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and summarize emails but do not post to Slack.",
    )
    args = parser.parse_args()

    result = run(dry_run=args.dry_run)
    print("\n--- RunResult ---")
    print(json.dumps(result, indent=2))

    if result.get("error"):
        sys.exit(1)


if __name__ == "__main__":
    main()
