"""Session persistence -- JSONL-based crash recovery and session resume."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path


class SessionPersistence:
    """Append-only JSONL session storage for crash recovery."""

    def __init__(self, session_id: str | None = None, sessions_dir: str | None = None):
        self.session_id = session_id or str(uuid.uuid4())
        self.sessions_dir = Path(sessions_dir or "~/.saltdesktop/sessions").expanduser()
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self._file = self.sessions_dir / f"{self.session_id}.jsonl"

    def save_checkpoint(
        self,
        messages: list[dict],
        system: str = "",
        metadata: dict | None = None,
    ) -> None:
        """Append a checkpoint to the session file.

        Called BEFORE each API call so a killed process can resume.
        """
        entry = {
            "type": "checkpoint",
            "messages": messages,
            "system": system,
            "metadata": metadata or {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        with open(self._file, "a") as f:
            f.write(json.dumps(entry, default=str) + "\n")

    def save_event(self, event_type: str, data: dict) -> None:
        """Append an event (tool use, completion, etc.)."""
        entry = {
            "type": event_type,
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        with open(self._file, "a") as f:
            f.write(json.dumps(entry, default=str) + "\n")

    def load_last_checkpoint(self) -> dict | None:
        """Load the most recent checkpoint from the session."""
        if not self._file.exists():
            return None
        last = None
        with open(self._file) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                entry = json.loads(line)
                if entry.get("type") == "checkpoint":
                    last = entry
        return last

    def list_sessions(self) -> list[dict]:
        """List all sessions with metadata."""
        sessions = []
        for f in sorted(
            self.sessions_dir.glob("*.jsonl"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        ):
            sessions.append({
                "session_id": f.stem,
                "path": str(f),
                "size": f.stat().st_size,
                "modified": f.stat().st_mtime,
            })
        return sessions

    def load_all_events(self) -> list[dict]:
        """Load all entries from the session file."""
        if not self._file.exists():
            return []
        entries = []
        with open(self._file) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                entries.append(json.loads(line))
        return entries

    def search_sessions(self, query: str, max_results: int = 10) -> list[dict]:
        """Search all sessions for matching content."""
        results = []
        for session_file in sorted(
            self.sessions_dir.glob("*.jsonl"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        ):
            with open(session_file) as f:
                for line_num, line in enumerate(f):
                    if query.lower() in line.lower():
                        try:
                            entry = json.loads(line)
                            results.append({
                                "session_id": session_file.stem,
                                "line": line_num,
                                "type": entry.get("type", "?"),
                                "preview": line.strip()[:200],
                                "timestamp": entry.get("timestamp", ""),
                            })
                        except (json.JSONDecodeError, KeyError):
                            pass
                        if len(results) >= max_results:
                            return results
        return results
