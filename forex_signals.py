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
        self.rsi_oversold = 40
        self.rsi_overbought = 60
        self.atr_sl_multiplier = 2.0
        self.atr_tp_multiplier = 4.0
        self.adx_threshold = 20
        
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
        Check market conditions using multi-indicator strategy
        
        Strategy:
        1. Trend bias: 1-hour EMA 50/200 crossover
        2. Trend strength: ADX > 20
        3. Entry conditions: RSI 40/60 + MACD histogram direction
        4. Confirmation: Bollinger Bands touch + Stochastic extreme
        
        Returns:
            dict: Signal data or None if no signal
        """
        try:
            print(f"\n[FOREX SIGNALS] Checking for signals on {self.symbol} {timeframe}...")
            
            # Fetch all indicators
            price = twelve_data_client.get_price(self.symbol)
            rsi = twelve_data_client.get_rsi(self.symbol, timeframe)
            macd_data = twelve_data_client.get_macd(self.symbol, timeframe)
            atr = twelve_data_client.get_atr(self.symbol, timeframe)
            adx = twelve_data_client.get_adx(self.symbol, timeframe)
            bbands = twelve_data_client.get_bbands(self.symbol, timeframe)
            stoch = twelve_data_client.get_stoch(self.symbol, timeframe)
            ema50 = twelve_data_client.get_ema(self.symbol, '1h', 50)
            ema200 = twelve_data_client.get_ema(self.symbol, '1h', 200)
            
            # Check if we have all required data
            if not all([price, rsi, macd_data, atr, adx, bbands, stoch, ema50, ema200]):
                print("[FOREX SIGNALS] ❌ Missing indicator data, skipping signal check")
                return None
            
            print(f"[FOREX SIGNALS] Price: {price:.2f}, RSI: {rsi:.2f}, MACD: {macd_data['macd']:.4f}, ADX: {adx:.2f}")
            print(f"[FOREX SIGNALS] Trend: EMA50={ema50:.2f}, EMA200={ema200:.2f}, Stoch K={stoch['k']:.2f}")
            
            # Step 1: Determine trend bias from 1-hour EMAs
            trend_is_bullish = ema50 > ema200
            trend_is_bearish = ema50 < ema200
            
            if not (trend_is_bullish or trend_is_bearish):
                print("[FOREX SIGNALS] No clear trend - EMA 50/200 too close")
                return None
            
            # Step 2: Check trend strength with ADX
            if adx < self.adx_threshold:
                print(f"[FOREX SIGNALS] Weak trend - ADX {adx:.2f} < {self.adx_threshold}")
                return None
            
            # Step 3: Check MACD histogram slope (momentum must be increasing)
            macd_histogram = macd_data['histogram']
            macd_slope = macd_data['histogram_slope']
            
            # For BUY: histogram should be positive AND slope positive (increasing bullish momentum)
            # For SELL: histogram should be negative AND slope negative (increasing bearish momentum)
            macd_momentum_increasing_bullish = macd_histogram > 0 and macd_slope > 0
            macd_momentum_increasing_bearish = macd_histogram < 0 and macd_slope < 0
            
            print(f"[FOREX SIGNALS] MACD Histogram: {macd_histogram:.4f}, Slope: {macd_slope:.4f}")
            
            # Step 4: Check for signal conditions with BOTH confirmations required
            signal_type = None
            
            # BUY signal: Trend bullish + RSI oversold + MACD momentum increasing + BOTH confirmations
            if trend_is_bullish and rsi < self.rsi_oversold and macd_momentum_increasing_bullish:
                # Check Bollinger Bands (price near lower band = oversold)
                bb_distance = abs(price - bbands['lower'])
                bb_touch = bb_distance < (atr * 0.5)
                
                # Check Stochastic (oversold)
                stoch_oversold = stoch['is_oversold']
                
                # Require BOTH confirmations
                if bb_touch and stoch_oversold:
                    signal_type = 'BUY'
                    print(f"[FOREX SIGNALS] 🟢 BUY signal - Trend=Bullish, RSI={rsi:.2f}, ADX={adx:.2f}, BB_touch=True, Stoch_oversold=True")
                else:
                    print(f"[FOREX SIGNALS] BUY conditions partial - BB_touch={bb_touch}, Stoch_oversold={stoch_oversold}")
            
            # SELL signal: Trend bearish + RSI overbought + MACD momentum increasing + BOTH confirmations
            elif trend_is_bearish and rsi > self.rsi_overbought and macd_momentum_increasing_bearish:
                # Check Bollinger Bands (price near upper band = overbought)
                bb_distance = abs(price - bbands['upper'])
                bb_touch = bb_distance < (atr * 0.5)
                
                # Check Stochastic (overbought)
                stoch_overbought = stoch['is_overbought']
                
                # Require BOTH confirmations
                if bb_touch and stoch_overbought:
                    signal_type = 'SELL'
                    print(f"[FOREX SIGNALS] 🔴 SELL signal - Trend=Bearish, RSI={rsi:.2f}, ADX={adx:.2f}, BB_touch=True, Stoch_overbought=True")
                else:
                    print(f"[FOREX SIGNALS] SELL conditions partial - BB_touch={bb_touch}, Stoch_overbought={stoch_overbought}")
            
            if not signal_type:
                print(f"[FOREX SIGNALS] No signal - Trend={'Bullish' if trend_is_bullish else 'Bearish'}, RSI={rsi:.2f}, MACD_momentum={'Increasing_Bullish' if macd_momentum_increasing_bullish else 'Increasing_Bearish' if macd_momentum_increasing_bearish else 'Not_Increasing'}")
                return None
            
            # Calculate TP/SL
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
