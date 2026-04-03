---
name: pr
description: Create a pull request with a well-structured title and description
user-invocable: true
requires:
  bins: [gh]
---
# Create Pull Request

Follow these steps to create a pull request:

1. Run `git status` to check for uncommitted changes -- commit them first if needed
2. Run `git log --oneline main..HEAD` (or the appropriate base branch) to see all commits
3. Run `git diff main...HEAD` to understand the full scope of changes
4. Check if the branch is pushed: `git rev-parse --abbrev-ref --symbolic-full-name @{u}` -- push with `-u` if needed
5. Draft a PR title (under 70 characters) and description:
   - Title: concise summary in imperative mood
   - Body: ## Summary section with 1-3 bullet points, ## Test plan with checklist
6. Create the PR: `gh pr create --title "..." --body "..."`
7. Return the PR URL to the user
