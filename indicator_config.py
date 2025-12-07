"""
Centralized Indicator Configuration Registry

This module defines all trading indicators in one place. Both signal generation
and thesis validation read from this registry, ensuring consistency.

To add a new indicator:
1. Add an entry to INDICATOR_REGISTRY with all required fields
2. The signal engine and thesis validator will automatically use it

To remove an indicator:
3. Set 'enabled': False or remove the entry entirely
"""

INDICATOR_REGISTRY = {
    'rsi': {
        'enabled': True,
        'name': 'RSI',
        'full_name': 'Relative Strength Index',
        'api_indicator': 'rsi',
        'api_params': {'time_period': 14},
        
        'signal_logic': {
            'buy_condition': lambda val, config: val < config.get('rsi_oversold', 48),
            'sell_condition': lambda val, config: val > config.get('rsi_overbought', 52),
            'description': 'Momentum oscillator measuring speed of price changes'
        },
        
        'validation_logic': {
            'weakening': {
                'buy': lambda current, original: current > 55,
                'sell': lambda current, original: current < 45,
                'description': 'RSI drifting toward neutral zone'
            },
            'broken': {
                'buy': lambda current, original: current > 65,
                'sell': lambda current, original: current < 35,
                'description': 'RSI in opposite extreme zone'
            }
        },
        
        'display': {
            'format': '{:.2f}',
            'emoji': '📊',
            'unit': ''
        }
    },
    
    'macd': {
        'enabled': True,
        'name': 'MACD',
        'full_name': 'Moving Average Convergence Divergence',
        'api_indicator': 'macd',
        'api_params': {'fast_period': 12, 'slow_period': 26, 'signal_period': 9},
        'value_key': 'macd',
        
        'signal_logic': {
            'buy_condition': lambda val, config: val > 0,
            'sell_condition': lambda val, config: val < 0,
            'description': 'Trend-following momentum indicator'
        },
        
        'validation_logic': {
            'weakening': {
                'buy': lambda current, original: current < original * 0.5 if original > 0 else False,
                'sell': lambda current, original: current > original * 0.5 if original < 0 else False,
                'description': 'MACD histogram weakening significantly'
            },
            'broken': {
                'buy': lambda current, original: current < 0,
                'sell': lambda current, original: current > 0,
                'description': 'MACD histogram flipped to opposite side'
            }
        },
        
        'display': {
            'format': '{:.4f}',
            'emoji': '📈',
            'unit': ''
        }
    },
    
    'adx': {
        'enabled': True,
        'name': 'ADX',
        'full_name': 'Average Directional Index',
        'api_indicator': 'adx',
        'api_params': {'time_period': 14},
        
        'signal_logic': {
            'buy_condition': lambda val, config: val > config.get('adx_threshold', 5),
            'sell_condition': lambda val, config: val > config.get('adx_threshold', 5),
            'description': 'Measures trend strength regardless of direction'
        },
        
        'validation_logic': {
            'weakening': {
                'buy': lambda current, original: current < original * 0.7,
                'sell': lambda current, original: current < original * 0.7,
                'description': 'ADX declining, trend losing strength'
            },
            'broken': {
                'buy': lambda current, original: current < 15,
                'sell': lambda current, original: current < 15,
                'description': 'ADX below threshold, no clear trend'
            }
        },
        
        'display': {
            'format': '{:.2f}',
            'emoji': '💪',
            'unit': ''
        }
    },
    
    'stochastic': {
        'enabled': True,
        'name': 'Stochastic',
        'full_name': 'Stochastic Oscillator',
        'api_indicator': 'stoch',
        'api_params': {'fast_k_period': 14, 'slow_k_period': 3, 'slow_d_period': 3},
        'value_key': 'k',
        
        'signal_logic': {
            'buy_condition': lambda val, config: val < 30,
            'sell_condition': lambda val, config: val > 70,
            'description': 'Momentum indicator comparing closing price to price range'
        },
        
        'validation_logic': {
            'weakening': {
                'buy': lambda current, original: current > 60,
                'sell': lambda current, original: current < 40,
                'description': 'Stochastic moving toward opposite zone'
            },
            'broken': {
                'buy': lambda current, original: current > 75,
                'sell': lambda current, original: current < 25,
                'description': 'Stochastic reversed to opposite extreme'
            }
        },
        
        'display': {
            'format': '{:.2f}',
            'emoji': '🔄',
            'unit': ''
        }
    },
    
    'bollinger': {
        'enabled': True,
        'name': 'Bollinger',
        'full_name': 'Bollinger Bands',
        'api_indicator': 'bbands',
        'api_params': {'time_period': 20, 'sd': 2},
        'value_key': 'middle',
        
        'signal_logic': {
            'buy_condition': lambda val, config: True,
            'sell_condition': lambda val, config: True,
            'description': 'Volatility bands around moving average'
        },
        
        'validation_logic': {
            'weakening': {
                'buy': lambda current, original: False,
                'sell': lambda current, original: False,
                'description': 'Bollinger position shifted'
            },
            'broken': {
                'buy': lambda current, original: False,
                'sell': lambda current, original: False,
                'description': 'Price crossed opposite Bollinger band'
            }
        },
        
        'display': {
            'format': '{:.2f}',
            'emoji': '📉',
            'unit': ''
        }
    },
    
    'atr': {
        'enabled': True,
        'name': 'ATR',
        'full_name': 'Average True Range',
        'api_indicator': 'atr',
        'api_params': {'time_period': 14},
        'is_volatility_indicator': True,
        
        'signal_logic': {
            'buy_condition': lambda val, config: True,
            'sell_condition': lambda val, config: True,
            'description': 'Volatility measure for position sizing'
        },
        
        'validation_logic': {
            'weakening': {
                'buy': lambda current, original: False,
                'sell': lambda current, original: False,
                'description': 'N/A - ATR used for sizing only'
            },
            'broken': {
                'buy': lambda current, original: False,
                'sell': lambda current, original: False,
                'description': 'N/A - ATR used for sizing only'
            }
        },
        
        'display': {
            'format': '{:.2f}',
            'emoji': '📉',
            'unit': ''
        }
    }
}


def get_enabled_indicators():
    """Return list of enabled indicator keys"""
    return [key for key, config in INDICATOR_REGISTRY.items() if config.get('enabled', True)]


def get_signal_indicators():
    """Return indicators used for signal generation (excludes volatility-only indicators)"""
    return [
        key for key, config in INDICATOR_REGISTRY.items() 
        if config.get('enabled', True) and not config.get('is_volatility_indicator', False)
    ]


def get_validation_indicators():
    """Return indicators used for thesis validation"""
    return [
        key for key, config in INDICATOR_REGISTRY.items() 
        if config.get('enabled', True) 
        and not config.get('is_volatility_indicator', False)
        and config.get('validation_logic')
    ]


def get_indicator_config(indicator_key):
    """Get configuration for a specific indicator"""
    return INDICATOR_REGISTRY.get(indicator_key)


def check_signal_condition(indicator_key, value, signal_type, forex_config):
    """
    Check if an indicator supports the given signal type.
    
    Args:
        indicator_key: Key from INDICATOR_REGISTRY
        value: Current indicator value
        signal_type: 'BUY' or 'SELL'
        forex_config: Config dict with thresholds (rsi_oversold, rsi_overbought, adx_threshold)
    
    Returns:
        bool: True if condition is met
    """
    config = INDICATOR_REGISTRY.get(indicator_key)
    if not config or not config.get('enabled', True):
        return True
    
    signal_logic = config.get('signal_logic', {})
    
    if signal_type == 'BUY':
        condition = signal_logic.get('buy_condition')
    else:
        condition = signal_logic.get('sell_condition')
    
    if condition and callable(condition):
        try:
            return condition(value, forex_config)
        except Exception:
            return True
    
    return True


def validate_indicator_thesis(indicator_key, current_value, original_value, signal_type):
    """
    Check if an indicator's thesis is still valid.
    
    Args:
        indicator_key: Key from INDICATOR_REGISTRY
        current_value: Current indicator value
        original_value: Original value at signal creation
        signal_type: 'BUY' or 'SELL'
    
    Returns:
        tuple: (status, description) where status is 'intact', 'weakening', or 'broken'
    """
    config = INDICATOR_REGISTRY.get(indicator_key)
    if not config or not config.get('enabled', True):
        return ('intact', None)
    
    validation = config.get('validation_logic', {})
    direction = 'buy' if signal_type == 'BUY' else 'sell'
    
    broken = validation.get('broken', {})
    broken_check = broken.get(direction)
    if broken_check and callable(broken_check):
        try:
            if broken_check(current_value, original_value):
                return ('broken', broken.get('description', f'{config["name"]} thesis broken'))
        except Exception:
            pass
    
    weakening = validation.get('weakening', {})
    weakening_check = weakening.get(direction)
    if weakening_check and callable(weakening_check):
        try:
            if weakening_check(current_value, original_value):
                return ('weakening', weakening.get('description', f'{config["name"]} showing weakness'))
        except Exception:
            pass
    
    return ('intact', None)


def get_indicator_display(indicator_key, value):
    """Format an indicator value for display"""
    config = INDICATOR_REGISTRY.get(indicator_key)
    if not config:
        return str(value)
    
    display = config.get('display', {})
    fmt = display.get('format', '{:.2f}')
    emoji = display.get('emoji', '')
    unit = display.get('unit', '')
    
    try:
        formatted = fmt.format(value)
        return f"{emoji} {config['name']}: {formatted}{unit}"
    except Exception:
        return f"{emoji} {config['name']}: {value}"
