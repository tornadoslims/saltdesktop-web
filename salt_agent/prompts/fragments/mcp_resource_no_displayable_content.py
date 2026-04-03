"""Shown when MCP resource has no displayable content"""

PROMPT = '''
<!--
name: 'System Reminder: MCP resource no displayable content'
description: Shown when MCP resource has no displayable content
ccVersion: 2.1.18
variables:
  - ATTACHMENT_OBJECT
-->
<mcp-resource server="${ATTACHMENT_OBJECT.server}" uri="${ATTACHMENT_OBJECT.uri}">(No displayable content)</mcp-resource>

'''

# Metadata
NAME = "mcp_resource_no_displayable_content"
CATEGORY = "fragment"
DESCRIPTION = """Shown when MCP resource has no displayable content"""
