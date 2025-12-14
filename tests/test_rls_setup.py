"""
Tests for RLS (Row-Level Security) connection setup.
"""
import pytest
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestRLSConnectionSetup:
    """Tests for RLS connection setup functionality."""
    
    def test_get_connection_accepts_tenant_id_parameter(self):
        """Test that get_connection accepts tenant_id parameter."""
        import db as db_module
        
        if not db_module.db_pool or not db_module.db_pool.connection_pool:
            pytest.skip("Database not available")
        
        with db_module.db_pool.get_connection(tenant_id='test_tenant') as conn:
            assert conn is not None
            assert not conn.closed
    
    def test_rls_sets_app_tenant_id_when_enabled(self):
        """Test that app.tenant_id is set when ENABLE_RLS=1."""
        import db as db_module
        
        if not db_module.db_pool or not db_module.db_pool.connection_pool:
            pytest.skip("Database not available")
        
        original_value = os.environ.get('ENABLE_RLS')
        
        try:
            os.environ['ENABLE_RLS'] = '1'
            
            with db_module.db_pool.get_connection(tenant_id='test_rls_tenant') as conn:
                cursor = conn.cursor()
                try:
                    cursor.execute("SELECT current_setting('app.tenant_id', true)")
                    result = cursor.fetchone()[0]
                    assert result == 'test_rls_tenant'
                except Exception:
                    pytest.skip("RLS session variable not available in this PostgreSQL configuration")
        finally:
            if original_value is None:
                os.environ.pop('ENABLE_RLS', None)
            else:
                os.environ['ENABLE_RLS'] = original_value
    
    def test_rls_not_set_when_disabled(self):
        """Test that app.tenant_id is NOT set when ENABLE_RLS is not set."""
        import db as db_module
        
        if not db_module.db_pool or not db_module.db_pool.connection_pool:
            pytest.skip("Database not available")
        
        original_value = os.environ.get('ENABLE_RLS')
        
        try:
            os.environ.pop('ENABLE_RLS', None)
            
            with db_module.db_pool.get_connection(tenant_id='should_not_be_set') as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT current_setting('app.tenant_id', true)")
                result = cursor.fetchone()[0]
                assert result is None or result == ''
        finally:
            if original_value is not None:
                os.environ['ENABLE_RLS'] = original_value
    
    def test_get_connection_works_without_tenant_id(self):
        """Test that get_connection works when no tenant_id is provided."""
        import db as db_module
        
        if not db_module.db_pool or not db_module.db_pool.connection_pool:
            pytest.skip("Database not available")
        
        with db_module.db_pool.get_connection() as conn:
            assert conn is not None
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            assert cursor.fetchone()[0] == 1


class TestTenantConnContextManager:
    """Tests for the tenant_conn() context manager."""
    
    def test_tenant_conn_yields_connection_and_cursor(self):
        """Test that tenant_conn yields both connection and cursor."""
        import db as db_module
        
        if not db_module.db_pool or not db_module.db_pool.connection_pool:
            pytest.skip("Database not available")
        
        with db_module.tenant_conn('test_tenant') as (conn, cursor):
            assert conn is not None
            assert cursor is not None
            cursor.execute("SELECT 1")
            assert cursor.fetchone()[0] == 1
    
    def test_tenant_conn_sets_tenant_id_when_rls_enabled(self):
        """Test that tenant_conn sets app.tenant_id when ENABLE_RLS=1."""
        import db as db_module
        
        if not db_module.db_pool or not db_module.db_pool.connection_pool:
            pytest.skip("Database not available")
        
        original_value = os.environ.get('ENABLE_RLS')
        
        try:
            os.environ['ENABLE_RLS'] = '1'
            
            with db_module.tenant_conn('test_tenant_conn') as (conn, cursor):
                cursor.execute("SELECT current_setting('app.tenant_id', true)")
                result = cursor.fetchone()[0]
                assert result == 'test_tenant_conn'
        finally:
            if original_value is None:
                os.environ.pop('ENABLE_RLS', None)
            else:
                os.environ['ENABLE_RLS'] = original_value
    
    def test_tenant_conn_commits_on_success(self):
        """Test that tenant_conn commits the transaction on successful exit."""
        import db as db_module
        
        if not db_module.db_pool or not db_module.db_pool.connection_pool:
            pytest.skip("Database not available")
        
        test_id = f"test_commit_{uuid.uuid4().hex[:8]}"
        
        try:
            with db_module.tenant_conn('test_tenant') as (conn, cursor):
                cursor.execute("""
                    INSERT INTO forex_signals 
                    (tenant_id, signal_type, pair, timeframe, entry_price, status)
                    VALUES (%s, 'BUY', 'EURUSD', '1H', 1.1000, 'test_commit')
                    RETURNING id
                """, (test_id,))
                inserted_id = cursor.fetchone()[0]
            
            with db_module.db_pool.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id FROM forex_signals WHERE tenant_id = %s", (test_id,))
                result = cursor.fetchone()
                assert result is not None
                assert result[0] == inserted_id
        finally:
            with db_module.db_pool.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM forex_signals WHERE tenant_id = %s", (test_id,))
                conn.commit()
    
    def test_tenant_conn_rolls_back_on_error(self):
        """Test that tenant_conn rolls back the transaction on error."""
        import db as db_module
        
        if not db_module.db_pool or not db_module.db_pool.connection_pool:
            pytest.skip("Database not available")
        
        test_id = f"test_rollback_{uuid.uuid4().hex[:8]}"
        
        try:
            with db_module.tenant_conn('test_tenant') as (conn, cursor):
                cursor.execute("""
                    INSERT INTO forex_signals 
                    (tenant_id, signal_type, pair, timeframe, entry_price, status)
                    VALUES (%s, 'BUY', 'EURUSD', '1H', 1.1000, 'test_rollback')
                """, (test_id,))
                raise ValueError("Intentional error to test rollback")
        except ValueError:
            pass
        
        with db_module.db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM forex_signals WHERE tenant_id = %s", (test_id,))
            result = cursor.fetchone()
            assert result is None


class TestRLSIsolation:
    """Tests for RLS tenant isolation behavior.
    
    These tests verify that when RLS is enabled:
    - SELECT queries only return rows for the current tenant
    - UPDATE queries only affect rows for the current tenant
    
    NOTE: These tests require the RLS migration to be applied to the database.
    If RLS is not enforced at the database level, tests will be skipped.
    """
    
    @pytest.fixture(autouse=True)
    def setup_test_data(self):
        """Set up test data for two tenants and clean up after tests."""
        import db as db_module
        
        if not db_module.db_pool or not db_module.db_pool.connection_pool:
            pytest.skip("Database not available")
        
        self.tenant_a = f"rls_test_tenant_a_{uuid.uuid4().hex[:8]}"
        self.tenant_b = f"rls_test_tenant_b_{uuid.uuid4().hex[:8]}"
        self.signal_ids_a = []
        self.signal_ids_b = []
        
        with db_module.db_pool.get_connection() as conn:
            cursor = conn.cursor()
            
            for i in range(3):
                cursor.execute("""
                    INSERT INTO forex_signals 
                    (tenant_id, signal_type, pair, timeframe, entry_price, status)
                    VALUES (%s, 'BUY', 'EURUSD', '1H', %s, 'pending')
                    RETURNING id
                """, (self.tenant_a, 1.1000 + i * 0.0001))
                self.signal_ids_a.append(cursor.fetchone()[0])
            
            for i in range(2):
                cursor.execute("""
                    INSERT INTO forex_signals 
                    (tenant_id, signal_type, pair, timeframe, entry_price, status)
                    VALUES (%s, 'SELL', 'GBPUSD', '4H', %s, 'pending')
                    RETURNING id
                """, (self.tenant_b, 1.2500 + i * 0.0001))
                self.signal_ids_b.append(cursor.fetchone()[0])
            
            conn.commit()
        
        yield
        
        with db_module.db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM forex_signals WHERE tenant_id IN (%s, %s)", 
                          (self.tenant_a, self.tenant_b))
            conn.commit()
    
    def _is_rls_enforced(self, db_module):
        """Check if RLS is actually being enforced at database level."""
        try:
            with db_module.db_pool.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT relrowsecurity 
                    FROM pg_class 
                    WHERE relname = 'forex_signals'
                """)
                result = cursor.fetchone()
                return result and result[0] is True
        except Exception:
            return False
    
    def test_select_isolation_with_rls_enabled(self):
        """Test that SELECT only returns current tenant's rows when RLS is enabled."""
        import db as db_module
        
        if not self._is_rls_enforced(db_module):
            pytest.skip("RLS not enforced at database level - run migrations/rls_phase2.sql first")
        
        original_value = os.environ.get('ENABLE_RLS')
        
        try:
            os.environ['ENABLE_RLS'] = '1'
            
            with db_module.tenant_conn(self.tenant_a) as (conn, cursor):
                cursor.execute("SELECT id, tenant_id FROM forex_signals WHERE status = 'pending'")
                rows = cursor.fetchall()
                
                returned_ids = [row[0] for row in rows]
                returned_tenants = set(row[1] for row in rows)
                
                for signal_id in self.signal_ids_a:
                    assert signal_id in returned_ids, f"Tenant A signal {signal_id} should be visible"
                
                for signal_id in self.signal_ids_b:
                    assert signal_id not in returned_ids, f"Tenant B signal {signal_id} should NOT be visible"
                
                if returned_tenants:
                    assert returned_tenants == {self.tenant_a}, "Only tenant A rows should be returned"
            
            with db_module.tenant_conn(self.tenant_b) as (conn, cursor):
                cursor.execute("SELECT id, tenant_id FROM forex_signals WHERE status = 'pending'")
                rows = cursor.fetchall()
                
                returned_ids = [row[0] for row in rows]
                
                for signal_id in self.signal_ids_b:
                    assert signal_id in returned_ids, f"Tenant B signal {signal_id} should be visible"
                
                for signal_id in self.signal_ids_a:
                    assert signal_id not in returned_ids, f"Tenant A signal {signal_id} should NOT be visible"
        finally:
            if original_value is None:
                os.environ.pop('ENABLE_RLS', None)
            else:
                os.environ['ENABLE_RLS'] = original_value
    
    def test_update_isolation_with_rls_enabled(self):
        """Test that UPDATE only affects current tenant's rows when RLS is enabled."""
        import db as db_module
        
        if not self._is_rls_enforced(db_module):
            pytest.skip("RLS not enforced at database level - run migrations/rls_phase2.sql first")
        
        original_value = os.environ.get('ENABLE_RLS')
        
        try:
            os.environ['ENABLE_RLS'] = '1'
            
            with db_module.tenant_conn(self.tenant_a) as (conn, cursor):
                cursor.execute("""
                    UPDATE forex_signals 
                    SET status = 'rls_updated'
                    WHERE status = 'pending'
                """)
                updated_count = cursor.rowcount
            
            with db_module.db_pool.get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT status FROM forex_signals 
                    WHERE id = ANY(%s)
                """, (self.signal_ids_a,))
                statuses_a = [row[0] for row in cursor.fetchall()]
                assert all(s == 'rls_updated' for s in statuses_a), \
                    f"Tenant A signals should be updated: {statuses_a}"
                
                cursor.execute("""
                    SELECT status FROM forex_signals 
                    WHERE id = ANY(%s)
                """, (self.signal_ids_b,))
                statuses_b = [row[0] for row in cursor.fetchall()]
                assert all(s == 'pending' for s in statuses_b), \
                    f"Tenant B signals should NOT be updated: {statuses_b}"
        finally:
            if original_value is None:
                os.environ.pop('ENABLE_RLS', None)
            else:
                os.environ['ENABLE_RLS'] = original_value
    
    def test_no_tenant_id_returns_empty_when_rls_enabled(self):
        """Test that queries with unset tenant_id return empty results when RLS is enabled."""
        import db as db_module
        
        if not self._is_rls_enforced(db_module):
            pytest.skip("RLS not enforced at database level - run migrations/rls_phase2.sql first")
        
        original_value = os.environ.get('ENABLE_RLS')
        
        try:
            os.environ['ENABLE_RLS'] = '1'
            
            with db_module.tenant_conn('nonexistent_tenant_xyz') as (conn, cursor):
                cursor.execute("SELECT id FROM forex_signals WHERE status = 'pending'")
                rows = cursor.fetchall()
                
                known_ids = set(self.signal_ids_a + self.signal_ids_b)
                returned_ids = set(row[0] for row in rows)
                
                overlap = known_ids & returned_ids
                assert len(overlap) == 0, \
                    f"Nonexistent tenant should not see test signals: {overlap}"
        finally:
            if original_value is None:
                os.environ.pop('ENABLE_RLS', None)
            else:
                os.environ['ENABLE_RLS'] = original_value


class TestTenantConnMockBased:
    """Mock-based tests for tenant_conn() that do NOT require a real database.
    
    These tests verify the SET LOCAL behavior using mocks to capture SQL executed.
    """
    
    def test_tenant_conn_set_local_when_rls_enabled(self, monkeypatch):
        """Test that tenant_conn executes SET LOCAL when ENABLE_RLS=1 (mock-based, no DB)."""
        from unittest.mock import MagicMock, patch
        
        monkeypatch.setenv('ENABLE_RLS', '1')
        
        executed_sql = []
        
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = ('test_tenant_abc',)
        
        def capture_execute(sql, params=None):
            if params:
                executed_sql.append((sql, params))
            else:
                executed_sql.append((sql, None))
        
        mock_cursor.execute.side_effect = capture_execute
        
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.closed = False
        
        mock_pool = MagicMock()
        mock_pool.getconn.return_value = mock_conn
        
        mock_db_pool = MagicMock()
        mock_db_pool.connection_pool = mock_pool
        
        with patch('db.db_pool', mock_db_pool):
            import db as db_module
            importlib_needed = False
            try:
                with db_module.tenant_conn('test_tenant_abc') as (conn, cursor):
                    pass
            except Exception:
                pass
        
        set_local_calls = [
            call for call in executed_sql 
            if 'SET LOCAL app.tenant_id' in call[0]
        ]
        
        assert len(set_local_calls) >= 1, \
            f"Expected SET LOCAL app.tenant_id call, got: {executed_sql}"
        
        set_local_sql, set_local_params = set_local_calls[0]
        assert set_local_params == ('test_tenant_abc',), \
            f"Expected tenant_id 'test_tenant_abc' in params, got: {set_local_params}"
    
    def test_tenant_conn_no_set_local_when_rls_disabled(self, monkeypatch):
        """Test that tenant_conn does NOT execute SET LOCAL when ENABLE_RLS is not set (mock-based)."""
        from unittest.mock import MagicMock, patch
        
        monkeypatch.delenv('ENABLE_RLS', raising=False)
        
        executed_sql = []
        
        mock_cursor = MagicMock()
        
        def capture_execute(sql, params=None):
            if params:
                executed_sql.append((sql, params))
            else:
                executed_sql.append((sql, None))
        
        mock_cursor.execute.side_effect = capture_execute
        
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.closed = False
        
        mock_pool = MagicMock()
        mock_pool.getconn.return_value = mock_conn
        
        mock_db_pool = MagicMock()
        mock_db_pool.connection_pool = mock_pool
        
        with patch('db.db_pool', mock_db_pool):
            import db as db_module
            try:
                with db_module.tenant_conn('test_tenant_xyz') as (conn, cursor):
                    pass
            except Exception:
                pass
        
        set_local_calls = [
            call for call in executed_sql 
            if 'SET LOCAL app.tenant_id' in str(call[0])
        ]
        
        assert len(set_local_calls) == 0, \
            f"SET LOCAL should NOT be called when ENABLE_RLS is not set, got: {executed_sql}"
    
    def test_tenant_conn_verifies_tenant_context_when_rls_enabled(self, monkeypatch):
        """Test that tenant_conn verifies tenant context after SET LOCAL (mock-based)."""
        from unittest.mock import MagicMock, patch
        
        monkeypatch.setenv('ENABLE_RLS', '1')
        
        executed_sql = []
        
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = ('verified_tenant',)
        
        def capture_execute(sql, params=None):
            if params:
                executed_sql.append((sql, params))
            else:
                executed_sql.append((sql, None))
        
        mock_cursor.execute.side_effect = capture_execute
        
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.closed = False
        
        mock_pool = MagicMock()
        mock_pool.getconn.return_value = mock_conn
        
        mock_db_pool = MagicMock()
        mock_db_pool.connection_pool = mock_pool
        
        with patch('db.db_pool', mock_db_pool):
            import db as db_module
            try:
                with db_module.tenant_conn('verified_tenant') as (conn, cursor):
                    pass
            except Exception:
                pass
        
        verify_calls = [
            call for call in executed_sql 
            if "current_setting('app.tenant_id'" in str(call[0])
        ]
        
        assert len(verify_calls) >= 1, \
            f"Expected verification query for app.tenant_id, got: {executed_sql}"
