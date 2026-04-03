"""Bash tool instruction: do not poll background tasks, wait for notification"""

PROMPT = '''
<!--
name: 'Tool Description: Bash (sleep — no polling background tasks)'
description: Bash tool instruction: do not poll background tasks, wait for notification
ccVersion: 2.1.53
-->
If waiting for a background task you started with `run_in_background`, you will be notified when it completes — do not poll.

'''

# Metadata
NAME = "bash_sleep_no_polling_background_tasks"
CATEGORY = "tool"
DESCRIPTION = """Bash tool instruction: do not poll background tasks, wait for notification"""
