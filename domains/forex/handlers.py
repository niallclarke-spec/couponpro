"""
Forex domain handlers.

Extracted from server.py - these handle forex signals, config, stats, and signal bot API endpoints.
"""
import json
from urllib.parse import urlparse, parse_qs

from core.logging import get_logger
from core.pip_calculator import PIPS_MULTIPLIER
from strategies.strategy_loader import get_valid_bot_types, is_valid_bot_type

logger = get_logger(__name__)


def handle_forex_signals(handler):
    """GET /api/forex-signals"""
    from db import get_forex_signals
    parsed_path = urlparse(handler.path)
    
    try:
        query_params = parse_qs(parsed_path.query)
        status_filter = query_params.get('status', [None])[0]
        limit = int(query_params.get('limit', [100])[0])
        
        signals = get_forex_signals(status=status_filter, limit=limit, tenant_id=handler.tenant_id)
        
        handler.send_response(200)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps(signals).encode())
    except Exception as e:
        logger.exception("Error getting signals")
        handler.send_response(500)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'error': str(e)}).encode())


def handle_forex_config(handler):
    """GET /api/forex-config"""
    from db import get_forex_config
    
    try:
        config = get_forex_config(tenant_id=handler.tenant_id)
        
        if config:
            handler.send_response(200)
            handler.send_header('Content-type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps(config).encode())
        else:
            handler.send_response(500)
            handler.send_header('Content-type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps({'error': 'Failed to load config'}).encode())
    except Exception as e:
        logger.exception("Error getting config")
        handler.send_response(500)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'error': str(e)}).encode())


def handle_forex_stats(handler):
    """GET /api/forex-stats"""
    from db import get_forex_stats, get_signal_metrics
    parsed_path = urlparse(handler.path)
    
    try:
        query_params = parse_qs(parsed_path.query)
        days = int(query_params.get('days', [7])[0])
        
        stats = get_forex_stats(days=days, tenant_id=handler.tenant_id)
        metrics = get_signal_metrics(tenant_id=handler.tenant_id)
        
        if stats:
            stats['avg_hold_time_minutes'] = metrics.get('avg_hold_time_minutes', 0)
            stats['avg_pips_per_trade'] = metrics.get('avg_pips_per_trade', 0)
            handler.send_response(200)
            handler.send_header('Content-type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps(stats).encode())
        else:
            handler.send_response(200)
            handler.send_header('Content-type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps({
                'total_signals': 0,
                'won_signals': 0,
                'lost_signals': 0,
                'pending_signals': 0,
                'win_rate': 0,
                'total_pips': 0,
                'signals_by_pair': [],
                'daily_signals': [],
                'avg_hold_time_minutes': 0,
                'avg_pips_per_trade': 0
            }).encode())
    except Exception as e:
        logger.exception("Error getting stats")
        handler.send_response(500)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'error': str(e)}).encode())


def handle_signal_bot_status(handler):
    """GET /api/signal-bot/status"""
    from db import get_active_bot, get_open_signal, get_signals_by_bot_type, get_queued_bot, get_daily_pnl
    from forex_api import twelve_data_client
    
    try:
        active_bot = get_active_bot(tenant_id=handler.tenant_id)
        queued_bot = get_queued_bot(tenant_id=handler.tenant_id)
        open_signal = get_open_signal(tenant_id=handler.tenant_id)
        
        current_price = None
        current_pips = None
        current_dollars = None
        
        if open_signal and open_signal.get('entry_price'):
            try:
                price_result = twelve_data_client.get_price("XAU/USD")
                if price_result is not None:
                    current_price = float(price_result)
                    entry_price = float(open_signal['entry_price'])
                    
                    if open_signal['signal_type'] == 'BUY':
                        price_diff = current_price - entry_price
                    else:
                        price_diff = entry_price - current_price
                    
                    # 1 pip = $0.10
                    current_pips = round(price_diff * PIPS_MULTIPLIER, 1)
                    current_dollars = round(price_diff, 2)
            except Exception as price_err:
                logger.exception("Error fetching current price")
        
        aggressive_signals = get_signals_by_bot_type('aggressive', limit=10, tenant_id=handler.tenant_id)
        conservative_signals = get_signals_by_bot_type('conservative', limit=10, tenant_id=handler.tenant_id)
        custom_signals = get_signals_by_bot_type('custom', limit=10, tenant_id=handler.tenant_id)
        legacy_signals = get_signals_by_bot_type('legacy', limit=10, tenant_id=handler.tenant_id)
        
        daily_pnl = get_daily_pnl(tenant_id=handler.tenant_id) or 0
        
        status = {
            'active_bot': active_bot or 'aggressive',
            'queued_bot': queued_bot,
            'available_bots': get_valid_bot_types(),
            'open_signal': open_signal,
            'current_price': current_price,
            'current_pips': current_pips,
            'current_dollars': current_dollars,
            'daily_pnl': daily_pnl,
            'recent_signals': {
                'aggressive': len(aggressive_signals),
                'conservative': len(conservative_signals),
                'custom': len(custom_signals),
                'legacy': len(legacy_signals)
            }
        }
        
        handler.send_response(200)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps(status).encode())
    except Exception as e:
        logger.exception("Error getting status")
        handler.send_response(500)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'error': str(e)}).encode())


def handle_forex_config_post(handler):
    """POST /api/forex-config"""
    import server
    
    try:
        content_length = int(handler.headers['Content-Length'])
        post_data = handler.rfile.read(content_length)
        data = json.loads(post_data.decode('utf-8'))
        
        valid_keys = ['rsi_oversold', 'rsi_overbought', 'adx_threshold', 
                     'atr_sl_multiplier', 'atr_tp_multiplier', 
                     'trading_start_hour', 'trading_end_hour',
                     'daily_loss_cap_pips', 'back_to_back_throttle_minutes',
                     'session_filter_enabled', 'session_start_hour_utc', 'session_end_hour_utc']
        
        config_updates = {}
        errors = []
        
        for key in valid_keys:
            if key in data:
                value = data[key]
                
                if key in ['rsi_oversold', 'rsi_overbought', 'adx_threshold', 'trading_start_hour', 'trading_end_hour']:
                    try:
                        int_value = int(value)
                        if key == 'rsi_oversold' and not (0 <= int_value <= 100):
                            errors.append(f'{key} must be between 0 and 100')
                        elif key == 'rsi_overbought' and not (0 <= int_value <= 100):
                            errors.append(f'{key} must be between 0 and 100')
                        elif key == 'adx_threshold' and not (0 <= int_value <= 100):
                            errors.append(f'{key} must be between 0 and 100')
                        elif key == 'trading_start_hour' and not (0 <= int_value <= 23):
                            errors.append(f'{key} must be between 0 and 23')
                        elif key == 'trading_end_hour' and not (0 <= int_value <= 23):
                            errors.append(f'{key} must be between 0 and 23')
                        else:
                            config_updates[key] = int_value
                    except ValueError:
                        errors.append(f'{key} must be an integer')
                
                elif key in ['atr_sl_multiplier', 'atr_tp_multiplier', 'daily_loss_cap_pips']:
                    try:
                        float_value = float(value)
                        if float_value <= 0:
                            errors.append(f'{key} must be greater than 0')
                        else:
                            config_updates[key] = float_value
                    except ValueError:
                        errors.append(f'{key} must be a number')
                
                elif key in ['session_start_hour_utc', 'session_end_hour_utc', 'back_to_back_throttle_minutes']:
                    try:
                        int_value = int(value)
                        if key in ['session_start_hour_utc', 'session_end_hour_utc'] and not (0 <= int_value <= 23):
                            errors.append(f'{key} must be between 0 and 23')
                        elif key == 'back_to_back_throttle_minutes' and int_value < 0:
                            errors.append(f'{key} must be positive')
                        else:
                            config_updates[key] = int_value
                    except ValueError:
                        errors.append(f'{key} must be an integer')
                
                elif key == 'session_filter_enabled':
                    config_updates[key] = str(value).lower() == 'true'
        
        if 'trading_start_hour' in config_updates and 'trading_end_hour' in config_updates:
            if config_updates['trading_start_hour'] >= config_updates['trading_end_hour']:
                errors.append('trading_start_hour must be less than trading_end_hour')
        elif 'trading_start_hour' in config_updates or 'trading_end_hour' in config_updates:
            from db import get_forex_config
            current_config = get_forex_config(tenant_id=handler.tenant_id) or {}
            start_hour = config_updates.get('trading_start_hour', current_config.get('trading_start_hour', 8))
            end_hour = config_updates.get('trading_end_hour', current_config.get('trading_end_hour', 22))
            if start_hour >= end_hour:
                errors.append('trading_start_hour must be less than trading_end_hour')
        
        if 'session_start_hour_utc' in config_updates and 'session_end_hour_utc' in config_updates:
            if config_updates['session_start_hour_utc'] >= config_updates['session_end_hour_utc']:
                errors.append('Session start hour must be less than end hour')
        
        if 'rsi_oversold' in config_updates and 'rsi_overbought' in config_updates:
            if config_updates['rsi_oversold'] >= config_updates['rsi_overbought']:
                errors.append('rsi_oversold must be less than rsi_overbought')
        
        if errors:
            handler.send_response(400)
            handler.send_header('Content-type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps({'error': ', '.join(errors)}).encode())
            return
        
        if not config_updates:
            handler.send_response(400)
            handler.send_header('Content-type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps({'error': 'No valid config values provided'}).encode())
            return
        
        from db import update_forex_config
        update_forex_config(config_updates, tenant_id=handler.tenant_id)
        
        if server.FOREX_SCHEDULER_AVAILABLE:
            from forex_signals import forex_signal_engine
            forex_signal_engine.reload_config()
        
        handler.send_response(200)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({
            'success': True,
            'message': 'Configuration updated successfully'
        }).encode())
        
    except json.JSONDecodeError:
        handler.send_response(400)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'error': 'Invalid request format'}).encode())
    except Exception as e:
        logger.exception("Error updating config")
        handler.send_response(500)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'error': str(e)}).encode())


def handle_forex_tp_config_post(handler):
    """POST /api/forex-tp-config"""
    try:
        content_length = int(handler.headers['Content-Length'])
        post_data = handler.rfile.read(content_length)
        data = json.loads(post_data.decode('utf-8'))
        
        tp_count = int(data.get('tp_count', 3))
        tp1_pct = int(data.get('tp1_percentage', 50))
        tp2_pct = int(data.get('tp2_percentage', 30))
        tp3_pct = int(data.get('tp3_percentage', 20))
        
        if tp1_pct + tp2_pct + tp3_pct != 100:
            handler.send_response(400)
            handler.send_header('Content-type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps({
                'error': 'TP percentages must add up to 100%'
            }).encode())
            return
        
        from db import update_forex_config
        update_forex_config({
            'tp_count': tp_count,
            'tp1_percentage': tp1_pct,
            'tp2_percentage': tp2_pct,
            'tp3_percentage': tp3_pct
        }, tenant_id=handler.tenant_id)
        
        logger.info(f"Updated: {tp_count} TPs at {tp1_pct}/{tp2_pct}/{tp3_pct}%")
        
        handler.send_response(200)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({
            'success': True,
            'message': 'TP configuration saved'
        }).encode())
        
    except json.JSONDecodeError:
        handler.send_response(400)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'error': 'Invalid JSON'}).encode())
    except Exception as e:
        logger.exception("Error saving config")
        handler.send_response(500)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'error': str(e)}).encode())


def handle_signal_bot_set_active(handler):
    """POST /api/signal-bot/set-active"""
    try:
        content_length = int(handler.headers['Content-Length'])
        post_data = handler.rfile.read(content_length)
        data = json.loads(post_data.decode('utf-8'))
        
        bot_type = data.get('bot_type')
        
        if not bot_type:
            handler.send_response(400)
            handler.send_header('Content-type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps({'error': 'bot_type is required'}).encode())
            return
        
        if not is_valid_bot_type(bot_type):
            valid_bots = get_valid_bot_types()
            handler.send_response(400)
            handler.send_header('Content-type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps({
                'error': f'Invalid bot_type. Must be one of: {", ".join(valid_bots)}'
            }).encode())
            return
        
        from db import set_active_bot, get_open_signal, set_queued_bot, clear_queued_bot, get_active_bot
        
        open_signal = get_open_signal(tenant_id=handler.tenant_id)
        current_bot = get_active_bot(tenant_id=handler.tenant_id)
        
        if open_signal:
            if bot_type == current_bot:
                clear_queued_bot(tenant_id=handler.tenant_id)
                handler.send_response(200)
                handler.send_header('Content-type', 'application/json')
                handler.end_headers()
                handler.wfile.write(json.dumps({
                    'success': True,
                    'active_bot': current_bot,
                    'queued_bot': None,
                    'message': f'{bot_type} is already active. Queue cleared.'
                }).encode())
                return
            
            set_queued_bot(bot_type, tenant_id=handler.tenant_id)
            handler.send_response(200)
            handler.send_header('Content-type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps({
                'success': True,
                'active_bot': current_bot,
                'queued_bot': bot_type,
                'signal_id': open_signal['id'],
                'message': f'{bot_type} queued. Will activate after Signal #{open_signal["id"]} closes.'
            }).encode())
            return
        
        clear_queued_bot(tenant_id=handler.tenant_id)
        success = set_active_bot(bot_type, tenant_id=handler.tenant_id)
        
        if success:
            handler.send_response(200)
            handler.send_header('Content-type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps({
                'success': True,
                'active_bot': bot_type,
                'queued_bot': None,
                'message': f'Switched to {bot_type} strategy'
            }).encode())
        else:
            handler.send_response(500)
            handler.send_header('Content-type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps({'error': 'Failed to update bot type'}).encode())
            
    except json.JSONDecodeError:
        handler.send_response(400)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'error': 'Invalid JSON'}).encode())
    except Exception as e:
        logger.exception("Error setting active bot")
        handler.send_response(500)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'error': str(e)}).encode())


def handle_signal_bot_cancel_queue(handler):
    """POST /api/signal-bot/cancel-queue"""
    try:
        from db import clear_queued_bot, get_active_bot
        
        clear_queued_bot(tenant_id=handler.tenant_id)
        active_bot = get_active_bot(tenant_id=handler.tenant_id)
        
        handler.send_response(200)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({
            'success': True,
            'active_bot': active_bot,
            'queued_bot': None,
            'message': 'Queued bot switch cancelled'
        }).encode())
    except Exception as e:
        logger.exception("Error cancelling queue")
        handler.send_response(500)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'error': str(e)}).encode())


def handle_forex_tp_config_get(handler):
    """GET /api/forex-tp-config"""
    from db import get_forex_config
    
    try:
        config = get_forex_config(tenant_id=handler.tenant_id) or {}
        
        tp_config = {
            'success': True,
            'tp_count': int(config.get('tp_count', 3)),
            'tp1_percentage': int(config.get('tp1_percentage', 50)),
            'tp2_percentage': int(config.get('tp2_percentage', 30)),
            'tp3_percentage': int(config.get('tp3_percentage', 20))
        }
        
        handler.send_response(200)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps(tp_config).encode())
    except Exception as e:
        logger.exception("Error getting config")
        handler.send_response(500)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'error': str(e)}).encode())


_sparkline_cache = {'data': None, 'timestamp': 0}

def handle_xauusd_sparkline(handler):
    """GET /api/forex/xauusd-sparkline"""
    import time
    from forex_api import twelve_data_client
    global _sparkline_cache
    
    try:
        current_time = time.time()
        if _sparkline_cache['data'] and (current_time - _sparkline_cache['timestamp']) < 60:
            response_data = _sparkline_cache['data']
        else:
            candles = twelve_data_client.get_time_series(
                symbol='XAU/USD',
                interval='1min',
                outputsize=30
            )
            
            if candles and len(candles) > 0:
                candles.reverse()
                prices = [c['close'] for c in candles]
                current_price = prices[-1] if prices else 0
                open_price = prices[0] if prices else 0
                
                if open_price > 0:
                    change_pct = ((current_price - open_price) / open_price) * 100
                else:
                    change_pct = 0
                
                response_data = {
                    'success': True,
                    'prices': prices,
                    'current': current_price,
                    'change_pct': round(change_pct, 2),
                    'timestamp': current_time
                }
                _sparkline_cache = {'data': response_data, 'timestamp': current_time}
            else:
                response_data = {
                    'success': False,
                    'error': 'Unable to fetch price data'
                }
        
        handler.send_response(200)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps(response_data).encode())
    except Exception as e:
        logger.exception("Error fetching sparkline")
        handler.send_response(500)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'error': str(e)}).encode())


def handle_signal_bot_signals(handler):
    """GET /api/signal-bot/signals"""
    from db import get_signals_by_bot_type, get_forex_signals
    parsed_path = urlparse(handler.path)
    
    try:
        query_params = parse_qs(parsed_path.query)
        bot_type = query_params.get('bot_type', [None])[0]
        limit = int(query_params.get('limit', [50])[0])
        
        if bot_type:
            signals = get_signals_by_bot_type(bot_type, limit=limit, tenant_id=handler.tenant_id)
        else:
            signals = get_forex_signals(limit=limit, tenant_id=handler.tenant_id)
        
        handler.send_response(200)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'signals': signals}).encode())
    except Exception as e:
        logger.exception("Error getting signals")
        handler.send_response(500)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'error': str(e)}).encode())
