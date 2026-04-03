---
name: commit
description: Create a git commit with a well-crafted message
user-invocable: true
---
# Git Commit

Create a git commit following these steps:

1. Run `git status` to see all changed files
2. Run `git diff` to see what changed (both staged and unstaged)
3. Run `git log --oneline -5` to see recent commit message style
4. Draft a concise commit message:
   - Use imperative mood ("Add feature" not "Added feature")
   - First line under 72 characters
   - Focus on the *why*, not the *what*
5. Stage relevant files selectively (not `git add .` -- be intentional)
6. Create the commit
7. Run `git status` to verify success
