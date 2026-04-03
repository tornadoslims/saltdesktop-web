---
name: upgrade
description: Upgrade project dependencies safely
user-invocable: true
---
# Upgrade Dependencies

Safely upgrade project dependencies:

1. Identify the package manager: pip, npm, yarn, cargo, go mod, etc.
2. List current outdated packages:
   - Python: `pip list --outdated`
   - Node.js: `npm outdated`
   - Rust: `cargo outdated`
   - Go: `go list -u -m all`
3. Check for breaking changes in major version bumps:
   - Read changelogs for major upgrades
   - Identify deprecated APIs being used
4. Upgrade incrementally:
   - Start with patch/minor updates (low risk)
   - Then tackle major version bumps one at a time
5. After each upgrade:
   - Run the test suite
   - Check for deprecation warnings
   - Verify the application starts correctly
6. Update lock files (package-lock.json, Pipfile.lock, etc.)
7. Summarize what was upgraded and any manual changes needed
