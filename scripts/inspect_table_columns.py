#!/usr/bin/env python3
"""
Inspect table columns for forex_config, bot_config, forex_signals.

Read-only script that prints column information to help debug schema issues.

Usage:
    python scripts/inspect_table_columns.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db as db_module


def inspect_table(table_name: str) -> None:
    """Print column information for a table."""
    print(f"\n{'=' * 60}")
    print(f"Table: {table_name}")
    print('=' * 60)
    
    if not db_module.db_pool or not db_module.db_pool.connection_pool:
        print("  [ERROR] Database pool not initialized")
        return
    
    try:
        with db_module.db_pool.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT 1 FROM information_schema.tables 
                WHERE table_schema = 'public' AND table_name = %s
            """, (table_name,))
            
            if not cursor.fetchone():
                print(f"  [TABLE NOT FOUND]")
                return
            
            cursor.execute("""
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = %s
                ORDER BY ordinal_position
            """, (table_name,))
            
            columns = cursor.fetchall()
            
            if not columns:
                print("  [NO COLUMNS FOUND]")
                return
            
            print(f"  {'Column Name':<30} {'Type':<20} {'Nullable':<10} Default")
            print(f"  {'-' * 30} {'-' * 20} {'-' * 10} {'-' * 30}")
            
            for col_name, data_type, nullable, default in columns:
                default_str = str(default)[:30] if default else ''
                print(f"  {col_name:<30} {data_type:<20} {nullable:<10} {default_str}")
            
            print(f"\n  Total columns: {len(columns)}")
            
    except Exception as e:
        print(f"  [ERROR] {e}")


def check_enable_columns() -> None:
    """Check which enable-related columns exist in forex_config."""
    print(f"\n{'=' * 60}")
    print("Enable Column Detection (forex_config)")
    print('=' * 60)
    
    if not db_module.db_pool or not db_module.db_pool.connection_pool:
        print("  [ERROR] Database pool not initialized")
        return
    
    columns_to_check = ['enabled', 'is_enabled', 'status', 'active']
    
    for col in columns_to_check:
        exists = db_module._column_exists('public', 'forex_config', col)
        status = "EXISTS" if exists else "NOT FOUND"
        print(f"  {col:<20}: {status}")
    
    print("\nQuery builder result:")
    query, params = db_module._build_forex_config_tenants_query()
    print(f"  Query: {query}")
    print(f"  Params: {params}")


def main():
    print("=" * 60)
    print("TABLE COLUMN INSPECTOR")
    print("=" * 60)
    
    tables = ['forex_config', 'bot_config', 'forex_signals']
    
    for table in tables:
        inspect_table(table)
    
    check_enable_columns()
    
    print("\n" + "=" * 60)
    print("INSPECTION COMPLETE")
    print("=" * 60)


if __name__ == '__main__':
    main()
