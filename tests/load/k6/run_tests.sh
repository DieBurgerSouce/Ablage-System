#!/bin/bash
#
# K6 Load Test Runner for Ablage-System
#
# Usage:
#   ./run_tests.sh                    # Run all tests (smoke)
#   ./run_tests.sh health             # Run health check tests
#   ./run_tests.sh auth               # Run auth flow tests
#   ./run_tests.sh upload             # Run document upload tests
#   ./run_tests.sh search             # Run search stress tests
#   ./run_tests.sh search-latency     # Run search latency tests (p99 < 200ms)
#   ./run_tests.sh ocr                # Run OCR processing tests
#   ./run_tests.sh ocr-queue          # Run OCR queue management tests
#   ./run_tests.sh ocr-backpressure   # Run OCR backpressure tests
#   ./run_tests.sh concurrent         # Run 100 concurrent users test
#   ./run_tests.sh all                # Run all tests sequentially
#
# Environment variables:
#   BASE_URL          - API base URL (default: http://localhost:8000)
#   TEST_EMAIL        - Test user email
#   TEST_PASSWORD     - Test user password
#   ENVIRONMENT       - Environment name (development, staging, production)
#   K6_OUT            - Output format (json, influxdb, cloud)
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Default configuration
export BASE_URL="${BASE_URL:-http://localhost:8000}"
export TEST_EMAIL="${TEST_EMAIL:-loadtest@ablage-system.local}"
export TEST_PASSWORD="${TEST_PASSWORD:-LoadTest123!@#}"
export ENVIRONMENT="${ENVIRONMENT:-development}"

# Results directory
RESULTS_DIR="${SCRIPT_DIR}/results"
mkdir -p "$RESULTS_DIR"

# Timestamp for results
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}   Ablage-System K6 Load Tests${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "Base URL: ${GREEN}${BASE_URL}${NC}"
echo -e "Environment: ${YELLOW}${ENVIRONMENT}${NC}"
echo ""

# Function to run a test
run_test() {
    local test_name=$1
    local test_file=$2
    local output_file="${RESULTS_DIR}/${test_name}_${TIMESTAMP}.json"

    echo -e "${BLUE}Running: ${test_name}${NC}"
    echo "----------------------------------------"

    if [ -n "$K6_OUT" ]; then
        k6 run \
            --out "${K6_OUT}" \
            --out "json=${output_file}" \
            "${test_file}"
    else
        k6 run \
            --out "json=${output_file}" \
            "${test_file}"
    fi

    echo ""
    echo -e "${GREEN}Completed: ${test_name}${NC}"
    echo -e "Results saved to: ${output_file}"
    echo ""
}

# Check if k6 is installed
if ! command -v k6 &> /dev/null; then
    echo -e "${RED}Error: k6 is not installed${NC}"
    echo ""
    echo "Install k6:"
    echo "  - Windows: winget install k6"
    echo "  - macOS: brew install k6"
    echo "  - Linux: https://k6.io/docs/getting-started/installation/"
    echo "  - Docker: docker pull grafana/k6"
    exit 1
fi

# Parse command line arguments
TEST_TYPE="${1:-smoke}"

case "$TEST_TYPE" in
    health)
        run_test "health_check" "${SCRIPT_DIR}/scenarios/health_check.js"
        ;;
    auth)
        run_test "auth_flow" "${SCRIPT_DIR}/scenarios/auth_flow.js"
        ;;
    upload)
        run_test "document_upload" "${SCRIPT_DIR}/scenarios/document_upload.js"
        ;;
    search)
        run_test "search_stress" "${SCRIPT_DIR}/scenarios/search_stress.js"
        ;;
    search-latency)
        run_test "search_latency" "${SCRIPT_DIR}/scenarios/search_latency.js"
        ;;
    ocr)
        run_test "ocr_processing" "${SCRIPT_DIR}/scenarios/ocr_processing.js"
        ;;
    ocr-queue)
        run_test "ocr_queue" "${SCRIPT_DIR}/scenarios/ocr_queue.js"
        ;;
    ocr-backpressure)
        run_test "ocr_backpressure" "${SCRIPT_DIR}/scenarios/ocr_backpressure.js"
        ;;
    concurrent)
        run_test "concurrent_users" "${SCRIPT_DIR}/scenarios/concurrent_users.js"
        ;;
    all)
        echo -e "${YELLOW}Running all load tests...${NC}"
        echo ""
        run_test "health_check" "${SCRIPT_DIR}/scenarios/health_check.js"
        sleep 5
        run_test "auth_flow" "${SCRIPT_DIR}/scenarios/auth_flow.js"
        sleep 5
        run_test "document_upload" "${SCRIPT_DIR}/scenarios/document_upload.js"
        sleep 5
        run_test "concurrent_users" "${SCRIPT_DIR}/scenarios/concurrent_users.js"
        sleep 5
        run_test "search_stress" "${SCRIPT_DIR}/scenarios/search_stress.js"
        sleep 5
        run_test "search_latency" "${SCRIPT_DIR}/scenarios/search_latency.js"
        sleep 5
        run_test "ocr_processing" "${SCRIPT_DIR}/scenarios/ocr_processing.js"
        sleep 5
        run_test "ocr_queue" "${SCRIPT_DIR}/scenarios/ocr_queue.js"
        sleep 5
        run_test "ocr_backpressure" "${SCRIPT_DIR}/scenarios/ocr_backpressure.js"
        ;;
    smoke)
        echo -e "${YELLOW}Running smoke tests (quick validation)...${NC}"
        echo ""
        run_test "health_smoke" "${SCRIPT_DIR}/scenarios/health_check.js"
        ;;
    *)
        echo -e "${RED}Unknown test type: ${TEST_TYPE}${NC}"
        echo ""
        echo "Available tests:"
        echo "  health           - Health check endpoint"
        echo "  auth             - Authentication flow"
        echo "  upload           - Document upload"
        echo "  concurrent       - 100 concurrent users"
        echo "  search           - Search stress test"
        echo "  search-latency   - Search latency (p99 < 200ms)"
        echo "  ocr              - OCR processing"
        echo "  ocr-queue        - OCR queue management"
        echo "  ocr-backpressure - OCR backpressure handling"
        echo "  all              - Run all tests"
        echo "  smoke            - Quick smoke test (default)"
        exit 1
        ;;
esac

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}   Load tests completed!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "Results directory: ${RESULTS_DIR}"
