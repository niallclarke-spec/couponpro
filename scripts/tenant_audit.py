#!/usr/bin/env python3
"""
Tenant Isolation Audit Script

Scans Python files for UPDATE/DELETE statements on tenant-aware tables
that don't include tenant_id in the WHERE clause.

Usage:
    python scripts/tenant_audit.py           # Scan all .py files
    python scripts/tenant_audit.py --db-only # Scan only db.py (legacy mode)

Exit codes:
    0 - All queries pass tenant isolation check
    1 - Found queries missing tenant_id filtering
"""

import argparse
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

EXCLUDED_PATHS = [
    'tests/',
    'test_',
    '__pycache__',
    '.git',
    'attached_assets/',
    'venv/',
    '.venv/',
    'node_modules/',
]


def find_project_root():
    """Find project root relative to script location."""
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    if (project_root / 'db.py').exists():
        return project_root
    if Path('db.py').exists():
        return Path('.')
    raise FileNotFoundError("Cannot find project root (no db.py found)")


def find_python_files(project_root, db_only=False):
    """Find all Python files to scan."""
    if db_only:
        db_file = project_root / 'db.py'
        if db_file.exists():
            return [db_file]
        raise FileNotFoundError("Cannot find db.py")
    
    py_files = []
    for py_file in project_root.rglob('*.py'):
        path_str = str(py_file)
        if any(excluded in path_str for excluded in EXCLUDED_PATHS):
            continue
        py_files.append(py_file)
    
    return sorted(py_files)


def extract_sql_blocks(content):
    """Extract SQL query blocks with their line numbers."""
    blocks = []
    
    patterns = [
        r'(cursor\.execute\s*\(\s*(?:f)?""")(.*?)("""\s*[,)])',
        r"(cursor\.execute\s*\(\s*(?:f)?'''')(.*?)(''''\s*[,)])",
        r'(cursor\.execute\s*\(\s*(?:f)?")(.*?)("\s*[,)])',
        r"(cursor\.execute\s*\(\s*(?:f)?')(.*?)('\s*[,)])",
    ]
    
    for pattern in patterns:
        for match in re.finditer(pattern, content, re.DOTALL):
            sql = match.group(2)
            start_pos = match.start()
            line_num = content[:start_pos].count('\n') + 1
            blocks.append((line_num, sql))
    
    return blocks


def check_query_isolation(line_num, sql, file_path):
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
                        'file': str(file_path),
                        'line': line_num,
                        'type': query_type,
                        'table': table,
                        'snippet': sql[:100].replace('\n', ' ').strip() + '...'
                    })
            else:
                query_type = 'UPDATE' if is_update else 'DELETE'
                issues.append({
                    'file': str(file_path),
                    'line': line_num,
                    'type': query_type,
                    'table': table,
                    'snippet': sql[:100].replace('\n', ' ').strip() + '...'
                })
            break
    
    return issues


def audit_file(file_path):
    """Audit a single Python file for tenant isolation issues."""
    try:
        content = file_path.read_text()
    except Exception as e:
        print(f"  ⚠️ Could not read {file_path}: {e}")
        return []
    
    blocks = extract_sql_blocks(content)
    
    all_issues = []
    for line_num, sql in blocks:
        issues = check_query_isolation(line_num, sql, file_path)
        all_issues.extend(issues)
    
    return all_issues


def audit_repo(db_only=False):
    """Main audit function."""
    print("=" * 60)
    print("TENANT ISOLATION AUDIT")
    print("=" * 60)
    print(f"\nChecking tables: {', '.join(TENANT_AWARE_TABLES)}\n")
    
    try:
        project_root = find_project_root()
        py_files = find_python_files(project_root, db_only=db_only)
        print(f"Scanning {len(py_files)} Python file(s)...\n")
    except FileNotFoundError as e:
        print(f"ERROR: {e}")
        return 1
    
    all_issues = []
    total_blocks = 0
    
    for py_file in py_files:
        content = py_file.read_text()
        blocks = extract_sql_blocks(content)
        total_blocks += len(blocks)
        
        if blocks:
            print(f"  {py_file.name}: {len(blocks)} SQL blocks")
        
        for line_num, sql in blocks:
            issues = check_query_isolation(line_num, sql, py_file)
            all_issues.extend(issues)
    
    print(f"\nTotal: {total_blocks} SQL query blocks scanned\n")
    
    if all_issues:
        print("=" * 60)
        print(f"FOUND {len(all_issues)} POTENTIAL ISOLATION ISSUES")
        print("=" * 60)
        for issue in all_issues:
            print(f"\n  {issue['file']}:{issue['line']}")
            print(f"  {issue['type']} on `{issue['table']}` - Missing tenant_id in WHERE")
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


def main():
    parser = argparse.ArgumentParser(description='Tenant Isolation Audit')
    parser.add_argument('--db-only', action='store_true',
                        help='Only scan db.py (legacy mode)')
    args = parser.parse_args()
    
    return audit_repo(db_only=args.db_only)


if __name__ == '__main__':
    sys.exit(main())
