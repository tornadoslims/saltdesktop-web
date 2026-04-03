"""Read file tool."""

from __future__ import annotations

import base64
import subprocess
from pathlib import Path

from salt_agent.tools.base import Tool, ToolDefinition, ToolParam

# Image file extensions
_IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"})

# Extension to MIME media type
_IMAGE_MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
}


class ReadTool(Tool):
    """Read a file from the filesystem with optional offset and limit."""

    def __init__(self, working_directory: str = ".") -> None:
        self.working_directory = working_directory
        self.files_read: set[str] = set()
        # Pending images for multimodal injection
        self._pending_images: list[dict] = []  # [{path, base64_data, media_type}]

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="read",
            description=(
                "Read a file from the filesystem. Returns file content with line numbers. "
                "Also supports images (.png, .jpg, .gif, .webp, .bmp) and PDFs (.pdf)."
            ),
            params=[
                ToolParam("file_path", "string", "Absolute path to the file to read."),
                ToolParam("offset", "integer", "Line number to start reading from (0-based).", required=False),
                ToolParam("limit", "integer", "Maximum number of lines to read.", required=False),
            ],
        )

    def _read_image(self, path: Path, file_path: str) -> str:
        """Read an image file and return a description. Stores base64 for multimodal."""
        try:
            raw = path.read_bytes()
            b64 = base64.b64encode(raw).decode("ascii")
            ext = path.suffix.lower()
            media_type = _IMAGE_MEDIA_TYPES.get(ext, "image/png")
            size = len(raw)
            self._pending_images.append({
                "path": str(path),
                "base64_data": b64,
                "media_type": media_type,
            })
            # Track as read
            resolved = str(path.resolve())
            self.files_read.add(resolved)
            return f"[Image file: {file_path}, {size} bytes, base64 encoded]"
        except Exception as e:
            return f"Error reading image: {e}"

    def _read_pdf(self, path: Path, file_path: str) -> str:
        """Read a PDF file, extracting text via pdftotext or raw read."""
        resolved = str(path.resolve())
        self.files_read.add(resolved)
        # Try pdftotext first
        try:
            result = subprocess.run(
                ["pdftotext", str(path), "-"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if result.returncode == 0 and result.stdout.strip():
                text = result.stdout
                lines = text.splitlines()
                header = f"PDF: {file_path} ({len(lines)} lines extracted via pdftotext)"
                numbered = [f"{i+1}\t{line}" for i, line in enumerate(lines)]
                return header + "\n" + "\n".join(numbered)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        # Fallback: read raw text (works for text-based PDFs)
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
            lines = text.splitlines()
            header = f"PDF: {file_path} ({len(lines)} lines, raw text extraction)"
            numbered = [f"{i+1}\t{line}" for i, line in enumerate(lines)]
            return header + "\n" + "\n".join(numbered)
        except Exception as e:
            return f"Error reading PDF: {e}"

    def execute(self, **kwargs) -> str:
        file_path: str = kwargs["file_path"]
        offset: int = kwargs.get("offset", 0) or 0
        limit: int | None = kwargs.get("limit")

        path = Path(file_path)
        if not path.is_absolute():
            path = Path(self.working_directory) / path
        if not path.exists():
            return f"Error: File not found: {file_path}"
        if not path.is_file():
            return f"Error: Not a file: {file_path}"

        # Check for image files
        ext = path.suffix.lower()
        if ext in _IMAGE_EXTENSIONS:
            return self._read_image(path, file_path)

        # Check for PDF files
        if ext == ".pdf":
            return self._read_pdf(path, file_path)

        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return f"Error reading file: {e}"

        lines = text.splitlines()
        total = len(lines)

        if offset > 0:
            lines = lines[offset:]
        if limit is not None and limit > 0:
            lines = lines[:limit]

        # Track that this file has been read
        resolved = str(path.resolve())
        self.files_read.add(resolved)

        # Format with line numbers (1-based display)
        numbered = []
        for i, line in enumerate(lines, start=offset + 1):
            numbered.append(f"{i}\t{line}")

        result = "\n".join(numbered)
        if not result:
            result = "(empty file)"

        header = f"File: {file_path} ({total} lines total)"
        if offset > 0 or limit is not None:
            shown = len(numbered)
            header += f", showing lines {offset + 1}-{offset + shown}"
        return header + "\n" + result
