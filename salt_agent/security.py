"""Security classifier for bash commands.

Rules-based classifier that categorizes bash commands as safe/needs-review/dangerous
before execution.  Designed to be fast (no LLM call) and conservative.

Also provides an async AI classifier that uses a cheap LLM side-query for
more nuanced classification of ambiguous commands.
"""

from __future__ import annotations


async def ai_classify_bash(command: str, provider) -> tuple[str, str]:
    """Use a cheap LLM call to classify a bash command's safety.

    Returns (action, reason) where action is "allow", "ask", or "deny".
    """
    prompt = f"""Classify this bash command's safety level.

Command: {command}

Respond with EXACTLY one line in this format:
ACTION: allow|ask|deny
REASON: brief explanation

Rules:
- allow: read-only commands, standard dev tools (ls, cat, grep, git status, python, pytest, npm test)
- ask: state-modifying but common (rm files, git push, pip install, chmod, mv)
- deny: destructive or dangerous (rm -rf /, sudo, dd, mkfs, fork bombs, curl|bash)
"""
    try:
        result = await provider.quick_query(prompt, max_tokens=50)
        for line in result.strip().splitlines():
            if line.startswith("ACTION:"):
                action = line.split(":", 1)[1].strip().lower()
                if action in ("allow", "ask", "deny"):
                    return action, result
        return "ask", "Could not parse classifier response"
    except Exception:
        return "ask", "Classifier failed, defaulting to ask"


class SecurityClassifier:
    """Classifies bash commands as safe/needs-review/dangerous."""

    SAFE_COMMANDS: set[str] = {
        "echo", "cat", "ls", "pwd", "head", "tail", "wc", "grep", "find",
        "date", "whoami", "python", "python3", "node", "pytest",
        "git status", "git log", "git diff", "git branch", "printenv", "env",
        "which", "type", "file", "stat", "du", "df", "uname", "hostname",
        "true", "false", "test", "seq", "sort", "uniq", "tr", "cut",
        "basename", "dirname", "realpath", "readlink", "tee",
    }

    DANGEROUS_PATTERNS: list[str] = [
        "rm -rf /",
        "rm -rf ~",
        "rm -rf .",
        "sudo ",
        "chmod 777",
        "> /dev/",
        "mkfs",
        "dd if=",
        ":(){ :|:& };:",
        "curl | bash",
        "wget | bash",
        "curl | sh",
        "wget | sh",
        "eval $(curl",
        "eval $(wget",
        "> /etc/",
        "git push --force",
        "git reset --hard",
    ]

    STATE_MODIFYING_COMMANDS: list[str] = [
        "rm ", "mv ", "cp ", "chmod ", "chown ", "kill ", "pkill ",
        "killall ", "mkdir ", "rmdir ", "ln ", "truncate ",
    ]

    NETWORK_COMMANDS: list[str] = [
        "curl ", "wget ", "ssh ", "scp ", "rsync ", "nc ", "ncat ",
        "telnet ", "ftp ", "sftp ",
    ]

    PACKAGE_INSTALL_COMMANDS: list[str] = [
        "pip install", "pip3 install",
        "npm install", "npm i ",
        "yarn add", "yarn install",
        "brew install", "brew cask install",
        "apt install", "apt-get install",
        "dnf install", "yum install",
        "gem install", "cargo install",
    ]

    def classify(self, command: str) -> tuple[str, str]:
        """Classify a bash command.

        Returns (action, reason) where action is one of:
        - "allow": safe to execute
        - "ask": needs user review
        - "deny": too dangerous, block outright
        """
        stripped = command.strip()
        if not stripped:
            return "allow", "empty command"

        # Fast path: known dangerous patterns (check FIRST -- before safe commands)
        for pattern in self.DANGEROUS_PATTERNS:
            if pattern in stripped:
                return "deny", f"dangerous pattern: {pattern}"

        # Pipe to shell (before network check, since curl|bash is dangerous not just "ask")
        if "| sh" in stripped or "| bash" in stripped or "| zsh" in stripped:
            return "deny", "pipe to shell execution"

        # Package management (before safe commands, since pip/npm are safe alone but install is not)
        for cmd in self.PACKAGE_INSTALL_COMMANDS:
            if cmd in stripped:
                return "ask", "package installation"

        # Fast path: known safe commands (check first word and two-word combos)
        first_word = stripped.split()[0]
        two_words = " ".join(stripped.split()[:2]) if len(stripped.split()) > 1 else ""

        if first_word in self.SAFE_COMMANDS or two_words in self.SAFE_COMMANDS:
            return "allow", "known safe command"

        # Medium risk: commands that modify state
        for cmd in self.STATE_MODIFYING_COMMANDS:
            if stripped.startswith(cmd) or f" {cmd}" in stripped or f"&& {cmd}" in stripped:
                return "ask", "state-modifying command"

        # Network commands
        for cmd in self.NETWORK_COMMANDS:
            if stripped.startswith(cmd) or f" {cmd}" in stripped or f"| {cmd}" in stripped:
                return "ask", "network command"

        # Default: allow (most commands are fine)
        return "allow", ""
