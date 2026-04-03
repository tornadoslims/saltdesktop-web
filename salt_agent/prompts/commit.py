"""Git commit message generation prompt for SaltAgent.

Adapted from Claude Code's quick git commit prompt.
"""

COMMIT_PROMPT = """Based on the current changes, create a single git commit.

## Git Safety Protocol

- NEVER update the git config.
- NEVER skip hooks (--no-verify) unless the user explicitly requests it.
- ALWAYS create NEW commits. NEVER use git commit --amend unless the user explicitly requests it.
- Do not commit files that likely contain secrets (.env, credentials.json, etc). Warn the user if they request it.
- If there are no changes to commit, do not create an empty commit.
- Never use git commands with the -i flag (like git rebase -i) since they require interactive input.

## Process

1. Run git status and git diff HEAD to see all changes.
2. Run git log --oneline -10 to see recent commit style.
3. Analyze all changes and draft a commit message:
   - Follow the repository's existing commit message style.
   - Summarize the nature of the changes (new feature, enhancement, bug fix, refactoring, test, docs).
   - "add" means a wholly new feature, "update" means an enhancement, "fix" means a bug fix.
   - Draft a concise (1-2 sentence) commit message that focuses on the "why" rather than the "what."
4. Stage relevant files and create the commit.
"""
