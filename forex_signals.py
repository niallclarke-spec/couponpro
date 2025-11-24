"""
Forex signal generation engine
Combines RSI + MACD + ATR for XAU/USD trading signals
"""
import os
from datetime import datetime, timedelta
from forex_api import twelve_data_client
from db import create_forex_signal, get_forex_signals, update_forex_signal_status
import asyncio

class ForexSignalEngine:
    def __init__(self):
        self.symbol = 'XAU/USD'
        self.rsi_oversold = 35
        self.rsi_overbought = 65
        self.atr_sl_multiplier = 2.0
        self.atr_tp_multiplier = 4.0
        
    def calculate_tp_sl(self, entry_price, atr_value, signal_type):
        """
        Calculate Take Profit and Stop Loss using ATR-based method
        
        Args:
            entry_price: Entry price for the signal
            atr_value: Current ATR value
            signal_type: 'BUY' or 'SELL'
        
        Returns:
            tuple: (take_profit, stop_loss)
        """
        if signal_type == 'BUY':
            stop_loss = round(entry_price - (atr_value * self.atr_sl_multiplier), 2)
            take_profit = round(entry_price + (atr_value * self.atr_tp_multiplier), 2)
        else:
            stop_loss = round(entry_price + (atr_value * self.atr_sl_multiplier), 2)
            take_profit = round(entry_price - (atr_value * self.atr_tp_multiplier), 2)
        
        return take_profit, stop_loss
    
    async def check_for_signals(self, timeframe='15min'):
        """
        Check market conditions and generate signals if criteria met
        
        Returns:
            dict: Signal data or None if no signal
        """
        try:
            print(f"\n[FOREX SIGNALS] Checking for signals on {self.symbol} {timeframe}...")
            
            rsi = twelve_data_client.get_rsi(self.symbol, timeframe)
            macd_data = twelve_data_client.get_macd(self.symbol, timeframe)
            atr = twelve_data_client.get_atr(self.symbol, timeframe)
            price = twelve_data_client.get_price(self.symbol)
            
            if not all([rsi, macd_data, atr, price]):
                print("[FOREX SIGNALS] ❌ Missing indicator data, skipping signal check")
                return None
            
            print(f"[FOREX SIGNALS] RSI: {rsi:.2f}, MACD: {macd_data['macd']:.4f}, Signal: {macd_data['signal']:.4f}, ATR: {atr:.2f}, Price: {price:.2f}")
            
            signal_type = None
            
            if rsi < self.rsi_oversold and macd_data['is_bullish_cross']:
                signal_type = 'BUY'
                print(f"[FOREX SIGNALS] 🟢 BUY signal detected! RSI oversold ({rsi:.2f}) + MACD bullish cross")
            elif rsi > self.rsi_overbought and macd_data['is_bearish_cross']:
                signal_type = 'SELL'
                print(f"[FOREX SIGNALS] 🔴 SELL signal detected! RSI overbought ({rsi:.2f}) + MACD bearish cross")
            else:
                print(f"[FOREX SIGNALS] No signal - RSI: {rsi:.2f}, MACD cross: Bullish={macd_data['is_bullish_cross']}, Bearish={macd_data['is_bearish_cross']}")
                return None
            
            take_profit, stop_loss = self.calculate_tp_sl(price, atr, signal_type)
            
            signal_data = {
                'signal_type': signal_type,
                'pair': self.symbol,
                'timeframe': timeframe,
                'entry_price': price,
                'take_profit': take_profit,
                'stop_loss': stop_loss,
                'rsi_value': rsi,
                'macd_value': macd_data['macd'],
                'atr_value': atr
            }
            
            print(f"[FOREX SIGNALS] ✅ Signal generated: {signal_type} @ {price:.2f}, TP: {take_profit:.2f}, SL: {stop_loss:.2f}")
            
            return signal_data
            
        except Exception as e:
            print(f"[FOREX SIGNALS] ❌ Error checking for signals: {e}")
            return None
    
    async def monitor_active_signals(self):
        """
        Monitor active signals for TP/SL hits and expiration
        Returns list of signals that need updates
        """
        try:
            active_signals = get_forex_signals(status='pending')
            
            if not active_signals:
                return []
            
            print(f"\n[FOREX MONITOR] Checking {len(active_signals)} active signals...")
            
            current_price = twelve_data_client.get_price(self.symbol)
            if not current_price:
                print("[FOREX MONITOR] ❌ Could not fetch current price")
                return []
            
            print(f"[FOREX MONITOR] Current {self.symbol} price: {current_price:.2f}")
            
            updates = []
            now = datetime.utcnow()
            
            for signal in active_signals:
                signal_id = signal['id']
                signal_type = signal['signal_type']
                entry = float(signal['entry_price'])
                tp = float(signal['take_profit'])
                sl = float(signal['stop_loss'])
                posted_at = signal['posted_at']
                
                hours_elapsed = (now - posted_at).total_seconds() / 3600
                
                if hours_elapsed >= 4:
                    print(f"[FOREX MONITOR] ⏱️  Signal #{signal_id} expired after 4 hours")
                    updates.append({
                        'id': signal_id,
                        'status': 'expired',
                        'pips': 0
                    })
                    continue
                
                if signal_type == 'BUY':
                    if current_price >= tp:
                        pips = round(tp - entry, 2)
                        print(f"[FOREX MONITOR] ✅ Signal #{signal_id} TP HIT! Profit: {pips} pips")
                        updates.append({
                            'id': signal_id,
                            'status': 'won',
                            'pips': pips
                        })
                    elif current_price <= sl:
                        pips = round(entry - sl, 2)
                        print(f"[FOREX MONITOR] ❌ Signal #{signal_id} SL HIT! Loss: -{pips} pips")
                        updates.append({
                            'id': signal_id,
                            'status': 'lost',
                            'pips': -pips
                        })
                else:
                    if current_price <= tp:
                        pips = round(entry - tp, 2)
                        print(f"[FOREX MONITOR] ✅ Signal #{signal_id} TP HIT! Profit: {pips} pips")
                        updates.append({
                            'id': signal_id,
                            'status': 'won',
                            'pips': pips
                        })
                    elif current_price >= sl:
                        pips = round(sl - entry, 2)
                        print(f"[FOREX MONITOR] ❌ Signal #{signal_id} SL HIT! Loss: -{pips} pips")
                        updates.append({
                            'id': signal_id,
                            'status': 'lost',
                            'pips': -pips
                        })
            
            return updates
            
        except Exception as e:
            print(f"[FOREX MONITOR] ❌ Error monitoring signals: {e}")
            return []
    
    def is_trading_hours(self):
        """
        Check if current time is within trading hours (8AM-10PM GMT)
        """
        from datetime import datetime
        now = datetime.utcnow()
        current_hour = now.hour
        
        if 8 <= current_hour < 22:
            return True
        return False

forex_signal_engine = ForexSignalEngine()
