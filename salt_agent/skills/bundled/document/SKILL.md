---
name: document
description: Generate documentation for code and APIs
user-invocable: true
---
# Generate Documentation

Create or update project documentation:

1. Analyze the codebase structure:
   - Read key modules and their public APIs
   - Identify entry points, configuration, and data models
2. Generate appropriate documentation:
   - README.md: project overview, setup, usage, contributing
   - API docs: endpoint descriptions, request/response schemas
   - Module docs: purpose, key classes, usage examples
   - Architecture docs: data flow, component interactions
3. Add or update docstrings:
   - Module-level docstrings explaining purpose
   - Class docstrings with attributes
   - Function docstrings with Args, Returns, Raises
4. Generate usage examples for key features
5. Document configuration options and environment variables
6. Verify all code references are accurate (imports exist, functions are real)
7. Keep documentation concise -- prefer examples over lengthy prose
