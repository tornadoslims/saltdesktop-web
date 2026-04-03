"""Tests for token budget tracking."""

from __future__ import annotations

import pytest

from salt_agent.token_budget import BudgetTracker, TurnBudget


class TestTurnBudget:
    def test_defaults(self):
        tb = TurnBudget()
        assert tb.max_output_tokens == 4096
        assert tb.used_input_tokens == 0
        assert tb.used_output_tokens == 0

    def test_output_remaining(self):
        tb = TurnBudget(max_output_tokens=1000, used_output_tokens=600)
        assert tb.output_remaining == 400

    def test_output_remaining_never_negative(self):
        tb = TurnBudget(max_output_tokens=100, used_output_tokens=200)
        assert tb.output_remaining == 0

    def test_output_utilization(self):
        tb = TurnBudget(max_output_tokens=1000, used_output_tokens=500)
        assert tb.output_utilization == 0.5

    def test_output_utilization_zero_max(self):
        tb = TurnBudget(max_output_tokens=0, used_output_tokens=0)
        assert tb.output_utilization == 1.0


class TestBudgetTracker:
    def test_start_turn(self):
        bt = BudgetTracker(max_output=2048)
        turn = bt.start_turn()
        assert turn.max_output_tokens == 2048
        assert bt.turn_count == 1

    def test_record_usage(self):
        bt = BudgetTracker()
        bt.start_turn()
        bt.record_usage(1000, 500)
        assert bt.total_input == 1000
        assert bt.total_output == 500
        assert bt.total_tokens == 1500

    def test_record_usage_multiple_turns(self):
        bt = BudgetTracker()
        bt.start_turn()
        bt.record_usage(1000, 500)
        bt.start_turn()
        bt.record_usage(2000, 800)
        assert bt.total_input == 3000
        assert bt.total_output == 1300
        assert bt.total_tokens == 4300

    def test_record_usage_updates_current_turn(self):
        bt = BudgetTracker()
        turn = bt.start_turn()
        bt.record_usage(1000, 500)
        assert turn.used_input_tokens == 1000
        assert turn.used_output_tokens == 500


class TestShouldContinue:
    def test_under_budget_returns_false(self):
        """Model used only 50% of output budget -- no need to continue."""
        bt = BudgetTracker(max_output=4096)
        bt.start_turn()
        bt.record_usage(10000, 2000)  # ~49% utilization
        assert bt.should_continue() is False

    def test_at_limit_returns_true(self):
        """Model used >90% of output budget -- should continue."""
        bt = BudgetTracker(max_output=4096)
        bt.start_turn()
        bt.record_usage(10000, 3900)  # ~95% utilization
        assert bt.should_continue() is True

    def test_exactly_at_90_percent(self):
        bt = BudgetTracker(max_output=1000)
        bt.start_turn()
        bt.record_usage(5000, 901)  # 90.1%
        assert bt.should_continue() is True

    def test_diminishing_returns_detection(self):
        """If last 3 turns each produced <500 tokens, stop nudging."""
        bt = BudgetTracker(max_output=4096)
        # Three turns, each producing very little output but hitting 90%+
        for _ in range(3):
            bt.start_turn()
            bt.record_usage(5000, 400)  # <500 output but >90%? No -- 400/4096 = ~10%
        # This won't trigger should_continue because utilization is only 10%
        assert bt.should_continue() is False

        # Now test with high utilization AND low absolute tokens
        bt2 = BudgetTracker(max_output=400)  # Very small budget
        for _ in range(3):
            bt2.start_turn()
            bt2.record_usage(5000, 380)  # 95% utilization, but <500 absolute
        # Diminishing returns: all 3 recent turns have <500 output tokens
        assert bt2.should_continue() is False

    def test_no_turns_returns_false(self):
        bt = BudgetTracker()
        assert bt.should_continue() is False


class TestCostEstimate:
    def test_cost_estimate_sonnet(self):
        bt = BudgetTracker(model="claude-sonnet-4-20250514")
        bt.start_turn()
        bt.record_usage(1_000_000, 100_000)
        # Input: 1M * $3/M = $3, Output: 100K * $15/M = $1.50
        cost = bt.total_cost_estimate
        assert abs(cost - 4.50) < 0.01

    def test_cost_estimate_unknown_model(self):
        bt = BudgetTracker(model="unknown-model-xyz")
        bt.start_turn()
        bt.record_usage(1_000_000, 100_000)
        # Falls back to default rates (3.0, 15.0)
        cost = bt.total_cost_estimate
        assert cost > 0

    def test_zero_tokens_zero_cost(self):
        bt = BudgetTracker()
        assert bt.total_cost_estimate == 0.0


class TestGetStats:
    def test_stats_structure(self):
        bt = BudgetTracker(model="gpt-4o")
        bt.start_turn()
        bt.record_usage(500, 200)
        stats = bt.get_stats()
        assert stats["turns"] == 1
        assert stats["total_input_tokens"] == 500
        assert stats["total_output_tokens"] == 200
        assert stats["total_tokens"] == 700
        assert "estimated_cost" in stats
        assert stats["model"] == "gpt-4o"


class TestFormat:
    def test_format_with_tokens(self):
        bt = BudgetTracker(model="gpt-4o")
        bt.start_turn()
        bt.record_usage(5000, 1000)
        formatted = bt.format()
        assert "6.0k tokens" in formatted
        assert "$" in formatted

    def test_format_no_tokens(self):
        bt = BudgetTracker()
        assert bt.format() == ""

    def test_format_small_tokens(self):
        bt = BudgetTracker()
        bt.start_turn()
        bt.record_usage(50, 30)
        formatted = bt.format()
        assert "80 tokens" in formatted
