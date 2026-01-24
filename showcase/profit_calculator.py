"""
Centralized Profit Calculator

Handles pips calculation and profit computation with commission
for XAU/USD trading. This ensures consistency between celebration
messages and showcase images.

NOTE: All pip calculations now use the centralized pip_calculator module.
See core/pip_calculator.py for the authoritative pip value definition.

Constants:
- COMMISSION_PER_LOT: $7 round-turn commission
- USD_PER_PIP: $1 profit per pip per lot for XAU/USD
- DEFAULT_LOT_SIZE: 1.0 lot
"""

from dataclasses import dataclass
from typing import List, Optional

from core.pip_calculator import (
    calculate_pips,
    COMMISSION_PER_LOT,
    USD_PER_PIP_PER_LOT as USD_PER_PIP,
    PIP_VALUE,
    PIPS_MULTIPLIER
)


DEFAULT_LOT_SIZE = 1.0


@dataclass
class TradeProfit:
    """Calculated trade profit data."""
    entry_price: float
    exit_price: float
    pips: float
    gross_profit: float
    commission: float
    net_profit: float
    lot_size: float
    
    @property
    def formatted_net_profit(self) -> str:
        """Format net profit with sign."""
        return f"{self.net_profit:,.2f}"




def calculate_profit(
    pips: float,
    lot_size: float = DEFAULT_LOT_SIZE,
    include_commission: bool = True
) -> TradeProfit:
    """
    Calculate trade profit with commission.
    
    For XAU/USD:
    - 1 lot = 100 oz
    - 1 pip = $0.10
    - Profit per pip = 100 oz × $0.10 / 10 = $1.00 per lot
    
    Args:
        pips: Number of pips
        lot_size: Lot size (default 1.0)
        include_commission: Whether to deduct $7 commission
        
    Returns:
        TradeProfit with gross/net calculations
    """
    gross_profit = pips * USD_PER_PIP * lot_size
    commission = COMMISSION_PER_LOT * lot_size if include_commission else 0
    net_profit = gross_profit - commission
    
    return TradeProfit(
        entry_price=0,  # Filled by caller
        exit_price=0,   # Filled by caller
        pips=pips,
        gross_profit=gross_profit,
        commission=commission,
        net_profit=net_profit,
        lot_size=lot_size
    )


def calculate_trade_profit(
    entry_price: float,
    exit_price: float,
    direction: str,
    lot_size: float = DEFAULT_LOT_SIZE,
    include_commission: bool = True
) -> TradeProfit:
    """
    Full trade profit calculation from prices.
    
    Args:
        entry_price: Entry price
        exit_price: Exit/TP price
        direction: "BUY" or "SELL"
        lot_size: Lot size (default 1.0)
        include_commission: Whether to deduct commission
        
    Returns:
        TradeProfit with all calculations
    """
    pips = calculate_pips(entry_price, exit_price, direction)
    profit = calculate_profit(pips, lot_size, include_commission)
    profit.entry_price = entry_price
    profit.exit_price = exit_price
    return profit


def build_cumulative_trades(
    entry_price: float,
    direction: str,
    tp1_price: Optional[float],
    tp2_price: Optional[float],
    tp3_price: Optional[float],
    tp_level: int,
    lot_size: float = DEFAULT_LOT_SIZE
) -> List[TradeProfit]:
    """
    Build cumulative trade list for showcase image.
    
    For TP1: returns [TP1 trade]
    For TP2: returns [TP1 trade, TP2 trade]
    For TP3: returns [TP1 trade, TP2 trade, TP3 trade]
    
    Args:
        entry_price: Original entry price
        direction: "BUY" or "SELL"
        tp1_price: TP1 exit price
        tp2_price: TP2 exit price (can be None)
        tp3_price: TP3 exit price (can be None)
        tp_level: Current TP level (1, 2, or 3)
        lot_size: Lot size for all trades
        
    Returns:
        List of TradeProfit objects for cumulative display
    """
    trades = []
    tp_prices = [tp1_price, tp2_price, tp3_price]
    
    for i in range(tp_level):
        tp_price = tp_prices[i]
        if tp_price is not None:
            trade = calculate_trade_profit(
                entry_price=entry_price,
                exit_price=tp_price,
                direction=direction,
                lot_size=lot_size,
                include_commission=True
            )
            trades.append(trade)
    
    return trades
