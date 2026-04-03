"""Skill system -- markdown-based prompt injection commands.

Skills are directories containing a SKILL.md file that teaches the agent
how to perform a specific task. When invoked (via /skill-name or the
skill tool), the SKILL.md content is injected into context.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class Skill:
    name: str
    description: str
    content: str  # Full SKILL.md body (after frontmatter)
    path: Path
    user_invocable: bool = True
    scripts_dir: Path | None = None
    references_dir: Path | None = None


# Directory containing bundled skills shipped with salt_agent
_BUNDLED_DIR = Path(__file__).resolve().parent / "bundled"


class SkillManager:
    """Discovers, loads, and manages skills from multiple directories."""

    SKILL_DIRS = [
        Path.cwd() / "skills",               # workspace skills (highest priority)
        Path.cwd() / ".skills",              # hidden workspace skills
        Path.home() / ".salt-agent" / "skills",  # user skills
    ]

    def __init__(self, extra_dirs: list[str] | None = None) -> None:
        self._skills: dict[str, Skill] = {}
        self._dirs: list[Path] = list(self.SKILL_DIRS)
        # Bundled skills have lowest priority (loaded first, overridden by others)
        self._dirs.insert(0, _BUNDLED_DIR)
        if extra_dirs:
            self._dirs.extend(Path(d) for d in extra_dirs)
        self.discover()

    def discover(self) -> None:
        """Scan skill directories and load all skills.

        Later directories override earlier ones (workspace > user > bundled).
        """
        self._skills.clear()
        for skill_dir in self._dirs:
            if not skill_dir.exists():
                continue
            try:
                entries = sorted(skill_dir.iterdir())
            except PermissionError:
                continue
            for entry in entries:
                if entry.is_dir():
                    skill_md = entry / "SKILL.md"
                    if skill_md.exists():
                        skill = self._load_skill(entry, skill_md)
                        if skill:
                            # Later directories override earlier ones
                            self._skills[skill.name] = skill

    @staticmethod
    def _load_skill(directory: Path, skill_md: Path) -> Skill | None:
        """Load a skill from its directory."""
        try:
            content = skill_md.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None

        # Parse YAML-like frontmatter (simple key: value, no yaml dependency)
        meta: dict[str, str] = {}
        body = content
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                for line in parts[1].strip().splitlines():
                    if ":" in line:
                        key, val = line.split(":", 1)
                        meta[key.strip()] = val.strip()
                body = parts[2].strip()

        name = meta.get("name", directory.name)
        description = meta.get("description", "")
        user_invocable = meta.get("user-invocable", "true").lower() != "false"

        scripts = directory / "scripts"
        references = directory / "references"

        return Skill(
            name=name,
            description=description,
            content=body,
            path=directory,
            user_invocable=user_invocable,
            scripts_dir=scripts if scripts.exists() else None,
            references_dir=references if references.exists() else None,
        )

    def get(self, name: str) -> Skill | None:
        """Get a skill by name."""
        return self._skills.get(name)

    def list_skills(self) -> list[Skill]:
        """Return all discovered skills."""
        return list(self._skills.values())

    def list_user_invocable(self) -> list[Skill]:
        """Return skills that can be invoked by the user (slash commands)."""
        return [s for s in self._skills.values() if s.user_invocable]

    def invoke(self, name: str) -> str:
        """Get the skill content for injection into context.

        Returns the SKILL.md body on success, or an error message if not found.
        """
        skill = self._skills.get(name)
        if not skill:
            available = ", ".join(sorted(self._skills.keys())) or "(none)"
            return f"Skill '{name}' not found. Available skills: {available}"
        return skill.content
