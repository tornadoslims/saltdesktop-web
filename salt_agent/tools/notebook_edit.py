"""NotebookEdit tool -- edit Jupyter notebook cells (.ipynb files)."""

from __future__ import annotations

import json
import os
from pathlib import Path

from salt_agent.tools.base import Tool, ToolDefinition, ToolParam


class NotebookEditTool(Tool):
    """Edit, insert, or delete cells in Jupyter notebooks."""

    def __init__(self, read_tool=None, working_directory: str | None = None) -> None:
        self._read_tool = read_tool
        self._wd = working_directory

    def _resolve(self, path: str) -> str:
        if os.path.isabs(path):
            return path
        base = self._wd or os.getcwd()
        return str(Path(base) / path)

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="notebook_edit",
            description=(
                "Edit Jupyter notebook cells. Supports replace, insert, and delete operations. "
                "You must Read the notebook first before editing. "
                "Use cell_id (the cell's id field) or cell index (e.g. 'cell-0', 'cell-1') "
                "to identify which cell to modify."
            ),
            params=[
                ToolParam("notebook_path", "string", "Absolute path to the .ipynb file"),
                ToolParam("new_source", "string", "New source content for the cell"),
                ToolParam(
                    "cell_id", "string",
                    "Cell ID or index (e.g. 'cell-0'). For insert mode, new cell goes after this cell.",
                    required=False,
                ),
                ToolParam(
                    "cell_type", "string",
                    "Cell type: 'code' or 'markdown'. Required for insert mode.",
                    required=False,
                    enum=["code", "markdown"],
                ),
                ToolParam(
                    "edit_mode", "string",
                    "Edit mode: replace (default), insert, or delete.",
                    required=False,
                    enum=["replace", "insert", "delete"],
                ),
            ],
        )

    @staticmethod
    def _parse_cell_index(cell_id: str) -> int | None:
        """Parse 'cell-N' format to integer index."""
        if cell_id.startswith("cell-"):
            try:
                return int(cell_id[5:])
            except ValueError:
                return None
        return None

    def _find_cell_index(self, cells: list, cell_id: str) -> int | None:
        """Find cell index by ID or cell-N format."""
        # First try exact ID match
        for i, cell in enumerate(cells):
            if cell.get("id") == cell_id:
                return i
        # Then try cell-N format
        idx = self._parse_cell_index(cell_id)
        if idx is not None and 0 <= idx < len(cells):
            return idx
        return None

    def execute(self, **kwargs) -> str:
        notebook_path = self._resolve(kwargs.get("notebook_path", ""))
        new_source = kwargs.get("new_source", "")
        cell_id = kwargs.get("cell_id")
        cell_type = kwargs.get("cell_type")
        edit_mode = kwargs.get("edit_mode", "replace")

        # Validate .ipynb extension
        if not notebook_path.endswith(".ipynb"):
            return "Error: File must be a Jupyter notebook (.ipynb). Use the edit tool for other files."

        # Check read-before-edit
        if self._read_tool and hasattr(self._read_tool, "files_read"):
            resolved = str(Path(notebook_path).resolve())
            if resolved not in self._read_tool.files_read:
                return "Error: Notebook has not been read yet. Read it first before editing."

        # Validate inputs
        if edit_mode == "insert" and not cell_type:
            return "Error: cell_type is required when using edit_mode=insert."
        if edit_mode in ("replace", "delete") and not cell_id:
            return "Error: cell_id is required for replace and delete modes."

        # Read notebook
        try:
            with open(notebook_path, "r", encoding="utf-8") as f:
                notebook = json.load(f)
        except FileNotFoundError:
            return f"Error: Notebook not found: {notebook_path}"
        except json.JSONDecodeError:
            return "Error: Notebook is not valid JSON."

        cells = notebook.get("cells", [])

        if edit_mode == "delete":
            idx = self._find_cell_index(cells, cell_id)
            if idx is None:
                return f"Error: Cell '{cell_id}' not found in notebook."
            cells.pop(idx)
            notebook["cells"] = cells
            self._write_notebook(notebook_path, notebook)
            return f"Deleted cell {cell_id}."

        elif edit_mode == "insert":
            # Determine insertion point
            if cell_id:
                idx = self._find_cell_index(cells, cell_id)
                if idx is None:
                    return f"Error: Cell '{cell_id}' not found in notebook."
                insert_at = idx + 1  # Insert after the specified cell
            else:
                insert_at = 0  # Insert at beginning

            new_cell = self._make_cell(notebook, new_source, cell_type or "code")
            cells.insert(insert_at, new_cell)
            notebook["cells"] = cells
            self._write_notebook(notebook_path, notebook)
            return f"Inserted {cell_type or 'code'} cell at position {insert_at}."

        else:  # replace
            idx = self._find_cell_index(cells, cell_id)
            if idx is None:
                return f"Error: Cell '{cell_id}' not found in notebook."
            target = cells[idx]
            target["source"] = new_source
            if target.get("cell_type") == "code":
                target["execution_count"] = None
                target["outputs"] = []
            if cell_type and cell_type != target.get("cell_type"):
                target["cell_type"] = cell_type
            self._write_notebook(notebook_path, notebook)
            return f"Updated cell {cell_id} with new source ({len(new_source)} chars)."

    @staticmethod
    def _make_cell(notebook: dict, source: str, cell_type: str) -> dict:
        """Create a new notebook cell with appropriate metadata."""
        import random
        import string

        cell: dict = {
            "cell_type": cell_type,
            "source": source,
            "metadata": {},
        }

        # Add id for nbformat >= 4.5
        nbformat = notebook.get("nbformat", 4)
        nbformat_minor = notebook.get("nbformat_minor", 0)
        if nbformat > 4 or (nbformat == 4 and nbformat_minor >= 5):
            cell["id"] = "".join(random.choices(string.ascii_lowercase + string.digits, k=12))

        if cell_type == "code":
            cell["execution_count"] = None
            cell["outputs"] = []

        return cell

    @staticmethod
    def _write_notebook(path: str, notebook: dict) -> None:
        """Write notebook back to disk with standard formatting."""
        with open(path, "w", encoding="utf-8") as f:
            json.dump(notebook, f, indent=1, ensure_ascii=False)
            f.write("\n")
