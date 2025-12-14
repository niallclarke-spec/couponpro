"""
Strategy Import Tests

Verifies that both import paths work identically:
- strategies/ (canonical)
- bots/strategies/ (backwards compat shim)

Ensures no duplicate registrations and same object references.
"""
import pytest


class TestStrategyImportPaths:
    """Test that both strategy import paths work identically."""
    
    def test_canonical_import_works(self):
        """strategies/ should be importable."""
        import strategies
        
        assert hasattr(strategies, 'BaseStrategy')
        assert hasattr(strategies, 'get_active_strategy')
        assert hasattr(strategies, 'STRATEGY_REGISTRY')
    
    def test_compat_import_works(self):
        """bots/strategies/ should be importable."""
        import bots.strategies
        
        assert hasattr(bots.strategies, 'BaseStrategy')
        assert hasattr(bots.strategies, 'get_active_strategy')
        assert hasattr(bots.strategies, 'STRATEGY_REGISTRY')
    
    def test_base_strategy_same_class(self):
        """Both paths should reference the same BaseStrategy class."""
        from strategies import BaseStrategy as CanonicalBase
        from bots.strategies import BaseStrategy as CompatBase
        
        assert CanonicalBase is CompatBase
    
    def test_aggressive_strategy_same_class(self):
        """Both paths should reference the same AggressiveStrategy class."""
        from strategies.aggressive import AggressiveStrategy as CanonicalAgg
        from bots.strategies import AggressiveStrategy as CompatAgg
        
        assert CanonicalAgg is CompatAgg
    
    def test_conservative_strategy_same_class(self):
        """Both paths should reference the same ConservativeStrategy class."""
        from strategies.conservative import ConservativeStrategy as CanonicalCon
        from bots.strategies import ConservativeStrategy as CompatCon
        
        assert CanonicalCon is CompatCon
    
    def test_raja_banks_strategy_same_class(self):
        """Both paths should reference the same RajaBanksStrategy class."""
        from strategies.raja_banks import RajaBanksStrategy as CanonicalRB
        from bots.strategies import RajaBanksStrategy as CompatRB
        
        assert CanonicalRB is CompatRB
    
    def test_get_active_strategy_same_function(self):
        """Both paths should reference the same get_active_strategy function."""
        from strategies import get_active_strategy as CanonicalFn
        from bots.strategies import get_active_strategy as CompatFn
        
        assert CanonicalFn is CompatFn
    
    def test_registry_same_object(self):
        """Both paths should reference the same STRATEGY_REGISTRY."""
        from strategies import STRATEGY_REGISTRY as CanonicalReg
        from bots.strategies import STRATEGY_REGISTRY as CompatReg
        
        assert CanonicalReg is CompatReg
    
    def test_no_duplicate_registrations(self):
        """Importing both should not create duplicate registry entries."""
        import strategies
        import bots.strategies
        
        from strategies import STRATEGY_REGISTRY
        
        strategy_names = list(STRATEGY_REGISTRY.keys())
        unique_names = set(strategy_names)
        
        assert len(strategy_names) == len(unique_names), \
            f"Duplicate registrations found: {strategy_names}"
    
    def test_registry_has_expected_strategies(self):
        """Registry should contain expected strategies."""
        from strategies import STRATEGY_REGISTRY
        
        assert 'aggressive' in STRATEGY_REGISTRY
        assert 'conservative' in STRATEGY_REGISTRY
        assert 'raja_banks' in STRATEGY_REGISTRY
    
    def test_get_active_strategy_returns_valid_instance(self):
        """get_active_strategy should return working strategy instances."""
        from strategies import get_active_strategy
        
        strategy = get_active_strategy('aggressive', tenant_id='import-test')
        assert strategy is not None
        assert hasattr(strategy, 'bot_type')
        assert strategy.bot_type == 'aggressive'
