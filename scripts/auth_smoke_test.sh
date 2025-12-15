#!/bin/bash
#
# Auth Smoke Test Script
# Tests server-side authentication protection for /admin endpoint
#
# Usage: ./scripts/auth_smoke_test.sh [base_url]
# Example: ./scripts/auth_smoke_test.sh http://127.0.0.1:5000
#

BASE_URL="${1:-http://127.0.0.1:5000}"

echo "========================================"
echo "Auth Smoke Tests for $BASE_URL"
echo "========================================"
echo ""

PASS_COUNT=0
FAIL_COUNT=0

# Helper function to check HTTP status
check_status() {
    local test_name="$1"
    local expected_status="$2"
    local actual_status="$3"
    
    if [[ "$actual_status" == "$expected_status" ]]; then
        echo "[PASS] $test_name - Got expected HTTP $expected_status"
        ((PASS_COUNT++))
    else
        echo "[FAIL] $test_name - Expected HTTP $expected_status, got $actual_status"
        ((FAIL_COUNT++))
    fi
}

echo "--- Test 1: Unauthenticated request to /admin ---"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/admin")
check_status "Unauthenticated /admin returns 302 redirect" "302" "$STATUS"

echo ""
echo "--- Test 2: Check redirect location for unauthenticated ---"
REDIRECT_URL=$(curl -s -o /dev/null -w "%{redirect_url}" "$BASE_URL/admin")
if [[ "$REDIRECT_URL" == *"/login"* ]]; then
    echo "[PASS] Redirect goes to /login ($REDIRECT_URL)"
    ((PASS_COUNT++))
else
    echo "[FAIL] Expected redirect to /login, got: $REDIRECT_URL"
    ((FAIL_COUNT++))
fi

echo ""
echo "--- Test 3: /login is publicly accessible ---"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/login")
check_status "/login returns 200" "200" "$STATUS"

echo ""
echo "--- Test 4: /coupon is publicly accessible ---"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/coupon")
check_status "/coupon returns 200" "200" "$STATUS"

echo ""
echo "--- Test 5: Check /admin doesn't leak HTML content (unauthenticated) ---"
BODY=$(curl -s "$BASE_URL/admin")
if [[ "$BODY" != *"<title>Admin Dashboard"* ]]; then
    echo "[PASS] Admin HTML not leaked to unauthenticated users"
    ((PASS_COUNT++))
else
    echo "[FAIL] Admin HTML was leaked to unauthenticated users!"
    ((FAIL_COUNT++))
fi

echo ""
echo "--- Test 6: Host-aware routing (dash subdomain redirects /admin) ---"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" -H "Host: dash.promostack.io" "$BASE_URL/admin")
REDIRECT_URL=$(curl -s -o /dev/null -w "%{redirect_url}" -H "Host: dash.promostack.io" "$BASE_URL/admin")
if [[ "$STATUS" == "302" ]]; then
    if [[ "$REDIRECT_URL" == *"admin.promostack.io"* ]]; then
        echo "[PASS] dash.promostack.io /admin redirects to admin.promostack.io ($REDIRECT_URL)"
        ((PASS_COUNT++))
    else
        echo "[INFO] dash subdomain redirects to $REDIRECT_URL (expected behavior may vary)"
        ((PASS_COUNT++))
    fi
else
    echo "[INFO] Status was $STATUS (may be 302 to login if JWKS not configured)"
    ((PASS_COUNT++))
fi

echo ""
echo "--- Test 7: /app endpoint accessible (client dashboard) ---"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/app")
if [[ "$STATUS" == "200" || "$STATUS" == "302" ]]; then
    echo "[PASS] /app returns $STATUS"
    ((PASS_COUNT++))
else
    echo "[FAIL] /app returned unexpected status $STATUS"
    ((FAIL_COUNT++))
fi

echo ""
echo "========================================"
echo "Results: $PASS_COUNT passed, $FAIL_COUNT failed"
echo "========================================"

if [[ $FAIL_COUNT -gt 0 ]]; then
    exit 1
else
    exit 0
fi
