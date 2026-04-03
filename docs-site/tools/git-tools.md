# Git Tools

Native git tools for common operations. These are lighter-weight than running git via bash and provide structured output.

## git_status

Get current git status including branch, changed files, staged/unstaged changes, untracked files, and ahead/behind counts.

**Parameters:** None

**Returns:** Formatted status including:
- Current branch name
- Changed files (short format)
- Ahead/behind remote tracking branch

**Example result:**
```
Branch: feature/api-refactor

Changed files:
 M src/api.py
 M tests/test_api.py
?? src/new_module.py

Ahead of origin/feature/api-refactor by 2 commits
```

---

## git_diff

Show git diff output.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `staged` | boolean | no | Show staged changes only (default false) |
| `file` | string | no | Diff a specific file |

**Returns:** Standard git diff output.

---

## git_commit

Create a git commit.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `message` | string | yes | Commit message |
| `files` | array | no | Specific files to stage (default: all modified) |

**Returns:** Commit confirmation with hash and summary.

---

## Configuration

Git tools are enabled by default. To disable:

```python
agent = create_agent(include_git_tools=False)
```

## Notes

- All git commands run with a 15-second timeout
- The working directory is used as the git repository root
- `_is_git_repo()` checks that the working directory is inside a git repository before any operation
- Errors (git not installed, not a repo, timeout) are returned as descriptive strings rather than raising exceptions
