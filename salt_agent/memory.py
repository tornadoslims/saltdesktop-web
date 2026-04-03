"""Memory system -- project instructions and cross-session memory."""

from __future__ import annotations

from pathlib import Path


class MemorySystem:
    """Loads project instructions (SALT.md / CLAUDE.md) and persistent memory files."""

    def __init__(
        self,
        working_directory: str = ".",
        memory_dir: str | None = None,
    ):
        self.working_dir = Path(working_directory)
        self.memory_dir = Path(memory_dir or "~/.saltdesktop/memory").expanduser()

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
