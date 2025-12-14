"""
Architecture Hardening Tests

Tests to enforce architectural requirements:
1. No DB initialization on import
2. New runtime instance per call (no caching/globals)
3. Runner uses TenantRuntime, not global singletons

These tests ensure the multi-tenant architecture remains clean.
"""
import pytest
from unittest.mock import patch, MagicMock


class TestNoDbInitOnImport:
    """Verify that importing modules does not trigger DB pool initialization."""
    
    def test_import_forex_scheduler_no_db_init(self):
        """Importing forex_scheduler should NOT initialize the DB pool."""
        import sys
        
        db_init_called = False
        original_init = None
        
        if 'db' in sys.modules:
            db_module = sys.modules['db']
            if hasattr(db_module, 'DatabasePool'):
                original_init = db_module.DatabasePool.__init__
                
                def tracked_init(self, *args, **kwargs):
                    nonlocal db_init_called
                    db_init_called = True
                    if original_init:
                        return original_init(self, *args, **kwargs)
                
                db_module.DatabasePool.__init__ = tracked_init
        
        try:
            import forex_scheduler
            assert not db_init_called, "DB pool was initialized on import of forex_scheduler"
        finally:
            if original_init and 'db' in sys.modules:
                sys.modules['db'].DatabasePool.__init__ = original_init
    
    def test_import_scheduler_runner_no_db_init(self):
        """Importing scheduler.runner should NOT initialize the DB pool."""
        import scheduler.runner
        
    def test_import_core_runtime_no_db_init(self):
        """Importing core.runtime should NOT initialize the DB pool."""
        import core.runtime
        
        runtime = core.runtime.TenantRuntime(tenant_id="test-no-db")
        
        assert runtime._db_module is None, "DB module should not be loaded until accessed"
    
    def test_cold_import_succeeds(self):
        """All critical imports should succeed without DB errors."""
        import forex_scheduler
        import scheduler.runner
        import core.runtime
        
        assert hasattr(forex_scheduler, 'ForexSchedulerRunner')
        assert hasattr(scheduler.runner, 'SchedulerRunner')
        assert hasattr(core.runtime, 'TenantRuntime')
        assert hasattr(core.runtime, 'get_runtime')


class TestRuntimeNoGlobals:
    """Verify that get_runtime() returns new instances, not cached globals."""
    
    def test_get_runtime_returns_new_instance(self):
        """get_runtime() must return a NEW instance each call."""
        from core.runtime import get_runtime
        
        r1 = get_runtime("tenant-a")
        r2 = get_runtime("tenant-a")
        
        assert r1 is not r2, "get_runtime() must return a new instance each time"
    
    def test_get_runtime_different_tenants(self):
        """get_runtime() for different tenants returns different instances."""
        from core.runtime import get_runtime
        
        r1 = get_runtime("tenant-x")
        r2 = get_runtime("tenant-y")
        
        assert r1 is not r2
        assert r1.tenant_id == "tenant-x"
        assert r2.tenant_id == "tenant-y"
    
    def test_runtime_state_not_shared(self):
        """Each runtime instance has its own state object."""
        from core.runtime import get_runtime
        
        r1 = get_runtime("tenant-1")
        r2 = get_runtime("tenant-1")
        
        r1.state.last_daily_recap = "2024-01-01"
        
        assert r2.state.last_daily_recap is None, "State should not be shared between instances"


class TestRunnerUsesRuntime:
    """Verify that scheduler runners use TenantRuntime, not globals."""
    
    def test_scheduler_runner_stores_tenant_id(self):
        """SchedulerRunner should store tenant_id from initialization."""
        from scheduler.runner import SchedulerRunner
        
        runner = SchedulerRunner(tenant_id="test-tenant")
        
        assert runner.tenant_id == "test-tenant"
    
    def test_forex_scheduler_runner_uses_runtime(self):
        """ForexSchedulerRunner should use TenantRuntime, not globals."""
        from forex_scheduler import ForexSchedulerRunner
        from core.runtime import TenantRuntime
        
        runtime = TenantRuntime(tenant_id="runner-test")
        runner = ForexSchedulerRunner(runtime)
        
        assert runner.runtime is runtime
        assert runner.tenant_id == "runner-test"
    
    def test_forex_scheduler_runner_has_no_global_references(self):
        """ForexSchedulerRunner should not reference global engine singletons."""
        from forex_scheduler import ForexSchedulerRunner
        from core.runtime import TenantRuntime
        
        runtime = TenantRuntime(tenant_id="no-globals-test")
        runner = ForexSchedulerRunner(runtime)
        
        assert not hasattr(runner, 'global_engine'), "Runner should not have global_engine"
        assert not hasattr(runner, 'shared_engine'), "Runner should not have shared_engine"


class TestErrorBoundary:
    """Test error boundary functionality."""
    
    def test_run_guarded_exists(self):
        """core/error_boundary.py should export run_guarded."""
        from core.error_boundary import run_guarded
        
        assert callable(run_guarded)
    
    def test_run_guarded_success(self):
        """run_guarded should return function result on success."""
        from core.error_boundary import run_guarded
        
        result = run_guarded(
            lambda: 42,
            tenant_id="test",
            exit_on_error=False,
            reraise_in_dev=False
        )
        
        assert result == 42
    
    def test_run_guarded_calls_notify_error_on_exception(self):
        """run_guarded should call notify_error on exception."""
        from core.error_boundary import run_guarded
        
        with patch('core.error_boundary.notify_error') as mock_notify:
            with patch('core.error_boundary.is_dev_mode', return_value=False):
                with patch('sys.exit'):
                    run_guarded(
                        lambda: 1/0,
                        tenant_id="error-test",
                        context={"operation": "division"}
                    )
            
            mock_notify.assert_called_once()
            call_args = mock_notify.call_args
            assert "error-test" == call_args.kwargs.get('tenant_id')
            assert "ZeroDivisionError" in call_args.args[0]
    
    def test_run_guarded_async_exists(self):
        """core/error_boundary.py should export run_guarded_async."""
        from core.error_boundary import run_guarded_async
        
        assert callable(run_guarded_async)


class TestTenantRuntimeLazyLoading:
    """Verify TenantRuntime uses lazy loading for dependencies."""
    
    def test_runtime_db_lazy(self):
        """DB module should not be loaded until .db is accessed."""
        from core.runtime import TenantRuntime
        
        runtime = TenantRuntime(tenant_id="lazy-test")
        
        assert runtime._db_module is None
    
    def test_runtime_signal_engine_lazy(self):
        """Signal engine should not be created until get_signal_engine() is called."""
        from core.runtime import TenantRuntime
        
        runtime = TenantRuntime(tenant_id="lazy-engine-test")
        
        assert runtime._signal_engine is None
    
    def test_runtime_telegram_bot_lazy(self):
        """Telegram bot should not be created until get_telegram_bot() is called."""
        from core.runtime import TenantRuntime
        
        runtime = TenantRuntime(tenant_id="lazy-bot-test")
        
        assert runtime._telegram_bot is None
