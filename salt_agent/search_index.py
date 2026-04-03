"""Session search index for fast content search across sessions.

Builds an inverted index from JSONL session files. Words map to
(session_id, line_number) pairs. Rebuilds on demand when sessions change.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path


@dataclass
class SearchResult:
    session_id: str
    line_number: int
    timestamp: str
    role: str
    preview: str
    score: float


class SessionSearchIndex:
    def __init__(self, sessions_dir: str):
        self.sessions_dir = Path(sessions_dir)
        self._index: dict[str, list[tuple[str, int, float]]] = defaultdict(list)  # word -> [(session_id, line, score)]
        self._session_mtimes: dict[str, float] = {}
        self._built = False

    def build(self, force: bool = False) -> None:
        """Build or rebuild the index from session files."""
        if not self.sessions_dir.exists():
            return

        for f in self.sessions_dir.glob("*.jsonl"):
            mtime = f.stat().st_mtime
            sid = f.stem

            if not force and sid in self._session_mtimes and self._session_mtimes[sid] >= mtime:
                continue  # unchanged

            self._session_mtimes[sid] = mtime
            self._index_session(sid, f)

        self._built = True

    def _index_session(self, session_id: str, path: Path) -> None:
        """Index a single session file."""
        # Remove old entries for this session
        for word in list(self._index.keys()):
            self._index[word] = [(s, l, sc) for s, l, sc in self._index[word] if s != session_id]

        with open(path) as f:
            for line_num, line in enumerate(f):
                try:
                    entry = json.loads(line.strip())
                    text = ""
                    if entry.get("type") == "checkpoint":
                        msgs = entry.get("messages", [])
                        for m in msgs[-3:]:  # index recent messages
                            content = m.get("content", "")
                            if isinstance(content, str):
                                text += " " + content

                    # Also index event data
                    if entry.get("type") not in ("checkpoint",) and "data" in entry:
                        data_str = json.dumps(entry["data"])
                        text += " " + data_str

                    # Tokenize and index
                    words = set(re.findall(r"\b\w{3,}\b", text.lower()))
                    for word in words:
                        self._index[word].append((session_id, line_num, 1.0))
                except Exception:
                    pass

    def search(self, query: str, max_results: int = 10) -> list[SearchResult]:
        """Search sessions for matching content."""
        if not self._built:
            self.build()

        query_words = set(re.findall(r"\b\w{3,}\b", query.lower()))
        if not query_words:
            return []

        # Score: number of matching query words
        scores: dict[tuple[str, int], float] = defaultdict(float)
        for word in query_words:
            for session_id, line_num, base_score in self._index.get(word, []):
                scores[(session_id, line_num)] += base_score

        # Sort by score descending
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:max_results]

        results = []
        for (session_id, line_num), score in ranked:
            preview, timestamp, role = self._get_preview(session_id, line_num)
            results.append(SearchResult(
                session_id=session_id,
                line_number=line_num,
                timestamp=timestamp,
                role=role,
                preview=preview,
                score=score,
            ))

        return results

    def _get_preview(self, session_id: str, line_num: int) -> tuple[str, str, str]:
        """Return (preview, timestamp, role) for a given session line."""
        path = self.sessions_dir / f"{session_id}.jsonl"
        if not path.exists():
            return "", "", ""
        try:
            with open(path) as f:
                for i, line in enumerate(f):
                    if i == line_num:
                        entry = json.loads(line.strip())
                        timestamp = entry.get("timestamp", "")
                        role = ""
                        if entry.get("type") == "checkpoint":
                            msgs = entry.get("messages", [])
                            if msgs:
                                role = msgs[-1].get("role", "")
                        preview = str(entry.get("data", entry))[:200]
                        return preview, timestamp, role
        except Exception:
            pass
        return "", "", ""

    def invalidate(self, session_id: str | None = None) -> None:
        """Invalidate the index for a session (or all sessions).

        Forces rebuild on next search.
        """
        if session_id:
            self._session_mtimes.pop(session_id, None)
        else:
            self._session_mtimes.clear()
            self._built = False
