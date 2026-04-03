"""Session persistence -- JSONL-based crash recovery and session resume."""

from __future__ import annotations

import json
import os
import signal
import uuid
from datetime import datetime, timezone
from pathlib import Path


class SessionPersistence:
    """Append-only JSONL session storage for crash recovery."""

    def __init__(self, session_id: str | None = None, sessions_dir: str | None = None):
        self.session_id = session_id or str(uuid.uuid4())
        self.sessions_dir = Path(sessions_dir or "~/.s_code/sessions").expanduser()
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self._file = self.sessions_dir / f"{self.session_id}.jsonl"

    # ------------------------------------------------------------------
    # Concurrent session detection
    # ------------------------------------------------------------------

    def check_concurrent_session(self) -> dict | None:
        """Check if another SaltAgent is using the same sessions directory.

        Returns the lock data dict if a live session is detected, else None.
        Also writes our own lock if no conflict.
        """
        lock_path = self.sessions_dir / ".lock"
        if lock_path.exists():
            try:
                lock_data = json.loads(lock_path.read_text())
                pid = lock_data.get("pid")
                if pid is not None:
                    try:
                        os.kill(pid, 0)  # Check if process exists
                        return lock_data  # Another session is running
                    except OSError:
                        pass  # Process is dead, stale lock
            except (json.JSONDecodeError, KeyError, TypeError):
                pass

        # Write our lock
        lock_path.write_text(json.dumps({
            "pid": os.getpid(),
            "started": datetime.now(timezone.utc).isoformat(),
            "session_id": self.session_id,
        }))
        return None  # No conflict

    def release_lock(self) -> None:
        """Release the session lock."""
        lock_path = self.sessions_dir / ".lock"
        if lock_path.exists():
            try:
                lock_data = json.loads(lock_path.read_text())
                if lock_data.get("pid") == os.getpid():
                    lock_path.unlink()
            except (json.JSONDecodeError, KeyError, TypeError, OSError):
                pass

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
        """Search all sessions for matching content using inverted index."""
        if not hasattr(self, "_search_index"):
            from salt_agent.search_index import SessionSearchIndex
            self._search_index = SessionSearchIndex(str(self.sessions_dir))
        results = self._search_index.search(query, max_results)
        # Return dicts for backward compatibility
        return [
            {
                "session_id": r.session_id,
                "line": r.line_number,
                "type": "checkpoint" if r.role else "event",
                "preview": r.preview[:200],
                "timestamp": r.timestamp,
                "score": r.score,
            }
            for r in results
        ]
