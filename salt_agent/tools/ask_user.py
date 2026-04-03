"""Ask the user a structured question with optional suggestions."""

from __future__ import annotations

from salt_agent.tools.base import Tool, ToolDefinition, ToolParam


class AskUserQuestionTool(Tool):
    """Ask the user a structured question with optional suggestions."""

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="ask_user",
            description="Ask the user a question when you need their input to proceed. Include suggestions when possible.",
            params=[
                ToolParam("question", "string", "The question to ask"),
                ToolParam(
                    "suggestions",
                    "array",
                    "Optional suggested answers",
                    required=False,
                    items={"type": "string"},
                ),
            ],
        )

    def execute(self, **kwargs) -> str:
        question = kwargs["question"]
        suggestions = kwargs.get("suggestions", [])
        # In CLI mode, this prompts the user inline
        print(f"\n\u2753 {question}")
        if suggestions:
            for i, s in enumerate(suggestions, 1):
                print(f"  {i}. {s}")
        try:
            response = input("> ")
            # If user typed a number, map to suggestion
            if suggestions and response.strip().isdigit():
                idx = int(response.strip()) - 1
                if 0 <= idx < len(suggestions):
                    return suggestions[idx]
            return response
        except (EOFError, KeyboardInterrupt):
            return "(user declined to answer)"
