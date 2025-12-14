"""
Tenant Isolation Integration Test

This "evil" test proves that tenant isolation cannot be bypassed.
It creates rows for two tenants, updates via real db helpers,
and verifies cross-tenant data is not modified.

Run: pytest tests/test_tenant_isolation_update.py -v
"""

import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db


TENANT_A = "entrylab"
TENANT_B = "tenant_test_isolation"


class TestTenantIsolationUpdate:
    """Test that UPDATE operations respect tenant boundaries."""
    
    @classmethod
    def setup_class(cls):
        """Ensure database connection pool is initialized."""
        if not db.db_pool.connection_pool:
            db.db_pool.initialize_pool()
    
    def _create_test_signal(self, tenant_id, signal_type="BUY"):
        """Create a test forex signal for a specific tenant."""
        try:
            with db.db_pool.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO forex_signals 
                    (tenant_id, signal_type, pair, timeframe, entry_price, stop_loss, take_profit, status)
                    VALUES (%s, %s, 'XAU/USD', '15min', 2650.00, 2640.00, 2670.00, 'active')
                    RETURNING id
                """, (tenant_id, signal_type))
                signal_id = cursor.fetchone()[0]
                conn.commit()
                return signal_id
        except Exception as e:
            print(f"Error creating test signal: {e}")
            return None
    
    def _get_signal_notes(self, signal_id, tenant_id):
        """Get the notes field for a signal."""
        try:
            with db.db_pool.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT notes FROM forex_signals WHERE id = %s AND tenant_id = %s
                """, (signal_id, tenant_id))
                row = cursor.fetchone()
                return row[0] if row else None
        except Exception as e:
            print(f"Error getting signal notes: {e}")
            return None
    
    def _cleanup_test_signals(self, signal_ids, tenant_ids):
        """Delete test signals."""
        try:
            with db.db_pool.get_connection() as conn:
                cursor = conn.cursor()
                for signal_id, tenant_id in zip(signal_ids, tenant_ids):
                    if signal_id:
                        cursor.execute("""
                            DELETE FROM forex_signals WHERE id = %s AND tenant_id = %s
                        """, (signal_id, tenant_id))
                conn.commit()
        except Exception as e:
            print(f"Error cleaning up test signals: {e}")
    
    def test_update_signal_guidance_respects_tenant_boundary(self):
        """
        EVIL TEST: Prove that update_signal_guidance cannot cross tenant boundaries.
        
        1. Create signal for Tenant A and Tenant B
        2. Update only Tenant A's signal via db helper
        3. Assert Tenant A signal IS updated
        4. Assert Tenant B signal is NOT modified
        """
        signal_a = None
        signal_b = None
        
        try:
            signal_a = self._create_test_signal(TENANT_A)
            signal_b = self._create_test_signal(TENANT_B)
            
            assert signal_a is not None, "Failed to create signal for Tenant A"
            assert signal_b is not None, "Failed to create signal for Tenant B"
            
            notes_before_a = self._get_signal_notes(signal_a, TENANT_A)
            notes_before_b = self._get_signal_notes(signal_b, TENANT_B)
            
            update_notes = f"ISOLATION_TEST_{datetime.utcnow().isoformat()}"
            result = db.update_signal_guidance(
                signal_id=signal_a,
                notes=update_notes,
                tenant_id=TENANT_A
            )
            
            assert result is True, "update_signal_guidance should return True"
            
            notes_after_a = self._get_signal_notes(signal_a, TENANT_A)
            notes_after_b = self._get_signal_notes(signal_b, TENANT_B)
            
            assert notes_after_a == update_notes, (
                f"Tenant A signal should be updated. Expected '{update_notes}', got '{notes_after_a}'"
            )
            
            assert notes_after_b == notes_before_b, (
                f"Tenant B signal should NOT be modified! "
                f"Before: '{notes_before_b}', After: '{notes_after_b}'"
            )
            
        finally:
            self._cleanup_test_signals(
                [signal_a, signal_b],
                [TENANT_A, TENANT_B]
            )
    
    def test_update_with_wrong_tenant_returns_false(self):
        """
        Test that updating a signal with the wrong tenant_id returns False
        (no rows affected) and does not modify the signal.
        """
        signal_a = None
        
        try:
            signal_a = self._create_test_signal(TENANT_A)
            assert signal_a is not None, "Failed to create signal for Tenant A"
            
            notes_before = self._get_signal_notes(signal_a, TENANT_A)
            
            result = db.update_signal_guidance(
                signal_id=signal_a,
                notes="SHOULD_NOT_APPEAR",
                tenant_id=TENANT_B
            )
            
            assert result is False, (
                "update_signal_guidance with wrong tenant should return False (no rows updated)"
            )
            
            notes_after = self._get_signal_notes(signal_a, TENANT_A)
            assert notes_after == notes_before, (
                f"Signal should NOT be modified when using wrong tenant! "
                f"Before: '{notes_before}', After: '{notes_after}'"
            )
            
        finally:
            self._cleanup_test_signals([signal_a], [TENANT_A])


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
