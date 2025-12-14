# Security Documentation

## Multi-tenant Isolation Guarantees

This application implements strict tenant isolation at the application layer to ensure that data belonging to one tenant cannot be accessed, modified, or deleted by another tenant.

### Tenant ID Filtering Requirement

**All database queries on tenant-aware tables MUST include `tenant_id` in the WHERE clause.**

Tenant-aware tables include:
- `campaigns`
- `bot_usage`
- `bot_users`
- `broadcast_jobs`
- `forex_signals`
- `forex_config`
- `bot_config`
- `recent_phrases`
- `telegram_subscriptions`

Every UPDATE and DELETE query targeting these tables must filter by `tenant_id` to prevent cross-tenant data modification.

### Automated Enforcement

#### Static Audit: `scripts/tenant_audit.py`

This script scans `db.py` for UPDATE and DELETE statements on tenant-aware tables and verifies that each includes `tenant_id` in the WHERE clause.

**Usage:**
```bash
python scripts/tenant_audit.py
```

**Exit codes:**
- `0` - All queries pass tenant isolation check
- `1` - Found queries missing `tenant_id` filtering

#### Test Gate: `test_tenant_audit_gate.py`

This pytest test executes the tenant audit script as part of the CI pipeline. If any isolation issues are detected, the test fails and blocks the build.

```bash
pytest tests/test_tenant_audit_gate.py -v
```

#### Integration Test: `test_tenant_isolation_update.py`

This "evil" test proves that tenant isolation cannot be bypassed at runtime:
1. Creates test data for two separate tenants
2. Attempts to update Tenant A's data
3. Verifies Tenant A's data IS updated
4. Verifies Tenant B's data is NOT modified

```bash
pytest tests/test_tenant_isolation_update.py -v
```

### Runtime Tripwire

The server includes a `log_tenant_context()` helper that logs tenant context on every request to tenant-aware API paths. If a request reaches a tenant-required path without a valid `tenant_id`, it raises an exception and logs a tripwire alert.

---

## Row Level Security (RLS) Feasibility Plan

### Overview

PostgreSQL Row Level Security (RLS) provides database-enforced tenant isolation as an additional defense layer. This section outlines how RLS could be implemented for this application.

### Migration Sketch for `forex_signals` Table

```sql
-- Step 1: Enable RLS on the table
ALTER TABLE forex_signals ENABLE ROW LEVEL SECURITY;

-- Step 2: Create policy that restricts access based on session variable
CREATE POLICY tenant_isolation_policy ON forex_signals
    USING (tenant_id = current_setting('app.current_tenant', true)::text)
    WITH CHECK (tenant_id = current_setting('app.current_tenant', true)::text);

-- Step 3: Force RLS for all roles (including table owner)
ALTER TABLE forex_signals FORCE ROW LEVEL SECURITY;

-- Step 4: At connection time, set the tenant context
-- This would be done in Python before executing queries:
-- cursor.execute("SET app.current_tenant = %s", (tenant_id,))
```

### Pros

1. **DB-enforced isolation**: Security is enforced at the database level, not just application code
2. **Defense in depth**: Even if application code has a bug, the database prevents cross-tenant access
3. **Queries can't accidentally bypass**: Developers cannot forget to add `tenant_id` filters; the database enforces it automatically
4. **Transparent to application**: Once configured, existing queries work without modification

### Cons

1. **Complexity**: Requires careful migration planning and testing
2. **Session variable management**: Every database connection must set `app.current_tenant` before executing queries
3. **Performance overhead**: RLS adds a small overhead to every query as PostgreSQL evaluates the policy
4. **Connection pooling challenges**: Must ensure tenant context is set correctly when reusing pooled connections
5. **Debugging difficulty**: Query results depend on session state, which can complicate debugging

### Recommendation

**Consider RLS for future implementation.** The current app-level enforcement is solid:
- Static audit catches isolation issues at development time
- Test gate prevents deployment of unsafe code
- Integration tests verify runtime behavior
- Runtime tripwire logs tenant context for audit trail

RLS would add valuable defense-in-depth but requires careful implementation to handle connection pooling and session management. Recommend implementing RLS as a Phase 2 security enhancement after the current app-level controls are battle-tested in production.

---

## RLS Phase 2 Implementation (SCAFFOLD)

### Environment Flag

Set `ENABLE_RLS=1` to enable RLS connection setup:

```bash
export ENABLE_RLS=1
```

When enabled, each database connection will execute:
```sql
SET app.tenant_id = '<tenant_id>'
```

### Migration File

The RLS policies are defined in `migrations/rls_phase2.sql`:
- **DO NOT auto-run** - requires manual execution after testing
- Enables RLS on: `forex_signals`, `forex_config`, `bot_config`, `telegram_subscriptions`, `bot_usage`
- Policy: `USING (tenant_id = current_setting('app.tenant_id', true))`

### Deployment Steps

1. Test in staging environment first
2. Set `ENABLE_RLS=1` in environment
3. Verify application sets tenant context correctly
4. Run migration manually: `psql $DATABASE_URL -f migrations/rls_phase2.sql`
5. Monitor for any access issues

### Rollback

If issues occur, rollback commands are included in the migration file.

---

## Smoke Testing

Run tenant isolation smoke tests:
```bash
make smoke
# or
python scripts/smoke_tenant_isolation.py
```

---

## Scheduler Sharding

Multi-tenant scheduler supports sharding for horizontal scaling:
```bash
# Run all tenants
python forex_scheduler.py --all-tenants --once

# Run specific shard (0 of 3)
python forex_scheduler.py --all-tenants --shard 0/3 --once
```

Sharding uses consistent hashing: `hash(tenant_id) % total_shards == shard_index`
