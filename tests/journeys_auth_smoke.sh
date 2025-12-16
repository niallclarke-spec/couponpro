#!/bin/bash
#
# Journeys API Auth Smoke Test
#
# Tests authentication for /api/journeys endpoint.
# Verifies both Bearer token and __session cookie auth methods work.
#
# Usage:
#   # Test with Bearer token:
#   export JOURNEYS_TEST_JWT="your_clerk_jwt_token"
#   bash tests/journeys_auth_smoke.sh
#
#   # Or test with session cookie:
#   export CLERK_SESSION_COOKIE="your_clerk_session_cookie"
#   bash tests/journeys_auth_smoke.sh
#
# To get a valid JWT or session cookie:
#   1. Sign into the app in browser
#   2. Open DevTools > Application > Cookies
#   3. Copy the value of __session cookie
#   4. Or: DevTools > Network > any authenticated request > Authorization header

set -e

BASE_URL="${BASE_URL:-http://localhost:5000}"
ENDPOINT="/api/journeys"

echo "========================================"
echo "Journeys API Auth Smoke Test"
echo "========================================"
echo "Base URL: $BASE_URL"
echo "Endpoint: $ENDPOINT"
echo ""

PASS=0
FAIL=0

# Test 1: Unauthenticated request should return 401
echo "Test 1: Unauthenticated request"
echo "  Expect: 401 Unauthorized"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL$ENDPOINT")
if [ "$STATUS" = "401" ]; then
    echo "  Result: PASS (got $STATUS)"
    PASS=$((PASS + 1))
else
    echo "  Result: FAIL (got $STATUS, expected 401)"
    FAIL=$((FAIL + 1))
fi
echo ""

# Test 2: Bearer token auth (if JOURNEYS_TEST_JWT is set)
if [ -n "$JOURNEYS_TEST_JWT" ]; then
    echo "Test 2: Bearer token authentication"
    echo "  Expect: 200 OK"
    STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
        -H "Authorization: Bearer $JOURNEYS_TEST_JWT" \
        "$BASE_URL$ENDPOINT")
    if [ "$STATUS" = "200" ]; then
        echo "  Result: PASS (got $STATUS)"
        PASS=$((PASS + 1))
    else
        echo "  Result: FAIL (got $STATUS, expected 200)"
        echo "  Note: Ensure JOURNEYS_TEST_JWT is a valid, non-expired Clerk JWT"
        FAIL=$((FAIL + 1))
    fi
    echo ""
else
    echo "Test 2: Bearer token authentication"
    echo "  SKIPPED - JOURNEYS_TEST_JWT not set"
    echo ""
fi

# Test 3: Cookie auth (if CLERK_SESSION_COOKIE is set)
if [ -n "$CLERK_SESSION_COOKIE" ]; then
    echo "Test 3: Session cookie authentication"
    echo "  Expect: 200 OK"
    STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
        -H "Cookie: __session=$CLERK_SESSION_COOKIE" \
        "$BASE_URL$ENDPOINT")
    if [ "$STATUS" = "200" ]; then
        echo "  Result: PASS (got $STATUS)"
        PASS=$((PASS + 1))
    else
        echo "  Result: FAIL (got $STATUS, expected 200)"
        echo "  Note: Ensure CLERK_SESSION_COOKIE is a valid, non-expired session"
        FAIL=$((FAIL + 1))
    fi
    echo ""
else
    echo "Test 3: Session cookie authentication"
    echo "  SKIPPED - CLERK_SESSION_COOKIE not set"
    echo ""
fi

# Test 4: X-Clerk-User-Email alone should NOT authenticate (security check)
echo "Test 4: X-Clerk-User-Email header alone (should fail)"
echo "  Expect: 401 Unauthorized (email header is NOT authentication)"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
    -H "X-Clerk-User-Email: test@example.com" \
    "$BASE_URL$ENDPOINT")
if [ "$STATUS" = "401" ]; then
    echo "  Result: PASS (got $STATUS - correctly rejected)"
    PASS=$((PASS + 1))
else
    echo "  Result: FAIL (got $STATUS, expected 401)"
    echo "  SECURITY ISSUE: Email header should not grant access!"
    FAIL=$((FAIL + 1))
fi
echo ""

# Summary
echo "========================================"
echo "Summary: $PASS passed, $FAIL failed"
echo "========================================"

if [ $FAIL -gt 0 ]; then
    exit 1
else
    echo "All tests PASSED!"
    exit 0
fi
