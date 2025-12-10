#!/usr/bin/env python3
"""
Test script for effective_sl P&L tracking.
Simulates different scenarios to verify correct status classification.
"""

def calculate_pips_buy(entry, exit_price):
    """For BUY: profit when price goes UP"""
    return round(exit_price - entry, 2)

def calculate_pips_sell(entry, exit_price):
    """For SELL: profit when price goes DOWN"""
    return round(entry - exit_price, 2)

def determine_status(pips):
    """Determine win/loss based on pips"""
    if pips >= 0:
        return 'won'
    return 'lost'

def test_buy_scenarios():
    """Test BUY signal scenarios"""
    print("\n" + "="*60)
    print("BUY SIGNAL SCENARIOS")
    print("="*60)
    
    entry = 2650.00
    original_sl = 2640.00  # Below entry
    tp1 = 2660.00          # Above entry
    tp2 = 2670.00
    
    print(f"\nSetup: Entry=${entry}, Original SL=${original_sl}, TP1=${tp1}, TP2=${tp2}")
    
    scenarios = [
        {
            'name': 'Original SL Hit (No Guidance)',
            'effective_sl': None,
            'exit_price': original_sl,
            'expected_status': 'lost',
            'expected_pips': -10.0
        },
        {
            'name': 'Breakeven SL Hit (70% milestone)',
            'effective_sl': entry,
            'exit_price': entry,
            'expected_status': 'won',
            'expected_pips': 0.0
        },
        {
            'name': 'Locked Profit at TP1 (TP1 hit, price reversed)',
            'effective_sl': tp1,
            'exit_price': tp1,
            'expected_status': 'won',
            'expected_pips': 10.0
        },
        {
            'name': 'Locked Profit at TP2 (TP2 hit, price reversed)',
            'effective_sl': tp2,
            'exit_price': tp2,
            'expected_status': 'won',
            'expected_pips': 20.0
        },
    ]
    
    all_passed = True
    for scenario in scenarios:
        sl = scenario['effective_sl'] if scenario['effective_sl'] else original_sl
        pips = calculate_pips_buy(entry, sl)
        status = determine_status(pips)
        
        pips_match = pips == scenario['expected_pips']
        status_match = status == scenario['expected_status']
        passed = pips_match and status_match
        
        if not passed:
            all_passed = False
        
        emoji = "✅" if passed else "❌"
        print(f"\n{emoji} {scenario['name']}")
        print(f"   Effective SL: {scenario['effective_sl'] or 'None (using original)'}")
        print(f"   Pips: {pips} (expected: {scenario['expected_pips']}) {'✓' if pips_match else '✗'}")
        print(f"   Status: {status} (expected: {scenario['expected_status']}) {'✓' if status_match else '✗'}")
    
    return all_passed

def test_sell_scenarios():
    """Test SELL signal scenarios"""
    print("\n" + "="*60)
    print("SELL SIGNAL SCENARIOS")
    print("="*60)
    
    entry = 2650.00
    original_sl = 2660.00  # Above entry (price going UP = loss)
    tp1 = 2640.00          # Below entry (price going DOWN = profit)
    tp2 = 2630.00
    
    print(f"\nSetup: Entry=${entry}, Original SL=${original_sl}, TP1=${tp1}, TP2=${tp2}")
    
    scenarios = [
        {
            'name': 'Original SL Hit (No Guidance)',
            'effective_sl': None,
            'exit_price': original_sl,
            'expected_status': 'lost',
            'expected_pips': -10.0
        },
        {
            'name': 'Breakeven SL Hit (70% milestone)',
            'effective_sl': entry,
            'exit_price': entry,
            'expected_status': 'won',
            'expected_pips': 0.0
        },
        {
            'name': 'Locked Profit at TP1 (TP1 hit, price reversed back up)',
            'effective_sl': tp1,
            'exit_price': tp1,
            'expected_status': 'won',
            'expected_pips': 10.0
        },
        {
            'name': 'Locked Profit at TP2 (TP2 hit, price reversed back up)',
            'effective_sl': tp2,
            'exit_price': tp2,
            'expected_status': 'won',
            'expected_pips': 20.0
        },
    ]
    
    all_passed = True
    for scenario in scenarios:
        sl = scenario['effective_sl'] if scenario['effective_sl'] else original_sl
        pips = calculate_pips_sell(entry, sl)
        status = determine_status(pips)
        
        pips_match = pips == scenario['expected_pips']
        status_match = status == scenario['expected_status']
        passed = pips_match and status_match
        
        if not passed:
            all_passed = False
        
        emoji = "✅" if passed else "❌"
        print(f"\n{emoji} {scenario['name']}")
        print(f"   Effective SL: {scenario['effective_sl'] or 'None (using original)'}")
        print(f"   Pips: {pips} (expected: {scenario['expected_pips']}) {'✓' if pips_match else '✗'}")
        print(f"   Status: {status} (expected: {scenario['expected_status']}) {'✓' if status_match else '✗'}")
    
    return all_passed

def test_edge_cases():
    """Test edge cases"""
    print("\n" + "="*60)
    print("EDGE CASES")
    print("="*60)
    
    all_passed = True
    
    print("\n--- BUY: Very small profit (0.01 pips) ---")
    entry = 2650.00
    effective_sl = 2650.01
    pips = calculate_pips_buy(entry, effective_sl)
    status = determine_status(pips)
    expected = 'won'
    passed = status == expected and pips > 0
    emoji = "✅" if passed else "❌"
    print(f"{emoji} Pips: {pips}, Status: {status} (expected: {expected})")
    if not passed: all_passed = False
    
    print("\n--- SELL: Very small profit (0.01 pips) ---")
    entry = 2650.00
    effective_sl = 2649.99
    pips = calculate_pips_sell(entry, effective_sl)
    status = determine_status(pips)
    expected = 'won'
    passed = status == expected and pips > 0
    emoji = "✅" if passed else "❌"
    print(f"{emoji} Pips: {pips}, Status: {status} (expected: {expected})")
    if not passed: all_passed = False
    
    print("\n--- BUY: Very small loss (-0.01 pips) ---")
    entry = 2650.00
    sl = 2649.99
    pips = calculate_pips_buy(entry, sl)
    status = determine_status(pips)
    expected = 'lost'
    passed = status == expected and pips < 0
    emoji = "✅" if passed else "❌"
    print(f"{emoji} Pips: {pips}, Status: {status} (expected: {expected})")
    if not passed: all_passed = False
    
    print("\n--- SELL: Very small loss (-0.01 pips) ---")
    entry = 2650.00
    sl = 2650.01
    pips = calculate_pips_sell(entry, sl)
    status = determine_status(pips)
    expected = 'lost'
    passed = status == expected and pips < 0
    emoji = "✅" if passed else "❌"
    print(f"{emoji} Pips: {pips}, Status: {status} (expected: {expected})")
    if not passed: all_passed = False
    
    return all_passed

def test_real_code_simulation():
    """Simulate the actual code logic from forex_signals.py"""
    print("\n" + "="*60)
    print("REAL CODE SIMULATION (forex_signals.py logic)")
    print("="*60)
    
    all_passed = True
    
    def simulate_buy_sl_hit(entry, original_sl, effective_sl, current_price):
        """Simulate BUY SL hit logic from forex_signals.py"""
        sl = float(effective_sl) if effective_sl else original_sl
        if current_price <= sl:
            pips = round(sl - entry, 2)
            if pips >= 0:
                status = 'won'
            else:
                status = 'lost'
            return {'hit': True, 'pips': pips, 'status': status}
        return {'hit': False}
    
    def simulate_sell_sl_hit(entry, original_sl, effective_sl, current_price):
        """Simulate SELL SL hit logic from forex_signals.py"""
        sl = float(effective_sl) if effective_sl else original_sl
        if current_price >= sl:
            pips = round(entry - sl, 2)
            if pips >= 0:
                status = 'won'
            else:
                status = 'lost'
            return {'hit': True, 'pips': pips, 'status': status}
        return {'hit': False}
    
    test_cases = [
        {
            'name': 'BUY: Original SL hit',
            'type': 'BUY',
            'entry': 2650.00,
            'original_sl': 2640.00,
            'effective_sl': None,
            'current_price': 2639.00,
            'expected': {'hit': True, 'pips': -10.0, 'status': 'lost'}
        },
        {
            'name': 'BUY: Breakeven hit',
            'type': 'BUY',
            'entry': 2650.00,
            'original_sl': 2640.00,
            'effective_sl': 2650.00,
            'current_price': 2649.00,
            'expected': {'hit': True, 'pips': 0.0, 'status': 'won'}
        },
        {
            'name': 'BUY: Locked profit at TP1',
            'type': 'BUY',
            'entry': 2650.00,
            'original_sl': 2640.00,
            'effective_sl': 2660.00,
            'current_price': 2659.00,
            'expected': {'hit': True, 'pips': 10.0, 'status': 'won'}
        },
        {
            'name': 'SELL: Original SL hit',
            'type': 'SELL',
            'entry': 2650.00,
            'original_sl': 2660.00,
            'effective_sl': None,
            'current_price': 2661.00,
            'expected': {'hit': True, 'pips': -10.0, 'status': 'lost'}
        },
        {
            'name': 'SELL: Breakeven hit',
            'type': 'SELL',
            'entry': 2650.00,
            'original_sl': 2660.00,
            'effective_sl': 2650.00,
            'current_price': 2651.00,
            'expected': {'hit': True, 'pips': 0.0, 'status': 'won'}
        },
        {
            'name': 'SELL: Locked profit at TP1',
            'type': 'SELL',
            'entry': 2650.00,
            'original_sl': 2660.00,
            'effective_sl': 2640.00,
            'current_price': 2641.00,
            'expected': {'hit': True, 'pips': 10.0, 'status': 'won'}
        },
    ]
    
    for tc in test_cases:
        if tc['type'] == 'BUY':
            result = simulate_buy_sl_hit(tc['entry'], tc['original_sl'], tc['effective_sl'], tc['current_price'])
        else:
            result = simulate_sell_sl_hit(tc['entry'], tc['original_sl'], tc['effective_sl'], tc['current_price'])
        
        passed = result == tc['expected']
        if not passed:
            all_passed = False
        
        emoji = "✅" if passed else "❌"
        print(f"\n{emoji} {tc['name']}")
        print(f"   Entry: ${tc['entry']}, Original SL: ${tc['original_sl']}, Effective SL: {tc['effective_sl']}")
        print(f"   Current Price: ${tc['current_price']}")
        print(f"   Result: {result}")
        print(f"   Expected: {tc['expected']}")
    
    return all_passed

if __name__ == '__main__':
    print("\n" + "#"*60)
    print("# EFFECTIVE SL P&L TRACKING TEST SUITE")
    print("#"*60)
    
    results = []
    results.append(('BUY Scenarios', test_buy_scenarios()))
    results.append(('SELL Scenarios', test_sell_scenarios()))
    results.append(('Edge Cases', test_edge_cases()))
    results.append(('Real Code Simulation', test_real_code_simulation()))
    
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    
    all_passed = True
    for name, passed in results:
        emoji = "✅" if passed else "❌"
        print(f"{emoji} {name}: {'PASSED' if passed else 'FAILED'}")
        if not passed:
            all_passed = False
    
    print("\n" + "="*60)
    if all_passed:
        print("🎉 ALL TESTS PASSED!")
    else:
        print("⚠️  SOME TESTS FAILED - Review the output above")
    print("="*60 + "\n")
