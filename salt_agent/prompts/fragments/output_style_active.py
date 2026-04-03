"""Notification that an output style is active"""

PROMPT = '''
<!--
name: 'System Reminder: Output style active'
description: Notification that an output style is active
ccVersion: 2.1.18
variables:
  - OUTPUT_STYLE_CONFIG
-->
${OUTPUT_STYLE_CONFIG.name} output style is active. Remember to follow the specific guidelines for this style.

'''

# Metadata
NAME = "output_style_active"
CATEGORY = "fragment"
DESCRIPTION = """Notification that an output style is active"""
