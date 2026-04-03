"""Per-turn token budget tracking with diminishing-returns detection.

Inspired by Claude Code's query/tokenBudget.ts:
- Track input/output tokens per turn from real API usage data
- Detect when the model hit the output limit (could say more)
- Detect diminishing returns (model producing very little new content)
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TurnBudget:
    """Token budget for a single turn."""

    max_output_tokens: int = 4096
    used_input_tokens: int = 0
    used_output_tokens: int = 0

    @property
    def output_remaining(self) -> int:
        return max(0, self.max_output_tokens - self.used_output_tokens)

    @property
    def output_utilization(self) -> float:
        """Fraction of output budget used (0.0 to 1.0+)."""
        if self.max_output_tokens == 0:
            return 1.0
        return self.used_output_tokens / self.max_output_tokens


class BudgetTracker:
    """Track token budgets across turns.

    Uses real token counts from the provider's usage data (not estimates).
    """

    # Cost per 1M tokens (input, output) for common models
    _COST_TABLE = {
        "claude-sonnet-4-20250514": (3.0, 15.0),
        "claude-3-5-sonnet-20241022": (3.0, 15.0),
        "claude-3-haiku-20240307": (0.25, 1.25),
        "gpt-4o": (2.50, 10.00),
        "gpt-4o-mini": (0.15, 0.60),
        "gpt-4.1": (2.00, 8.00),
        "gpt-4.1-mini": (0.40, 1.60),
        "gpt-4.1-nano": (0.10, 0.40),
    }

    def __init__(
        self,
        context_window: int = 200_000,
        max_output: int = 4096,
        model: str = "",
    ) -> None:
        self.context_window = context_window
        self.max_output = max_output
        self.model = model
        self._turns: list[TurnBudget] = []
        self._total_input: int = 0
        self._total_output: int = 0

    def start_turn(self) -> TurnBudget:
        """Start tracking a new turn."""
        budget = TurnBudget(max_output_tokens=self.max_output)
        self._turns.append(budget)
        return budget

    def record_usage(self, input_tokens: int, output_tokens: int) -> None:
        """Record actual token usage from the API response."""
        if self._turns:
            self._turns[-1].used_input_tokens = input_tokens
            self._turns[-1].used_output_tokens = output_tokens
        self._total_input += input_tokens
        self._total_output += output_tokens

    def should_continue(self) -> bool:
        """Check if the model should be nudged to continue.

        Returns True if the model used >90% of its output budget (likely
        cut off), UNLESS diminishing returns are detected (last 3 turns
        each produced <500 output tokens).
        """
        if not self._turns:
            return False
        last = self._turns[-1]

        # If model used > 90% of output budget, it might have been cut off
        if last.output_utilization > 0.90:
            # Check for diminishing returns
            if len(self._turns) >= 3:
                recent = self._turns[-3:]
                if all(t.used_output_tokens < 500 for t in recent):
                    return False  # Diminishing returns -- stop nudging
            return True

        return False

    @property
    def total_input(self) -> int:
        return self._total_input

    @property
    def total_output(self) -> int:
        return self._total_output

    @property
    def total_tokens(self) -> int:
        return self._total_input + self._total_output

    @property
    def total_cost_estimate(self) -> float:
        """Cost estimate using model-specific rates, or Sonnet defaults."""
        rates = self._COST_TABLE.get(self.model, (3.0, 15.0))
        input_cost = self._total_input * rates[0] / 1_000_000
        output_cost = self._total_output * rates[1] / 1_000_000
        return input_cost + output_cost

    @property
    def turn_count(self) -> int:
        return len(self._turns)

    def get_stats(self) -> dict:
        """Return a summary dict of budget tracking stats."""
        return {
            "turns": len(self._turns),
            "total_input_tokens": self._total_input,
            "total_output_tokens": self._total_output,
            "total_tokens": self.total_tokens,
            "estimated_cost": round(self.total_cost_estimate, 4),
            "model": self.model,
        }

    def format(self) -> str:
        """Human-readable summary string."""
        total = self.total_tokens
        if total == 0:
            return ""
        if total < 1000:
            tok_str = f"{total} tokens"
        else:
            tok_str = f"{total / 1000:.1f}k tokens"
        cost = self.total_cost_estimate
        return f"{tok_str} ({self._total_input} in / {self._total_output} out) \u00b7 ${cost:.4f}"
