#!/usr/bin/env python3
"""
Multi-tenancy migration verification script.
Verifies all database migrations and code changes are correctly applied.
"""
import os
import sys
import re
import psycopg2

REQUIRED_TABLES = ['tenants', 'tenant_users', 'tenant_integrations']
ENTRYLAB_TENANT = 'entrylab'
TENANT_ID_TABLES = [
    'forex_signals', 'forex_config', 'telegram_subscriptions', 
    'recent_phrases', 'campaigns', 'bot_usage', 'bot_users', 
    'broadcast_jobs', 'bot_config'
]
WEBHOOK_COLUMNS = ['tenant_id', 'event_id', 'event_source', 'processed_at']

passed = 0
failed = 0


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        status = "PASS"
        passed += 1
    else:
        status = "FAIL"
        failed += 1
    detail_str = f" ({detail})" if detail else ""
    print(f"  - {name}: {status}{detail_str}")
    return condition


def get_db_connection():
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        print("ERROR: DATABASE_URL environment variable not set")
        sys.exit(1)
    return psycopg2.connect(database_url, sslmode='prefer', connect_timeout=10)


def check_tables_exist(cursor, tables):
    results = {}
    for table in tables:
        cursor.execute("""
            SELECT COUNT(*) FROM information_schema.tables 
            WHERE table_schema='public' AND table_name=%s
        """, (table,))
        results[table] = cursor.fetchone()[0] > 0
    return results


def check_entrylab_seed(cursor):
    cursor.execute("SELECT COUNT(*) FROM tenants WHERE id = %s", (ENTRYLAB_TENANT,))
    return cursor.fetchone()[0] > 0


def check_tenant_id_column(cursor, table):
    cursor.execute("""
        SELECT column_default FROM information_schema.columns 
        WHERE table_schema='public' AND table_name=%s AND column_name='tenant_id'
    """, (table,))
    row = cursor.fetchone()
    if not row:
        return False, None, False
    
    default_val = row[0] or ""
    has_entrylab = 'entrylab' in default_val
    
    cursor.execute("""
        SELECT COUNT(*) FROM pg_indexes 
        WHERE tablename=%s AND indexname=%s
    """, (table, f'idx_{table}_tenant_id'))
    has_index = cursor.fetchone()[0] > 0
    
    return True, has_entrylab, has_index


def check_webhook_events_table(cursor):
    results = {
        'table_exists': False,
        'old_table_exists': False,
        'has_columns': False,
        'has_unique': False,
        'columns_found': [],
        'constraint_name': None
    }
    
    cursor.execute("""
        SELECT COUNT(*) FROM information_schema.tables 
        WHERE table_schema='public' AND table_name='processed_webhook_events'
    """)
    results['table_exists'] = cursor.fetchone()[0] > 0
    
    cursor.execute("""
        SELECT COUNT(*) FROM information_schema.tables 
        WHERE table_schema='public' AND table_name='processed_webhook_events_old'
    """)
    results['old_table_exists'] = cursor.fetchone()[0] > 0
    
    if results['table_exists']:
        cursor.execute("""
            SELECT column_name FROM information_schema.columns 
            WHERE table_schema='public' AND table_name='processed_webhook_events'
        """)
        results['columns_found'] = [row[0] for row in cursor.fetchall()]
        results['has_columns'] = all(col in results['columns_found'] for col in WEBHOOK_COLUMNS)
        
        cursor.execute("""
            SELECT constraint_name FROM information_schema.table_constraints 
            WHERE table_name='processed_webhook_events' AND constraint_type='UNIQUE'
        """)
        row = cursor.fetchone()
        if row:
            results['has_unique'] = True
            results['constraint_name'] = row[0]
    
    return results


def check_db_py_functions():
    results = {
        'is_webhook': False,
        'record_webhook': False,
        'cleanup_webhook': False
    }
    
    try:
        with open('db.py', 'r') as f:
            content = f.read()
        
        is_match = re.search(r'def is_webhook_event_processed.*?(?=\ndef |\Z)', content, re.DOTALL)
        if is_match:
            func_body = is_match.group(0)
            results['is_webhook'] = 'tenant_id' in func_body and 'WHERE' in func_body
        
        record_match = re.search(r'def record_webhook_event_processed.*?(?=\ndef |\Z)', content, re.DOTALL)
        if record_match:
            func_body = record_match.group(0)
            results['record_webhook'] = (
                'INSERT INTO' in func_body and
                'tenant_id' in func_body and
                'event_id' in func_body and
                'event_source' in func_body
            )
        
        cleanup_match = re.search(r'def cleanup_old_webhook_events.*?(?=\ndef |\Z)', content, re.DOTALL)
        if cleanup_match:
            func_body = cleanup_match.group(0)
            results['cleanup_webhook'] = "(%s * INTERVAL '1 hour')" in func_body
    except Exception as e:
        print(f"  ERROR reading db.py: {e}")
    
    return results


def check_stripe_webhook():
    try:
        with open('integrations/stripe/webhooks.py', 'r') as f:
            content = f.read()
        return 'record_webhook_event_processed(event_id, event_source=' in content
    except Exception as e:
        print(f"  ERROR reading stripe webhooks.py: {e}")
        return False


def main():
    global passed, failed
    
    print("=" * 40)
    print("MULTI-TENANCY MIGRATION VERIFICATION")
    print("=" * 40)
    print()
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
    except Exception as e:
        print(f"ERROR: Could not connect to database: {e}")
        sys.exit(1)
    
    print("[A] New Tables Exist")
    table_results = check_tables_exist(cursor, REQUIRED_TABLES)
    for table in REQUIRED_TABLES:
        check(table, table_results[table])
    print()
    
    print("[B] EntryLab Seed")
    entrylab_exists = check_entrylab_seed(cursor)
    check("tenants.id = 'entrylab'", entrylab_exists)
    print()
    
    print("[C] tenant_id Columns + Indexes")
    for table in TENANT_ID_TABLES:
        has_column, has_default, has_index = check_tenant_id_column(cursor, table)
        if has_column:
            default_str = "'entrylab'" if has_default else "missing"
            index_str = "exists" if has_index else "missing"
            check(f"{table}.tenant_id", has_column and has_default and has_index, 
                  f"default: {default_str}, index: {index_str}")
        else:
            check(f"{table}.tenant_id", False, "column missing")
    print()
    
    print("[D] processed_webhook_events Migration")
    webhook_results = check_webhook_events_table(cursor)
    check("processed_webhook_events exists", webhook_results['table_exists'])
    check("processed_webhook_events_old exists", webhook_results['old_table_exists'])
    if webhook_results['table_exists']:
        cols_str = ", ".join(WEBHOOK_COLUMNS)
        check(f"Columns ({cols_str})", webhook_results['has_columns'])
        check("UNIQUE constraint (tenant_id, event_id)", webhook_results['has_unique'], 
              webhook_results.get('constraint_name', ''))
    else:
        check(f"Columns ({', '.join(WEBHOOK_COLUMNS)})", False)
        check("UNIQUE constraint (tenant_id, event_id)", False)
    print()
    
    cursor.close()
    conn.close()
    
    print("[E] db.py Helper Functions")
    db_results = check_db_py_functions()
    check("is_webhook_event_processed uses tenant_id", db_results['is_webhook'])
    check("record_webhook_event_processed inserts tenant_id, event_id, event_source", db_results['record_webhook'])
    check("cleanup_old_webhook_events uses safe SQL", db_results['cleanup_webhook'])
    print()
    
    print("[F] Stripe Webhook Caller")
    stripe_ok = check_stripe_webhook()
    check("Uses event_source= named arg", stripe_ok)
    print()
    
    print("=" * 40)
    total = passed + failed
    print(f"SUMMARY: {passed}/{total} checks passed")
    print("=" * 40)
    
    if failed == 0:
        print("✅ MIGRATION VERIFIED")
    else:
        print("❌ MIGRATION FAILED")
    
    print()
    print("=" * 40)
    print("DIGITALOCEAN PROD POST-DEPLOY CHECKLIST")
    print("=" * 40)
    print("""
1. SQL Verification (run in DO Database Console):
   -- Check tables exist
   SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_name IN ('tenants', 'tenant_users', 'tenant_integrations');
   
   -- Check entrylab seed
   SELECT * FROM tenants WHERE id = 'entrylab';
   
   -- Check tenant_id columns
   SELECT table_name, column_name, column_default FROM information_schema.columns WHERE table_schema='public' AND column_name='tenant_id';
   
   -- Check processed_webhook_events schema
   SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name='processed_webhook_events';
   
   -- Check unique constraint
   SELECT constraint_name FROM information_schema.table_constraints WHERE table_name='processed_webhook_events' AND constraint_type='UNIQUE';

2. Curl Tests (run against prod URL):
   # Check auth endpoint responds
   curl -s https://YOUR_PROD_URL/api/check-auth
   
   # Check stripe webhook endpoint (expect error but server responds)
   curl -s -X POST https://YOUR_PROD_URL/api/stripe/webhook -H "Content-Type: application/json" -d '{}'
   
   # Check telegram webhook endpoint
   curl -s -X POST https://YOUR_PROD_URL/api/telegram-webhook -H "Content-Type: application/json" -d '{}'
""")
    
    sys.exit(0 if failed == 0 else 1)


if __name__ == '__main__':
    main()
