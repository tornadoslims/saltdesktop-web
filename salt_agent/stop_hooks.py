"""Post-turn hooks that run between agent turns.

Inspired by Claude Code's query/stopHooks.ts:
- Memory extraction: scan conversation for things worth remembering
- Session title: generate a title from the first exchange
- Cleanup: any post-turn housekeeping

These run BETWEEN turns, after the model responds and tools execute.
They should be fast and never crash the agent.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from salt_agent.agent import SaltAgent


class StopHookRunner:
    """Runs post-turn hooks between agent turns."""

    def __init__(self, agent: "SaltAgent") -> None:
        self.agent = agent
        self._hooks = [
            self._extract_memories,
            self._generate_session_title,
            self._log_turn_stats,
            self._consolidate_memories,
            self._generate_suggestions,
        ]
        self.last_suggestions: list[str] = []

    async def run_after_turn(self, messages: list[dict], turn: int) -> None:
        """Run all stop hooks. Called after each completed turn."""
        for hook in self._hooks:
            try:
                await hook(messages, turn)
            except Exception:
                pass  # Stop hooks must NEVER crash the agent

    async def _extract_memories(self, messages: list[dict], turn: int) -> None:
        """Scan recent conversation for things worth saving to memory.

        Only runs every 5 turns to control cost.
        """
        if turn % 5 != 0 or turn == 0:
            return

        # Get last 3 exchanges (6 messages)
        recent = messages[-6:] if len(messages) >= 6 else messages
        conversation_text = self._format_messages(recent)

        prompt = (
            "Review this conversation excerpt. Is there anything worth saving to long-term memory?\n\n"
            "Memory types:\n"
            "- user: preferences, expertise, role\n"
            "- feedback: corrections, confirmations of approach\n"
            "- project: decisions, deadlines, ongoing work\n"
            "- reference: external system locations\n\n"
            "Rules:\n"
            "- Only save things useful in FUTURE conversations\n"
            "- Don't save code, debugging solutions, or things derivable from the codebase\n"
            "- Don't save ephemeral task details\n\n"
            'If nothing is worth saving, respond with exactly "NONE".\n'
            "Otherwise respond with one memory entry in this format:\n"
            "TYPE: feedback\n"
            "NAME: user_prefers_short_responses\n"
            "DESCRIPTION: User wants concise responses without filler\n"
            'CONTENT: User said "stop summarizing what you did, I can read the diff." '
            "They prefer direct, terse communication.\n\n"
            f"Conversation:\n{conversation_text}"
        )

        result = await self.agent.provider.quick_query(prompt, max_tokens=500)

        if not result or "NONE" in result.upper():
            return

        memory = self._parse_memory_entry(result)
        if memory:
            self.agent.memory.save_memory_file(
                name=memory["name"],
                content=memory["content"],
                memory_type=memory["type"],
                description=memory["description"],
            )
            self.agent.hooks.fire("memory_saved", {
                "name": memory["name"],
                "type": memory["type"],
            })

    async def _generate_session_title(self, messages: list[dict], turn: int) -> None:
        """Generate a session title from the first exchange."""
        if turn != 1:  # Only on first completed turn
            return
        if not self.agent.persistence:
            return

        first_msg = messages[0]["content"] if messages else ""
        if isinstance(first_msg, list):
            first_msg = str(first_msg)

        prompt = (
            "Generate a 3-6 word title for a coding session that started with:\n\n"
            f"{str(first_msg)[:300]}\n\nTitle only, no quotes:"
        )

        title = await self.agent.provider.quick_query(prompt, max_tokens=30)
        title = title.strip().strip('"').strip("'")

        if title:
            self.agent.persistence.save_event("session_title", {"title": title})

    async def _log_turn_stats(self, messages: list[dict], turn: int) -> None:
        """Log turn statistics for debugging/analytics."""
        if self.agent.persistence:
            self.agent.persistence.save_event("turn_complete", {
                "turn": turn,
                "total_messages": len(messages),
                "estimated_tokens": sum(
                    len(str(m.get("content", ""))) // 4 for m in messages
                ),
            })

    async def _consolidate_memories(self, messages: list[dict], turn: int) -> None:
        """Consolidate memories: merge duplicates, remove stale, organize.

        Runs every 20 turns (expensive operation).
        """
        if turn % 20 != 0 or turn == 0:
            return

        memory_files = self.agent.memory.scan_memory_files()
        if len(memory_files) < 3:
            return  # not enough to consolidate

        # Build a summary of all memories
        summaries = []
        for mf in memory_files:
            content = self.agent.memory.load_memory_file(mf["filename"])
            summaries.append(
                f"File: {mf['filename']}\nType: {mf.get('type', '?')}\n"
                f"Description: {mf.get('description', '')}\nContent: {content[:300]}"
            )

        prompt = (
            "Review these memory files and suggest consolidation:\n\n"
            + "\n".join(summaries) + "\n\n"
            "For each action, respond with one of:\n"
            "- KEEP: filename (no change needed)\n"
            "- MERGE: filename1 + filename2 -> new_name (combine duplicates)\n"
            "- DELETE: filename (stale or useless)\n"
            "- UPDATE: filename -> new_description (better description)\n\n"
            "Only suggest changes if clearly needed. When in doubt, KEEP."
        )

        result = await self.agent.provider.quick_query(prompt, max_tokens=500)

        # Parse and apply DELETE actions only (safest)
        for line in result.splitlines():
            line = line.strip()
            if line.startswith("DELETE:"):
                filename = line.split(":", 1)[1].strip()
                # Only delete if the file actually exists
                file_path = self.agent.memory.memory_dir / filename
                if file_path.exists():
                    file_path.unlink()
                    self.agent.memory._update_index(filename, "")  # remove from index
                    self.agent.hooks.fire("memory_deleted", {
                        "filename": filename,
                    })

    async def _generate_suggestions(self, messages: list[dict], turn: int) -> None:
        """Generate follow-up prompt suggestions.

        Only runs when the last message is from the assistant with plain text
        (i.e., the final response, not a mid-turn tool result exchange).
        """
        if turn < 1:
            return

        # Only generate suggestions at the end of a conversation turn, not
        # between tool calls. If the last message is tool_results (list content
        # from user role), we're mid-turn and should skip.
        if messages:
            last_msg = messages[-1]
            if last_msg.get("role") == "user" and isinstance(last_msg.get("content"), list):
                return

        # Get the last exchange
        recent = messages[-2:] if len(messages) >= 2 else messages
        conversation = "\n".join(
            f"[{m.get('role', '?')}]: {str(m.get('content', ''))[:200]}"
            for m in recent
        )

        prompt = (
            "Based on this exchange, suggest 2-3 brief follow-up prompts the user "
            "might want to try. Each should be under 60 characters. Return as a "
            "simple numbered list.\n\n" + conversation
        )

        result = await self.agent.provider.quick_query(prompt, max_tokens=200)

        # Store suggestions for the CLI to display
        self.last_suggestions = []
        for line in result.strip().splitlines():
            line = line.strip().lstrip("0123456789.-) ")
            if line and len(line) < 80:
                self.last_suggestions.append(line)
        self.last_suggestions = self.last_suggestions[:3]

    @staticmethod
    def _format_messages(messages: list[dict]) -> str:
        """Format messages for the LLM prompt."""
        lines = []
        for m in messages:
            role = m.get("role", "?")
            content = m.get("content", "")
            if isinstance(content, str):
                lines.append(f"[{role}]: {content[:500]}")
            elif isinstance(content, list):
                text_parts = [
                    b.get("text", "")
                    for b in content
                    if isinstance(b, dict) and b.get("type") == "text"
                ]
                lines.append(f"[{role}]: {' '.join(text_parts)[:500]}")
        return "\n".join(lines)

    @staticmethod
    def _parse_memory_entry(text: str) -> dict | None:
        """Parse a memory entry from the LLM response."""
        lines = text.strip().splitlines()
        entry: dict[str, str] = {}
        content_lines: list[str] = []
        in_content = False

        for line in lines:
            if line.startswith("TYPE:"):
                entry["type"] = line.split(":", 1)[1].strip().lower()
            elif line.startswith("NAME:"):
                entry["name"] = line.split(":", 1)[1].strip()
            elif line.startswith("DESCRIPTION:"):
                entry["description"] = line.split(":", 1)[1].strip()
            elif line.startswith("CONTENT:"):
                entry["content"] = line.split(":", 1)[1].strip()
                in_content = True
            elif in_content:
                content_lines.append(line)

        if content_lines:
            entry["content"] = entry.get("content", "") + "\n" + "\n".join(content_lines)

        if all(k in entry for k in ("type", "name", "description", "content")):
            return entry
        return None
