"""
Unit tests for tenant isolation in strategy calls and scheduler DB pool validation.

Tests:
1. Strategies call get_daily_pnl with tenant_id
2. Scheduler refuses to run if DB pool init fails
"""
import os
import sys
import pytest
from unittest.mock import patch, MagicMock


class TestStrategyTenantCalls:
    """Tests that strategies correctly pass tenant_id to DB functions."""
    
    def test_aggressive_strategy_passes_tenant_id_to_get_daily_pnl(self):
        """Verify AggressiveStrategy.check_guardrails calls get_daily_pnl with tenant_id."""
        with patch('strategies.aggressive.get_daily_pnl') as mock_get_daily_pnl, \
             patch('strategies.aggressive.get_forex_config') as mock_get_forex_config, \
             patch('strategies.aggressive.get_last_completed_signal') as mock_get_last_signal:
            
            mock_get_forex_config.return_value = {}
            mock_get_daily_pnl.return_value = 0.0
            mock_get_last_signal.return_value = None
            
            from strategies.aggressive import AggressiveStrategy
            strategy = AggressiveStrategy(tenant_id='test_tenant_123')
            
            strategy.check_guardrails()
            
            mock_get_daily_pnl.assert_called_once()
            call_kwargs = mock_get_daily_pnl.call_args
            assert call_kwargs.kwargs.get('tenant_id') == 'test_tenant_123', \
                f"Expected tenant_id='test_tenant_123', got {call_kwargs}"
    
    def test_conservative_strategy_passes_tenant_id_to_get_daily_pnl(self):
        """Verify ConservativeStrategy.check_guardrails calls get_daily_pnl with tenant_id."""
        with patch('strategies.conservative.get_daily_pnl') as mock_get_daily_pnl, \
             patch('strategies.conservative.get_forex_config') as mock_get_forex_config, \
             patch('strategies.conservative.get_last_completed_signal') as mock_get_last_signal:
            
            mock_get_forex_config.return_value = {}
            mock_get_daily_pnl.return_value = 0.0
            mock_get_last_signal.return_value = None
            
            from strategies.conservative import ConservativeStrategy
            strategy = ConservativeStrategy(tenant_id='test_tenant_456')
            
            strategy.check_guardrails()
            
            mock_get_daily_pnl.assert_called_once()
            call_kwargs = mock_get_daily_pnl.call_args
            assert call_kwargs.kwargs.get('tenant_id') == 'test_tenant_456', \
                f"Expected tenant_id='test_tenant_456', got {call_kwargs}"
    
    def test_raja_banks_strategy_passes_tenant_id_to_get_daily_pnl(self):
        """Verify RajaBanksStrategy.check_guardrails calls get_daily_pnl with tenant_id."""
        with patch('strategies.raja_banks.get_daily_pnl') as mock_get_daily_pnl, \
             patch('strategies.raja_banks.get_forex_config') as mock_get_forex_config, \
             patch('strategies.raja_banks.count_signals_today_by_bot') as mock_count_signals, \
             patch('strategies.raja_banks.get_last_signal_time_by_bot') as mock_last_signal_time:
            
            mock_get_forex_config.return_value = {}
            mock_get_daily_pnl.return_value = 0.0
            mock_count_signals.return_value = 0
            mock_last_signal_time.return_value = None
            
            from strategies.raja_banks import RajaBanksStrategy
            strategy = RajaBanksStrategy(tenant_id='test_tenant_789')
            
            with patch.object(strategy, 'is_in_session', return_value=(True, 'London')):
                strategy.check_guardrails()
            
            mock_get_daily_pnl.assert_called_once()
            call_kwargs = mock_get_daily_pnl.call_args
            assert call_kwargs.kwargs.get('tenant_id') == 'test_tenant_789', \
                f"Expected tenant_id='test_tenant_789', got {call_kwargs}"


class TestSchedulerDbPoolValidation:
    """Tests that scheduler refuses to run if DB pool init fails."""
    
    def test_require_db_pool_or_exit_succeeds_when_no_database_url(self):
        """When DATABASE_URL is not set, should pass without error."""
        with patch.dict(os.environ, {}, clear=True):
            if 'DATABASE_URL' in os.environ:
                del os.environ['DATABASE_URL']
            
            from forex_scheduler import require_db_pool_or_exit
            require_db_pool_or_exit()
    
    def test_require_db_pool_or_exit_fails_when_pool_not_initialized(self):
        """When DATABASE_URL is set but pool is None, should exit with code 1."""
        with patch.dict(os.environ, {'DATABASE_URL': 'postgres://fake:5432/db'}):
            mock_db_module = MagicMock()
            mock_db_module.db_pool = None
            
            with patch.dict(sys.modules, {'db': mock_db_module}):
                from forex_scheduler import require_db_pool_or_exit
                
                with pytest.raises(SystemExit) as exc_info:
                    import importlib
                    import forex_scheduler
                    importlib.reload(forex_scheduler)
                    forex_scheduler.require_db_pool_or_exit()
                
                assert exc_info.value.code == 1
    
    def test_require_db_pool_or_exit_fails_when_connection_fails(self):
        """When DATABASE_URL is set but connection fails, should exit with code 1."""
        with patch.dict(os.environ, {'DATABASE_URL': 'postgres://fake:5432/db'}):
            mock_pool = MagicMock()
            mock_pool.connection_pool = MagicMock()
            mock_pool.get_connection.side_effect = Exception("Connection refused")
            
            mock_db_module = MagicMock()
            mock_db_module.db_pool = mock_pool
            
            with patch.dict(sys.modules, {'db': mock_db_module}):
                with pytest.raises(SystemExit) as exc_info:
                    import importlib
                    import forex_scheduler
                    importlib.reload(forex_scheduler)
                    forex_scheduler.require_db_pool_or_exit()
                
                assert exc_info.value.code == 1
    
    def test_check_db_pool_ready_returns_true_when_no_database_url(self):
        """When DATABASE_URL is not set, should return True."""
        with patch.dict(os.environ, {}, clear=True):
            if 'DATABASE_URL' in os.environ:
                del os.environ['DATABASE_URL']
            
            from forex_scheduler import check_db_pool_ready
            assert check_db_pool_ready() is True
    
    def test_check_db_pool_ready_returns_false_when_pool_fails(self):
        """When DATABASE_URL is set but pool fails, should return False."""
        mock_db_module = MagicMock()
        mock_db_module.db_pool = None
        
        with patch.dict(os.environ, {'DATABASE_URL': 'postgres://fake:5432/db'}):
            with patch.dict(sys.modules, {'db': mock_db_module}):
                import importlib
                import forex_scheduler
                importlib.reload(forex_scheduler)
                
                result = forex_scheduler.check_db_pool_ready()
                assert result is False
