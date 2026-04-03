# Bash Tool

Execute shell commands with configurable sandbox, timeout, and security controls.

## Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `command` | string | yes | The shell command to execute |
| `timeout` | integer | no | Override default timeout (seconds) |
| `description` | string | no | Human-readable description of the command |

## Returns

Command stdout and stderr. Output is truncated to `max_output_chars` (default 30,000) if exceeded.

## Security

### BashSandbox

The bash tool can be configured with a `BashSandbox` that enforces:

| Setting | Default | Description |
|---------|---------|-------------|
| `timeout` | 30s | Command timeout |
| `max_output_chars` | 30,000 | Max output length |
| `allowed_commands` | None (all) | Whitelist of allowed commands |
| `blocked_commands` | rm -rf /, sudo rm, mkfs, dd, fork bombs | Blacklist of blocked commands |
| `blocked_patterns` | curl \| bash, wget \| bash | Blocked command patterns |
| `allow_network` | True | Allow network commands |
| `allow_sudo` | False | Allow sudo |
| `allow_background` | True | Allow background processes (&) |
| `restricted_paths` | /etc, /usr, /System, /var | Paths that trigger review |
| `env_whitelist` | None (all) | Allowed environment variables |
| `env_blacklist` | AWS_SECRET_ACCESS_KEY, API keys | Scrubbed environment variables |

### SecurityClassifier

Before execution, bash commands pass through the `SecurityClassifier`:

**Safe commands** (always allowed):
`echo`, `cat`, `ls`, `pwd`, `head`, `tail`, `grep`, `find`, `python`, `pytest`, `git status`, `git log`, `git diff`, `git branch`, and more.

**Dangerous patterns** (always blocked):
`rm -rf /`, `sudo`, `chmod 777`, `mkfs`, `dd if=/dev`, fork bombs, and more.

**AI classifier** (optional):
For ambiguous commands, an async LLM side-query provides nuanced classification. The AI can escalate (allow to ask, ask to deny) but never downgrade a hard deny.

## Permission Integration

The permission system checks bash commands in this order:

1. **SecurityClassifier** -- fast rules-based check
2. **PermissionRule matching** -- glob patterns against the command
3. **AI classifier** (if enabled) -- LLM side-query for ambiguous commands
4. **Ask callback** (if configured) -- prompt the user for approval

## Examples

```python
# Simple command
agent.tools.get("bash").execute(command="ls -la /tmp")

# With custom sandbox
from salt_agent.tools.bash import BashSandbox

sandbox = BashSandbox(
    timeout=60,
    allow_sudo=False,
    allow_network=False,
    blocked_commands={"rm -rf", "sudo"},
)

agent = create_agent(bash_sandbox=sandbox)
```
