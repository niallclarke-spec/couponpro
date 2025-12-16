#!/usr/bin/env python3
"""
Smoke tests for Journeys API routes.

Run with: python3 tests/journeys_smoke_test.py

Tests:
1. Routes require authentication (401 when unauthenticated)
2. Repo can find seeded journey by deeplink
3. Basic route connectivity
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_repo_find_journey_by_deeplink():
    """Test that repo.get_active_journey_by_deeplink() finds the seeded journey."""
    from domains.journeys import repo
    
    journey = repo.get_active_journey_by_deeplink('entrylab', 'default', 'broker_signup')
    
    if journey:
        print(f"[PASS] Found journey: {journey['name']} (id={journey['id']}, status={journey['status']})")
        return True
    else:
        print("[FAIL] Journey 'broker_signup' not found. Try running: python3 -m domains.journeys.seed")
        return False


def test_routes_require_auth():
    """Test that journey routes return 401 when unauthenticated."""
    import http.client
    
    routes = [
        ('GET', '/api/journeys'),
        ('GET', '/api/journeys/debug/sessions'),
        ('POST', '/api/journeys'),
    ]
    
    all_passed = True
    
    for method, path in routes:
        try:
            conn = http.client.HTTPConnection('localhost', 5000, timeout=5)
            conn.request(method, path)
            response = conn.getresponse()
            
            if response.status == 401:
                print(f"[PASS] {method} {path} -> 401 (auth required)")
            else:
                print(f"[FAIL] {method} {path} -> {response.status} (expected 401)")
                all_passed = False
            conn.close()
        except Exception as e:
            print(f"[FAIL] {method} {path} -> Error: {e}")
            all_passed = False
    
    return all_passed


def main():
    print("=" * 60)
    print("Journeys Smoke Tests")
    print("=" * 60)
    print()
    
    results = []
    
    print("Test 1: Routes require authentication")
    print("-" * 40)
    results.append(test_routes_require_auth())
    print()
    
    print("Test 2: Repo finds seeded journey by deeplink")
    print("-" * 40)
    results.append(test_repo_find_journey_by_deeplink())
    print()
    
    print("=" * 60)
    if all(results):
        print("All tests PASSED!")
        return 0
    else:
        print("Some tests FAILED!")
        return 1


if __name__ == '__main__':
    sys.exit(main())
