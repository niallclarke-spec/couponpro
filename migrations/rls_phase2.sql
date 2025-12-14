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
-- Usage:
--   psql $DATABASE_URL -f migrations/rls_phase2.sql
--

-- ============================================================================
-- forex_signals
-- ============================================================================
ALTER TABLE forex_signals ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_forex_signals ON forex_signals;
CREATE POLICY tenant_isolation_forex_signals
ON forex_signals
FOR ALL
USING (tenant_id = current_setting('app.tenant_id', true))
WITH CHECK (tenant_id = current_setting('app.tenant_id', true));

-- ============================================================================
-- forex_config
-- ============================================================================
ALTER TABLE forex_config ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_forex_config ON forex_config;
CREATE POLICY tenant_isolation_forex_config
ON forex_config
FOR ALL
USING (tenant_id = current_setting('app.tenant_id', true))
WITH CHECK (tenant_id = current_setting('app.tenant_id', true));

-- ============================================================================
-- bot_config
-- ============================================================================
ALTER TABLE bot_config ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_bot_config ON bot_config;
CREATE POLICY tenant_isolation_bot_config
ON bot_config
FOR ALL
USING (tenant_id = current_setting('app.tenant_id', true))
WITH CHECK (tenant_id = current_setting('app.tenant_id', true));

-- ============================================================================
-- telegram_subscriptions
-- ============================================================================
ALTER TABLE telegram_subscriptions ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_telegram_subscriptions ON telegram_subscriptions;
CREATE POLICY tenant_isolation_telegram_subscriptions
ON telegram_subscriptions
FOR ALL
USING (tenant_id = current_setting('app.tenant_id', true))
WITH CHECK (tenant_id = current_setting('app.tenant_id', true));

-- ============================================================================
-- recent_phrases
-- ============================================================================
ALTER TABLE recent_phrases ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_recent_phrases ON recent_phrases;
CREATE POLICY tenant_isolation_recent_phrases
ON recent_phrases
FOR ALL
USING (tenant_id = current_setting('app.tenant_id', true))
WITH CHECK (tenant_id = current_setting('app.tenant_id', true));

-- ============================================================================
-- campaigns
-- ============================================================================
ALTER TABLE campaigns ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_campaigns ON campaigns;
CREATE POLICY tenant_isolation_campaigns
ON campaigns
FOR ALL
USING (tenant_id = current_setting('app.tenant_id', true))
WITH CHECK (tenant_id = current_setting('app.tenant_id', true));

-- ============================================================================
-- bot_usage
-- ============================================================================
ALTER TABLE bot_usage ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_bot_usage ON bot_usage;
CREATE POLICY tenant_isolation_bot_usage
ON bot_usage
FOR ALL
USING (tenant_id = current_setting('app.tenant_id', true))
WITH CHECK (tenant_id = current_setting('app.tenant_id', true));

-- ============================================================================
-- bot_users
-- ============================================================================
ALTER TABLE bot_users ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_bot_users ON bot_users;
CREATE POLICY tenant_isolation_bot_users
ON bot_users
FOR ALL
USING (tenant_id = current_setting('app.tenant_id', true))
WITH CHECK (tenant_id = current_setting('app.tenant_id', true));

-- ============================================================================
-- broadcast_jobs
-- ============================================================================
ALTER TABLE broadcast_jobs ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_broadcast_jobs ON broadcast_jobs;
CREATE POLICY tenant_isolation_broadcast_jobs
ON broadcast_jobs
FOR ALL
USING (tenant_id = current_setting('app.tenant_id', true))
WITH CHECK (tenant_id = current_setting('app.tenant_id', true));

-- ============================================================================
-- processed_webhook_events
-- ============================================================================
ALTER TABLE processed_webhook_events ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_processed_webhook_events ON processed_webhook_events;
CREATE POLICY tenant_isolation_processed_webhook_events
ON processed_webhook_events
FOR ALL
USING (tenant_id = current_setting('app.tenant_id', true))
WITH CHECK (tenant_id = current_setting('app.tenant_id', true));

-- ============================================================================
-- Notes:
-- - The second parameter 'true' in current_setting makes it return NULL 
--   instead of error if the setting doesn't exist.
-- - When app.tenant_id is not set, queries will return empty results (safe default).
-- ============================================================================

-- ============================================================================
-- ROLLBACK COMMANDS (if needed):
-- ============================================================================
-- DROP POLICY IF EXISTS tenant_isolation_forex_signals ON forex_signals;
-- DROP POLICY IF EXISTS tenant_isolation_forex_config ON forex_config;
-- DROP POLICY IF EXISTS tenant_isolation_bot_config ON bot_config;
-- DROP POLICY IF EXISTS tenant_isolation_telegram_subscriptions ON telegram_subscriptions;
-- DROP POLICY IF EXISTS tenant_isolation_recent_phrases ON recent_phrases;
-- DROP POLICY IF EXISTS tenant_isolation_campaigns ON campaigns;
-- DROP POLICY IF EXISTS tenant_isolation_bot_usage ON bot_usage;
-- DROP POLICY IF EXISTS tenant_isolation_bot_users ON bot_users;
-- DROP POLICY IF EXISTS tenant_isolation_broadcast_jobs ON broadcast_jobs;
-- DROP POLICY IF EXISTS tenant_isolation_processed_webhook_events ON processed_webhook_events;
-- ALTER TABLE forex_signals DISABLE ROW LEVEL SECURITY;
-- ALTER TABLE forex_config DISABLE ROW LEVEL SECURITY;
-- ALTER TABLE bot_config DISABLE ROW LEVEL SECURITY;
-- ALTER TABLE telegram_subscriptions DISABLE ROW LEVEL SECURITY;
-- ALTER TABLE recent_phrases DISABLE ROW LEVEL SECURITY;
-- ALTER TABLE campaigns DISABLE ROW LEVEL SECURITY;
-- ALTER TABLE bot_usage DISABLE ROW LEVEL SECURITY;
-- ALTER TABLE bot_users DISABLE ROW LEVEL SECURITY;
-- ALTER TABLE broadcast_jobs DISABLE ROW LEVEL SECURITY;
-- ALTER TABLE processed_webhook_events DISABLE ROW LEVEL SECURITY;
