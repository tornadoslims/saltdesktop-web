# CLAUDE.md

**Path:** `CLAUDE.md`
**Purpose:** Instructions for Claude Code when working in this repository. Defines work style, coordination protocol, architecture, and project structure.

## Key Information

- The app is called **Salt Desktop**. JBCP is invisible infrastructure.
- The webui-v2 is a **temporary development tool** -- the real product is a Swift macOS native app.
- All coding tasks must be delegated to subagents (background agents).
- Two living docs must be maintained: `docs/ACTIVITY_LOG.md` (append-only) and `docs/SYSTEM_SPEC.md` (regenerated on architecture changes).
- There is a **coordination protocol** between a Backend Claude (this workspace) and a Frontend Claude (Swift app at `~/Projects/santiago-salt-desktop/`).
- Architecture: direct LLM calls for planning, Claude Code CLI for building, SQLite for data, in-memory event bus for SSE.
- Credentials stored at `~/.missionos/credentials/` by the Swift companion app.
- 20+ supported external services for connector integration.
