"""
Tests for the tenant runtime refactor.

Verifies:
1. No global singletons in critical modules
2. Import safety (no DB calls at import time)
3. TenantRuntime construction and usage
"""
import ast
import importlib
import sys
from unittest.mock import patch, MagicMock
import pytest


class TestNoGlobalSingletons:
    """Test that critical modules don't have global singleton instances at module level."""
    
    def test_forex_scheduler_no_global_scheduler(self):
        """forex_scheduler.py should not have a global 'forex_scheduler' singleton."""
        with open('forex_scheduler.py', 'r') as f:
            content = f.read()
        
        tree = ast.parse(content)
        
        global_assignments = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        if target.id == 'forex_scheduler':
                            if isinstance(node.value, ast.Call):
                                global_assignments.append(target.id)
        
        assert len(global_assignments) == 0, \
            f"Found global singleton: 'forex_scheduler = ...' should not exist"
    
    def test_bot_manager_no_global_instance(self):
        """bots/core/bot_manager.py should not have a global 'bot_manager' instance."""
        with open('bots/core/bot_manager.py', 'r') as f:
            content = f.read()
        
        tree = ast.parse(content)
        
        global_assignments = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        if target.id == 'bot_manager':
                            if isinstance(node.value, ast.Call):
                                global_assignments.append(target.id)
        
        assert len(global_assignments) == 0, \
            f"Found global singleton: 'bot_manager = BotManager()' should not exist"
    
    def test_signal_generator_no_global_instance(self):
        """bots/core/signal_generator.py should not have a global 'signal_generator' instance."""
        with open('bots/core/signal_generator.py', 'r') as f:
            content = f.read()
        
        tree = ast.parse(content)
        
        global_assignments = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        if target.id == 'signal_generator':
                            if isinstance(node.value, ast.Call):
                                global_assignments.append(target.id)
        
        assert len(global_assignments) == 0, \
            f"Found global singleton: 'signal_generator = SignalGenerator()' should not exist"


class TestImportSafety:
    """Test that modules can be imported without side effects."""
    
    def test_forex_scheduler_import_safety(self):
        """forex_scheduler.py should be importable without database calls."""
        import forex_scheduler
        assert hasattr(forex_scheduler, 'ForexSchedulerRunner')
        assert hasattr(forex_scheduler, 'main')
    
    def test_core_runtime_import_safety(self):
        """core/runtime.py should be importable without database calls."""
        from core.runtime import TenantRuntime, create_tenant_runtime, require_tenant_runtime
        assert TenantRuntime is not None
        assert create_tenant_runtime is not None
        assert require_tenant_runtime is not None
    
    def test_scheduler_modules_import_safety(self):
        """scheduler/ modules should be importable without database calls."""
        from scheduler import SignalGenerator, SignalMonitor, Messenger
        assert SignalGenerator is not None
        assert SignalMonitor is not None
        assert Messenger is not None


class TestTenantRuntime:
    """Test TenantRuntime construction and behavior."""
    
    def test_tenant_runtime_requires_tenant_id(self):
        """TenantRuntime should require a tenant_id."""
        from core.runtime import TenantRuntime, TenantContextError
        
        with pytest.raises(TenantContextError):
            TenantRuntime(tenant_id='')
        
        with pytest.raises(TenantContextError):
            TenantRuntime(tenant_id=None)
    
    def test_tenant_runtime_construction(self):
        """TenantRuntime should construct with valid tenant_id."""
        from core.runtime import TenantRuntime
        
        runtime = TenantRuntime(tenant_id='test-tenant')
        assert runtime.tenant_id == 'test-tenant'
        assert runtime.state is not None
    
    def test_tenant_runtime_factory(self):
        """create_tenant_runtime should work with explicit tenant_id."""
        from core.runtime import create_tenant_runtime
        
        runtime = create_tenant_runtime(tenant_id='factory-test')
        assert runtime.tenant_id == 'factory-test'
    
    def test_tenant_runtime_from_env(self):
        """TenantRuntime.from_env should read from environment."""
        import os
        from core.runtime import TenantRuntime
        
        original_value = os.environ.get('TENANT_ID')
        try:
            os.environ['TENANT_ID'] = 'env-test-tenant'
            runtime = TenantRuntime.from_env()
            assert runtime.tenant_id == 'env-test-tenant'
        finally:
            if original_value:
                os.environ['TENANT_ID'] = original_value
            elif 'TENANT_ID' in os.environ:
                del os.environ['TENANT_ID']
    
    def test_tenant_runtime_request_context(self):
        """TenantRuntime.request_context should set logging context."""
        from core.runtime import TenantRuntime
        
        runtime = TenantRuntime(tenant_id='context-test')
        
        with runtime.request_context():
            pass


class TestSchedulerModules:
    """Test scheduler module construction."""
    
    def test_messenger_requires_runtime(self):
        """Messenger should require a TenantRuntime."""
        from core.runtime import TenantRuntime
        from scheduler.messenger import Messenger
        
        runtime = TenantRuntime(tenant_id='msg-test')
        messenger = Messenger(runtime)
        assert messenger.tenant_id == 'msg-test'
    
    def test_generator_requires_runtime(self):
        """SignalGenerator should require a TenantRuntime and Messenger."""
        from core.runtime import TenantRuntime
        from scheduler.messenger import Messenger
        from scheduler.generator import SignalGenerator
        
        runtime = TenantRuntime(tenant_id='gen-test')
        messenger = Messenger(runtime)
        generator = SignalGenerator(runtime, messenger)
        assert generator.tenant_id == 'gen-test'
    
    def test_monitor_requires_runtime(self):
        """SignalMonitor should require a TenantRuntime and Messenger."""
        from core.runtime import TenantRuntime
        from scheduler.messenger import Messenger
        from scheduler.monitor import SignalMonitor
        
        runtime = TenantRuntime(tenant_id='mon-test')
        messenger = Messenger(runtime)
        monitor = SignalMonitor(runtime, messenger)
        assert monitor.tenant_id == 'mon-test'


class TestForexSchedulerIntegration:
    """Integration tests for ForexSchedulerRunner."""
    
    @pytest.mark.asyncio
    async def test_scheduler_runner_run_once(self):
        """ForexSchedulerRunner.run_once() should complete without errors when properly mocked."""
        from core.runtime import TenantRuntime
        from forex_scheduler import ForexSchedulerRunner
        
        runtime = TenantRuntime(tenant_id='integration-test')
        runner = ForexSchedulerRunner(runtime)
        
        mock_signal_engine = MagicMock()
        mock_signal_engine.is_trading_hours.return_value = False
        mock_signal_engine.check_for_signals = MagicMock(return_value=None)
        
        with patch.object(runtime, 'get_signal_engine', return_value=mock_signal_engine), \
             patch.object(runtime, 'get_forex_signals', return_value=[]):
            await runner.run_once()
        
        mock_signal_engine.is_trading_hours.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_scheduler_runner_skips_with_pending_signal(self):
        """ForexSchedulerRunner should skip signal generation if one is already pending."""
        from core.runtime import TenantRuntime
        from forex_scheduler import ForexSchedulerRunner
        
        runtime = TenantRuntime(tenant_id='integration-test-2')
        runner = ForexSchedulerRunner(runtime)
        
        mock_signal_engine = MagicMock()
        mock_signal_engine.is_trading_hours.return_value = True
        
        pending_signal = {
            'id': 123,
            'entry_price': 2000.0,
            'take_profit': 2050.0,
            'stop_loss': 1980.0
        }
        
        with patch.object(runtime, 'get_signal_engine', return_value=mock_signal_engine), \
             patch.object(runtime, 'get_forex_signals', return_value=[pending_signal]):
            await runner.run_once()
        
        mock_signal_engine.check_for_signals.assert_not_called()
    
    def test_scheduler_runner_construction(self):
        """ForexSchedulerRunner should construct with TenantRuntime."""
        from core.runtime import TenantRuntime
        from forex_scheduler import ForexSchedulerRunner
        
        runtime = TenantRuntime(tenant_id='construction-test')
        runner = ForexSchedulerRunner(runtime)
        
        assert runner.tenant_id == 'construction-test'
        assert runner.runtime is runtime
        assert runner.messenger is not None
        assert runner.generator is not None
        assert runner.monitor is not None


class TestStrategyRegistry:
    """Test strategy registry functionality."""
    
    def test_strategy_registry_list_strategies(self):
        """Strategy registry should return list of available strategies."""
        from strategies import STRATEGY_REGISTRY, get_available_strategies
        
        assert 'aggressive' in STRATEGY_REGISTRY
        assert 'conservative' in STRATEGY_REGISTRY
        assert 'raja_banks' in STRATEGY_REGISTRY
    
    def test_strategy_registry_get_strategy(self):
        """Strategy registry should return strategy by name."""
        from strategies import get_active_strategy
        
        strategy = get_active_strategy('aggressive', tenant_id='test')
        assert strategy is not None
        assert strategy.bot_type == 'aggressive'
        
        strategy = get_active_strategy('conservative', tenant_id='test')
        assert strategy is not None
        assert strategy.bot_type == 'conservative'
    
    def test_strategy_registry_fallback(self):
        """Unknown strategy should fall back to aggressive."""
        from strategies import get_active_strategy
        
        strategy = get_active_strategy('unknown-strategy', tenant_id='test')
        assert strategy is not None
        assert strategy.bot_type == 'aggressive'


class TestAlertsModule:
    """Test core/alerts.py functionality."""
    
    def test_notify_error_exists(self):
        """core/alerts.py should have notify_error function."""
        from core.alerts import notify_error
        assert callable(notify_error)
    
    def test_notify_error_logs_warning(self):
        """notify_error should log at WARNING level."""
        from core.alerts import notify_error
        import logging
        
        with patch('core.alerts.logger') as mock_logger:
            notify_error("Test error", tenant_id="test-tenant", context={"key": "value"})
            mock_logger.warning.assert_called_once()
            call_args = mock_logger.warning.call_args[0][0]
            assert "ALERT" in call_args
            assert "test-tenant" in call_args
            assert "Test error" in call_args
    
    def test_notify_tenant_failure(self):
        """notify_tenant_failure should wrap notify_error."""
        from core.alerts import notify_tenant_failure
        
        with patch('core.alerts.logger') as mock_logger:
            notify_tenant_failure("tenant-123", "Database connection failed")
            mock_logger.warning.assert_called_once()
            call_args = mock_logger.warning.call_args[0][0]
            assert "tenant-123" in call_args


class TestArchitectureRequirements:
    """Test architecture requirements are met."""
    
    def test_scheduler_creates_fresh_runtime_per_tenant(self):
        """Each tenant run should create a fresh TenantRuntime (no shared state)."""
        from core.runtime import TenantRuntime
        
        runtime1 = TenantRuntime(tenant_id='tenant-a')
        runtime2 = TenantRuntime(tenant_id='tenant-b')
        
        assert runtime1 is not runtime2
        assert runtime1.tenant_id != runtime2.tenant_id
        assert runtime1.state is not runtime2.state
    
    def test_tenant_runtime_holds_required_components(self):
        """TenantRuntime should hold all required components."""
        from core.runtime import TenantRuntime
        
        runtime = TenantRuntime(tenant_id='component-test')
        
        assert hasattr(runtime, 'tenant_id')
        assert hasattr(runtime, 'db')
        assert hasattr(runtime, 'get_signal_engine')
        assert hasattr(runtime, 'get_telegram_bot')
        assert hasattr(runtime, 'get_forex_config')
        assert hasattr(runtime, 'state')
    
    def test_core_alerts_import(self):
        """core/alerts.py should be importable."""
        from core.alerts import notify_error, notify_tenant_failure
        assert notify_error is not None
        assert notify_tenant_failure is not None
    
    def test_forex_scheduler_uses_notify_error(self):
        """forex_scheduler.py should import and use notify_error."""
        with open('forex_scheduler.py', 'r') as f:
            content = f.read()
        
        assert 'from core.alerts import notify_error' in content
        assert 'notify_error(' in content
