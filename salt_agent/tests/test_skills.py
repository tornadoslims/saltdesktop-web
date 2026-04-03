"""Tests for the skill system."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from salt_agent.skills.manager import Skill, SkillManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_skill_dir(base: Path, name: str, content: str) -> Path:
    """Create a skill directory with a SKILL.md file."""
    skill_dir = base / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(content)
    return skill_dir


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSkillDiscovery:
    def test_discover_from_directory(self, tmp_path: Path):
        """Skills are discovered from directories containing SKILL.md."""
        _create_skill_dir(tmp_path, "my-skill", "---\nname: my-skill\ndescription: A test skill\n---\nDo the thing.")
        mgr = SkillManager(extra_dirs=[str(tmp_path)])
        assert mgr.get("my-skill") is not None
        assert mgr.get("my-skill").description == "A test skill"

    def test_discover_multiple_skills(self, tmp_path: Path):
        _create_skill_dir(tmp_path, "alpha", "---\nname: alpha\n---\nAlpha content")
        _create_skill_dir(tmp_path, "beta", "---\nname: beta\n---\nBeta content")
        mgr = SkillManager(extra_dirs=[str(tmp_path)])
        names = {s.name for s in mgr.list_skills()}
        # Should find at least alpha and beta (plus bundled)
        assert "alpha" in names
        assert "beta" in names

    def test_ignore_dirs_without_skill_md(self, tmp_path: Path):
        (tmp_path / "not-a-skill").mkdir()
        (tmp_path / "not-a-skill" / "README.md").write_text("hello")
        mgr = SkillManager(extra_dirs=[str(tmp_path)])
        assert mgr.get("not-a-skill") is None

    def test_nonexistent_directory(self):
        """Non-existent directories are silently skipped."""
        mgr = SkillManager(extra_dirs=["/nonexistent/path/that/does/not/exist"])
        # Should not crash; still loads bundled skills
        assert isinstance(mgr.list_skills(), list)


class TestSkillFrontmatter:
    def test_parse_frontmatter(self, tmp_path: Path):
        content = "---\nname: custom-name\ndescription: Does things\nuser-invocable: true\n---\nBody here."
        _create_skill_dir(tmp_path, "dir-name", content)
        mgr = SkillManager(extra_dirs=[str(tmp_path)])
        skill = mgr.get("custom-name")
        assert skill is not None
        assert skill.name == "custom-name"
        assert skill.description == "Does things"
        assert skill.user_invocable is True
        assert skill.content == "Body here."

    def test_name_defaults_to_directory_name(self, tmp_path: Path):
        content = "---\ndescription: No name field\n---\nBody."
        _create_skill_dir(tmp_path, "fallback-name", content)
        mgr = SkillManager(extra_dirs=[str(tmp_path)])
        skill = mgr.get("fallback-name")
        assert skill is not None
        assert skill.name == "fallback-name"

    def test_no_frontmatter(self, tmp_path: Path):
        content = "Just plain markdown, no frontmatter."
        _create_skill_dir(tmp_path, "plain", content)
        mgr = SkillManager(extra_dirs=[str(tmp_path)])
        skill = mgr.get("plain")
        assert skill is not None
        assert skill.name == "plain"
        assert skill.content == "Just plain markdown, no frontmatter."

    def test_user_invocable_false(self, tmp_path: Path):
        content = "---\nname: internal\nuser-invocable: false\n---\nInternal only."
        _create_skill_dir(tmp_path, "internal", content)
        mgr = SkillManager(extra_dirs=[str(tmp_path)])
        skill = mgr.get("internal")
        assert skill is not None
        assert skill.user_invocable is False


class TestSkillInvoke:
    def test_invoke_returns_content(self, tmp_path: Path):
        _create_skill_dir(tmp_path, "greet", "---\nname: greet\n---\nSay hello!")
        mgr = SkillManager(extra_dirs=[str(tmp_path)])
        result = mgr.invoke("greet")
        assert result == "Say hello!"

    def test_invoke_not_found(self, tmp_path: Path):
        mgr = SkillManager(extra_dirs=[str(tmp_path)])
        result = mgr.invoke("nonexistent")
        assert "not found" in result.lower()


class TestUserInvocableFilter:
    def test_filter_user_invocable(self, tmp_path: Path):
        _create_skill_dir(tmp_path, "public", "---\nname: public\nuser-invocable: true\n---\nPublic.")
        _create_skill_dir(tmp_path, "private", "---\nname: private\nuser-invocable: false\n---\nPrivate.")
        mgr = SkillManager(extra_dirs=[str(tmp_path)])
        invocable_names = {s.name for s in mgr.list_user_invocable()}
        assert "public" in invocable_names
        assert "private" not in invocable_names


class TestBundledSkills:
    def test_bundled_commit_skill_exists(self):
        mgr = SkillManager()
        skill = mgr.get("commit")
        assert skill is not None
        assert skill.user_invocable is True
        assert "git" in skill.content.lower()

    def test_bundled_review_skill_exists(self):
        mgr = SkillManager()
        skill = mgr.get("review")
        assert skill is not None
        assert skill.user_invocable is True
        assert "review" in skill.content.lower() or "diff" in skill.content.lower()

    def test_bundled_skills_discovered(self):
        mgr = SkillManager()
        names = {s.name for s in mgr.list_skills()}
        assert "commit" in names
        assert "review" in names


class TestSkillOverride:
    def test_later_dirs_override_earlier(self, tmp_path: Path):
        """Skills in later directories override skills from earlier ones."""
        dir1 = tmp_path / "first"
        dir2 = tmp_path / "second"
        _create_skill_dir(dir1, "test", "---\nname: test\n---\nOriginal.")
        _create_skill_dir(dir2, "test", "---\nname: test\n---\nOverridden.")
        mgr = SkillManager(extra_dirs=[str(dir1), str(dir2)])
        assert mgr.invoke("test") == "Overridden."


class TestScriptsAndReferences:
    def test_scripts_dir_detected(self, tmp_path: Path):
        skill_dir = _create_skill_dir(tmp_path, "with-scripts", "---\nname: with-scripts\n---\nHas scripts.")
        (skill_dir / "scripts").mkdir()
        mgr = SkillManager(extra_dirs=[str(tmp_path)])
        skill = mgr.get("with-scripts")
        assert skill.scripts_dir is not None
        assert skill.scripts_dir.name == "scripts"

    def test_references_dir_detected(self, tmp_path: Path):
        skill_dir = _create_skill_dir(tmp_path, "with-refs", "---\nname: with-refs\n---\nHas refs.")
        (skill_dir / "references").mkdir()
        mgr = SkillManager(extra_dirs=[str(tmp_path)])
        skill = mgr.get("with-refs")
        assert skill.references_dir is not None

    def test_no_scripts_dir(self, tmp_path: Path):
        _create_skill_dir(tmp_path, "no-scripts", "---\nname: no-scripts\n---\nNo scripts.")
        mgr = SkillManager(extra_dirs=[str(tmp_path)])
        skill = mgr.get("no-scripts")
        assert skill.scripts_dir is None
        assert skill.references_dir is None


class TestBundledSkills:
    """Verify all expected bundled skills are discovered."""

    EXPECTED_BUNDLED = {"commit", "review", "simplify", "debug", "test", "explain", "refactor"}

    def test_all_bundled_skills_discovered(self):
        mgr = SkillManager()
        names = {s.name for s in mgr.list_skills()}
        for expected in self.EXPECTED_BUNDLED:
            assert expected in names, f"Bundled skill '{expected}' not found"

    def test_bundled_skills_have_descriptions(self):
        mgr = SkillManager()
        for name in self.EXPECTED_BUNDLED:
            skill = mgr.get(name)
            assert skill is not None, f"Skill '{name}' not found"
            assert skill.description, f"Skill '{name}' has no description"

    def test_bundled_skills_have_content(self):
        mgr = SkillManager()
        for name in self.EXPECTED_BUNDLED:
            skill = mgr.get(name)
            assert skill is not None
            assert len(skill.content) > 10, f"Skill '{name}' has insufficient content"

    def test_bundled_skills_are_user_invocable(self):
        mgr = SkillManager()
        invocable = {s.name for s in mgr.list_user_invocable()}
        for name in self.EXPECTED_BUNDLED:
            assert name in invocable, f"Skill '{name}' should be user-invocable"

    def test_invoke_simplify(self):
        mgr = SkillManager()
        content = mgr.invoke("simplify")
        assert "complexity" in content.lower() or "simpl" in content.lower()

    def test_invoke_debug(self):
        mgr = SkillManager()
        content = mgr.invoke("debug")
        assert "root cause" in content.lower() or "error" in content.lower()

    def test_invoke_test(self):
        mgr = SkillManager()
        content = mgr.invoke("test")
        assert "test" in content.lower()

    def test_invoke_explain(self):
        mgr = SkillManager()
        content = mgr.invoke("explain")
        assert "explain" in content.lower()

    def test_invoke_refactor(self):
        mgr = SkillManager()
        content = mgr.invoke("refactor")
        assert "refactor" in content.lower()
