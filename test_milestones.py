"""
Test script to send all milestone messages to Telegram test channel
Run with: python test_milestones.py
"""

import asyncio
import os
from telegram import Bot
from bots.core.milestone_tracker import milestone_tracker

TEST_CHANNEL_ID = "-1003343226469"

async def send_all_milestone_messages():
    """Send all milestone message types to test channel"""
    
    token = os.environ.get('ENTRYLAB_TEST_BOT') or os.environ.get('FOREX_BOT_TOKEN')
    if not token:
        print("No bot token found!")
        return
    
    bot = Bot(token=token)
    
    print("Sending milestone messages to test channel...\n")
    
    sample_event = {
        'signal_id': 99,
        'signal_type': 'BUY',
        'milestone': 'tp1_40_motivational',
        'milestone_key': 'tp1_40',
        'progress_tp': 42,
        'progress_sl': 0,
        'current_price': 2658.50,
        'current_pips': 8.50,
        'entry_price': 2650.00,
        'tp1': 2670.00,
        'tp2': 2680.00,
        'tp3': 2690.00,
        'sl': 2640.00,
        'tp1_hit': False,
        'tp2_hit': False
    }
    
    print("1. Sending 40% Motivational Message...")
    msg_40 = milestone_tracker.generate_milestone_message(sample_event)
    await bot.send_message(chat_id=TEST_CHANNEL_ID, text=msg_40, parse_mode='HTML')
    print("   Sent!\n")
    await asyncio.sleep(2)
    
    print("2. Sending 70% Breakeven Alert...")
    sample_event['milestone'] = 'tp1_70_breakeven'
    sample_event['progress_tp'] = 72
    sample_event['current_pips'] = 14.40
    msg_70 = milestone_tracker.generate_milestone_message(sample_event)
    await bot.send_message(chat_id=TEST_CHANNEL_ID, text=msg_70, parse_mode='HTML')
    print("   Sent!\n")
    await asyncio.sleep(2)
    
    print("3. Sending TP1 Hit Celebration (with remaining %)...")
    msg_tp1 = milestone_tracker.generate_tp1_celebration('BUY', 20.00, remaining_pct=50)
    await bot.send_message(chat_id=TEST_CHANNEL_ID, text=msg_tp1, parse_mode='HTML')
    print("   Sent!\n")
    await asyncio.sleep(2)
    
    print("4. Sending 50% toward TP2 Celebration...")
    sample_event['milestone'] = 'tp2_50_celebration'
    sample_event['tp1_hit'] = True
    sample_event['progress_tp'] = 52
    msg_tp2_50 = milestone_tracker.generate_milestone_message(sample_event)
    await bot.send_message(chat_id=TEST_CHANNEL_ID, text=msg_tp2_50, parse_mode='HTML')
    print("   Sent!\n")
    await asyncio.sleep(2)
    
    print("5. Sending TP2 Hit Celebration (with SL advice)...")
    msg_tp2 = milestone_tracker.generate_tp2_celebration('BUY', 30.00, tp1_price=2670.00, remaining_pct=20)
    await bot.send_message(chat_id=TEST_CHANNEL_ID, text=msg_tp2, parse_mode='HTML')
    print("   Sent!\n")
    await asyncio.sleep(2)
    
    print("6. Sending TP3 Hit BIG Celebration...")
    msg_tp3 = milestone_tracker.generate_tp3_celebration('BUY', 40.00)
    await bot.send_message(chat_id=TEST_CHANNEL_ID, text=msg_tp3, parse_mode='HTML')
    print("   Sent!\n")
    await asyncio.sleep(2)
    
    print("7. Sending SL Warning (60% toward SL)...")
    sample_event['milestone'] = 'sl_60_warning'
    sample_event['tp1_hit'] = False
    sample_event['progress_sl'] = 62
    sample_event['current_pips'] = -6.20
    msg_sl = milestone_tracker.generate_milestone_message(sample_event)
    await bot.send_message(chat_id=TEST_CHANNEL_ID, text=msg_sl, parse_mode='HTML')
    print("   Sent!\n")
    await asyncio.sleep(2)
    
    print("8. Sending SL Hit Message...")
    msg_sl_hit = milestone_tracker.generate_sl_hit_message(10.00)
    await bot.send_message(chat_id=TEST_CHANNEL_ID, text=msg_sl_hit, parse_mode='HTML')
    print("   Sent!\n")
    
    print("=" * 50)
    print("All milestone messages sent to test channel!")
    print("=" * 50)

if __name__ == '__main__':
    asyncio.run(send_all_milestone_messages())
