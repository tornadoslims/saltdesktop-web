---
name: review
description: Review code changes for bugs, quality, and style
user-invocable: true
---
# Code Review

Review the current code changes thoroughly:

1. Run `git diff` to see all unstaged changes
2. Run `git diff --cached` to see staged changes
3. For each changed file, check for:
   - **Bugs**: logic errors, off-by-one, null/None handling, race conditions
   - **Security**: injection, hardcoded secrets, unsafe deserialization
   - **Error handling**: missing try/except, swallowed errors, unhelpful messages
   - **Style**: naming conventions, dead code, unnecessary complexity
   - **Tests**: are changes covered by tests? any new untested paths?
4. Report findings with file:line references
5. Suggest specific fixes where possible
