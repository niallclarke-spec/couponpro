"""
Trade Win Showcase Module

Generates branded images showcasing trading account wins.
Used with TP hit notifications to demonstrate real performance.
"""

from showcase.trade_win_generator import (
    generate_trade_win_image,
    generate_single_trade_image,
    TradeWinData
)

from showcase.profit_calculator import (
    COMMISSION_PER_LOT,
    USD_PER_PIP,
    DEFAULT_LOT_SIZE,
    TradeProfit,
    calculate_pips,
    calculate_profit,
    calculate_trade_profit,
    build_cumulative_trades
)

__all__ = [
    'generate_trade_win_image',
    'generate_single_trade_image', 
    'TradeWinData',
    'COMMISSION_PER_LOT',
    'USD_PER_PIP',
    'DEFAULT_LOT_SIZE',
    'TradeProfit',
    'calculate_pips',
    'calculate_profit',
    'calculate_trade_profit',
    'build_cumulative_trades'
]
