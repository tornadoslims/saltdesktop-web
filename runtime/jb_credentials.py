"""
Credential Store — reads credentials written by the Salt Desktop Swift app.

Credentials are stored as JSON files at ~/.missionos/credentials/{service_id}.json.
The Swift app handles OAuth flows and API key entry. This module only READS.

ONE EXCEPTION: Refreshed OAuth tokens are written back to the JSON file.
"""

import json
import os
from pathlib import Path
from typing import Optional

CRED_DIR = Path.home() / ".missionos" / "credentials"

# Known service IDs and their types
SERVICE_CATALOG = {
    "gmail": {"name": "Gmail", "type": "oauth", "category": "email"},
    "google_calendar": {"name": "Google Calendar", "type": "oauth", "category": "productivity"},
    "google_drive": {"name": "Google Drive", "type": "oauth", "category": "storage"},
    "github": {"name": "GitHub", "type": "oauth", "category": "developer"},
    "salesforce": {"name": "Salesforce", "type": "oauth", "category": "crm"},
    "notion": {"name": "Notion", "type": "api_key", "category": "productivity"},
    "linear": {"name": "Linear", "type": "api_key", "category": "project_management"},
    "jira": {"name": "Jira", "type": "oauth", "category": "project_management"},
    "discord": {"name": "Discord", "type": "api_key", "category": "messaging"},
    "telegram": {"name": "Telegram", "type": "api_key", "category": "messaging"},
    "openai": {"name": "OpenAI", "type": "api_key", "category": "ai"},
    "stripe": {"name": "Stripe", "type": "api_key", "category": "payments"},
    "aws": {"name": "AWS", "type": "key_pair", "category": "cloud"},
    "snowflake": {"name": "Snowflake", "type": "connection_string", "category": "database"},
    "mysql": {"name": "MySQL", "type": "connection_string", "category": "database"},
    "postgres": {"name": "PostgreSQL", "type": "connection_string", "category": "database"},
    "oracle": {"name": "Oracle", "type": "connection_string", "category": "database"},
    "redis": {"name": "Redis", "type": "connection_string", "category": "database"},
    "gcp": {"name": "Google Cloud", "type": "oauth", "category": "cloud"},
    "slack": {"name": "Slack", "type": "oauth", "category": "messaging"},
}

# OAuth client credentials for Google services (read from env or config)
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")


class CredentialStore:
    """Read-only access to credentials stored by the Swift app."""

    def __init__(self, cred_dir: Path = CRED_DIR):
        self._dir = cred_dir

    def get(self, service_id: str) -> Optional[dict]:
        """Get credentials for a service. Returns None if not connected."""
        path = self._dir / f"{service_id}.json"
        if not path.exists():
            return None
        try:
            with open(path) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return None

    def is_connected(self, service_id: str) -> bool:
        """Check if a service has credentials."""
        return self.get(service_id) is not None

    def list_connected(self) -> list[str]:
        """List all service IDs that have credential files."""
        if not self._dir.exists():
            return []
        return [f.stem for f in self._dir.glob("*.json")]

    def list_all(self) -> list[dict]:
        """List all known services with connection status."""
        connected = set(self.list_connected())
        result = []
        for sid, info in SERVICE_CATALOG.items():
            result.append({
                "id": sid,
                "name": info["name"],
                "type": info["type"],
                "category": info["category"],
                "connected": sid in connected,
            })
        # Also include any connected services not in catalog
        for sid in connected:
            if sid not in SERVICE_CATALOG:
                result.append({
                    "id": sid,
                    "name": sid.replace("_", " ").title(),
                    "type": "unknown",
                    "category": "other",
                    "connected": True,
                })
        return result

    def refresh_google_token(self, service_id: str) -> Optional[str]:
        """Refresh an expired Google OAuth token. Returns new access_token or None."""
        creds = self.get(service_id)
        if not creds or "refresh_token" not in creds:
            return None

        import httpx
        try:
            resp = httpx.post("https://oauth2.googleapis.com/token", data={
                "grant_type": "refresh_token",
                "refresh_token": creds["refresh_token"],
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
            })
            if resp.status_code == 200:
                new_data = resp.json()
                creds["access_token"] = new_data["access_token"]
                if "expires_in" in new_data:
                    creds["expires_in"] = new_data["expires_in"]
                # Write back — the ONE exception to read-only
                path = self._dir / f"{service_id}.json"
                with open(path, "w") as f:
                    json.dump(creds, f, indent=2)
                return new_data["access_token"]
        except Exception:
            pass
        return None


# Module-level singleton
credentials = CredentialStore()


# ---------------------------------------------------------------------------
# Connector metadata (stored in SQLite)
# ---------------------------------------------------------------------------

def register_connector(
    service_type: str,
    label: str,
    credential_file: str,
    account_id: str | None = None,
    scope: str | None = None,
    metadata: dict | None = None,
) -> str:
    """Register a connector in the database. Returns connector_id."""
    from uuid import uuid4
    from runtime.jb_common import utc_now_iso
    from runtime.jb_database import get_db, _json_dumps

    connector_id = str(uuid4())
    now = utc_now_iso()

    with get_db() as conn:
        conn.execute(
            """INSERT INTO connectors
               (connector_id, service_type, label, account_id,
                credential_file, status, scope, connected_at,
                last_used_at, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (connector_id, service_type, label, account_id,
             credential_file, "active", scope, now, None,
             _json_dumps(metadata or {})),
        )
    return connector_id


def list_connectors_with_metadata() -> list[dict]:
    """List all connectors with their metadata from SQLite,
    enriched with connection status from credential files."""
    from runtime.jb_database import get_db, _json_loads

    with get_db() as conn:
        rows = conn.execute("SELECT * FROM connectors").fetchall()

    result = []
    for row in rows:
        d = dict(row)
        d["metadata"] = _json_loads(d.get("metadata")) or {}
        # Check if credential file still exists
        cred_path = CRED_DIR / d["credential_file"]
        d["file_exists"] = cred_path.exists()
        result.append(d)
    return result


def get_connector(connector_id: str) -> dict | None:
    """Get a single connector by ID."""
    from runtime.jb_database import get_db, _json_loads

    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM connectors WHERE connector_id = ?", (connector_id,)
        ).fetchone()
    if row is None:
        return None
    d = dict(row)
    d["metadata"] = _json_loads(d.get("metadata")) or {}
    return d


def touch_connector(connector_id: str) -> None:
    """Update last_used_at for a connector."""
    from runtime.jb_common import utc_now_iso
    from runtime.jb_database import get_db

    with get_db() as conn:
        conn.execute(
            "UPDATE connectors SET last_used_at = ? WHERE connector_id = ?",
            (utc_now_iso(), connector_id),
        )
