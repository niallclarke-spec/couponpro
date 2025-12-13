# Migration Verification Scripts

## verify_migrations.py

Verifies that all multi-tenancy database migrations are correctly applied.

### Usage
```bash
python3 scripts/verify_migrations.py
```

### What it checks
- New tables: tenants, tenant_users, tenant_integrations
- EntryLab seed exists
- tenant_id columns added to 9 tables with correct defaults
- processed_webhook_events migrated correctly
- db.py helper functions use correct SQL
- Stripe webhook caller uses correct parameters

### Exit codes
- 0: All checks passed
- 1: One or more checks failed
