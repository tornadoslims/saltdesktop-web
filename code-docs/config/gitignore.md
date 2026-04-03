# .gitignore

**Path:** `.gitignore`
**Purpose:** Defines files excluded from version control.

## Key Exclusions

- **Python artifacts**: `__pycache__/`, `*.pyc`, `.venv/`, `*.egg-info/`, `dist/`, `build/`
- **User data**: `data/jbcp.db` (SQLite database), `data/signals/`, `data/companies/`, `logs/`, `pipelines/`, `components/` -- all generated at runtime
- **Secrets**: `.env`, `*.secret`, `secrets.json`
- **OS files**: `.DS_Store`, `Thumbs.db`
- **Node**: `node_modules/`
- **IDE**: `.idea/`, `.vscode/`, `*.swp`
- **Temp**: `nohup.out`, `*.tmp`

The database and all runtime-generated data are excluded, so each developer/installation starts fresh.
