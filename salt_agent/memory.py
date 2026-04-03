"""Memory system -- project instructions, cross-session memory, and LLM-powered recall.

Implements Claude Code's memdir/ pattern: typed memory files with YAML frontmatter,
an index file (MEMORY.md), and per-turn relevance ranking via LLM side-query.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from salt_agent.providers.base import ProviderAdapter

# Memory type taxonomy (mirrors Claude Code's memoryTypes.ts)
MEMORY_TYPES = {
    "user": {
        "description": "Information about the user's role, goals, preferences, knowledge",
        "when_to_save": "When you learn details about the user's role, preferences, or knowledge",
        "when_to_use": "When your work should be informed by the user's profile",
    },
    "feedback": {
        "description": "Corrections and confirmations from the user about approach",
        "when_to_save": "When the user corrects your approach OR confirms a non-obvious approach worked",
        "when_to_use": "Let these guide your behavior so the user doesn't repeat guidance",
    },
    "project": {
        "description": "Ongoing work, goals, decisions, deadlines within the project",
        "when_to_save": "When you learn who is doing what, why, or by when",
        "when_to_use": "Understand broader context behind the user's request",
    },
    "reference": {
        "description": "Pointers to where information can be found in external systems",
        "when_to_save": "When you learn about resources in external systems",
        "when_to_use": "When the user references an external system",
    },
}


class MemorySystem:
    """Loads project instructions (SALT.md / CLAUDE.md) and persistent memory files."""

    def __init__(
        self,
        working_directory: str = ".",
        memory_dir: str | None = None,
    ):
        self.working_dir = Path(working_directory)
        self.memory_dir = Path(memory_dir or "~/.salt-agent/memory").expanduser()

    def load_project_instructions(self) -> str:
        """Find and load SALT.md / CLAUDE.md from working dir and parents.

        Searches up to 10 levels. Closer-to-cwd files appear first.
        """
        instructions: list[str] = []
        search_dir = self.working_dir.resolve()
        for _ in range(10):  # max 10 levels up
            for name in ["SALT.md", "CLAUDE.md", ".claude/instructions.md"]:
                path = search_dir / name
                if path.exists():
                    try:
                        content = path.read_text()[:5000]
                        instructions.append(
                            f"# Instructions from {path}\n\n{content}"
                        )
                    except (OSError, PermissionError):
                        pass
            parent = search_dir.parent
            if parent == search_dir:
                break
            search_dir = parent
        return "\n\n---\n\n".join(instructions)

    def load_memory_index(self) -> list[dict]:
        """Load MEMORY.md index for per-turn memory surfacing."""
        index_path = self.memory_dir / "MEMORY.md"
        if not index_path.exists():
            return []
        entries: list[dict] = []
        try:
            for line in index_path.read_text().splitlines():
                line = line.strip()
                if line.startswith("- ["):
                    # Parse: - [Title](file.md) -- description
                    entries.append({"line": line, "raw": line})
        except (OSError, PermissionError):
            pass
        return entries

    def load_memory_file(self, filename: str) -> str:
        """Load a specific memory file."""
        path = self.memory_dir / filename
        if path.exists():
            try:
                return path.read_text()[:3000]
            except (OSError, PermissionError):
                return ""
        return ""

    def save_memory(self, filename: str, content: str) -> None:
        """Save a memory file."""
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        (self.memory_dir / filename).write_text(content)

    # --- Memory types + frontmatter support ---

    def scan_memory_files(self) -> list[dict]:
        """Scan memory directory and extract frontmatter from each .md file.

        Returns a list of dicts with keys: filename, name, description, type.
        """
        entries = []
        if not self.memory_dir.exists():
            return entries
        for f in sorted(self.memory_dir.glob("*.md")):
            if f.name == "MEMORY.md":
                continue
            try:
                content = f.read_text()
            except (OSError, PermissionError):
                continue
            meta = self._parse_frontmatter(content)
            entries.append({
                "filename": f.name,
                "name": meta.get("name", f.stem),
                "description": meta.get("description", ""),
                "type": meta.get("type", "project"),
            })
        return entries

    @staticmethod
    def _parse_frontmatter(content: str) -> dict:
        """Parse YAML-style frontmatter from a memory file.

        Expects:
            ---
            key: value
            ---
        Uses simple key:value parsing to avoid a yaml dependency.
        """
        if not content.startswith("---"):
            return {}
        parts = content.split("---", 2)
        if len(parts) < 3:
            return {}
        meta: dict[str, str] = {}
        for line in parts[1].strip().splitlines():
            if ":" in line:
                key, val = line.split(":", 1)
                meta[key.strip()] = val.strip()
        return meta

    def save_memory_file(
        self,
        name: str,
        content: str,
        memory_type: str,
        description: str,
    ) -> None:
        """Save a memory file with YAML frontmatter and update the index."""
        self.memory_dir.mkdir(parents=True, exist_ok=True)

        slug = name.lower().replace(" ", "_").replace("-", "_")
        # Remove any characters that aren't alphanumeric or underscore
        slug = "".join(c for c in slug if c.isalnum() or c == "_")
        filename = f"{slug}.md"

        file_content = (
            f"---\n"
            f"name: {name}\n"
            f"description: {description}\n"
            f"type: {memory_type}\n"
            f"---\n\n"
            f"{content}\n"
        )
        (self.memory_dir / filename).write_text(file_content)

        # Update MEMORY.md index
        self._update_index(filename, description)

    def _update_index(self, filename: str, description: str) -> None:
        """Add or update an entry in MEMORY.md index (max 200 lines)."""
        index_path = self.memory_dir / "MEMORY.md"
        lines: list[str] = []
        if index_path.exists():
            try:
                lines = index_path.read_text().splitlines()
            except (OSError, PermissionError):
                pass

        entry_line = f"- [{filename.replace('.md', '')}]({filename}) — {description[:100]}"

        # Check if entry already exists -- update in place
        updated = False
        for i, line in enumerate(lines):
            if filename in line:
                lines[i] = entry_line
                updated = True
                break
        if not updated:
            lines.append(entry_line)

        # Enforce 200 line limit (keep newest)
        if len(lines) > 200:
            lines = lines[-200:]

        index_path.write_text("\n".join(lines) + "\n")


async def find_relevant_memories(
    query: str,
    memory_index: list[dict],
    provider: "ProviderAdapter",
) -> list[str]:
    """LLM side-query to select 0-5 relevant memories for this turn.

    Args:
        query: The current user query / task description.
        memory_index: List of dicts from MemorySystem.scan_memory_files().
        provider: A ProviderAdapter with quick_query().

    Returns:
        List of filenames (max 5) that are relevant.
    """
    if not memory_index:
        return []

    descriptions = "\n".join(
        f"- {m['filename']}: {m['description']}"
        for m in memory_index[:50]  # cap to avoid huge prompt
    )

    prompt = (
        "Which of these memory files (0-5 max) are relevant to the current task?\n\n"
        f"Current task/query: {query[:500]}\n\n"
        f"Available memories:\n{descriptions}\n\n"
        "Return ONLY the filenames that are relevant, one per line.\n"
        'Return "NONE" if nothing is relevant. Do not explain.'
    )

    try:
        result = await provider.quick_query(prompt, max_tokens=200)
    except Exception:
        return []

    if not result or "NONE" in result.upper():
        return []

    filenames: list[str] = []
    for line in result.strip().splitlines():
        line = line.strip().strip("- ")
        if line and not line.upper().startswith("NONE"):
            # Match against known filenames
            for m in memory_index:
                if m["filename"] in line or line in m["filename"]:
                    filenames.append(m["filename"])
                    break

    return filenames[:5]
