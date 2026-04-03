"""
Provider-specific prompt adaptations for SaltAgent.

Different LLMs respond differently to the same instructions. This module
provides adaptation layers that adjust prompt wording, structure, and emphasis
for optimal behavior per provider.

Analysis based on system prompts from:
- Anthropic: Claude Code, Claude Opus 4.6, Claude Sonnet 4.6
- OpenAI: GPT-5.4 API, GPT-5.4 Thinking, Codex CLI, GPT-4o, GPT-5 Agent Mode
- Google: Gemini CLI, Gemini 3.1 Pro API, Gemini 3 Pro
- xAI: Grok 4.2
"""

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def adapt_for_provider(prompt: str, provider: str, model: str = "") -> str:
    """Adapt a system prompt for a specific provider.

    Args:
        prompt: The base system prompt to adapt.
        provider: One of "anthropic", "openai", "gemini", "xai".
        model: Optional model identifier for finer-grained adaptation
               (e.g. "gpt-5.4", "codex", "gemini-3.1-pro").

    Returns:
        The adapted prompt string.
    """
    adapter = _ADAPTERS.get(provider)
    if adapter is None:
        return prompt
    return adapter(prompt, model)


# ---------------------------------------------------------------------------
# Anthropic (Claude) adapter
# ---------------------------------------------------------------------------


def _adapt_for_anthropic(prompt: str, model: str = "") -> str:
    """Claude models prefer prose-heavy, minimal-formatting prompts.

    Key findings from Claude Code / Opus 4.6 / Sonnet 4.6 system prompts:
    - Responds best to natural-language prose over bullet-heavy instructions
    - Has native anti-sycophancy training; no need to repeat it
    - Parses XML tags (<context>, <instructions>) for structural separation
    - Strongly adheres to "read before edit" and anti-overengineering rules
    - Does NOT use channel tags, preamble updates, or numeric tuning params
    - Prefers dedicated tool descriptions in JSON Schema format
    - Avoids emojis, time estimates, and excessive formatting
    """
    sections = []

    # Claude parses XML context tags well -- wrap supplementary context
    sections.append(prompt)

    # Add Claude-specific behavioral reinforcement
    sections.append(_ANTHROPIC_BEHAVIORAL_SUFFIX)

    return "\n\n".join(sections)


_ANTHROPIC_BEHAVIORAL_SUFFIX = """\
## Provider Notes (Anthropic)

- Respond in prose paragraphs, not bullet lists, unless the user requests a list.
- Do not use emojis or excessive markdown formatting.
- Lead with the answer or action, then explain only if needed.
- Do not give time estimates for tasks.
- When referencing code, use file_path:line_number format.
- Use absolute file paths, never relative.
- When making tool calls, provide clear descriptions but do not narrate the call \
itself ("Let me read the file." not "Let me read the file:").
"""


# ---------------------------------------------------------------------------
# OpenAI (GPT) adapter
# ---------------------------------------------------------------------------


def _adapt_for_openai(prompt: str, model: str = "") -> str:
    """GPT models prefer structured prompts with explicit output calibration.

    Key findings from GPT-5.4 / Codex CLI / GPT-5 Agent Mode:
    - GPT-5.4+ uses a channel system (analysis/commentary/final)
    - Codex CLI expects brief preamble messages before tool calls
    - Responds well to structured formatting rules (headers, bullets, monospace)
    - apply_patch (diff-based) editing is native; string replacement is not
    - Oververbosity / Juice parameters control response length
    - Has sandbox escalation model with explicit permission requests
    - Expects progress updates every ~15 seconds or 2-3 tool calls
    - Distinguishes "ambitious" (new projects) from "surgical" (existing code)
    """
    sections = []

    sections.append(prompt)

    # GPT models benefit from explicit output calibration
    sections.append(_OPENAI_BEHAVIORAL_SUFFIX)

    # For Codex CLI / agent mode, add preamble guidance
    if model and ("codex" in model.lower() or "agent" in model.lower()):
        sections.append(_OPENAI_AGENT_SUFFIX)

    return "\n\n".join(sections)


_OPENAI_BEHAVIORAL_SUFFIX = """\
## Provider Notes (OpenAI)

- Keep responses concise but use clear structure: headers for sections, \
bullets for lists of items, backticks for code/paths.
- Before performing multi-step work, share a brief plan or preamble \
describing what you are about to do.
- When editing files, describe changes as diffs (what was removed, what was added) \
rather than showing full file contents.
- Share progress updates periodically during longer tasks.
- For new/greenfield work, be ambitious and creative. \
For existing codebases, be surgical and precise.
- Always validate your work by running tests or builds when available.
"""

_OPENAI_AGENT_SUFFIX = """\
## Agent Mode Notes

- Send brief preamble messages before tool calls to keep the user informed.
- Group related actions and describe them together rather than narrating each one.
- Keep preamble messages to 1-2 sentences (8-12 words for quick updates).
- Build on prior context in updates to create a sense of momentum.
"""


# ---------------------------------------------------------------------------
# Google (Gemini) adapter
# ---------------------------------------------------------------------------


def _adapt_for_gemini(prompt: str, model: str = "") -> str:
    """Gemini models prefer hierarchical context and phased workflows.

    Key findings from Gemini CLI / Gemini 3.1 Pro / Gemini 3 Pro:
    - Uses context hierarchy: <project_context> > <extension_context> > <global_context>
    - Trained for Research -> Strategy -> Execution lifecycle
    - Context efficiency is a first-class concern
    - Distinguishes Directives (take action) from Inquiries (analyze only)
    - Sub-agent delegation for complex tasks
    - "Explain Before Acting" mandate
    - GEMINI.md files override system prompt instructions
    - Prefers non-interactive command flags
    - Formal validation requirements (build, lint, test after every change)
    """
    sections = []

    # Wrap the base prompt in Gemini's expected context hierarchy
    sections.append("<project_context>")
    sections.append(prompt)
    sections.append("</project_context>")

    # Add Gemini-specific behavioral guidance
    sections.append(_GEMINI_BEHAVIORAL_SUFFIX)

    return "\n\n".join(sections)


_GEMINI_BEHAVIORAL_SUFFIX = """\
## Provider Notes (Gemini)

### Workflow
Follow a Research -> Strategy -> Execution lifecycle:
1. Research: Investigate the codebase and validate assumptions before acting.
2. Strategy: Formulate a plan and share a concise summary.
3. Execution: Apply targeted changes, then validate with tests/builds.

### Context Efficiency
- Minimize unnecessary tool calls and context consumption.
- Combine independent searches into parallel calls.
- Use conservative limits on search results and file reads.
- Prefer grep/search to identify points of interest over reading entire files.

### Communication
- Provide a concise one-sentence explanation before executing tool calls.
- After completing code changes, do not provide summaries unless asked.
- Keep responses under 3 lines of text (excluding code) when practical.
- Use GitHub-flavored Markdown for formatting.

### Validation
- After making code changes, run project-specific build, lint, and test commands.
- A task is only complete when behavioral correctness is verified.
- Never assume success without validation.
"""


# ---------------------------------------------------------------------------
# xAI (Grok) adapter
# ---------------------------------------------------------------------------


def _adapt_for_xai(prompt: str, model: str = "") -> str:
    """Grok models prefer direct, personality-infused prompts.

    Key findings from Grok 4.2:
    - Multi-agent team architecture (leader + teammates)
    - Standard function-call JSON for tools
    - Strong emphasis on truthfulness and independent analysis
    - Humanist values framework
    - Render components for rich visual output
    - X/Twitter deep integration
    """
    sections = []
    sections.append(prompt)
    sections.append(_XAI_BEHAVIORAL_SUFFIX)
    return "\n\n".join(sections)


_XAI_BEHAVIORAL_SUFFIX = """\
## Provider Notes (xAI)

- Be direct and truthful. Acknowledge uncertainty rather than guessing.
- Responses should stem from independent analysis, not assumptions.
- Use code execution for computation rather than mental math.
- When web search would improve accuracy, use it proactively.
- Keep a concise, friendly tone without excessive formality.
"""


# ---------------------------------------------------------------------------
# Adapter registry
# ---------------------------------------------------------------------------

_ADAPTERS = {
    "anthropic": _adapt_for_anthropic,
    "openai": _adapt_for_openai,
    "gemini": _adapt_for_gemini,
    "google": _adapt_for_gemini,  # alias
    "xai": _adapt_for_xai,
    "grok": _adapt_for_xai,  # alias
}


# ---------------------------------------------------------------------------
# Utility: get provider-specific tool format hints
# ---------------------------------------------------------------------------


def get_tool_format_hints(provider: str) -> dict:
    """Return provider-specific hints about how tools should be described.

    Useful for the prompt assembler when composing tool descriptions.

    Returns a dict with:
        - format: "json_schema", "typescript", "freeform"
        - parallel: whether to mention parallel execution
        - channel_tags: whether to include channel tags
        - sandbox_model: "none", "configurable", "always"
    """
    return _TOOL_HINTS.get(provider, _TOOL_HINTS["default"])


_TOOL_HINTS = {
    "anthropic": {
        "format": "json_schema",
        "parallel": True,
        "channel_tags": False,
        "sandbox_model": "none",
        "edit_style": "string_replacement",
        "notes": "Use dedicated tools (Read, Edit, Write) instead of bash for file ops.",
    },
    "openai": {
        "format": "typescript",
        "parallel": True,
        "channel_tags": True,
        "sandbox_model": "configurable",
        "edit_style": "diff_patch",
        "notes": "Tools are namespaced. FREEFORM input type means raw text, not JSON.",
    },
    "gemini": {
        "format": "json_schema",
        "parallel": True,
        "channel_tags": False,
        "sandbox_model": "none",
        "edit_style": "string_replacement",
        "notes": "Context efficiency matters. Combine parallel reads/searches.",
    },
    "google": {
        "format": "json_schema",
        "parallel": True,
        "channel_tags": False,
        "sandbox_model": "none",
        "edit_style": "string_replacement",
        "notes": "Context efficiency matters. Combine parallel reads/searches.",
    },
    "xai": {
        "format": "json_schema",
        "parallel": True,
        "channel_tags": False,
        "sandbox_model": "none",
        "edit_style": "string_replacement",
        "notes": "Standard function-call format. Render components in final response only.",
    },
    "default": {
        "format": "json_schema",
        "parallel": True,
        "channel_tags": False,
        "sandbox_model": "none",
        "edit_style": "string_replacement",
        "notes": "",
    },
}


# ---------------------------------------------------------------------------
# Utility: get provider-specific response style hints
# ---------------------------------------------------------------------------


def get_response_style_hints(provider: str) -> dict:
    """Return provider-specific hints about response formatting preferences.

    Useful when SaltAgent needs to instruct the model about output style.
    """
    return _RESPONSE_HINTS.get(provider, _RESPONSE_HINTS["default"])


_RESPONSE_HINTS = {
    "anthropic": {
        "formatting": "minimal",
        "bullets": "avoid unless requested",
        "headers": "avoid unless multi-section",
        "emojis": "never",
        "tone": "warm, professional, concise",
        "progress_style": "milestone-based",
        "preamble_before_tools": False,
    },
    "openai": {
        "formatting": "structured",
        "bullets": "use with bold keywords",
        "headers": "use for multi-part results",
        "emojis": "sparingly if at all",
        "tone": "friendly, conversational, direct",
        "progress_style": "time-based (every ~15s or 2-3 tool calls)",
        "preamble_before_tools": True,
    },
    "gemini": {
        "formatting": "moderate",
        "bullets": "use for digestible lists",
        "headers": "use for hierarchy",
        "emojis": "avoid",
        "tone": "professional, direct, minimal",
        "progress_style": "explain-before-acting",
        "preamble_before_tools": True,
    },
    "xai": {
        "formatting": "moderate",
        "bullets": "use when helpful",
        "headers": "use when helpful",
        "emojis": "avoid",
        "tone": "direct, curious, friendly",
        "progress_style": "as-needed",
        "preamble_before_tools": False,
    },
    "default": {
        "formatting": "moderate",
        "bullets": "use when helpful",
        "headers": "use when helpful",
        "emojis": "avoid",
        "tone": "professional, concise",
        "progress_style": "milestone-based",
        "preamble_before_tools": False,
    },
}
