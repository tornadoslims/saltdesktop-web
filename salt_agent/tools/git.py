"""Git tools -- native git status, diff, and commit tools."""

from __future__ import annotations

import subprocess
from pathlib import Path

from salt_agent.tools.base import Tool, ToolDefinition, ToolParam


def _run_git(args: list[str], cwd: str, timeout: int = 15) -> tuple[str, bool]:
    """Run a git command and return (output, success)."""
    try:
        result = subprocess.run(
            ["git"] + args,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
        )
        output = result.stdout
        if result.stderr:
            output = (output + "\n" + result.stderr).strip()
        return output or "(no output)", result.returncode == 0
    except FileNotFoundError:
        return "Error: git is not installed or not in PATH", False
    except subprocess.TimeoutExpired:
        return f"Error: git command timed out after {timeout}s", False
    except Exception as e:
        return f"Error: {e}", False


def _is_git_repo(cwd: str) -> bool:
    """Check if the working directory is inside a git repository."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=cwd,
        )
        return result.returncode == 0
    except Exception:
        return False


class GitStatusTool(Tool):
    """Get current git status: branch, changed files, ahead/behind."""

    def __init__(self, working_directory: str = ".") -> None:
        self.working_directory = working_directory

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="git_status",
            description=(
                "Get current git status including branch name, changed files, "
                "staged/unstaged changes, and untracked files."
            ),
            params=[],
        )

    def execute(self, **kwargs) -> str:
        cwd = self.working_directory
        if not _is_git_repo(cwd):
            return "Error: not a git repository (or any parent up to mount point)"

        parts: list[str] = []

        # Branch
        branch_out, ok = _run_git(["branch", "--show-current"], cwd)
        if ok:
            parts.append(f"Branch: {branch_out.strip()}")

        # Status (porcelain for machine-readable, then also human-readable)
        status_out, ok = _run_git(["status", "--short"], cwd)
        if ok:
            if status_out.strip():
                parts.append(f"\nChanged files:\n{status_out.strip()}")
            else:
                parts.append("\nWorking tree clean.")

        # Ahead/behind
        tracking_out, ok = _run_git(
            ["rev-list", "--left-right", "--count", "HEAD...@{upstream}"], cwd
        )
        if ok:
            counts = tracking_out.strip().split()
            if len(counts) == 2:
                ahead, behind = counts
                if ahead != "0" or behind != "0":
                    parts.append(f"\nAhead: {ahead}, Behind: {behind}")

        return "\n".join(parts)


class GitDiffTool(Tool):
    """Show git diff for staged or unstaged changes."""

    def __init__(self, working_directory: str = ".") -> None:
        self.working_directory = working_directory

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="git_diff",
            description="Show git diff. Use staged=true for staged changes, or file_path for a specific file.",
            params=[
                ToolParam("staged", "boolean", "Show staged changes instead of unstaged.", required=False),
                ToolParam("file_path", "string", "Specific file to diff.", required=False),
            ],
        )

    def execute(self, **kwargs) -> str:
        cwd = self.working_directory
        if not _is_git_repo(cwd):
            return "Error: not a git repository (or any parent up to mount point)"

        staged = kwargs.get("staged", False)
        file_path = kwargs.get("file_path", "")

        cmd = ["diff"]
        if staged:
            cmd.append("--staged")
        if file_path:
            cmd.extend(["--", file_path])

        output, ok = _run_git(cmd, cwd)
        if not ok:
            return output
        if not output.strip() or output.strip() == "(no output)":
            which = "staged" if staged else "unstaged"
            return f"No {which} changes."
        return output


class GitCommitTool(Tool):
    """Create a git commit with a message."""

    def __init__(self, working_directory: str = ".") -> None:
        self.working_directory = working_directory

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="git_commit",
            description=(
                "Stage all changes and create a git commit. "
                "Provide a clear, descriptive commit message."
            ),
            params=[
                ToolParam("message", "string", "The commit message."),
                ToolParam(
                    "files", "array", "Specific files to stage (default: all changes).",
                    required=False,
                    items={"type": "string"},
                ),
            ],
        )

    def execute(self, **kwargs) -> str:
        cwd = self.working_directory
        if not _is_git_repo(cwd):
            return "Error: not a git repository (or any parent up to mount point)"

        message = kwargs.get("message", "")
        if not message:
            return "Error: commit message is required"

        files = kwargs.get("files", None)

        # Stage files
        if files:
            for f in files:
                out, ok = _run_git(["add", f], cwd)
                if not ok:
                    return f"Error staging {f}: {out}"
        else:
            out, ok = _run_git(["add", "-A"], cwd)
            if not ok:
                return f"Error staging changes: {out}"

        # Check if there is anything staged
        status_out, _ = _run_git(["diff", "--staged", "--stat"], cwd)
        if not status_out.strip() or status_out.strip() == "(no output)":
            return "Nothing to commit (no staged changes)."

        # Commit
        out, ok = _run_git(["commit", "-m", message], cwd)
        if not ok:
            return f"Commit failed: {out}"

        return out
