# Token Budget

The `BudgetTracker` tracks real token usage from API responses and provides cost estimation, diminishing-returns detection, and budget enforcement.

## TurnBudget

Each turn has a budget:

```python
@dataclass
class TurnBudget:
    max_output_tokens: int = 4096
    used_input_tokens: int = 0
    used_output_tokens: int = 0
```

Properties:

- `output_remaining` -- how many output tokens are left
- `output_utilization` -- fraction of output budget used (0.0 to 1.0+)

## BudgetTracker

Tracks budgets across turns and accumulates totals:

```python
tracker = BudgetTracker(
    context_window=200_000,
    max_output=4096,
    model="gpt-4o",
)

# Each turn:
tracker.start_turn()
# ... API call ...
tracker.record_turn(input_tokens=5000, output_tokens=1200)

# Check totals:
print(tracker.total_input_tokens)     # 5000
print(tracker.total_output_tokens)    # 1200
print(tracker.total_cost_estimate)    # $0.0245
```

## Cost Table

The tracker knows pricing for common models:

| Model | Input ($/1M tokens) | Output ($/1M tokens) |
|-------|---------------------|----------------------|
| claude-sonnet-4-20250514 | $3.00 | $15.00 |
| claude-3-5-sonnet-20241022 | $3.00 | $15.00 |
| claude-3-haiku-20240307 | $0.25 | $1.25 |
| gpt-4o | $2.50 | $10.00 |
| gpt-4o-mini | $0.15 | $0.60 |
| gpt-4.1 | $2.00 | $8.00 |
| gpt-4.1-mini | $0.40 | $1.60 |
| gpt-4.1-nano | $0.10 | $0.40 |

For unknown models, a conservative estimate is used.

## Budget Enforcement

When `max_budget_usd` is set in `AgentConfig`, the agent checks the budget before each API call:

```python
if self.budget.total_cost_estimate >= self.config.max_budget_usd:
    yield AgentError(error=f"Budget limit reached (${self.config.max_budget_usd})", recoverable=False)
    return
```

## Diminishing Returns Detection

The tracker can detect when the model is producing very little new content per turn, suggesting it's stuck or has finished but hasn't stopped.

## CLI Commands

| Command | Description |
|---------|-------------|
| `/tokens` | Show token usage stats |
| `/budget` | Show budget tracker stats |
| `/cost` | Show token usage this session |

## State Integration

Token and cost data is published to the state store:

```python
agent.state.update(
    total_input_tokens=tracker.total_input_tokens,
    total_output_tokens=tracker.total_output_tokens,
    total_cost=tracker.total_cost_estimate,
)
```

Subscribe to track costs in real-time:

```python
agent.state.subscribe(lambda field, val:
    print(f"Cost: ${val:.4f}") if field == "total_cost" else None
)
```
