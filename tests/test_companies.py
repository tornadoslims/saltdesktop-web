"""Tests for runtime.jb_companies and runtime.jb_company_mapping."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from runtime.jb_common import JsonStore
from runtime.jb_companies import (
    create_company,
    get_company,
    list_companies,
    update_company_name,
    update_company_description,
    archive_company,
    attach_mission,
    set_focused_mission,
    get_focused_mission_id,
    get_company_context_path,
    get_mission_context_path,
    ensure_mission_context,
)
from runtime.jb_company_mapping import (
    create_mapping,
    get_company_id_by_external,
    get_external_id_by_company,
    list_mappings,
    delete_mapping,
)


@pytest.fixture()
def tmp_companies(tmp_path):
    """Patch company, mapping, and mission modules to use temp dirs with SQLite."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    db_path = data_dir / "jbcp.db"

    # Legacy JSON files
    companies_file = data_dir / "jb_companies.json"
    mappings_file = data_dir / "jb_company_mappings.json"
    missions_file = data_dir / "jb_missions.json"
    companies_file.write_text("[]", encoding="utf-8")
    mappings_file.write_text("[]", encoding="utf-8")
    missions_file.write_text("[]", encoding="utf-8")

    patches = [
        # Database path
        patch("runtime.jb_database.DB_PATH", db_path),
        patch("runtime.jb_database.DATA_DIR", data_dir),
        # DATA_DIR for modules
        patch("runtime.jb_companies.DATA_DIR", data_dir),
        patch("runtime.jb_company_mapping.DATA_DIR", data_dir),
        patch("runtime.jb_missions.DATA_DIR", data_dir),
        # Legacy stores
        patch("runtime.jb_companies.COMPANIES_FILE", companies_file),
        patch("runtime.jb_companies._store", JsonStore(companies_file)),
        patch("runtime.jb_company_mapping.MAPPINGS_FILE", mappings_file),
        patch("runtime.jb_company_mapping._store", JsonStore(mappings_file)),
        patch("runtime.jb_missions.MISSIONS_FILE", missions_file),
        patch("runtime.jb_missions._store", JsonStore(missions_file)),
    ]

    for p in patches:
        p.start()

    # Initialize the database (and clear cache so it re-inits)
    import runtime.jb_database as _db_mod
    _db_mod._initialized_dbs.discard(str(db_path))
    _db_mod.init_db(db_path)

    yield {"root": tmp_path, "data_dir": data_dir}

    for p in patches:
        p.stop()


# -- Company CRUD -----------------------------------------------------------

class TestCreateCompany:
    def test_returns_id(self, tmp_companies):
        cid = create_company(name="Test Corp")
        assert isinstance(cid, str)
        assert len(cid) > 0

    def test_default_active(self, tmp_companies):
        cid = create_company(name="Test Corp")
        c = get_company(cid)
        assert c["status"] == "active"

    def test_preserves_name(self, tmp_companies):
        cid = create_company(name="My Company")
        c = get_company(cid)
        assert c["name"] == "My Company"

    def test_empty_name_raises(self, tmp_companies):
        with pytest.raises(ValueError, match="non-empty string"):
            create_company(name="")

    def test_invalid_status_raises(self, tmp_companies):
        with pytest.raises(ValueError, match="Invalid company status"):
            create_company(name="Test", status="bogus")

    def test_creates_context_dir(self, tmp_companies):
        cid = create_company(name="Test Corp")
        c = get_company(cid)
        context_path = Path(c["company_context_path"])
        assert context_path.exists()

    def test_empty_mission_ids(self, tmp_companies):
        cid = create_company(name="Test")
        c = get_company(cid)
        assert c["mission_ids"] == []
        assert c["focused_mission_id"] is None


class TestGetCompany:
    def test_existing(self, tmp_companies):
        cid = create_company(name="Test")
        assert get_company(cid) is not None

    def test_nonexistent(self, tmp_companies):
        assert get_company("nope") is None


class TestListCompanies:
    def test_empty(self, tmp_companies):
        assert list_companies() == []

    def test_returns_all(self, tmp_companies):
        create_company(name="A")
        create_company(name="B")
        assert len(list_companies()) == 2


class TestUpdateCompany:
    def test_rename(self, tmp_companies):
        cid = create_company(name="Old Name")
        result = update_company_name(cid, "New Name")
        assert result["name"] == "New Name"

    def test_archive(self, tmp_companies):
        cid = create_company(name="Test")
        result = archive_company(cid)
        assert result["status"] == "archived"

    def test_nonexistent_raises(self, tmp_companies):
        with pytest.raises(ValueError, match="Company not found"):
            update_company_name("nope", "New")

    def test_update_description(self, tmp_companies):
        cid = create_company(name="Test Corp")
        c = get_company(cid)
        assert c["description"] is None
        result = update_company_description(cid, "A great company")
        assert result["description"] == "A great company"
        # Verify persistence
        c2 = get_company(cid)
        assert c2["description"] == "A great company"

    def test_description_defaults_none(self, tmp_companies):
        cid = create_company(name="Test Corp")
        c = get_company(cid)
        assert c["description"] is None


# -- Mission management -----------------------------------------------------

class TestMissionManagement:
    def test_attach_mission(self, tmp_companies):
        cid = create_company(name="Test")
        result = attach_mission(cid, "m1")
        assert "m1" in result["mission_ids"]

    def test_attach_multiple(self, tmp_companies):
        cid = create_company(name="Test")
        attach_mission(cid, "m1")
        result = attach_mission(cid, "m2")
        assert result["mission_ids"] == ["m1", "m2"]

    def test_no_duplicates(self, tmp_companies):
        cid = create_company(name="Test")
        attach_mission(cid, "m1")
        result = attach_mission(cid, "m1")
        assert result["mission_ids"].count("m1") == 1

    def test_nonexistent_company_raises(self, tmp_companies):
        with pytest.raises(ValueError, match="Company not found"):
            attach_mission("nope", "m1")


class TestFocusedMission:
    def test_set_focused(self, tmp_companies):
        cid = create_company(name="Test")
        attach_mission(cid, "m1")
        result = set_focused_mission(cid, "m1")
        assert result["focused_mission_id"] == "m1"

    def test_get_focused(self, tmp_companies):
        cid = create_company(name="Test")
        attach_mission(cid, "m1")
        set_focused_mission(cid, "m1")
        assert get_focused_mission_id(cid) == "m1"

    def test_unattached_mission_raises(self, tmp_companies):
        cid = create_company(name="Test")
        with pytest.raises(ValueError, match="not attached"):
            set_focused_mission(cid, "m1")

    def test_nonexistent_company(self, tmp_companies):
        assert get_focused_mission_id("nope") is None

    def test_switch_focused(self, tmp_companies):
        cid = create_company(name="Test")
        attach_mission(cid, "m1")
        attach_mission(cid, "m2")
        set_focused_mission(cid, "m1")
        assert get_focused_mission_id(cid) == "m1"
        set_focused_mission(cid, "m2")
        assert get_focused_mission_id(cid) == "m2"


# -- Context paths -----------------------------------------------------------

class TestContextPaths:
    def test_company_context_path(self, tmp_companies):
        cid = create_company(name="Test")
        path = get_company_context_path(cid)
        assert "company_context.md" in str(path)

    def test_mission_context_path(self, tmp_companies):
        cid = create_company(name="Test")
        path = get_mission_context_path(cid, "m1")
        assert "mission_context.md" in str(path)
        assert "m1" in str(path)

    def test_ensure_mission_context(self, tmp_companies):
        cid = create_company(name="Test")
        path = ensure_mission_context(cid, "m1", goal="Build the thing")
        assert path.exists()
        content = path.read_text()
        assert "Build the thing" in content

    def test_ensure_idempotent(self, tmp_companies):
        cid = create_company(name="Test")
        path1 = ensure_mission_context(cid, "m1", goal="First")
        path1.write_text("Custom content", encoding="utf-8")
        path2 = ensure_mission_context(cid, "m1", goal="Second")
        assert path2.read_text() == "Custom content"


# -- Company Mapping ---------------------------------------------------------

class TestMapping:
    def test_create_mapping(self, tmp_companies):
        cid = create_company(name="Test")
        m = create_mapping("frontend", "chan-123", cid)
        assert m["source"] == "frontend"
        assert m["external_id"] == "chan-123"
        assert m["company_id"] == cid

    def test_lookup_by_external(self, tmp_companies):
        cid = create_company(name="Test")
        create_mapping("frontend", "chan-123", cid)
        assert get_company_id_by_external("frontend", "chan-123") == cid

    def test_lookup_by_company(self, tmp_companies):
        cid = create_company(name="Test")
        create_mapping("frontend", "chan-123", cid)
        assert get_external_id_by_company(cid, "frontend") == "chan-123"

    def test_lookup_nonexistent(self, tmp_companies):
        assert get_company_id_by_external("frontend", "nope") is None

    def test_duplicate_raises(self, tmp_companies):
        cid = create_company(name="Test")
        create_mapping("frontend", "chan-123", cid)
        with pytest.raises(ValueError, match="already exists"):
            create_mapping("frontend", "chan-123", cid)

    def test_different_sources_ok(self, tmp_companies):
        cid = create_company(name="Test")
        create_mapping("frontend", "chan-123", cid)
        create_mapping("telegram", "chat-456", cid)
        assert len(list_mappings()) == 2

    def test_delete_mapping(self, tmp_companies):
        cid = create_company(name="Test")
        create_mapping("frontend", "chan-123", cid)
        assert delete_mapping("frontend", "chan-123") is True
        assert get_company_id_by_external("frontend", "chan-123") is None

    def test_delete_nonexistent(self, tmp_companies):
        assert delete_mapping("frontend", "nope") is False

    def test_empty_source_raises(self, tmp_companies):
        with pytest.raises(ValueError, match="source must be non-empty"):
            create_mapping("", "chan-123", "some-id")

    def test_empty_external_id_raises(self, tmp_companies):
        with pytest.raises(ValueError, match="external_id must be non-empty"):
            create_mapping("frontend", "", "some-id")


# -- CLI fallback name -------------------------------------------------------

# CLI fallback name tests removed (jb_cli.py was removed)
