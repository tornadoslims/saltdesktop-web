# runtime/jb_company_mapping.py

**Path:** `runtime/jb_company_mapping.py`
**Purpose:** Maps external workspace IDs to JBCP company IDs. Generic mapping layer -- any source (frontend, webchat, Discord, etc.) can be mapped.

## Functions

### `list_mappings() -> list[dict]`
Returns all mappings from the `company_mappings` table.

### `create_mapping(source, external_id, company_id) -> dict`
Creates a new mapping. Validates all fields are non-empty. Checks for duplicates (unique constraint on source + external_id). Returns the mapping dict.

### `get_company_id_by_external(source, external_id) -> str | None`
Looks up a company_id from a source and external_id. Returns `None` if no mapping exists.

### `get_external_id_by_company(company_id, source=None) -> str | None`
Reverse lookup: finds the external_id for a company. Optionally filters by source.

### `delete_mapping(source, external_id) -> bool`
Deletes a mapping. Returns `True` if a row was deleted.
