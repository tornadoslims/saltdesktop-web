"""Reminder to verify completed plan"""

PROMPT = '''
<!--
name: 'System Reminder: Verify plan reminder'
description: Reminder to verify completed plan
ccVersion: 2.1.18
variables:
  - TASK_TOOL_NAME
-->
You have completed implementing the plan. Please call the "" tool directly (NOT the ${TASK_TOOL_NAME} tool or an agent) to verify that all plan items were completed correctly.

'''

# Metadata
NAME = "verify_plan_reminder"
CATEGORY = "fragment"
DESCRIPTION = """Reminder to verify completed plan"""
