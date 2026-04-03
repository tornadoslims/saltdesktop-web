# runtime/jb_company_mapping.py
#
# Maps external workspace IDs to JBCP company IDs.
# Generic mapping layer -- any source (frontend, webchat, etc.) can be mapped.

from __future__ import annotations

from typing import Any
from uuid import uuid4

from runtime.jb_common import utc_now_iso, DATA_DIR, JsonStore
from runtime.jb_database import get_db, init_db

MAPPINGS_FILE = DATA_DIR / "jb_company_mappings.json"
_store = JsonStore(MAPPINGS_FILE)



def _row_to_mapping(row) -> dict[str, Any]:
    """Convert a sqlite3.Row to a mapping dict."""
    d = dict(row)
    # Remove mapping_id from output to match original API shape
    # (original had no mapping_id, just source/external_id/company_id/created_at)
    d.pop("mapping_id", None)
    return d


def _normalize_mapping(m: dict[str, Any]) -> dict[str, Any]:
    source = (m.get("source") or "").strip()
    external_id = (m.get("external_id") or "").strip()
    company_id = (m.get("company_id") or "").strip()

    if not source:
        raise ValueError("Mapping source must be non-empty")
    if not external_id:
        raise ValueError("Mapping external_id must be non-empty")
    if not company_id:
        raise ValueError("Mapping company_id must be non-empty")

    return {
        "source": source,
        "external_id": external_id,
        "company_id": company_id,
        "created_at": m.get("created_at") or utc_now_iso(),
    }


# -- CRUD -------------------------------------------------------------------

def list_mappings() -> list[dict[str, Any]]:
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM company_mappings").fetchall()
    return [_row_to_mapping(r) for r in rows]


def create_mapping(source: str, external_id: str, company_id: str) -> dict[str, Any]:
    # Validate
    normalized = _normalize_mapping({
        "source": source,
        "external_id": external_id,
        "company_id": company_id,
    })

    mapping_id = str(uuid4())
    now = utc_now_iso()

    with get_db() as conn:
        # Check for duplicate
        existing = conn.execute(
            "SELECT 1 FROM company_mappings WHERE source = ? AND external_id = ?",
            (normalized["source"], normalized["external_id"]),
        ).fetchone()
        if existing:
            raise ValueError(
                f"Mapping already exists: {normalized['source']}:{normalized['external_id']} "
                f"-> existing"
            )

        conn.execute(
            """INSERT INTO company_mappings
               (mapping_id, source, external_id, company_id, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (mapping_id, normalized["source"], normalized["external_id"],
             normalized["company_id"], now),
        )

    return {
        "source": normalized["source"],
        "external_id": normalized["external_id"],
        "company_id": normalized["company_id"],
        "created_at": now,
    }


def get_company_id_by_external(source: str, external_id: str) -> str | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT company_id FROM company_mappings WHERE source = ? AND external_id = ?",
            (source, external_id),
        ).fetchone()
    if row is None:
        return None
    return row["company_id"]


def get_external_id_by_company(company_id: str, source: str | None = None) -> str | None:
    with get_db() as conn:
        if source is not None:
            row = conn.execute(
                "SELECT external_id FROM company_mappings WHERE company_id = ? AND source = ?",
                (company_id, source),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT external_id FROM company_mappings WHERE company_id = ?",
                (company_id,),
            ).fetchone()
    if row is None:
        return None
    return row["external_id"]


def delete_mapping(source: str, external_id: str) -> bool:
    with get_db() as conn:
        cursor = conn.execute(
            "DELETE FROM company_mappings WHERE source = ? AND external_id = ?",
            (source, external_id),
        )
    return cursor.rowcount > 0
