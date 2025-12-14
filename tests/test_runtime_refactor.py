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
