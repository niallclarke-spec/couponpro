#!/usr/bin/env python3
"""
Database schema validation script.
Checks that the database schema matches what the code expects.
Prints missing tables/columns and exits non-zero if mismatches found.
"""
import os
import sys
import psycopg2

EXPECTED_SCHEMA = {
    'tenants': {
        'id': 'character varying',
        'name': 'character varying',
        'created_at': 'timestamp',
        'is_active': 'boolean',
        'display_name': 'text',
        'owner_email': 'text',
        'status': 'text',
        'last_seen_at': 'timestamp',
    },
    'tenant_users': {
        'id': 'integer',
        'clerk_user_id': 'character varying',
        'tenant_id': 'character varying',
        'email': 'character varying',
        'role': 'character varying',
        'created_at': 'timestamp',
    },
    'tenant_integrations': {
        'id': 'integer',
        'tenant_id': 'character varying',
        'provider': 'character varying',
        'config_json': 'jsonb',
        'created_at': 'timestamp',
        'updated_at': 'timestamp',
    },
    'tenant_bot_connections': {
        'id': 'integer',
        'tenant_id': 'character varying',
        'bot_role': 'character varying',
        'bot_token': 'text',
        'bot_username': 'character varying',
        'channel_id': 'character varying',
        'webhook_secret': 'character varying',
        'created_at': 'timestamp',
    },
    'onboarding_state': {
        'tenant_id': 'character varying',
        'current_step': 'integer',
        'telegram_completed': 'boolean',
        'stripe_completed': 'boolean',
        'business_completed': 'boolean',
        'is_complete': 'boolean',
        'progress_json': 'jsonb',
        'created_at': 'timestamp',
        'updated_at': 'timestamp',
    },
    'clerk_users': {
        'id': 'integer',
        'clerk_user_id': 'text',
        'email': 'text',
        'name': 'text',
        'avatar_url': 'text',
        'role': 'text',
        'tenant_id': 'text',
        'created_at': 'timestamp',
        'last_login_at': 'timestamp',
    },
    'forex_signals': {
        'id': 'integer',
        'tenant_id': 'character varying',
        'signal_type': 'character varying',
        'pair': 'character varying',
        'timeframe': 'character varying',
        'entry_price': 'numeric',
        'take_profit': 'numeric',
        'stop_loss': 'numeric',
        'status': 'character varying',
        'posted_at': 'timestamp',
        'telegram_message_id': 'bigint',
        'bot_type': 'character varying',
    },
    'forex_config': {
        'id': 'integer',
        'tenant_id': 'character varying',
        'setting_key': 'character varying',
        'setting_value': 'text',
        'updated_at': 'timestamp',
    },
    'telegram_subscriptions': {
        'id': 'integer',
        'tenant_id': 'character varying',
        'email': 'character varying',
        'telegram_user_id': 'bigint',
        'telegram_username': 'character varying',
        'status': 'character varying',
        'created_at': 'timestamp',
    },
    'bot_users': {
        'tenant_id': 'character varying',
        'chat_id': 'bigint',
        'username': 'character varying',
        'first_name': 'character varying',
        'last_name': 'character varying',
        'first_used': 'timestamp',
        'last_used': 'timestamp',
    },
    'bot_usage': {
        'id': 'integer',
        'tenant_id': 'character varying',
        'chat_id': 'bigint',
        'template_slug': 'character varying',
        'coupon_code': 'character varying',
        'success': 'boolean',
        'error_type': 'character varying',
        'device_type': 'character varying',
        'created_at': 'timestamp',
    },
    'bot_config': {
        'id': 'integer',
        'tenant_id': 'character varying',
        'setting_key': 'character varying',
        'setting_value': 'text',
        'updated_at': 'timestamp',
    },
    'broadcast_jobs': {
        'id': 'integer',
        'tenant_id': 'character varying',
        'message': 'text',
        'status': 'character varying',
        'created_at': 'timestamp',
    },
    'journeys': {
        'id': 'uuid',
        'tenant_id': 'character varying',
        'bot_id': 'character varying',
        'name': 'character varying',
        'description': 'text',
        'status': 'character varying',
        're_entry_policy': 'character varying',
        'created_at': 'timestamp',
        'updated_at': 'timestamp',
    },
    'journey_triggers': {
        'id': 'uuid',
        'journey_id': 'uuid',
        'trigger_type': 'character varying',
        'trigger_config': 'jsonb',
        'is_active': 'boolean',
        'created_at': 'timestamp',
    },
    'journey_steps': {
        'id': 'uuid',
        'journey_id': 'uuid',
        'step_order': 'integer',
        'step_type': 'character varying',
        'config': 'jsonb',
        'created_at': 'timestamp',
    },
    'journey_user_sessions': {
        'id': 'uuid',
        'journey_id': 'uuid',
        'tenant_id': 'character varying',
        'telegram_chat_id': 'bigint',
        'current_step_id': 'uuid',
        'status': 'character varying',
        'started_at': 'timestamp',
        'last_activity_at': 'timestamp',
    },
    'journey_scheduled_messages': {
        'id': 'uuid',
        'session_id': 'uuid',
        'step_id': 'uuid',
        'scheduled_for': 'timestamp',
        'status': 'character varying',
        'created_at': 'timestamp',
    },
    'tenant_crosspromo_settings': {
        'tenant_id': 'character varying',
        'enabled': 'boolean',
        'free_channel_id': 'character varying',
        'vip_channel_id': 'character varying',
        'created_at': 'timestamp',
        'updated_at': 'timestamp',
    },
    'crosspromo_jobs': {
        'id': 'uuid',
        'tenant_id': 'character varying',
        'job_type': 'character varying',
        'status': 'character varying',
        'run_at': 'timestamp',
        'created_at': 'timestamp',
    },
    'processed_webhook_events': {
        'tenant_id': 'character varying',
        'event_id': 'character varying',
        'event_source': 'character varying',
        'processed_at': 'timestamp',
    },
}

REQUIRED_UNIQUE_CONSTRAINTS = {
    'tenant_bot_connections': [('tenant_id', 'bot_role')],
    'forex_config': [('tenant_id', 'setting_key')],
    'bot_config': [('tenant_id', 'setting_key')],
    'telegram_subscriptions': [('tenant_id', 'email')],
    'bot_users': [('tenant_id', 'chat_id')],
    'processed_webhook_events': [('tenant_id', 'event_id')],
}

REQUIRED_INDEXES = {
    'tenant_users': ['idx_tenant_users_tenant_id', 'idx_tenant_users_email'],
    'tenant_integrations': ['idx_tenant_integrations_tenant_id'],
    'journeys': ['idx_journeys_tenant_status'],
    'clerk_users': ['idx_clerk_users_email', 'idx_clerk_users_clerk_user_id'],
}


def get_db_connection():
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        print("ERROR: DATABASE_URL environment variable not set")
        sys.exit(1)
    return psycopg2.connect(database_url, sslmode='prefer', connect_timeout=10)


def get_existing_tables(cursor):
    cursor.execute("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
    """)
    return {row[0] for row in cursor.fetchall()}


def get_table_columns(cursor, table_name):
    cursor.execute("""
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_schema = 'public' AND table_name = %s
    """, (table_name,))
    return {row[0]: row[1] for row in cursor.fetchall()}


def get_unique_constraints(cursor, table_name):
    """Get unique constraints grouped by constraint name as list of tuples."""
    cursor.execute("""
        SELECT tc.constraint_name, kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu 
            ON tc.constraint_name = kcu.constraint_name 
            AND tc.table_schema = kcu.table_schema
        WHERE tc.table_name = %s 
            AND tc.constraint_type = 'UNIQUE'
            AND tc.table_schema = 'public'
        ORDER BY tc.constraint_name, kcu.ordinal_position
    """, (table_name,))
    
    constraints = {}
    for row in cursor.fetchall():
        constraint_name, col_name = row
        if constraint_name not in constraints:
            constraints[constraint_name] = []
        constraints[constraint_name].append(col_name)
    
    return [tuple(cols) for cols in constraints.values()]


def get_indexes(cursor, table_name):
    cursor.execute("""
        SELECT indexname 
        FROM pg_indexes 
        WHERE tablename = %s AND schemaname = 'public'
    """, (table_name,))
    return {row[0] for row in cursor.fetchall()}


def normalize_type(data_type):
    """Normalize data types for comparison (ignore precision differences)."""
    type_map = {
        'timestamp without time zone': 'timestamp',
        'timestamp with time zone': 'timestamp',
        'character varying': 'character varying',
        'varchar': 'character varying',
        'int': 'integer',
        'int4': 'integer',
        'serial': 'integer',
        'bigserial': 'bigint',
        'int8': 'bigint',
        'bool': 'boolean',
        'decimal': 'numeric',
        'double precision': 'numeric',
        'real': 'numeric',
    }
    return type_map.get(data_type, data_type)


def main():
    print("=" * 60)
    print("DATABASE SCHEMA VALIDATION")
    print("=" * 60)
    print()
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
    except Exception as e:
        print(f"ERROR: Could not connect to database: {e}")
        sys.exit(1)
    
    existing_tables = get_existing_tables(cursor)
    
    missing_tables = []
    missing_columns = []
    type_mismatches = []
    missing_indexes = []
    extra_info = []
    
    print("[1] Checking Tables...")
    for table_name in sorted(EXPECTED_SCHEMA.keys()):
        if table_name not in existing_tables:
            missing_tables.append(table_name)
            print(f"  MISSING TABLE: {table_name}")
        else:
            print(f"  OK: {table_name}")
    print()
    
    print("[2] Checking Columns...")
    for table_name, expected_columns in sorted(EXPECTED_SCHEMA.items()):
        if table_name not in existing_tables:
            continue
        
        actual_columns = get_table_columns(cursor, table_name)
        table_has_issues = False
        
        for col_name, expected_type in expected_columns.items():
            if col_name not in actual_columns:
                missing_columns.append((table_name, col_name, expected_type))
                print(f"  MISSING: {table_name}.{col_name} (expected: {expected_type})")
                table_has_issues = True
            else:
                actual_type = normalize_type(actual_columns[col_name])
                expected_normalized = normalize_type(expected_type)
                if actual_type != expected_normalized:
                    type_mismatches.append((table_name, col_name, expected_normalized, actual_type))
                    print(f"  TYPE MISMATCH: {table_name}.{col_name} (expected: {expected_normalized}, actual: {actual_type})")
                    table_has_issues = True
        
        extra_cols = set(actual_columns.keys()) - set(expected_columns.keys())
        if extra_cols:
            extra_info.append((table_name, list(extra_cols)))
        
        if not table_has_issues:
            print(f"  OK: {table_name} (all {len(expected_columns)} columns present)")
    print()
    
    print("[3] Checking Required Indexes...")
    for table_name, expected_indexes in sorted(REQUIRED_INDEXES.items()):
        if table_name not in existing_tables:
            continue
        
        actual_indexes = get_indexes(cursor, table_name)
        for idx_name in expected_indexes:
            if idx_name not in actual_indexes:
                missing_indexes.append((table_name, idx_name))
                print(f"  MISSING INDEX: {table_name}.{idx_name}")
            else:
                print(f"  OK: {table_name}.{idx_name}")
    print()
    
    print("[4] Checking Unique Constraints...")
    missing_constraints = []
    for table_name, constraints in sorted(REQUIRED_UNIQUE_CONSTRAINTS.items()):
        if table_name not in existing_tables:
            continue
        
        actual_constraints = get_unique_constraints(cursor, table_name)
        for expected_cols in constraints:
            expected_tuple = tuple(expected_cols)
            if expected_tuple in actual_constraints:
                print(f"  OK: {table_name} UNIQUE({', '.join(expected_cols)})")
            else:
                missing_constraints.append((table_name, expected_cols))
                print(f"  MISSING: {table_name} UNIQUE({', '.join(expected_cols)})")
    print()
    
    cursor.close()
    conn.close()
    
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    total_issues = len(missing_tables) + len(missing_columns) + len(type_mismatches) + len(missing_constraints)
    
    if missing_tables:
        print(f"\nMissing Tables ({len(missing_tables)}):")
        for table in missing_tables:
            print(f"  - {table}")
    
    if missing_columns:
        print(f"\nMissing Columns ({len(missing_columns)}):")
        for table, col, expected_type in missing_columns:
            print(f"  - {table}.{col} ({expected_type})")
    
    if type_mismatches:
        print(f"\nType Mismatches ({len(type_mismatches)}):")
        for table, col, expected, actual in type_mismatches:
            print(f"  - {table}.{col}: expected {expected}, got {actual}")
    
    if missing_indexes:
        print(f"\nMissing Indexes ({len(missing_indexes)}):")
        for table, idx in missing_indexes:
            print(f"  - {table}.{idx}")
    
    if missing_constraints:
        print(f"\nMissing Unique Constraints ({len(missing_constraints)}):")
        for table, cols in missing_constraints:
            print(f"  - {table} UNIQUE({', '.join(cols)})")
    
    if extra_info:
        print(f"\nExtra Columns (not in expected schema, may be OK):")
        for table, cols in extra_info:
            print(f"  - {table}: {', '.join(cols)}")
    
    print()
    if total_issues == 0:
        print("STATUS: SCHEMA VALID")
        sys.exit(0)
    else:
        print(f"STATUS: {total_issues} ISSUES FOUND")
        print("\nTo fix missing columns, the app's init_db() should add them on startup.")
        print("If issues persist, create a migration script to add missing columns.")
        sys.exit(1)


if __name__ == '__main__':
    main()
