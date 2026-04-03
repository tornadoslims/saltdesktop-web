"""File history -- content-addressed snapshots for rewind support."""

from __future__ import annotations

import hashlib
import shutil
from datetime import datetime, timezone
from pathlib import Path


class FileHistory:
    """Content-addressed file backups enabling full session rewind.

    Before any file modification, call ``snapshot(path)`` to save the
    original content.  Call ``rewind()`` to restore every modified file
    to its pre-session state and delete files that were created during
    the session.
    """

    def __init__(
        self,
        session_id: str,
        backup_dir: str | None = None,
        max_snapshots: int = 100,
    ) -> None:
        self.session_id = session_id
        self.backup_dir = (
            Path(backup_dir or "~/.saltdesktop/snapshots").expanduser() / session_id
        )
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self._snapshots: list[dict] = []
        self._created_files: set[str] = set()
        self.max_snapshots = max_snapshots

    def snapshot(self, file_path: str) -> None:
        """Snapshot a file before modification.

        If the file does not yet exist it is tracked as *created* so that
        ``rewind()`` can delete it.
        """
        path = Path(file_path)
        if not path.is_absolute():
            return  # safety: only handle absolute paths

        if not path.exists():
            self._created_files.add(str(path.resolve()))
            return

        if len(self._snapshots) >= self.max_snapshots:
            return  # don't exceed limit

        content = path.read_bytes()
        file_hash = hashlib.sha256(content).hexdigest()
        backup_path = self.backup_dir / f"{file_hash}.bak"

        if not backup_path.exists():
            backup_path.write_bytes(content)

        self._snapshots.append({
            "path": str(path.resolve()),
            "hash": file_hash,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def rewind(self) -> list[str]:
        """Restore all modified files and delete created files.

        For each file that was snapshotted, only the *first* snapshot
        (the original pre-session state) is used.
        """
        restored: list[str] = []

        # Restore modified files — first snapshot per path is the original
        seen_paths: set[str] = set()
        for snap in self._snapshots:
            if snap["path"] in seen_paths:
                continue
            seen_paths.add(snap["path"])

            backup_path = self.backup_dir / f"{snap['hash']}.bak"
            if backup_path.exists():
                target = Path(snap["path"])
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(backup_path), str(target))
                restored.append(f"Restored: {snap['path']}")

        # Delete files created during this session
        for created in sorted(self._created_files):
            p = Path(created)
            if p.exists():
                p.unlink()
                restored.append(f"Deleted (created this session): {created}")

        return restored

    def get_history(self) -> list[dict]:
        """Return a copy of the snapshot history."""
        return list(self._snapshots)
