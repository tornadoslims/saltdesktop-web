"""Shown when MCP resource has no content"""

PROMPT = '''
<!--
name: 'System Reminder: MCP resource no content'
description: Shown when MCP resource has no content
ccVersion: 2.1.18
variables:
  - ATTACHMENT_OBJECT
-->
<mcp-resource server="${ATTACHMENT_OBJECT.server}" uri="${ATTACHMENT_OBJECT.uri}">(No content)</mcp-resource>

'''

# Metadata
NAME = "mcp_resource_no_content"
CATEGORY = "fragment"
DESCRIPTION = """Shown when MCP resource has no content"""
