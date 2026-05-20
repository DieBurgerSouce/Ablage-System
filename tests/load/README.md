# Ablage-System Load Testing

Load testing infrastructure using [k6](https://k6.io/) for the Ablage-System document processing platform.

## Performance Targets

Based on CLAUDE.md requirements:

| Metric | Target | Critical |
|--------|--------|----------|
| API Health Check | < 50ms (p95) | < 100ms (p99) |
| Document Upload | < 500ms (p95) | < 1000ms (p99) |
| OCR Processing (GPU) | < 2s (p95) | < 5s (p99) |
| OCR Processing (CPU) | < 10s (p95) | < 30s (p99) |
| Search Query | < 100ms (p95) | < 200ms (p99) |
| Concurrent Users | 100+ | - |
| Documents/Hour | 500+ (GPU) | - |

## Prerequisites

### Install k6

**Windows (winget):**
```bash
winget install k6
```

**Windows (Chocolatey):**
```bash
choco install k6
```

**macOS:**
```bash
brew install k6
```

**Linux (Debian/Ubuntu):**
```bash
sudo gpg -k
sudo gpg --no-default-keyring --keyring /usr/share/keyrings/k6-archive-keyring.gpg --keyserver hkp://keyserver.ubuntu.com:80 --recv-keys C5AD17C747E3415A3642D57D77C6C491D6AC1D69
echo "deb [signed-by=/usr/share/keyrings/k6-archive-keyring.gpg] https://dl.k6.io/deb stable main" | sudo tee /etc/apt/sources.list.d/k6.list
sudo apt-get update
sudo apt-get install k6
```

**Docker:**
```bash
docker pull grafana/k6
```

### Environment Setup

Create a test user in the system:
```bash
# Email: loadtest@ablage-system.local
# Password: LoadTest123!@#
```

Or set environment variables:
```bash
export BASE_URL=http://localhost:8000
export TEST_EMAIL=your-test-user@example.com
export TEST_PASSWORD=your-test-password
```

## Directory Structure

```
tests/load/
+-- README.md                 # This file
+-- k6/
    +-- config.js             # Global configuration
    +-- thresholds.json       # Performance thresholds
    +-- run_tests.sh          # Test runner script
    +-- lib/
    |   +-- auth.js           # Authentication helpers
    |   +-- helpers.js        # Utility functions
    |   +-- config.js         # Configuration module
    +-- scenarios/
    |   +-- health_check.js   # Health endpoint test
    |   +-- auth_flow.js      # Authentication flow test
    |   +-- document_upload.js # Document upload test
    |   +-- concurrent_users.js # 100 concurrent users test
    |   +-- search_latency.js  # Search performance test
    |   +-- search_stress.js   # Search stress test
    |   +-- ocr_processing.js  # OCR processing test
    |   +-- ocr_queue.js       # OCR queue management test
    |   +-- ocr_backpressure.js # OCR backpressure test
    +-- results/              # Test results (auto-created)
```

## Running Tests

### Using the Test Runner Script

```bash
# Make script executable (Unix)
chmod +x tests/load/k6/run_tests.sh

# Run smoke test (quick validation)
./tests/load/k6/run_tests.sh smoke

# Run specific test
./tests/load/k6/run_tests.sh health
./tests/load/k6/run_tests.sh auth
./tests/load/k6/run_tests.sh upload
./tests/load/k6/run_tests.sh search
./tests/load/k6/run_tests.sh ocr

# Run all tests
./tests/load/k6/run_tests.sh all
```

### Running Individual Tests Directly

```bash
# Health check
k6 run tests/load/k6/scenarios/health_check.js

# Concurrent users (100 users)
k6 run tests/load/k6/scenarios/concurrent_users.js

# Search latency
k6 run tests/load/k6/scenarios/search_latency.js

# OCR queue test
k6 run tests/load/k6/scenarios/ocr_queue.js

# OCR backpressure
k6 run tests/load/k6/scenarios/ocr_backpressure.js
```

### Test Scenarios

#### Concurrent Users Test

Tests system behavior with 100 concurrent users performing typical workflows.

```bash
k6 run tests/load/k6/scenarios/concurrent_users.js

# With custom settings
k6 run tests/load/k6/scenarios/concurrent_users.js --vus 100 --duration 5m
```

Workflow per user:
1. Login
2. View Dashboard
3. Browse Document List
4. Search Documents
5. View Document Detail
6. Logout

#### Search Latency Test

Tests search performance with target p99 < 200ms.

```bash
k6 run tests/load/k6/scenarios/search_latency.js
```

Search types tested:
- Fulltext search (40%)
- Entity search (20%)
- Filter search (20%)
- Advanced search (20%)

#### OCR Queue Test

Tests OCR queue management and recovery.

```bash
# Sustained load (default)
k6 run tests/load/k6/scenarios/ocr_queue.js

# Spike test
k6 run tests/load/k6/scenarios/ocr_queue.js --env SCENARIO=spike

# Stress test
k6 run tests/load/k6/scenarios/ocr_queue.js --env SCENARIO=stress

# Quick smoke test
k6 run tests/load/k6/scenarios/ocr_queue.js --env SCENARIO=smoke
```

#### Document Upload Test

Tests document upload performance targeting 500 docs/hour.

```bash
k6 run tests/load/k6/scenarios/document_upload.js
```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `BASE_URL` | API base URL | `http://localhost:8000` |
| `TEST_EMAIL` | Test user email | `loadtest@ablage-system.local` |
| `TEST_PASSWORD` | Test user password | `LoadTest123!@#` |
| `ENVIRONMENT` | Environment name | `development` |
| `K6_OUT` | Output format | JSON file |
| `SCENARIO` | Test scenario (for ocr_queue.js) | `sustained` |

### Custom Configuration

```bash
# With environment variables
BASE_URL=http://staging.example.com k6 run tests/load/k6/scenarios/concurrent_users.js

# With custom VUs and duration
k6 run --vus 50 --duration 10m tests/load/k6/scenarios/search_latency.js
```

## Interpreting Results

### Console Output

k6 provides real-time metrics during test execution:
- **http_req_duration**: Request latency (p95, p99, avg)
- **http_req_failed**: Error rate
- **http_reqs**: Request throughput
- **vus**: Active virtual users

### Thresholds

Tests define pass/fail thresholds. A threshold failure indicates performance regression:

```
[PASS] http_req_duration..........: avg=45.23ms  p(95)=89.45ms
[FAIL] http_req_duration..........: p(95)=523.45ms > 500ms
```

### JSON Results

Results are saved to `tests/load/k6/results/` with timestamps:
```bash
# View results
cat tests/load/k6/results/health_check_20240115_143022.json | jq '.metrics'
```

### Custom Metrics

Each test exports custom metrics for specific monitoring:
- `login_duration`: Authentication latency
- `search_duration`: Search query latency
- `ocr_queue_depth`: Current OCR queue size
- `ocr_queue_wait_time`: Time spent in queue
- `documents_uploaded`: Upload counter

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Load Tests

on:
  schedule:
    - cron: '0 2 * * *'  # Daily at 2 AM
  workflow_dispatch:

jobs:
  load-test:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Install k6
        run: |
          sudo gpg -k
          sudo gpg --no-default-keyring --keyring /usr/share/keyrings/k6-archive-keyring.gpg \
            --keyserver hkp://keyserver.ubuntu.com:80 --recv-keys C5AD17C747E3415A3642D57D77C6C491D6AC1D69
          echo "deb [signed-by=/usr/share/keyrings/k6-archive-keyring.gpg] https://dl.k6.io/deb stable main" \
            | sudo tee /etc/apt/sources.list.d/k6.list
          sudo apt-get update
          sudo apt-get install k6

      - name: Run Load Tests
        env:
          BASE_URL: ${{ secrets.LOAD_TEST_URL }}
          TEST_EMAIL: ${{ secrets.LOAD_TEST_EMAIL }}
          TEST_PASSWORD: ${{ secrets.LOAD_TEST_PASSWORD }}
        run: |
          k6 run tests/load/k6/scenarios/health_check.js
          k6 run tests/load/k6/scenarios/concurrent_users.js

      - name: Upload Results
        uses: actions/upload-artifact@v4
        with:
          name: k6-results
          path: tests/load/k6/results/
```

### Docker Compose Integration

```yaml
# docker-compose.test.yml
services:
  load-test:
    image: grafana/k6
    volumes:
      - ./tests/load/k6:/scripts
    environment:
      - BASE_URL=http://backend:8000
      - TEST_EMAIL=loadtest@ablage-system.local
      - TEST_PASSWORD=LoadTest123!@#
    command: run /scripts/scenarios/concurrent_users.js
    depends_on:
      - backend
```

Run with:
```bash
docker-compose -f docker-compose.yml -f docker-compose.test.yml run load-test
```

## Extending Tests

### Adding New Scenarios

1. Create new file in `tests/load/k6/scenarios/`
2. Import from `../config.js` for shared configuration
3. Define custom metrics with `new Trend()`, `new Rate()`, etc.
4. Export `options` with scenarios and thresholds
5. Export test functions
6. Add to `run_tests.sh`

Example template:
```javascript
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Trend, Rate } from 'k6/metrics';
import { BASE_URL, API_PREFIX, TEST_USER, getHeaders } from '../config.js';

const myMetric = new Trend('my_metric', true);
const myErrors = new Rate('my_errors');

export const options = {
  scenarios: {
    my_test: {
      executor: 'constant-vus',
      vus: 10,
      duration: '5m',
      exec: 'myTestFunction',
    },
  },
  thresholds: {
    'my_metric': ['p(95)<500'],
    'my_errors': ['rate<0.05'],
  },
};

export function myTestFunction() {
  // Test logic
}

export default function() {
  myTestFunction();
}
```

### Using Library Functions

```javascript
import { ensureAuth, authMetrics } from '../lib/auth.js';
import { randomGermanText, generateTestPDF } from '../lib/helpers.js';
import { getUrl, THRESHOLDS } from '../lib/config.js';

export function myTest() {
  const token = ensureAuth();
  if (!token) return;

  const pdf = generateTestPDF(2);
  // ... rest of test
}
```

## Troubleshooting

### Common Issues

**1. Authentication Failures**
```
Login failed after 3 attempts
```
- Verify test user exists in database
- Check credentials in environment variables
- Ensure API is running and accessible

**2. Rate Limiting**
```
Rate limit hit during login
```
- Expected under high load
- Tests include backoff handling
- Adjust rate limits in config if needed

**3. Connection Refused**
```
dial tcp: connection refused
```
- Verify `BASE_URL` is correct
- Ensure backend is running
- Check network/firewall settings

**4. Timeout Errors**
```
request timeout
```
- Increase timeout in test options
- Check backend performance
- Reduce concurrent users

### Debug Mode

Run with verbose output:
```bash
k6 run --verbose tests/load/k6/scenarios/health_check.js
```

### View Detailed Metrics

```bash
k6 run --out json=results.json tests/load/k6/scenarios/concurrent_users.js
cat results.json | jq '.metrics | keys'
```

## Performance Tuning

### Recommendations

1. **Start Small**: Begin with smoke tests before full load
2. **Warm-up Period**: Tests include ramp-up stages
3. **Monitor Resources**: Watch CPU, memory, GPU during tests
4. **Baseline First**: Establish baseline before changes
5. **Isolate Tests**: Run one scenario at a time for accurate results

### k6 Options for Large Tests

```bash
# More granular output
k6 run --summary-trend-stats="avg,min,med,max,p(90),p(95),p(99)" ...

# Output to multiple destinations
k6 run --out json=results.json --out influxdb=http://localhost:8086/k6 ...
```

## References

- [k6 Documentation](https://k6.io/docs/)
- [k6 JavaScript API](https://k6.io/docs/javascript-api/)
- [k6 Thresholds](https://k6.io/docs/using-k6/thresholds/)
- [k6 Scenarios](https://k6.io/docs/using-k6/scenarios/)
- [Ablage-System CLAUDE.md](../../CLAUDE.md)
