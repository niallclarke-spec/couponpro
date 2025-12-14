#!/usr/bin/env python3
"""
Smoke Test: Tenant Isolation Verification

Tests database isolation between two tenants across key tables:
- forex_signals
- forex_config  
- bot_config

Requirements:
    - Postgres DATABASE_URL must be set and reachable
    - Example: export DATABASE_URL="postgres://user:pass@host:5432/dbname"

Usage:
    python scripts/smoke_tenant_isolation.py
    python scripts/smoke_tenant_isolation.py --tenant-a foo --tenant-b bar
    python scripts/smoke_tenant_isolation.py --keep-data

Options:
    --keep-data    Retains test rows for manual inspection after run

Exit codes:
    0 = All tests passed
    1 = One or more tests failed
"""
import argparse
import os
import sys
from datetime import datetime
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.logging import get_logger

logger = get_logger(__name__)


def parse_args():
    parser = argparse.ArgumentParser(description='Tenant Isolation Smoke Test')
    parser.add_argument('--tenant-a', type=str, default='tenant_smoke_a',
                        help='First tenant ID (default: tenant_smoke_a)')
    parser.add_argument('--tenant-b', type=str, default='tenant_smoke_b',
                        help='Second tenant ID (default: tenant_smoke_b)')
    parser.add_argument('--keep-data', action='store_true',
                        help='Keep test data after test run (default: cleanup)')
    return parser.parse_args()


class TenantIsolationTest:
    """Tests tenant isolation across database operations."""
    
    def __init__(self, tenant_a: str, tenant_b: str, keep_data: bool = False):
        self.tenant_a = tenant_a
        self.tenant_b = tenant_b
        self.keep_data = keep_data
        self.created_signals = []
        self.passed = 0
        self.failed = 0
        self.db = None
        self.db_initialized = False
    
    def setup(self):
        """Initialize database connection with fail-fast behavior."""
        db_url = os.environ.get('DATABASE_URL')
        if not db_url:
            print("Smoke test requires a reachable Postgres DATABASE_URL. Connection failed: DATABASE_URL not set")
            sys.exit(1)
        
        try:
            import db as db_module
            self.db = db_module
            
            if not self.db.db_pool or not self.db.db_pool.connection_pool:
                print("Smoke test requires a reachable Postgres DATABASE_URL. Connection failed: database pool not initialized")
                sys.exit(1)
            
            with self.db.db_pool.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                cursor.fetchone()
            
            self.db_initialized = True
            
        except Exception as e:
            print(f"Smoke test requires a reachable Postgres DATABASE_URL. Connection failed: {e}")
            sys.exit(1)
        
        logger.info(f"Testing isolation between tenant_a={self.tenant_a} and tenant_b={self.tenant_b}")
    
    def cleanup(self):
        """Remove test data created during tests."""
        if not self.db_initialized:
            return
        
        if self.keep_data:
            logger.info("--keep-data specified, skipping cleanup")
            return
        
        logger.info("Cleaning up test data...")
        
        try:
            with self.db.db_pool.get_connection() as conn:
                cursor = conn.cursor()
                
                for signal_id, tenant_id in self.created_signals:
                    cursor.execute(
                        "DELETE FROM forex_signals WHERE id = %s AND tenant_id = %s",
                        (signal_id, tenant_id)
                    )
                
                cursor.execute(
                    "DELETE FROM forex_config WHERE tenant_id = %s",
                    (self.tenant_a,)
                )
                cursor.execute(
                    "DELETE FROM forex_config WHERE tenant_id = %s",
                    (self.tenant_b,)
                )
                
                cursor.execute(
                    "DELETE FROM bot_config WHERE tenant_id = %s",
                    (self.tenant_a,)
                )
                cursor.execute(
                    "DELETE FROM bot_config WHERE tenant_id = %s",
                    (self.tenant_b,)
                )
                
                conn.commit()
                logger.info(f"Cleaned up {len(self.created_signals)} signals and configs")
        except Exception as e:
            logger.error(f"Cleanup failed: {e}")
    
    def assert_test(self, condition: bool, test_name: str, details: str = ""):
        """Record test result."""
        if condition:
            self.passed += 1
            logger.info(f"✅ PASS: {test_name}")
        else:
            self.failed += 1
            logger.error(f"❌ FAIL: {test_name} - {details}")
        return condition
    
    def test_forex_signals_read_isolation(self):
        """Test that tenant_b cannot read tenant_a's forex_signals."""
        logger.info("\n--- Testing forex_signals READ isolation ---")
        
        signal_id = self.db.create_forex_signal(
            signal_type='BUY',
            pair='XAU/USD',
            timeframe='15m',
            entry_price=Decimal('2000.00'),
            tenant_id=self.tenant_a,
            take_profit=Decimal('2010.00'),
            stop_loss=Decimal('1990.00')
        )
        self.created_signals.append((signal_id, self.tenant_a))
        
        self.assert_test(signal_id is not None, "Create signal for tenant_a")
        
        signals_a = self.db.get_forex_signals(self.tenant_a, status='pending')
        found_in_a = any(s['id'] == signal_id for s in signals_a)
        self.assert_test(found_in_a, "Tenant_a can read own signal")
        
        signals_b = self.db.get_forex_signals(self.tenant_b, status='pending')
        found_in_b = any(s['id'] == signal_id for s in signals_b)
        self.assert_test(not found_in_b, "Tenant_b CANNOT read tenant_a's signal", 
                        f"Found signal {signal_id} in tenant_b results")
    
    def test_forex_signals_update_isolation(self):
        """Test that tenant_b cannot update tenant_a's forex_signals."""
        logger.info("\n--- Testing forex_signals UPDATE isolation ---")
        
        signal_id = self.db.create_forex_signal(
            signal_type='SELL',
            pair='XAU/USD',
            timeframe='15m',
            entry_price=Decimal('2050.00'),
            tenant_id=self.tenant_a,
            take_profit=Decimal('2040.00'),
            stop_loss=Decimal('2060.00')
        )
        self.created_signals.append((signal_id, self.tenant_a))
        
        result = self.db.update_signal_status(signal_id, 'active', self.tenant_b)
        
        signals_a = self.db.get_forex_signals(self.tenant_a, status='pending')
        still_pending = any(s['id'] == signal_id and s['status'] == 'pending' for s in signals_a)
        
        self.assert_test(still_pending, "Tenant_b update has no effect on tenant_a's signal",
                        "Signal status was changed by wrong tenant")
        
        result = self.db.update_signal_status(signal_id, 'active', self.tenant_a)
        signals_a = self.db.get_forex_signals(self.tenant_a, status='active')
        now_active = any(s['id'] == signal_id and s['status'] == 'active' for s in signals_a)
        
        self.assert_test(now_active, "Tenant_a CAN update own signal")
    
    def test_forex_config_isolation(self):
        """Test forex_config tenant isolation."""
        logger.info("\n--- Testing forex_config isolation ---")
        
        config_a = self.db.get_forex_config(self.tenant_a)
        config_b = self.db.get_forex_config(self.tenant_b)
        
        self.assert_test(
            config_a.get('tenant_id') == self.tenant_a or config_a == {},
            "forex_config returns correct tenant or empty",
            f"Got tenant_id={config_a.get('tenant_id')}"
        )
        
        self.assert_test(
            config_b.get('tenant_id') == self.tenant_b or config_b == {},
            "forex_config for tenant_b returns correct tenant or empty",
            f"Got tenant_id={config_b.get('tenant_id')}"
        )
    
    def test_bot_config_isolation(self):
        """Test bot_config tenant isolation."""
        logger.info("\n--- Testing bot_config isolation ---")
        
        config_a = self.db.get_bot_config(self.tenant_a)
        config_b = self.db.get_bot_config(self.tenant_b)
        
        self.assert_test(
            config_a.get('tenant_id') == self.tenant_a or config_a == {},
            "bot_config returns correct tenant or empty",
            f"Got tenant_id={config_a.get('tenant_id')}"
        )
        
        self.assert_test(
            config_b.get('tenant_id') == self.tenant_b or config_b == {},
            "bot_config for tenant_b returns correct tenant or empty", 
            f"Got tenant_id={config_b.get('tenant_id')}"
        )
    
    def run_all_tests(self) -> int:
        """Run all isolation tests and return exit code."""
        try:
            self.setup()
            
            self.test_forex_signals_read_isolation()
            self.test_forex_signals_update_isolation()
            self.test_forex_config_isolation()
            self.test_bot_config_isolation()
            
            return 0 if self.failed == 0 else 1
            
        except Exception as e:
            logger.exception(f"Test suite error: {e}")
            return 1
        finally:
            self.cleanup()
            self.print_summary()
    
    def print_summary(self):
        """Print test results summary."""
        total = self.passed + self.failed
        logger.info("\n" + "=" * 50)
        logger.info(f"TENANT ISOLATION SMOKE TEST RESULTS")
        logger.info(f"Passed: {self.passed}/{total}")
        logger.info(f"Failed: {self.failed}/{total}")
        logger.info("=" * 50)
        
        if self.failed == 0:
            logger.info("✅ ALL TESTS PASSED")
        else:
            logger.error("❌ SOME TESTS FAILED")


def main():
    args = parse_args()
    
    test = TenantIsolationTest(
        tenant_a=args.tenant_a,
        tenant_b=args.tenant_b,
        keep_data=args.keep_data
    )
    
    exit_code = test.run_all_tests()
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
