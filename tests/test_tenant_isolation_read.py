"""
Tenant Isolation Read Test

This test proves that tenant-scoped SELECT queries cannot leak data.
It creates rows for two tenants, reads via real db helpers,
and verifies cross-tenant data is never returned.

Run: pytest tests/test_tenant_isolation_read.py -v
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db
from db import database_url_is_set, can_connect


TENANT_A = "entrylab"
TENANT_B = "tenant_test_read_isolation"


class TestTenantIsolationRead:
    """Test that SELECT operations respect tenant boundaries."""
    
    @classmethod
    def setup_class(cls):
        """Ensure database connection pool is initialized."""
        if not database_url_is_set() or not can_connect():
            pytest.skip("DATABASE_URL not set or DB unreachable")
        if not db.db_pool.connection_pool:
            db.db_pool.initialize_pool()
    
    def _create_test_signal(self, tenant_id, signal_type="BUY", notes=None):
        """Create a test forex signal for a specific tenant."""
        try:
            with db.db_pool.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO forex_signals 
                    (tenant_id, signal_type, pair, timeframe, entry_price, stop_loss, take_profit, status, notes)
                    VALUES (%s, %s, 'XAU/USD', '15min', 2650.00, 2640.00, 2670.00, 'active', %s)
                    RETURNING id
                """, (tenant_id, signal_type, notes))
                signal_id = cursor.fetchone()[0]
                conn.commit()
                return signal_id
        except Exception as e:
            print(f"Error creating test signal: {e}")
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
    
    def test_get_forex_signals_returns_only_own_tenant_rows(self):
        """
        ISOLATION TEST: Prove that get_forex_signals cannot return other tenant's data.
        
        1. Create signal for Tenant A with unique notes
        2. Create signal for Tenant B with unique notes
        3. Call get_forex_signals for Tenant A
        4. Assert only Tenant A rows are returned
        5. Assert Tenant B rows are NEVER returned
        """
        signal_a = None
        signal_b = None
        notes_a = "READ_ISOLATION_TEST_TENANT_A"
        notes_b = "READ_ISOLATION_TEST_TENANT_B"
        
        try:
            signal_a = self._create_test_signal(TENANT_A, notes=notes_a)
            signal_b = self._create_test_signal(TENANT_B, notes=notes_b)
            
            assert signal_a is not None, "Failed to create signal for Tenant A"
            assert signal_b is not None, "Failed to create signal for Tenant B"
            
            results_a = db.get_forex_signals(status='active', limit=1000, tenant_id=TENANT_A)
            
            signal_ids_returned = [s['id'] for s in results_a]
            notes_returned = [s.get('notes') for s in results_a]
            
            assert signal_a in signal_ids_returned, (
                f"Tenant A's signal (id={signal_a}) should be in results"
            )
            
            assert signal_b not in signal_ids_returned, (
                f"Tenant B's signal (id={signal_b}) should NEVER appear in Tenant A's results! "
                f"Data leak detected!"
            )
            
            assert notes_b not in notes_returned, (
                f"Tenant B's notes should NEVER appear in Tenant A's results! "
                f"Data leak detected!"
            )
            
        finally:
            self._cleanup_test_signals(
                [signal_a, signal_b],
                [TENANT_A, TENANT_B]
            )
    
    def test_get_forex_signals_with_wrong_tenant_returns_empty(self):
        """
        NEGATIVE TEST: Reading with wrong tenant_id returns empty/no matching rows.
        
        1. Create signal for Tenant A
        2. Query with Tenant B's tenant_id
        3. Assert Tenant A's signal is NOT returned
        """
        signal_a = None
        notes_marker = "NEGATIVE_READ_TEST_MARKER"
        
        try:
            signal_a = self._create_test_signal(TENANT_A, notes=notes_marker)
            assert signal_a is not None, "Failed to create signal for Tenant A"
            
            results_b = db.get_forex_signals(status='active', limit=1000, tenant_id=TENANT_B)
            
            signal_ids_returned = [s['id'] for s in results_b]
            notes_returned = [s.get('notes') for s in results_b]
            
            assert signal_a not in signal_ids_returned, (
                f"Tenant A's signal (id={signal_a}) should NOT be returned when querying as Tenant B! "
                f"Cross-tenant data leak detected!"
            )
            
            assert notes_marker not in notes_returned, (
                f"Tenant A's notes marker should NOT appear when querying as Tenant B!"
            )
            
        finally:
            self._cleanup_test_signals([signal_a], [TENANT_A])
    
    def test_multiple_rows_per_tenant_isolation(self):
        """
        Test with multiple rows per tenant to ensure complete isolation.
        
        1. Create 3 signals for Tenant A
        2. Create 2 signals for Tenant B
        3. Query each tenant
        4. Assert exact counts and no cross-contamination
        """
        signals_a = []
        signals_b = []
        
        try:
            for i in range(3):
                sig = self._create_test_signal(TENANT_A, notes=f"MULTI_A_{i}")
                if sig:
                    signals_a.append(sig)
            
            for i in range(2):
                sig = self._create_test_signal(TENANT_B, notes=f"MULTI_B_{i}")
                if sig:
                    signals_b.append(sig)
            
            assert len(signals_a) == 3, "Should create 3 signals for Tenant A"
            assert len(signals_b) == 2, "Should create 2 signals for Tenant B"
            
            results_a = db.get_forex_signals(status='active', limit=1000, tenant_id=TENANT_A)
            results_b = db.get_forex_signals(status='active', limit=1000, tenant_id=TENANT_B)
            
            ids_in_results_a = [s['id'] for s in results_a]
            ids_in_results_b = [s['id'] for s in results_b]
            
            for sig_a in signals_a:
                assert sig_a in ids_in_results_a, f"Tenant A signal {sig_a} should be in Tenant A results"
                assert sig_a not in ids_in_results_b, f"Tenant A signal {sig_a} should NOT be in Tenant B results"
            
            for sig_b in signals_b:
                assert sig_b in ids_in_results_b, f"Tenant B signal {sig_b} should be in Tenant B results"
                assert sig_b not in ids_in_results_a, f"Tenant B signal {sig_b} should NOT be in Tenant A results"
            
        finally:
            self._cleanup_test_signals(
                signals_a + signals_b,
                [TENANT_A] * len(signals_a) + [TENANT_B] * len(signals_b)
            )


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
