-- RLS Phase 2: Row-Level Security Policies for Multi-Tenant Isolation
-- 
-- WARNING: DO NOT AUTO-RUN THIS MIGRATION
-- This file is a scaffold for future RLS implementation.
-- Run manually after thorough testing in staging environment.
--
-- Prerequisites:
-- 1. All tenant-aware tables must have tenant_id column
-- 2. Application must SET app.tenant_id on each connection
-- 3. ENABLE_RLS=1 environment variable must be set
--

-- Enable RLS on tenant-aware tables
ALTER TABLE forex_signals ENABLE ROW LEVEL SECURITY;
ALTER TABLE forex_config ENABLE ROW LEVEL SECURITY;
ALTER TABLE bot_config ENABLE ROW LEVEL SECURITY;
ALTER TABLE telegram_subscriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE bot_usage ENABLE ROW LEVEL SECURITY;

-- Create RLS policies using current_setting('app.tenant_id')
-- Policy: Users can only see rows where tenant_id matches their session setting

CREATE POLICY tenant_isolation_forex_signals ON forex_signals
    USING (tenant_id = current_setting('app.tenant_id', true));

CREATE POLICY tenant_isolation_forex_config ON forex_config
    USING (tenant_id = current_setting('app.tenant_id', true));

CREATE POLICY tenant_isolation_bot_config ON bot_config
    USING (tenant_id = current_setting('app.tenant_id', true));

CREATE POLICY tenant_isolation_telegram_subscriptions ON telegram_subscriptions
    USING (tenant_id = current_setting('app.tenant_id', true));

CREATE POLICY tenant_isolation_bot_usage ON bot_usage
    USING (tenant_id = current_setting('app.tenant_id', true));

-- Note: The second parameter 'true' in current_setting makes it return NULL 
-- instead of error if the setting doesn't exist. This provides a safe fallback.
--
-- ROLLBACK COMMANDS (if needed):
-- DROP POLICY tenant_isolation_forex_signals ON forex_signals;
-- DROP POLICY tenant_isolation_forex_config ON forex_config;
-- DROP POLICY tenant_isolation_bot_config ON bot_config;
-- DROP POLICY tenant_isolation_telegram_subscriptions ON telegram_subscriptions;
-- DROP POLICY tenant_isolation_bot_usage ON bot_usage;
-- ALTER TABLE forex_signals DISABLE ROW LEVEL SECURITY;
-- ALTER TABLE forex_config DISABLE ROW LEVEL SECURITY;
-- ALTER TABLE bot_config DISABLE ROW LEVEL SECURITY;
-- ALTER TABLE telegram_subscriptions DISABLE ROW LEVEL SECURITY;
-- ALTER TABLE bot_usage DISABLE ROW LEVEL SECURITY;
