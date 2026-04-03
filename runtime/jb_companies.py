# runtime/jb_companies.py

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from runtime.jb_common import utc_now_iso, DATA_DIR, JsonStore
from runtime.jb_database import get_db, init_db, _json_dumps, _json_loads

COMPANIES_FILE = DATA_DIR / "jb_companies.json"
_store = JsonStore(COMPANIES_FILE)

VALID_COMPANY_STATUSES = {"active", "archived"}



def _company_dir(company_id: str) -> Path:
    return DATA_DIR / "companies" / company_id


def _ensure_company_dirs(company_id: str) -> None:
    cdir = _company_dir(company_id)
    cdir.mkdir(parents=True, exist_ok=True)
    (cdir / "missions").mkdir(exist_ok=True)

    context_file = cdir / "company_context.md"
    if not context_file.exists():
        context_file.write_text(
            "# Company Context\n",
            encoding="utf-8",
        )


def _row_to_company(row) -> dict[str, Any]:
    """Convert a sqlite3.Row to a company dict."""
    d = dict(row)
    d["mission_ids"] = _json_loads(d.get("mission_ids")) or []
    return d


def _validate_company(company: dict[str, Any]) -> None:
    """Validate company fields, raising ValueError on problems."""
    status = company.get("status", "active")
    if status not in VALID_COMPANY_STATUSES:
        raise ValueError(
            f"Invalid company status '{status}'. "
            f"Valid statuses: {sorted(VALID_COMPANY_STATUSES)}"
        )

    name = (company.get("name") or "").strip()
    if not name:
        raise ValueError("Company name must be a non-empty string")

    mission_ids = company.get("mission_ids")
    if mission_ids is not None and not isinstance(mission_ids, list):
        raise ValueError("mission_ids must be a list")


def _normalize_company(company: dict[str, Any]) -> dict[str, Any]:
    """Normalize a company dict (for backward compat with code that calls this)."""
    now = utc_now_iso()
    status = company.get("status", "active")

    if status not in VALID_COMPANY_STATUSES:
        raise ValueError(
            f"Invalid company status '{status}'. "
            f"Valid statuses: {sorted(VALID_COMPANY_STATUSES)}"
        )

    name = (company.get("name") or "").strip()
    if not name:
        raise ValueError("Company name must be a non-empty string")

    company_id = company.get("company_id") or str(uuid4())

    mission_ids = company.get("mission_ids")
    if mission_ids is None:
        mission_ids = []
    if not isinstance(mission_ids, list):
        raise ValueError("mission_ids must be a list")

    return {
        "company_id": company_id,
        "name": name,
        "description": company.get("description"),
        "status": status,
        "focused_mission_id": company.get("focused_mission_id"),
        "mission_ids": list(mission_ids),
        "company_context_path": str(_company_dir(company_id) / "company_context.md"),
        "created_at": company.get("created_at") or now,
        "updated_at": company.get("updated_at") or now,
    }


# -- CRUD -------------------------------------------------------------------

def list_companies() -> list[dict[str, Any]]:
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM companies").fetchall()
    return [_row_to_company(r) for r in rows]


def get_company(company_id: str) -> dict[str, Any] | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM companies WHERE company_id = ?", (company_id,)
        ).fetchone()
    if row is None:
        return None
    return _row_to_company(row)


def create_company(
    name: str,
    status: str = "active",
    description: str | None = None,
) -> str:
    _validate_company({"name": name, "status": status})
    name = name.strip()

    company_id = str(uuid4())
    now = utc_now_iso()
    context_path = str(_company_dir(company_id) / "company_context.md")

    _ensure_company_dirs(company_id)

    with get_db() as conn:
        conn.execute(
            """INSERT INTO companies
               (company_id, name, description, status, focused_mission_id,
                mission_ids, company_context_path, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (company_id, name, description, status, None,
             "[]", context_path, now, now),
        )
    return company_id


def _update_company(company_id: str, updates: dict[str, Any]) -> dict[str, Any]:
    company = get_company(company_id)
    if company is None:
        raise ValueError(f"Company not found: {company_id}")

    merged = {**company, **updates}
    # Validate the merged result
    _validate_company(merged)

    name = (merged.get("name") or "").strip()
    now = utc_now_iso()

    with get_db() as conn:
        conn.execute(
            """UPDATE companies SET
               name = ?, description = ?, status = ?,
               focused_mission_id = ?, mission_ids = ?,
               company_context_path = ?, updated_at = ?
               WHERE company_id = ?""",
            (name, merged.get("description"), merged.get("status", "active"),
             merged.get("focused_mission_id"),
             _json_dumps(merged.get("mission_ids", [])),
             merged.get("company_context_path", str(_company_dir(company_id) / "company_context.md")),
             now, company_id),
        )

    result = get_company(company_id)
    return result


def update_company_name(company_id: str, name: str) -> dict[str, Any]:
    return _update_company(company_id, {"name": name})


def update_company_description(company_id: str, description: str) -> dict[str, Any]:
    """Update company description. Returns updated company."""
    return _update_company(company_id, {"description": description})


def archive_company(company_id: str) -> dict[str, Any]:
    return _update_company(company_id, {"status": "archived"})


# -- Mission management -----------------------------------------------------

def attach_mission(company_id: str, mission_id: str) -> dict[str, Any]:
    company = get_company(company_id)
    if company is None:
        raise ValueError(f"Company not found: {company_id}")

    mission_ids = list(company.get("mission_ids", []))
    if mission_id not in mission_ids:
        mission_ids.append(mission_id)

    return _update_company(company_id, {"mission_ids": mission_ids})


def set_focused_mission(company_id: str, mission_id: str) -> dict[str, Any]:
    company = get_company(company_id)
    if company is None:
        raise ValueError(f"Company not found: {company_id}")

    if mission_id not in company.get("mission_ids", []):
        raise ValueError(
            f"Mission {mission_id} is not attached to company {company_id}"
        )

    return _update_company(company_id, {"focused_mission_id": mission_id})


def get_focused_mission_id(company_id: str) -> str | None:
    company = get_company(company_id)
    if company is None:
        return None
    return company.get("focused_mission_id")


# -- Context paths -----------------------------------------------------------

def get_company_context_path(company_id: str) -> Path:
    return _company_dir(company_id) / "company_context.md"


def get_mission_context_path(company_id: str, mission_id: str) -> Path:
    return _company_dir(company_id) / "missions" / mission_id / "mission_context.md"


def ensure_mission_context(company_id: str, mission_id: str, goal: str = "") -> Path:
    mdir = _company_dir(company_id) / "missions" / mission_id
    mdir.mkdir(parents=True, exist_ok=True)

    context_file = mdir / "mission_context.md"
    if not context_file.exists():
        context_file.write_text(
            f"# Mission Context\n\n## Goal: {goal}\n",
            encoding="utf-8",
        )
    return context_file
