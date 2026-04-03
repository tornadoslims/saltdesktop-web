# runtime/jb_companies.py

**Path:** `runtime/jb_companies.py`
**Purpose:** Company/workspace CRUD. Companies are the top-level organizational unit. Each has missions, a focused mission, and context files on disk.

## Constants

- `VALID_COMPANY_STATUSES`: `{"active", "archived"}`

## CRUD Functions

### `list_companies() -> list[dict]`
Returns all companies from SQLite.

### `get_company(company_id: str) -> dict | None`
Fetches a single company by ID.

### `create_company(name, status="active", description=None) -> str`
Creates a new company with a UUID. Also creates the company directory structure on disk (`data/companies/{id}/` with a `missions/` subdirectory and `company_context.md` file). Returns the new company_id.

### `_update_company(company_id, updates) -> dict`
Merges updates, validates, and writes back. Returns updated company.

### `update_company_name(company_id, name) -> dict`
### `update_company_description(company_id, description) -> dict`
### `archive_company(company_id) -> dict`
Convenience wrappers around `_update_company`.

## Mission Management

### `attach_mission(company_id, mission_id) -> dict`
Appends mission_id to the company's `mission_ids` list.

### `set_focused_mission(company_id, mission_id) -> dict`
Sets the focused mission. Validates the mission is attached to the company.

### `get_focused_mission_id(company_id) -> str | None`
Returns the focused mission ID or `None`.

## Context Paths

### `get_company_context_path(company_id) -> Path`
Returns: `data/companies/{company_id}/company_context.md`

### `get_mission_context_path(company_id, mission_id) -> Path`
Returns: `data/companies/{company_id}/missions/{mission_id}/mission_context.md`

### `ensure_mission_context(company_id, mission_id, goal="") -> Path`
Creates the mission directory and context file if they don't exist. Returns the path to the context file.

## Internal Helpers

- `_company_dir(company_id)`: Returns `DATA_DIR / "companies" / company_id`
- `_ensure_company_dirs(company_id)`: Creates company dir, missions subdir, and initial context file
- `_row_to_company(row)`: Parses `mission_ids` from JSON
- `_validate_company(company)`: Validates name is non-empty and status is valid
