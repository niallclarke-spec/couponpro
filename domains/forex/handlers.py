"""
Forex domain handlers.

Extracted from server.py - these handle forex signals, config, stats, and signal bot API endpoints.
"""
import json
from urllib.parse import urlparse, parse_qs


def handle_forex_signals(handler):
    """GET /api/forex-signals"""
    from db import get_forex_signals
    parsed_path = urlparse(handler.path)
    
    try:
        query_params = parse_qs(parsed_path.query)
        status_filter = query_params.get('status', [None])[0]
        limit = int(query_params.get('limit', [100])[0])
        
        signals = get_forex_signals(status=status_filter, limit=limit)
        
        handler.send_response(200)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps(signals).encode())
    except Exception as e:
        print(f"[FOREX] Error getting signals: {e}")
        handler.send_response(500)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'error': str(e)}).encode())


def handle_forex_config(handler):
    """GET /api/forex-config"""
    from db import get_forex_config
    
    try:
        config = get_forex_config()
        
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
        print(f"[FOREX] Error getting config: {e}")
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
        
        stats = get_forex_stats(days=days)
        metrics = get_signal_metrics()
        
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
        print(f"[FOREX] Error getting stats: {e}")
        handler.send_response(500)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'error': str(e)}).encode())


def handle_signal_bot_status(handler):
    """GET /api/signal-bot/status"""
    from db import get_active_bot, get_open_signal, get_signals_by_bot_type, get_queued_bot, get_daily_pnl
    from forex_api import twelve_data_client
    
    try:
        active_bot = get_active_bot()
        queued_bot = get_queued_bot()
        open_signal = get_open_signal()
        
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
                    
                    # XAU/USD: 1 pip = $0.01, multiply by 100
                    current_pips = round(price_diff * 100, 1)
                    current_dollars = round(price_diff, 2)
            except Exception as price_err:
                print(f"[BOT STATUS] Error fetching current price: {price_err}")
        
        aggressive_signals = get_signals_by_bot_type('aggressive', limit=10)
        conservative_signals = get_signals_by_bot_type('conservative', limit=10)
        custom_signals = get_signals_by_bot_type('custom', limit=10)
        legacy_signals = get_signals_by_bot_type('legacy', limit=10)
        
        daily_pnl = get_daily_pnl() or 0
        
        status = {
            'active_bot': active_bot or 'aggressive',
            'queued_bot': queued_bot,
            'available_bots': ['aggressive', 'conservative', 'custom', 'raja_banks'],
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
        print(f"[SIGNAL BOT] Error getting status: {e}")
        handler.send_response(500)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'error': str(e)}).encode())
