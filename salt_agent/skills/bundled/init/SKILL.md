---
name: init
description: Initialize a new project with standard configuration
user-invocable: true
---
# Initialize Project

Set up a new project from scratch:

1. Ask what type of project (Python, Node.js, Rust, Go, etc.) if not specified
2. Create the project directory structure:
   - Source directory (src/ or package name)
   - Tests directory (tests/)
   - Configuration files (.gitignore, README.md, LICENSE)
3. Initialize version control: `git init`
4. Set up language-specific tooling:
   - Python: pyproject.toml or requirements.txt, virtual environment
   - Node.js: package.json, .nvmrc
   - Rust: Cargo.toml
   - Go: go.mod
5. Create a minimal "hello world" entry point
6. Run initial build/test to verify setup works
7. Create initial commit
