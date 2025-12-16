#!/usr/bin/env python3
"""
Migration script to update bot_role values from legacy to canonical names.

Legacy roles: 'signal', 'message'
Canonical roles: 'signal_bot', 'message_bot'

This script is idempotent - safe to run multiple times.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db
from core.logging import get_logger

logger = get_logger(__name__)

ROLE_MIGRATIONS = [
    ('signal', 'signal_bot'),
    ('message', 'message_bot'),
]


def migrate_bot_roles():
    """
    Migrate legacy bot_role values to canonical names.
    
    Updates:
    - 'signal' -> 'signal_bot'
    - 'message' -> 'message_bot'
    
    Handles unique constraint conflicts by keeping the canonical row
    and deleting the legacy row (after merging any missing data).
    """
    if not db.db_pool or not db.db_pool.connection_pool:
        logger.error("Database not available")
        return False
    
    total_updated = 0
    total_conflicts = 0
    
    with db.db_pool.get_connection() as conn:
        cursor = conn.cursor()
        
        for legacy_role, canonical_role in ROLE_MIGRATIONS:
            cursor.execute("""
                SELECT tenant_id, bot_role 
                FROM tenant_bot_connections 
                WHERE bot_role = %s
            """, (legacy_role,))
            legacy_rows = cursor.fetchall()
            
            if not legacy_rows:
                logger.info(f"No rows with bot_role='{legacy_role}' found, skipping")
                continue
            
            for tenant_id, _ in legacy_rows:
                cursor.execute("""
                    SELECT id FROM tenant_bot_connections 
                    WHERE tenant_id = %s AND bot_role = %s
                """, (tenant_id, canonical_role))
                existing_canonical = cursor.fetchone()
                
                if existing_canonical:
                    logger.warning(
                        f"Conflict: tenant={tenant_id} has both '{legacy_role}' and '{canonical_role}'. "
                        f"Deleting legacy row."
                    )
                    cursor.execute("""
                        DELETE FROM tenant_bot_connections 
                        WHERE tenant_id = %s AND bot_role = %s
                    """, (tenant_id, legacy_role))
                    total_conflicts += 1
                else:
                    cursor.execute("""
                        UPDATE tenant_bot_connections 
                        SET bot_role = %s, updated_at = NOW()
                        WHERE tenant_id = %s AND bot_role = %s
                    """, (canonical_role, tenant_id, legacy_role))
                    total_updated += 1
                    logger.info(f"Migrated tenant={tenant_id}: '{legacy_role}' -> '{canonical_role}'")
        
        conn.commit()
    
    logger.info(f"Migration complete: {total_updated} updated, {total_conflicts} conflicts resolved")
    return True


def verify_migration():
    """Verify no legacy role names remain in the database."""
    if not db.db_pool or not db.db_pool.connection_pool:
        return False
    
    with db.db_pool.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT DISTINCT bot_role FROM tenant_bot_connections
        """)
        roles = [row[0] for row in cursor.fetchall()]
    
    legacy_found = [r for r in roles if r in ('signal', 'message')]
    if legacy_found:
        logger.error(f"Legacy roles still exist: {legacy_found}")
        return False
    
    logger.info(f"Verification passed. Current roles: {roles}")
    return True


if __name__ == "__main__":
    print("=" * 60)
    print("Bot Role Migration: signal -> signal_bot, message -> message_bot")
    print("=" * 60)
    
    db.init_db()
    
    if migrate_bot_roles():
        print("\n[SUCCESS] Migration completed successfully")
        if verify_migration():
            print("[SUCCESS] Verification passed")
        else:
            print("[WARNING] Verification found issues")
            sys.exit(1)
    else:
        print("\n[FAILED] Migration failed")
        sys.exit(1)
