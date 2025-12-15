"""
Unit tests for _build_forex_config_tenants_query() and _column_exists().

Tests all 5 rules for schema-tolerant tenant discovery without needing a real database.
"""
import pytest
from unittest.mock import patch, MagicMock


class TestBuildForexConfigTenantsQuery:
    """Test the query builder logic for all 5 rules."""
    
    @patch('db._column_exists')
    def test_rule1_enabled_column_exists(self, mock_col_exists):
        """Rule 1: Use 'enabled' column when it exists."""
        import db
        
        def col_exists_side_effect(schema, table, column):
            return column == 'enabled'
        
        mock_col_exists.side_effect = col_exists_side_effect
        
        query, params, rule = db._build_forex_config_tenants_query()
        
        assert 'enabled = true' in query
        assert 'is_enabled' not in query
        assert params == ()
        assert rule == "rule1_enabled"
    
    @patch('db._column_exists')
    def test_rule2_is_enabled_column_exists(self, mock_col_exists):
        """Rule 2: Use 'is_enabled' column when 'enabled' doesn't exist."""
        import db
        
        def col_exists_side_effect(schema, table, column):
            return column == 'is_enabled'
        
        mock_col_exists.side_effect = col_exists_side_effect
        
        query, params, rule = db._build_forex_config_tenants_query()
        
        assert 'is_enabled = true' in query
        assert params == ()
        assert rule == "rule2_is_enabled"
    
    @patch('db._column_exists')
    def test_rule3_status_column_exists(self, mock_col_exists):
        """Rule 3: Use 'status' column when 'enabled' and 'is_enabled' don't exist."""
        import db
        
        def col_exists_side_effect(schema, table, column):
            return column == 'status'
        
        mock_col_exists.side_effect = col_exists_side_effect
        
        query, params, rule = db._build_forex_config_tenants_query()
        
        assert "status IN ('active', 'enabled', 'on')" in query
        assert params == ()
        assert rule == "rule3_status"
    
    @patch('db._column_exists')
    def test_rule4_active_column_exists(self, mock_col_exists):
        """Rule 4: Use 'active' column as last resort before fallback."""
        import db
        
        def col_exists_side_effect(schema, table, column):
            return column == 'active'
        
        mock_col_exists.side_effect = col_exists_side_effect
        
        query, params, rule = db._build_forex_config_tenants_query()
        
        assert 'active = true' in query
        assert params == ()
        assert rule == "rule4_active"
    
    @patch('db._column_exists')
    def test_rule5_no_enable_column_fallback(self, mock_col_exists):
        """Rule 5: Return all tenants when no known enable column exists."""
        import db
        
        mock_col_exists.return_value = False
        
        query, params, rule = db._build_forex_config_tenants_query()
        
        assert 'tenant_id IS NOT NULL' in query
        assert 'enabled' not in query
        assert 'is_enabled' not in query
        assert 'status' not in query
        assert 'active' not in query
        assert params == ()
        assert rule == "rule5_fallback"
    
    @patch('db._column_exists')
    def test_priority_enabled_over_is_enabled(self, mock_col_exists):
        """Verify 'enabled' takes priority over 'is_enabled'."""
        import db
        
        def col_exists_side_effect(schema, table, column):
            return column in ('enabled', 'is_enabled')
        
        mock_col_exists.side_effect = col_exists_side_effect
        
        query, params, rule = db._build_forex_config_tenants_query()
        
        assert 'enabled = true' in query
        assert 'is_enabled' not in query
        assert rule == "rule1_enabled"


class TestColumnExists:
    """Test the _column_exists helper function."""
    
    @patch('db.db_pool', None)
    def test_returns_false_when_pool_is_none(self):
        """Should return False when db_pool is None."""
        import db
        result = db._column_exists('public', 'forex_config', 'enabled')
        assert result is False
    
    @patch('db.db_pool')
    def test_returns_false_when_connection_pool_is_none(self, mock_db_pool):
        """Should return False when connection_pool is None."""
        import db
        mock_db_pool.connection_pool = None
        
        result = db._column_exists('public', 'forex_config', 'enabled')
        assert result is False


class TestGetActiveTenantsIntegration:
    """Integration tests for get_active_tenants with mocked database."""
    
    @patch('db.db_pool')
    @patch('db._build_forex_config_tenants_query')
    def test_uses_query_builder(self, mock_query_builder, mock_db_pool):
        """Verify get_active_tenants uses the query builder."""
        import db
        
        mock_query_builder.return_value = (
            "SELECT DISTINCT tenant_id FROM forex_config WHERE tenant_id IS NOT NULL",
            (),
            "rule5_fallback"
        )
        
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [('tenant1',), ('tenant2',)]
        mock_conn.cursor.return_value = mock_cursor
        mock_db_pool.connection_pool = MagicMock()
        mock_db_pool.get_connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_db_pool.get_connection.return_value.__exit__ = MagicMock(return_value=False)
        
        result = db.get_active_tenants()
        
        mock_query_builder.assert_called_once()
        assert result == ['tenant1', 'tenant2']
    
    @patch('db.db_pool', None)
    def test_returns_empty_when_pool_is_none(self):
        """Should return empty list when db_pool is None."""
        import db
        result = db.get_active_tenants()
        assert result == []
