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

## RLS Phase 2 Implementation

Row-Level Security (RLS) Phase 2 provides database-enforced tenant isolation as an additional defense layer beyond application-level filtering.

### Covered Tables

RLS policies are defined for all 10 tenant-aware tables:
- `forex_signals`
- `forex_config`
- `bot_config`
- `telegram_subscriptions`
- `recent_phrases`
- `campaigns`
- `bot_usage`
- `bot_users`
- `broadcast_jobs`
- `processed_webhook_events`

### How to Apply the Migration

Apply the RLS policies manually after testing in staging:

```bash
psql $DATABASE_URL -f migrations/rls_phase2.sql
```

### How to Enable RLS

Set the `ENABLE_RLS` environment variable:

```bash
export ENABLE_RLS=1
```

When enabled, the application will execute `SET LOCAL app.tenant_id = '<tenant_id>'` on each database connection before executing queries.

### Using the tenant_conn() Helper

The `tenant_conn()` context manager provides a convenient way to execute tenant-scoped database operations:

```python
from db import tenant_conn

with tenant_conn('tenant_123') as (conn, cursor):
    cursor.execute("SELECT * FROM forex_signals")
    rows = cursor.fetchall()
```

This helper:
- Gets a connection from the pool
- Begins a transaction
- Sets `app.tenant_id` when `ENABLE_RLS=1`
- Yields `(connection, cursor)` for your operations
- Commits on success, rolls back on error
- Returns the connection to the pool

### Expected Behavior When app.tenant_id Is Not Set

When RLS is enabled and `app.tenant_id` is not set (or set to a non-matching value):
- **SELECT queries** return empty results (no rows visible)
- **INSERT queries** fail with policy violation (if tenant_id doesn't match session)
- **UPDATE/DELETE queries** affect zero rows (no matching rows visible)

This provides a safe default: if tenant context is missing, queries are denied rather than exposing data.

### Rollback Instructions

If issues occur after enabling RLS:

**Step 1: Disable the flag**
```bash
unset ENABLE_RLS
# or set ENABLE_RLS=0
```

**Step 2: Remove RLS policies (if needed)**
```sql
-- Run these commands to completely remove RLS
DROP POLICY IF EXISTS tenant_isolation_forex_signals ON forex_signals;
DROP POLICY IF EXISTS tenant_isolation_forex_config ON forex_config;
DROP POLICY IF EXISTS tenant_isolation_bot_config ON bot_config;
DROP POLICY IF EXISTS tenant_isolation_telegram_subscriptions ON telegram_subscriptions;
DROP POLICY IF EXISTS tenant_isolation_recent_phrases ON recent_phrases;
DROP POLICY IF EXISTS tenant_isolation_campaigns ON campaigns;
DROP POLICY IF EXISTS tenant_isolation_bot_usage ON bot_usage;
DROP POLICY IF EXISTS tenant_isolation_bot_users ON bot_users;
DROP POLICY IF EXISTS tenant_isolation_broadcast_jobs ON broadcast_jobs;
DROP POLICY IF EXISTS tenant_isolation_processed_webhook_events ON processed_webhook_events;

ALTER TABLE forex_signals DISABLE ROW LEVEL SECURITY;
ALTER TABLE forex_config DISABLE ROW LEVEL SECURITY;
ALTER TABLE bot_config DISABLE ROW LEVEL SECURITY;
ALTER TABLE telegram_subscriptions DISABLE ROW LEVEL SECURITY;
ALTER TABLE recent_phrases DISABLE ROW LEVEL SECURITY;
ALTER TABLE campaigns DISABLE ROW LEVEL SECURITY;
ALTER TABLE bot_usage DISABLE ROW LEVEL SECURITY;
ALTER TABLE bot_users DISABLE ROW LEVEL SECURITY;
ALTER TABLE broadcast_jobs DISABLE ROW LEVEL SECURITY;
ALTER TABLE processed_webhook_events DISABLE ROW LEVEL SECURITY;
```

### Testing RLS

Run RLS-specific tests:
```bash
pytest tests/test_rls_setup.py -v
```

Tests verify:
- `tenant_conn()` sets tenant context correctly
- SELECT isolation: queries only return current tenant's rows
- UPDATE isolation: updates only affect current tenant's rows
- Empty results when tenant context is not set

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
