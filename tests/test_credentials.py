"""Tests for runtime.jb_credentials — credential store."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from runtime.jb_credentials import CredentialStore, SERVICE_CATALOG


@pytest.fixture()
def cred_dir(tmp_path: Path):
    """Create a temp credential directory."""
    d = tmp_path / "credentials"
    d.mkdir()
    return d


@pytest.fixture()
def store(cred_dir: Path):
    """CredentialStore backed by temp directory."""
    return CredentialStore(cred_dir=cred_dir)


def _write_cred(cred_dir: Path, service_id: str, data: dict):
    (cred_dir / f"{service_id}.json").write_text(json.dumps(data), encoding="utf-8")


# ── get ───────────────────────────────────────────────────────────────────

class TestGet:
    def test_existing_file(self, store, cred_dir):
        _write_cred(cred_dir, "gmail", {"access_token": "tok123", "refresh_token": "ref456"})
        result = store.get("gmail")
        assert result is not None
        assert result["access_token"] == "tok123"
        assert result["refresh_token"] == "ref456"

    def test_missing_file(self, store):
        assert store.get("nonexistent") is None

    def test_corrupt_json(self, store, cred_dir):
        (cred_dir / "broken.json").write_text("{bad json", encoding="utf-8")
        assert store.get("broken") is None


# ── is_connected ──────────────────────────────────────────────────────────

class TestIsConnected:
    def test_connected(self, store, cred_dir):
        _write_cred(cred_dir, "github", {"token": "ghp_abc"})
        assert store.is_connected("github") is True

    def test_not_connected(self, store):
        assert store.is_connected("github") is False


# ── list_connected ────────────────────────────────────────────────────────

class TestListConnected:
    def test_empty_dir(self, store):
        assert store.list_connected() == []

    def test_multiple(self, store, cred_dir):
        _write_cred(cred_dir, "gmail", {"token": "a"})
        _write_cred(cred_dir, "slack", {"token": "b"})
        connected = store.list_connected()
        assert set(connected) == {"gmail", "slack"}

    def test_nonexistent_dir(self, tmp_path):
        s = CredentialStore(cred_dir=tmp_path / "nope")
        assert s.list_connected() == []


# ── list_all ──────────────────────────────────────────────────────────────

class TestListAll:
    def test_all_disconnected(self, store):
        result = store.list_all()
        assert len(result) == len(SERVICE_CATALOG)
        for item in result:
            assert item["connected"] is False
            assert "id" in item
            assert "name" in item

    def test_marks_connected(self, store, cred_dir):
        _write_cred(cred_dir, "gmail", {"token": "x"})
        result = store.list_all()
        gmail = [r for r in result if r["id"] == "gmail"][0]
        assert gmail["connected"] is True
        notion = [r for r in result if r["id"] == "notion"][0]
        assert notion["connected"] is False

    def test_unknown_service_included(self, store, cred_dir):
        _write_cred(cred_dir, "custom_svc", {"key": "val"})
        result = store.list_all()
        custom = [r for r in result if r["id"] == "custom_svc"]
        assert len(custom) == 1
        assert custom[0]["connected"] is True
        assert custom[0]["type"] == "unknown"
        assert custom[0]["category"] == "other"
        assert custom[0]["name"] == "Custom Svc"


# ── refresh_google_token ─────────────────────────────────────────────────

class TestRefreshGoogleToken:
    def test_no_creds(self, store):
        assert store.refresh_google_token("gmail") is None

    def test_no_refresh_token(self, store, cred_dir):
        _write_cred(cred_dir, "gmail", {"access_token": "old"})
        assert store.refresh_google_token("gmail") is None

    def test_successful_refresh(self, store, cred_dir):
        _write_cred(cred_dir, "gmail", {
            "access_token": "old_tok",
            "refresh_token": "ref_tok",
        })
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "access_token": "new_tok",
            "expires_in": 3600,
        }
        with patch("httpx.post", return_value=mock_resp) as mock_post:
            result = store.refresh_google_token("gmail")

        assert result == "new_tok"
        mock_post.assert_called_once()

        # Verify file was updated
        updated = json.loads((cred_dir / "gmail.json").read_text())
        assert updated["access_token"] == "new_tok"
        assert updated["expires_in"] == 3600
        assert updated["refresh_token"] == "ref_tok"

    def test_failed_refresh(self, store, cred_dir):
        _write_cred(cred_dir, "gmail", {
            "access_token": "old",
            "refresh_token": "ref",
        })
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        with patch("httpx.post", return_value=mock_resp):
            assert store.refresh_google_token("gmail") is None

    def test_network_error(self, store, cred_dir):
        _write_cred(cred_dir, "gmail", {
            "access_token": "old",
            "refresh_token": "ref",
        })
        with patch("httpx.post", side_effect=Exception("timeout")):
            assert store.refresh_google_token("gmail") is None
