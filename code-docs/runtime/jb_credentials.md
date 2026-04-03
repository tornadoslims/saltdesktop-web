# runtime/jb_credentials.py

**Path:** `runtime/jb_credentials.py`
**Purpose:** Credential store that reads credentials written by the Salt Desktop Swift app. Read-only with one exception: refreshed OAuth tokens are written back.

## Constants

- `CRED_DIR`: `~/.missionos/credentials/` -- where the Swift app writes credential JSON files
- `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`: Read from env vars for token refresh
- `SERVICE_CATALOG`: Dict of 20 known service IDs with name, type (oauth/api_key/connection_string/key_pair), and category

## Supported Services (20)

gmail, google_calendar, google_drive, github, salesforce, notion, linear, jira, discord, telegram, openai, stripe, aws, snowflake, mysql, postgres, oracle, redis, gcp, slack

## Classes

### `CredentialStore`

**Constructor:** `__init__(self, cred_dir: Path = CRED_DIR)`

**Methods:**

- **`get(service_id) -> dict | None`**: Reads `{service_id}.json` from the credential directory. Returns parsed JSON dict or `None` if file doesn't exist or is invalid.
- **`is_connected(service_id) -> bool`**: Returns `True` if credentials exist for the service.
- **`list_connected() -> list[str]`**: Returns all service IDs that have `.json` files in the credential directory.
- **`list_all() -> list[dict]`**: Lists all known services (from catalog + any extra connected ones) with connection status. Each entry: `{id, name, type, category, connected}`.
- **`refresh_google_token(service_id) -> str | None`**: POSTs to `https://oauth2.googleapis.com/token` with the refresh_token. On success, updates the JSON file with the new access_token and returns it. This is the ONE exception to the read-only rule.

**Module singleton:** `credentials = CredentialStore()`

## Connector Metadata (SQLite)

### `register_connector(service_type, label, credential_file, account_id=None, scope=None, metadata=None) -> str`
Registers a connector record in the `connectors` database table. Returns connector_id.

### `list_connectors_with_metadata() -> list[dict]`
Lists all connectors from SQLite, enriched with `file_exists` check against the credential directory.

### `get_connector(connector_id) -> dict | None`
Fetches a single connector by ID.

### `touch_connector(connector_id) -> None`
Updates `last_used_at` timestamp for a connector.
