"""
Base Strategy Abstract Class
All trading strategies must inherit from this class
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass


@dataclass
class TakeProfitLevel:
    price: float
    percentage: int
    hit: bool = False


@dataclass
class SignalData:
    signal_type: str
    pair: str
    timeframe: str
    entry_price: float
    stop_loss: float
    take_profits: List[TakeProfitLevel]
    indicators: Dict
    bot_type: str
    
    @property
    def tp1(self) -> float:
        return self.take_profits[0].price if len(self.take_profits) > 0 else 0
    
    @property
    def tp2(self) -> Optional[float]:
        return self.take_profits[1].price if len(self.take_profits) > 1 else None
    
    @property
    def tp3(self) -> Optional[float]:
        return self.take_profits[2].price if len(self.take_profits) > 2 else None
    
    def to_dict(self) -> Dict:
        return {
            'signal_type': self.signal_type,
            'pair': self.pair,
            'timeframe': self.timeframe,
            'entry_price': self.entry_price,
            'stop_loss': self.stop_loss,
            'take_profit': self.tp1,
            'take_profit_2': self.tp2,
            'take_profit_3': self.tp3,
            'tp1_percentage': self.take_profits[0].percentage if len(self.take_profits) > 0 else 100,
            'tp2_percentage': self.take_profits[1].percentage if len(self.take_profits) > 1 else 0,
            'tp3_percentage': self.take_profits[2].percentage if len(self.take_profits) > 2 else 0,
            'all_indicators': self.indicators,
            'bot_type': self.bot_type
        }


class BaseStrategy(ABC):
    name: str = "Base Strategy"
    description: str = "Abstract base strategy"
    bot_type: str = "base"
    
    tp_levels: int = 1
    tp_percentages: List[int] = [100]
    
    breakeven_threshold: float = 70.0
    
    def __init__(self):
        self.symbol = 'XAU/USD'
    
    @abstractmethod
    async def check_for_signals(self, timeframe: str = '15min') -> Optional[SignalData]:
        """
        Check market conditions and return a signal if conditions are met.
        Must be implemented by each strategy.
        
        Returns:
            SignalData object or None if no signal
        """
        pass
    
    @abstractmethod
    def calculate_tp_sl(self, entry_price: float, atr_value: float, signal_type: str) -> Tuple[List[TakeProfitLevel], float]:
        """
        Calculate Take Profit levels and Stop Loss.
        
        Returns:
            Tuple of (list of TakeProfitLevel, stop_loss price)
        """
        pass
    
    def get_thesis_rules(self) -> Dict:
        """
        Return thesis validation rules for this strategy.
        Override to customize thesis logic, or return empty to use auto-generated rules.
        
        Returns:
            Dict with 'weakening' and 'broken' rules per indicator
        """
        return {}
    
    def get_indicators_used(self) -> List[str]:
        """Return list of indicator names used by this strategy"""
        return []
    
    def get_display_info(self) -> Dict:
        """Return display information for the admin panel"""
        return {
            'name': self.name,
            'description': self.description,
            'bot_type': self.bot_type,
            'indicators': self.get_indicators_used(),
            'tp_levels': self.tp_levels,
            'tp_percentages': self.tp_percentages,
            'breakeven_threshold': self.breakeven_threshold
        }
