# File Tools

## read

Read a file from the filesystem with optional offset and limit.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `file_path` | string | yes | Absolute path to the file to read |
| `offset` | integer | no | Line number to start reading from (0-based) |
| `limit` | integer | no | Maximum number of lines to read |

**Returns:** File content with line numbers (cat -n format).

**Special capabilities:**

- Images (`.png`, `.jpg`, `.gif`, `.webp`, `.bmp`) -- reads as base64 and stores for multimodal injection
- PDFs (`.pdf`) -- extracts text content using `pdftotext`
- Tracks which files have been read (enforced by `edit` and `write`)
- Tracks file modification time at read time for external change detection

**Example result:**
```
     1  import os
     2  import sys
     3
     4  def main():
     5      print("hello")
```

---

## write

Write content to a file. Creates parent directories automatically.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `file_path` | string | yes | Absolute path to the file to write |
| `content` | string | yes | The content to write to the file |

**Constraints:**

- If the file already exists, it **must** have been read first (enforced via the read tool's tracking)
- Creates parent directories if they don't exist

**Returns:** `"Successfully wrote N lines to /path/to/file"`

---

## edit

Perform exact string replacement in a file.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `file_path` | string | yes | Absolute path to the file to edit |
| `old_string` | string | yes | The exact text to find and replace |
| `new_string` | string | yes | The replacement text |
| `replace_all` | boolean | no | Replace all occurrences (default false) |

**Constraints:**

- The file **must** have been read first
- `old_string` must be unique in the file unless `replace_all` is true
- `old_string` and `new_string` must be different

**Returns:** Success message with line count, or error description.

---

## multi_edit

Perform multiple edits on a single file in one operation.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `file_path` | string | yes | Absolute path to the file to edit |
| `edits` | array | yes | Array of `{old_string, new_string}` objects |

**Constraints:**

- Same as `edit` -- file must have been read first
- Each `old_string` must be unique in the file
- Edits are applied in order

---

## glob

Find files matching a glob pattern.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `pattern` | string | yes | The glob pattern (e.g., `**/*.py`, `src/**/*.ts`) |
| `path` | string | no | Directory to search in (defaults to working directory) |

**Returns:** Sorted list of matching file paths, filtered to exclude hidden directories and common noise (`.git`, `__pycache__`, `node_modules`, `.venv`).

---

## grep

Search file contents using regex patterns. Uses ripgrep if available, falls back to grep.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `pattern` | string | yes | Regex pattern to search for |
| `path` | string | no | File or directory to search in |
| `glob` | string | no | Glob pattern to filter files (e.g., `*.py`) |
| `case_insensitive` / `-i` | boolean | no | Case insensitive search |
| `output_mode` | string | no | `files_with_matches` (default), `content`, `count` |
| `context` / `-C` | integer | no | Context lines around matches (content mode) |
| `-A` | integer | no | Lines after each match |
| `-B` | integer | no | Lines before each match |
| `head_limit` | integer | no | Max results (default 250) |
| `offset` | integer | no | Skip first N results |
| `multiline` | boolean | no | Enable multiline matching |
| `type` | string | no | Filter by file type (e.g., `py`, `js`, `ts`) |
| `-n` | boolean | no | Show line numbers (default true in content mode) |

**Returns:** File paths, matching lines with context, or match counts depending on `output_mode`.

---

## list_files

List files in a directory with metadata.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `path` | string | yes | Directory path to list |

**Returns:** File listing with sizes and types.

---

## notebook_edit

Edit Jupyter notebook (`.ipynb`) cells.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `file_path` | string | yes | Path to the `.ipynb` file |
| `cell_index` | integer | yes | Cell index to edit |
| `new_source` | string | yes | New cell source content |

**Constraints:**

- File must have been read first
- Cell index must be valid

**Returns:** Success message with cell details.
