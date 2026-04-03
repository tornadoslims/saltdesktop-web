"""Skill system -- markdown-based prompt injection commands.

Skills are directories containing a SKILL.md file that teaches the agent
how to perform a specific task. When invoked (via /skill-name or the
skill tool), the SKILL.md content is injected into context.
"""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass, field
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
    metadata: dict | None = None  # Parsed frontmatter metadata (requires, os, etc.)


# Directory containing bundled skills shipped with salt_agent
_BUNDLED_DIR = Path(__file__).resolve().parent / "bundled"


class SkillManager:
    """Discovers, loads, and manages skills from multiple directories."""

    SKILL_DIRS = [
        Path.cwd() / "skills",               # workspace skills (highest priority)
        Path.cwd() / ".skills",              # hidden workspace skills
        Path.home() / ".s_code" / "skills",  # user skills
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
                        if skill and self._should_activate(skill):
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
        metadata: dict = {}
        body = content
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                metadata = SkillManager._parse_frontmatter(parts[1].strip())
                # Flatten top-level for backward compat
                for k, v in metadata.items():
                    if isinstance(v, str):
                        meta[k] = v
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
            metadata=metadata or None,
        )

    @staticmethod
    def _parse_frontmatter(text: str) -> dict:
        """Parse YAML-like frontmatter including nested maps and lists.

        Supports up to 3 levels of nesting:
          key: value
          key:
            sub_key: value
            sub_key:
              sub_sub_key: [a, b, c]
        """
        result: dict = {}
        # Stack: list of (indent_level, key, dict_ref)
        stack: list[tuple[int, str, dict]] = [(-1, "", result)]

        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or ":" not in stripped:
                continue

            leading_spaces = len(line) - len(line.lstrip())
            key, val = stripped.split(":", 1)
            key = key.strip()
            val = val.strip()

            # Pop stack until we find a parent with lower indent
            while len(stack) > 1 and stack[-1][0] >= leading_spaces:
                stack.pop()

            parent_dict = stack[-1][2]

            if val:
                # Inline value or inline list
                if val.startswith("[") and val.endswith("]"):
                    items = [v.strip().strip("'\"") for v in val[1:-1].split(",") if v.strip()]
                    parent_dict[key] = items
                else:
                    parent_dict[key] = val
            else:
                # Start a new nested dict
                new_dict: dict = {}
                parent_dict[key] = new_dict
                stack.append((leading_spaces, key, new_dict))

        return result

    @staticmethod
    def _should_activate(skill: Skill) -> bool:
        """Check if a skill's requirements are met.

        Checks metadata.requires for:
        - bins: list of required binaries (checked via shutil.which)
        - env: list of required environment variables
        - os: list of allowed platforms (sys.platform values)

        The metadata dict may have "requires" at the top level, or nested
        under a "metadata" key (from frontmatter parsing).
        """
        meta = skill.metadata or {}

        # Support both top-level requires and nested under metadata key
        if "metadata" in meta and isinstance(meta["metadata"], dict):
            inner = meta["metadata"]
            requires = inner.get("requires", {})
            # Also check os at the inner level
            if "os" not in meta and "os" in inner:
                meta = {**meta, "os": inner["os"]}
        else:
            requires = meta.get("requires", {})

        if not isinstance(requires, dict):
            return True

        # Check required binaries
        bins = requires.get("bins", [])
        if isinstance(bins, list):
            for b in bins:
                if not shutil.which(str(b)):
                    return False

        # Check required env vars
        env_vars = requires.get("env", [])
        if isinstance(env_vars, list):
            for e in env_vars:
                if not os.environ.get(str(e)):
                    return False

        # Check OS
        os_list = meta.get("os", [])
        if isinstance(os_list, list) and os_list:
            if sys.platform not in os_list:
                return False

        return True

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
