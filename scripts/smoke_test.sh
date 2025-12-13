#!/bin/bash
# Pre-Deploy Smoke Test Script
# Usage: ./scripts/smoke_test.sh [BASE_URL]
# Default: http://localhost:5000

BASE_URL="${1:-http://localhost:5000}"

echo "========================================="
echo "SMOKE TEST: $BASE_URL"
echo "========================================="

# Test function
test_endpoint() {
    local method=$1
    local path=$2
    local expected=$3
    local data=$4
    
    if [ "$method" = "GET" ]; then
        status=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL$path")
    else
        status=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL$path" -H "Content-Type: application/json" -d "$data")
    fi
    
    if [ "$status" = "$expected" ]; then
        echo "✅ $method $path → $status"
        return 0
    else
        echo "❌ $method $path → $status (expected $expected)"
        return 1
    fi
}

PASSED=0
FAILED=0

# GET tests
test_endpoint "GET" "/api/check-auth" "401" && ((PASSED++)) || ((FAILED++))
test_endpoint "GET" "/admin" "200" && ((PASSED++)) || ((FAILED++))
test_endpoint "GET" "/assets/promostack-logo.png" "200" && ((PASSED++)) || ((FAILED++))
test_endpoint "GET" "/login" "200" && ((PASSED++)) || ((FAILED++))

# POST tests (webhooks)
test_endpoint "POST" "/api/telegram-webhook" "200" "{}" && ((PASSED++)) || ((FAILED++))
test_endpoint "POST" "/api/forex-telegram-webhook" "200" "{}" && ((PASSED++)) || ((FAILED++))
# Stripe webhook returns 400 without signature, that's expected
status=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/api/stripe/webhook" -H "Content-Type: application/json" -d '{}')
if [ "$status" != "404" ]; then
    echo "✅ POST /api/stripe/webhook → $status (route exists)"
    ((PASSED++))
else
    echo "❌ POST /api/stripe/webhook → 404 (route missing!)"
    ((FAILED++))
fi

echo "========================================="
echo "RESULTS: $PASSED passed, $FAILED failed"
echo "========================================="

if [ $FAILED -eq 0 ]; then
    echo "✅ ALL SMOKE TESTS PASSED"
    exit 0
else
    echo "❌ SOME TESTS FAILED"
    exit 1
fi
