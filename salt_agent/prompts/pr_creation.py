"""Pull request creation prompt for SaltAgent.

Adapted from Claude Code's quick PR creation prompt.
"""

PR_CREATION_PROMPT = """Analyze all changes and create a pull request.

## Git Safety Protocol

- NEVER update the git config.
- NEVER run destructive/irreversible git commands unless the user explicitly requests them.
- NEVER skip hooks unless the user explicitly requests it.
- NEVER force push to main/master. Warn the user if they request it.
- Do not commit files that likely contain secrets (.env, credentials.json, etc).

## Process

1. Analyze all changes that will be included in the PR — look at ALL commits from the branch divergence point, not just the latest commit.
2. Create a new branch if on the default branch (use a descriptive feature name).
3. Create a single commit with an appropriate message.
4. Push the branch to origin.
5. Create the PR with:
   - A short title (under 70 characters). Use the body for details.
   - A body with:
     - Summary (1-3 bullet points)
     - Test plan (checklist of testing TODOs)

## PR Body Format

```
## Summary
- <bullet point 1>
- <bullet point 2>

## Test plan
- [ ] <test step 1>
- [ ] <test step 2>
```

Return the PR URL when done.
"""
