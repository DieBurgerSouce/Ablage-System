# Load Testing

You are setting up and executing load tests for the Ablage-System API.

## Your Task

Create comprehensive load testing infrastructure:

### 1. Choose Testing Tool

Use **Locust** (Python-based, async support):

```python
# locustfile.py
from locust import HttpUser, task, between
import random
```

### 2. Create Test Scenarios

Implement realistic user scenarios:

#### Scenario 1: Document Upload & Processing
```python
class DocumentProcessingUser(HttpUser):
    wait_time = between(1, 3)

    @task(3)
    def upload_document(self):
        # Upload a test document
        pass

    @task(2)
    def check_status(self):
        # Poll document status
        pass

    @task(1)
    def download_result(self):
        # Download processed document
        pass
```

#### Scenario 2: Search & Retrieval
```python
class SearchUser(HttpUser):
    wait_time = between(2, 5)

    @task
    def search_documents(self):
        # Search with various queries
        pass
```

### 3. Load Test Configuration

Create `tests/load/locustfile.py` with:

- **Test Data**: Pre-generate test documents (PDFs, images)
- **Authentication**: Include token generation
- **Realistic Patterns**: Mix of upload, search, download
- **Error Handling**: Log failures appropriately
- **Metrics**: Track custom metrics (OCR time, queue length)

### 4. Test Profiles

Create multiple test profiles:

#### Profile 1: Normal Load
- 10 concurrent users
- 5 min duration
- Expected: All requests < 2s response time

#### Profile 2: Peak Load
- 50 concurrent users
- 10 min duration
- Expected: 95th percentile < 5s

#### Profile 3: Stress Test
- 100+ users, ramp up
- Find breaking point
- Identify bottlenecks

#### Profile 4: Endurance Test
- 20 users
- 2 hours duration
- Check for memory leaks, performance degradation

### 5. Metrics to Track

Monitor and report:
- Requests per second (RPS)
- Response time (mean, median, 95th, 99th percentile)
- Error rate
- GPU utilization
- CPU utilization
- Memory usage
- Database connection pool usage
- Redis memory
- OCR processing queue length

### 6. Execution Scripts

Create helper scripts:

**`scripts/load_test.sh`**
```bash
#!/bin/bash
# Run load tests with different profiles

PROFILE=${1:-normal}

case $PROFILE in
  normal)
    locust -f tests/load/locustfile.py --users 10 --spawn-rate 2 --run-time 5m --headless
    ;;
  peak)
    locust -f tests/load/locustfile.py --users 50 --spawn-rate 5 --run-time 10m --headless
    ;;
  stress)
    locust -f tests/load/locustfile.py --users 100 --spawn-rate 10 --headless
    ;;
esac
```

### 7. Results Analysis

After tests, analyze:
- Generate HTML report
- Identify bottlenecks
- Compare against performance targets
- Provide recommendations

## Performance Targets (from CLAUDE.md)

- **Health Check**: < 50ms
- **Document Upload**: < 500ms
- **OCR Processing**: < 2s (GPU), < 10s (CPU)
- **Search Query**: < 500ms

## Output

Provide:
1. Complete `locustfile.py`
2. `scripts/load_test.sh`
3. Test data generation script
4. Execution instructions
5. Sample results interpretation
6. Performance optimization recommendations
