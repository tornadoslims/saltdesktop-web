---
name: migrate
description: Create and run database migrations
user-invocable: true
---
# Database Migration

Handle database schema changes safely:

1. Identify the migration framework in use (Alembic, Django, Prisma, Knex, etc.)
2. Review the current schema and pending changes
3. Generate a new migration:
   - Alembic: `alembic revision --autogenerate -m "description"`
   - Django: `python manage.py makemigrations`
   - Prisma: `npx prisma migrate dev --name description`
4. Review the generated migration file for correctness:
   - Check for data loss risks (column drops, type changes)
   - Verify rollback/downgrade path exists
   - Ensure indexes are created for new foreign keys
5. Run the migration against the development database
6. Verify the schema matches expectations
7. Warn about any destructive operations that need manual review
