#!/bin/bash
# Load Testing Script - Ablage-System OCR
# Performance testing using k6 or locust

set -e

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
API_URL="${API_URL:-http://localhost:8000}"
RESULTS_DIR="load-test-results"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Ensure results directory exists
mkdir -p "$RESULTS_DIR"

# Function to check dependencies
check_dependencies() {
    echo -e "${BLUE}🔍 Checking dependencies...${NC}"

    if command -v k6 &> /dev/null; then
        echo -e "${GREEN}✅ k6 is installed${NC}"
        LOAD_TEST_TOOL="k6"
    elif command -v locust &> /dev/null; then
        echo -e "${GREEN}✅ Locust is installed${NC}"
        LOAD_TEST_TOOL="locust"
    elif command -v ab &> /dev/null; then
        echo -e "${YELLOW}⚠️  Only Apache Bench (ab) available - limited functionality${NC}"
        LOAD_TEST_TOOL="ab"
    else
        echo -e "${RED}❌ No load testing tool found!${NC}"
        echo -e "${YELLOW}Install k6 or locust:${NC}"
        echo -e "   k6:     brew install k6  (or download from https://k6.io)"
        echo -e "   locust: pip install locust"
        exit 1
    fi
}

# Function to check if API is running
check_api_running() {
    echo -e "${BLUE}🔍 Checking if API is running...${NC}"

    if curl -s -f "$API_URL/health" > /dev/null 2>&1; then
        echo -e "${GREEN}✅ API is accessible at $API_URL${NC}"
    else
        echo -e "${RED}❌ API is not accessible at $API_URL${NC}"
        echo -e "${YELLOW}   Start the API first: make dev${NC}"
        exit 1
    fi
}

# Function to create k6 test script
create_k6_script() {
    cat > "$RESULTS_DIR/load-test.k6.js" <<'EOF'
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate } from 'k6/metrics';

// Custom metrics
const errorRate = new Rate('errors');

// Test configuration
export const options = {
  stages: [
    { duration: '30s', target: 10 },  // Ramp up to 10 users
    { duration: '1m', target: 10 },   // Stay at 10 users
    { duration: '30s', target: 50 },  // Ramp up to 50 users
    { duration: '2m', target: 50 },   // Stay at 50 users
    { duration: '30s', target: 100 }, // Spike to 100 users
    { duration: '1m', target: 100 },  // Stay at 100 users
    { duration: '30s', target: 0 },   // Ramp down to 0 users
  ],
  thresholds: {
    http_req_duration: ['p(95)<500'], // 95% of requests must complete below 500ms
    errors: ['rate<0.1'],             // Error rate must be below 10%
  },
};

const BASE_URL = __ENV.API_URL || 'http://localhost:8000';

// Test data
let authToken = null;

export function setup() {
  // Login to get auth token
  const loginRes = http.post(`${BASE_URL}/api/v1/auth/login`, JSON.stringify({
    email: 'user@example.com',
    password: 'password'
  }), {
    headers: { 'Content-Type': 'application/json' },
  });

  if (loginRes.status === 200) {
    const body = JSON.parse(loginRes.body);
    return { token: body.access_token };
  }

  return { token: null };
}

export default function(data) {
  const headers = data.token
    ? { 'Authorization': `Bearer ${data.token}` }
    : {};

  // Test 1: Health check (unauthenticated)
  let res = http.get(`${BASE_URL}/health`);
  check(res, {
    'health check status is 200': (r) => r.status === 200,
  }) || errorRate.add(1);

  sleep(1);

  // Test 2: List documents (authenticated)
  if (data.token) {
    res = http.get(`${BASE_URL}/api/v1/documents?limit=20`, { headers });
    check(res, {
      'list documents status is 200': (r) => r.status === 200,
      'response time < 500ms': (r) => r.timings.duration < 500,
    }) || errorRate.add(1);
  }

  sleep(2);

  // Test 3: Get current user (authenticated)
  if (data.token) {
    res = http.get(`${BASE_URL}/api/v1/users/me`, { headers });
    check(res, {
      'get user status is 200': (r) => r.status === 200,
    }) || errorRate.add(1);
  }

  sleep(1);
}

export function teardown(data) {
  console.log('Load test completed');
}
EOF
}

# Function to create Locust test script
create_locust_script() {
    cat > "$RESULTS_DIR/locustfile.py" <<'EOF'
import os
from locust import HttpUser, task, between

class AblageSystemUser(HttpUser):
    wait_time = between(1, 3)
    token = None

    def on_start(self):
        """Login and get auth token"""
        response = self.client.post("/api/v1/auth/login", json={
            "email": "user@example.com",
            "password": "password"
        })

        if response.status_code == 200:
            self.token = response.json()["access_token"]

    @task(3)
    def health_check(self):
        """Health check endpoint (unauthenticated)"""
        self.client.get("/health")

    @task(5)
    def list_documents(self):
        """List documents (authenticated)"""
        if self.token:
            headers = {"Authorization": f"Bearer {self.token}"}
            self.client.get("/api/v1/documents?limit=20", headers=headers)

    @task(2)
    def get_current_user(self):
        """Get current user (authenticated)"""
        if self.token:
            headers = {"Authorization": f"Bearer {self.token}"}
            self.client.get("/api/v1/users/me", headers=headers)

    @task(1)
    def api_docs(self):
        """Access API documentation"""
        self.client.get("/docs")
EOF
}

# Function to run k6 load test
run_k6_test() {
    echo -e "${BLUE}🚀 Running k6 load test...${NC}"

    create_k6_script

    REPORT_FILE="$RESULTS_DIR/k6-report-$TIMESTAMP.json"

    API_URL="$API_URL" k6 run \
        --out json="$REPORT_FILE" \
        --summary-export="$RESULTS_DIR/k6-summary-$TIMESTAMP.json" \
        "$RESULTS_DIR/load-test.k6.js"

    echo -e "${GREEN}✅ k6 test complete${NC}"
    echo -e "${BLUE}   Report: $REPORT_FILE${NC}"
}

# Function to run Locust load test
run_locust_test() {
    echo -e "${BLUE}🚀 Running Locust load test...${NC}"

    create_locust_script

    echo -e "${YELLOW}Starting Locust web interface...${NC}"
    echo -e "${BLUE}   Web UI: http://localhost:8089${NC}"
    echo -e "${YELLOW}   Configure test parameters in the web interface${NC}"
    echo ""

    locust \
        -f "$RESULTS_DIR/locustfile.py" \
        --host="$API_URL" \
        --web-host="0.0.0.0" \
        --web-port=8089 \
        --html="$RESULTS_DIR/locust-report-$TIMESTAMP.html" \
        --csv="$RESULTS_DIR/locust-stats-$TIMESTAMP"

    echo -e "${GREEN}✅ Locust test complete${NC}"
}

# Function to run Apache Bench test (fallback)
run_ab_test() {
    echo -e "${BLUE}🚀 Running Apache Bench test...${NC}"

    # Health check endpoint
    echo -e "${BLUE}Testing health endpoint...${NC}"
    ab -n 1000 -c 10 -g "$RESULTS_DIR/ab-health-$TIMESTAMP.tsv" "$API_URL/health" > "$RESULTS_DIR/ab-health-$TIMESTAMP.txt"

    # API documentation
    echo -e "${BLUE}Testing docs endpoint...${NC}"
    ab -n 500 -c 5 -g "$RESULTS_DIR/ab-docs-$TIMESTAMP.tsv" "$API_URL/docs" > "$RESULTS_DIR/ab-docs-$TIMESTAMP.txt"

    echo -e "${GREEN}✅ Apache Bench test complete${NC}"
    echo -e "${BLUE}   Health report: $RESULTS_DIR/ab-health-$TIMESTAMP.txt${NC}"
    echo -e "${BLUE}   Docs report: $RESULTS_DIR/ab-docs-$TIMESTAMP.txt${NC}"
}

# Function to analyze results
analyze_results() {
    echo ""
    echo -e "${BLUE}📊 Load Test Results Summary${NC}"
    echo -e "${BLUE}════════════════════════════${NC}"

    if [ "$LOAD_TEST_TOOL" == "k6" ]; then
        # Parse k6 summary
        SUMMARY_FILE=$(ls -t "$RESULTS_DIR"/k6-summary-*.json 2>/dev/null | head -1)

        if [ -f "$SUMMARY_FILE" ]; then
            echo -e "${GREEN}K6 Test Results:${NC}"
            echo ""
            cat "$SUMMARY_FILE" | python3 -m json.tool | grep -E "(http_req_duration|http_reqs|http_req_failed|errors)" || true
        fi

    elif [ "$LOAD_TEST_TOOL" == "ab" ]; then
        # Parse Apache Bench results
        HEALTH_REPORT=$(ls -t "$RESULTS_DIR"/ab-health-*.txt 2>/dev/null | head -1)

        if [ -f "$HEALTH_REPORT" ]; then
            echo -e "${GREEN}Apache Bench Results (Health Endpoint):${NC}"
            echo ""
            grep -E "(Requests per second|Time per request|Failed requests)" "$HEALTH_REPORT" || true
        fi
    fi

    echo ""
    echo -e "${GREEN}📁 All results saved in: $RESULTS_DIR${NC}"
}

# Function to display recommendations
show_recommendations() {
    echo ""
    echo -e "${BLUE}💡 Recommendations:${NC}"
    echo ""
    echo -e "  • ${GREEN}Response Time:${NC} Should be <500ms for 95th percentile"
    echo -e "  • ${GREEN}Error Rate:${NC} Should be <1% under normal load"
    echo -e "  • ${GREEN}Throughput:${NC} Aim for >100 req/sec for production"
    echo -e "  • ${GREEN}GPU Usage:${NC} Monitor with 'make gpu-status' during tests"
    echo ""
    echo -e "${YELLOW}For comprehensive testing:${NC}"
    echo -e "  1. Test with realistic document uploads"
    echo -e "  2. Test OCR processing under load"
    echo -e "  3. Monitor database connection pool"
    echo -e "  4. Check memory leaks with extended tests"
    echo -e "  5. Test with different user load patterns"
    echo ""
}

# Main script
main() {
    echo -e "${BLUE}⚡ Load Testing Script${NC}"
    echo -e "${BLUE}═════════════════════${NC}"
    echo ""

    check_dependencies
    check_api_running

    # Run load test based on available tool
    case "$LOAD_TEST_TOOL" in
        k6)
            run_k6_test
            ;;
        locust)
            run_locust_test
            ;;
        ab)
            run_ab_test
            ;;
    esac

    analyze_results
    show_recommendations

    echo -e "${GREEN}✅ Load testing complete!${NC}"
}

# Parse command line arguments
COMMAND=${1:-run}

case "$COMMAND" in
    run)
        main
        ;;
    analyze)
        analyze_results
        ;;
    help|-h|--help)
        echo "Usage: $0 [command]"
        echo ""
        echo "Commands:"
        echo "  run      - Run load test (default)"
        echo "  analyze  - Analyze previous test results"
        echo "  help     - Show this help message"
        ;;
    *)
        echo -e "${RED}❌ Unknown command: $COMMAND${NC}"
        exit 1
        ;;
esac
