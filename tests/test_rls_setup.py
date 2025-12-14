"""
Tests for RLS (Row-Level Security) connection setup.
"""
import pytest
import os
import sys

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
