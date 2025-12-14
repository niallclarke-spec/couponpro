#!/usr/bin/env python3
"""
Tenant Isolation Audit Script

Scans db.py for UPDATE/DELETE statements on tenant-aware tables
that don't include tenant_id in the WHERE clause.

Usage:
    python scripts/tenant_audit.py

Exit codes:
    0 - All queries pass tenant isolation check
    1 - Found queries missing tenant_id filtering
"""

import re
import sys
from pathlib import Path

TENANT_AWARE_TABLES = [
    'campaigns',
    'bot_usage',
    'bot_users',
    'broadcast_jobs',
    'forex_signals',
    'forex_config',
    'bot_config',
    'recent_phrases',
    'telegram_subscriptions',
]

def find_db_file():
    """Find db.py relative to script location."""
    script_dir = Path(__file__).parent
    db_file = script_dir.parent / 'db.py'
    if db_file.exists():
        return db_file
    db_file = Path('db.py')
    if db_file.exists():
        return db_file
    raise FileNotFoundError("Cannot find db.py")

def extract_sql_blocks(content):
    """Extract SQL query blocks with their line numbers."""
    pattern = r'(cursor\.execute\s*\(\s*(?:f)?""")(.*?)("""\s*,)'
    blocks = []
    
    for match in re.finditer(pattern, content, re.DOTALL):
        sql = match.group(2)
        start_pos = match.start()
        line_num = content[:start_pos].count('\n') + 1
        blocks.append((line_num, sql))
    
    pattern2 = r"(cursor\.execute\s*\(\s*(?:f)?'''')(.*?)(''''\s*,)"
    for match in re.finditer(pattern2, content, re.DOTALL):
        sql = match.group(2)
        start_pos = match.start()
        line_num = content[:start_pos].count('\n') + 1
        blocks.append((line_num, sql))
    
    return blocks

def check_query_isolation(line_num, sql):
    """Check if UPDATE/DELETE query has tenant_id in WHERE clause."""
    issues = []
    
    sql_upper = sql.upper()
    
    is_insert_upsert = re.search(r'\bINSERT\s+INTO\s+.*ON\s+CONFLICT.*DO\s+UPDATE', sql_upper, re.DOTALL)
    if is_insert_upsert:
        return issues
    
    is_update = re.search(r'\bUPDATE\s+', sql_upper)
    is_delete = re.search(r'\bDELETE\s+FROM\s+', sql_upper)
    
    if not (is_update or is_delete):
        return issues
    
    for table in TENANT_AWARE_TABLES:
        table_pattern = rf'\b{table}\b'
        if re.search(table_pattern, sql, re.IGNORECASE):
            where_match = re.search(r'WHERE\s+(.+?)(?:RETURNING|$)', sql_upper, re.DOTALL)
            if where_match:
                where_clause = where_match.group(1)
                if 'TENANT_ID' not in where_clause:
                    query_type = 'UPDATE' if is_update else 'DELETE'
                    issues.append({
                        'line': line_num,
                        'type': query_type,
                        'table': table,
                        'snippet': sql[:100].replace('\n', ' ').strip() + '...'
                    })
            else:
                query_type = 'UPDATE' if is_update else 'DELETE'
                issues.append({
                    'line': line_num,
                    'type': query_type,
                    'table': table,
                    'snippet': sql[:100].replace('\n', ' ').strip() + '...'
                })
            break
    
    return issues

def audit_db_file():
    """Main audit function."""
    print("=" * 60)
    print("TENANT ISOLATION AUDIT")
    print("=" * 60)
    print(f"\nChecking tables: {', '.join(TENANT_AWARE_TABLES)}\n")
    
    try:
        db_file = find_db_file()
        print(f"Scanning: {db_file}\n")
    except FileNotFoundError as e:
        print(f"ERROR: {e}")
        return 1
    
    content = db_file.read_text()
    blocks = extract_sql_blocks(content)
    
    print(f"Found {len(blocks)} SQL query blocks\n")
    
    all_issues = []
    for line_num, sql in blocks:
        issues = check_query_isolation(line_num, sql)
        all_issues.extend(issues)
    
    if all_issues:
        print("=" * 60)
        print(f"FOUND {len(all_issues)} POTENTIAL ISOLATION ISSUES")
        print("=" * 60)
        for issue in all_issues:
            print(f"\n  Line {issue['line']}: {issue['type']} on `{issue['table']}`")
            print(f"  Missing tenant_id in WHERE clause")
            print(f"  Snippet: {issue['snippet']}")
        print("\n" + "=" * 60)
        print("AUDIT FAILED - Fix the above queries")
        print("=" * 60)
        return 1
    else:
        print("=" * 60)
        print("AUDIT PASSED - All UPDATE/DELETE queries include tenant_id")
        print("=" * 60)
        return 0

if __name__ == '__main__':
    sys.exit(audit_db_file())
