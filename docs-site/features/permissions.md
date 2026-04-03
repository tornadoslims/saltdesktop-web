# Permissions

SaltAgent includes a multi-layer permission system that controls which tool calls are allowed.

## Permission Flow

```
Tool Call
    |
    v
1. Auto mode check ──→ (allow all if auto_mode=True)
    |
    v
2. Plan mode check ──→ (deny all except todo_write if plan_mode=True)
    |
    v
3. SecurityClassifier (bash only) ──→ fast rules-based check
    |
    v
4. PermissionRule matching ──→ glob-based pattern matching
    |
    v
5. AI classifier (optional) ──→ LLM side-query for ambiguous commands
    |
    v
Allow / Ask / Deny
```

## Auto Mode

When `auto_mode=True`, all permission checks are bypassed. Use for:

- Server-side deployments
- Trusted environments
- Background tasks

```python
agent = create_agent(auto_mode=True)
```

## Plan Mode

When `plan_mode=True`, only the `todo_write` tool is allowed. The agent must create a plan before executing any actions. Use `/approve` in the CLI to exit plan mode.

## SecurityClassifier

Fast, rules-based classification of bash commands:

**Safe commands** (always allowed):
```
echo, cat, ls, pwd, head, tail, grep, find, python, pytest,
git status, git log, git diff, git branch, which, type, file, ...
```

**Dangerous patterns** (always denied):
```
rm -rf /, sudo, chmod 777, mkfs, dd if=/dev, fork bombs,
curl|bash, wget|bash, > /dev/sda, ...
```

**Needs review** (trigger ask callback):
Everything between safe and dangerous.

## Permission Rules

Rules are glob-based patterns matched against tool names and inputs:

```python
from salt_agent import PermissionRule

rules = [
    # Bash rules
    PermissionRule("bash", "rm -rf *", "deny"),
    PermissionRule("bash", "sudo *", "deny"),
    PermissionRule("bash", "chmod *", "ask"),
    PermissionRule("bash", "git push *", "ask"),
    PermissionRule("bash", "pip install *", "ask"),

    # File write rules
    PermissionRule("write", "/etc/*", "deny"),
    PermissionRule("write", "/usr/*", "deny"),
    PermissionRule("write", "~/*", "ask"),

    # Default
    PermissionRule("*", "*", "allow"),
]

agent = create_agent(permission_rules=rules)
```

### Rule Matching

| Field | Matching |
|-------|---------|
| `tool` | Exact match or `"*"` for all tools |
| `pattern` | `fnmatch` glob against the command (bash) or file path (write/edit) |
| `action` | `"allow"`, `"ask"`, `"deny"` |

Rules are checked in order. The first match wins.

## Ask Callback

When a rule or classifier returns `"ask"`, the `ask_callback` is invoked:

```python
def my_ask_callback(tool_name: str, tool_input: dict, reason: str) -> bool:
    """Return True to allow, False to deny."""
    print(f"Permission needed: {tool_name} -- {reason}")
    return input("Allow? [y/n] ").lower() == "y"

agent = create_agent(permission_ask_callback=my_ask_callback)
```

If no callback is configured, `"ask"` defaults to `"allow"`.

## AI Classifier

For ambiguous bash commands, an LLM side-query provides more nuanced classification:

```python
# The AI classifier runs automatically for bash commands when:
# - auto_mode is False
# - The SecurityClassifier didn't already deny
# It uses the agent's provider for a quick_query side-call
```

The AI classifier can escalate (allow to ask, ask to deny) but **never downgrade** a hard deny.

## Default Rules

```python
DEFAULT_RULES = [
    PermissionRule("bash", "rm -rf *", "deny"),
    PermissionRule("bash", "sudo *", "deny"),
    PermissionRule("bash", "chmod *", "ask"),
    PermissionRule("bash", "kill *", "ask"),
    PermissionRule("bash", "git push *", "ask"),
    PermissionRule("bash", "git reset --hard*", "deny"),
    PermissionRule("bash", "pip install *", "ask"),
    PermissionRule("write", "/etc/*", "deny"),
    PermissionRule("write", "/usr/*", "deny"),
    PermissionRule("write", "~/*", "ask"),
    PermissionRule("*", "*", "allow"),
]
```
