#!/bin/bash
# Verification Script for Vision 2.0 Phase 3 Tests
# Run this inside Docker: docker-compose exec backend bash verify_vision_2_0_tests.sh

echo "================================================"
echo "Vision 2.0 Phase 3 - Test Verification"
echo "================================================"
echo ""

echo "📁 Test Files:"
echo "  1. test_event_sourcing_service.py"
echo "  2. test_graphql_api.py"
echo "  3. test_delta_sync_service.py"
echo ""

echo "📊 Test Count per File:"
grep -c "^async def test_\|^def test_" tests/unit/services/test_event_sourcing_service.py | awk '{print "  Event Sourcing: " $1 " tests"}'
grep -c "^async def test_\|^def test_" tests/unit/services/test_graphql_api.py | awk '{print "  GraphQL API: " $1 " tests"}'
grep -c "^async def test_\|^def test_" tests/unit/services/test_delta_sync_service.py | awk '{print "  Delta Sync: " $1 " tests"}'
echo ""

echo "🔍 Running Tests..."
echo ""

# Run Event Sourcing Tests
echo "▶ Event Sourcing Tests:"
pytest tests/unit/services/test_event_sourcing_service.py -v --tb=short 2>&1 | tail -5
echo ""

# Run GraphQL API Tests
echo "▶ GraphQL API Tests:"
pytest tests/unit/services/test_graphql_api.py -v --tb=short 2>&1 | tail -5
echo ""

# Run Delta Sync Tests
echo "▶ Delta Sync Tests:"
pytest tests/unit/services/test_delta_sync_service.py -v --tb=short 2>&1 | tail -5
echo ""

# Run all with coverage
echo "📈 Coverage Report:"
pytest tests/unit/services/test_event_sourcing_service.py \
    tests/unit/services/test_graphql_api.py \
    tests/unit/services/test_delta_sync_service.py \
    --cov=app/services/event_sourcing \
    --cov=app/api/v1/graphql_api \
    --cov=app/services/sync \
    --cov-report=term-missing \
    2>&1 | grep -A 20 "TOTAL"

echo ""
echo "================================================"
echo "✅ Verification Complete"
echo "================================================"
