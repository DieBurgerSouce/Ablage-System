# Performance Map of Content (MOC)

**Purpose:** Central hub for all performance-related documentation, benchmarks, and optimization guides in the Ablage-System.

**Last Updated:** 2025-01-22
**Maintained By:** ML Engineering Team, DevOps Team

---

## Overview

This MOC serves as the single source of truth for performance targets, benchmarks, optimization techniques, and monitoring strategies across the Ablage-System.

**Performance Philosophy:** "Fast by default, optimized where it matters" - Prioritize user-facing latency while maintaining high throughput for batch operations.

---

## Quick Reference

### Performance Targets (SLIs)

| Metric | Target | Current | Status |
|--------|--------|---------|--------|
| **API Response Time (P95)** | < 500ms | 320ms | ✅ Exceeds |
| **Document Upload** | < 2s | 1.2s | ✅ Exceeds |
| **OCR Processing (per page)** | < 3s | 2.8s | ✅ Meets |
| **Throughput** | 150 docs/hour | 192 docs/hour | ✅ Exceeds |
| **GPU Utilization** | 75-85% | 82% | ✅ Optimal |
| **Error Rate** | < 1% | 0.3% | ✅ Exceeds |

### Critical Performance Paths

1. **Document Upload → OCR → Storage** (End-to-End: < 10s)
2. **API Authentication** (< 50ms)
3. **Database Queries** (P95 < 100ms)
4. **GPU Batch Processing** (2-16 docs, 0.8-2.8s per page)

---

## Performance Documentation Index

### 1. Architecture & Design

**Core ADRs:**
- **[ADR-001: GPU Architecture Selection](../../Static_Knowledge/ADRs/ADR_001_gpu_architecture.md)**
  - Why RTX 4080 was chosen
  - VRAM requirements (16GB)
  - Performance benchmarks

- **[ADR-003: OCR Backend Selection](../../Static_Knowledge/ADRs/ADR_003_ocr_backend_selection.md)**
  - Multi-backend strategy rationale
  - Performance vs accuracy tradeoffs
  - Backend selection decision tree

**Related:**
- Database schema design for query performance
- Caching strategy (Redis)
- Async/await architecture patterns

### 2. Benchmarks & Experiments

**GPU Optimization:**
- **[GPU Memory Optimization Experiment](../../Dynamic_Knowledge/Experiments/gpu_memory_optimization_experiment.yaml)**
  - Dynamic batch sizing results (+60% throughput)
  - VRAM utilization optimization
  - Gradient checkpointing performance impact

**OCR Backends:**
- **DeepSeek-Janus-Pro**: 2.8% CER, 2.8s/page, 12GB VRAM
- **GOT-OCR 2.0**: 5.9% CER, 0.8s/page, 10GB VRAM
- **Surya + Docling**: 8.7% CER, 5.0s/page (CPU), 1.9s (GPU)

**Database:**
- Connection pool sizing: 20 connections (optimal for workload)
- Query performance: P95 < 50ms (indexed queries)
- Migration performance: < 5s for schema changes

### 3. Optimization Guides

**Code-Level Optimizations:**
- **[Celery Task Optimization](../../Dynamic_Knowledge/Learnings/celery_task_optimization.md)**
  - Worker configuration (--pool=solo for GPU tasks)
  - Batch sizing strategies
  - Memory cleanup patterns

**Database Optimization:**
- Index strategies (B-tree for lookups, GIN for full-text)
- Query optimization techniques
- Connection pooling best practices

**GPU Optimization:**
- Batch size selection (complexity-aware)
- VRAM management (85% threshold)
- Model quantization (FP16 vs INT8)

### 4. Monitoring & Observability

**Prometheus Metrics:**
```yaml
key_metrics:
  api_response_time:
    metric: "http_request_duration_seconds"
    alert_threshold: "P95 > 1s for 5 minutes"

  gpu_vram_usage:
    metric: "gpu_vram_percent"
    alert_threshold: "> 90% for 2 minutes"

  ocr_processing_duration:
    metric: "ocr_processing_duration_seconds"
    alert_threshold: "P95 > 5s for 10 minutes"

  error_rate:
    metric: "http_requests_total{status=~'5..'}"
    alert_threshold: "> 1% for 5 minutes"
```

**Grafana Dashboards:**
- **Performance Overview**: API latency, throughput, error rate
- **GPU Metrics**: VRAM usage, utilization, temperature
- **OCR Pipeline**: Backend selection, processing time, accuracy
- **Database**: Query performance, connection pool, cache hit rate

**Related:**
- **[Monitoring Agent](../../Execution_Layer/Agents/monitoring_agent.py)** - Automated health checks
- **[Troubleshooting Index](../Indexes/troubleshooting_index.yaml)** - Performance issue resolution

### 5. Load Testing & Capacity Planning

**Load Testing Results (2024 Q4):**
```yaml
baseline_load:
  concurrent_users: 50
  requests_per_second: 120
  p95_latency: 320ms
  error_rate: 0.2%

peak_load:
  concurrent_users: 200
  requests_per_second: 450
  p95_latency: 890ms
  error_rate: 1.1%

breaking_point:
  concurrent_users: 350
  requests_per_second: 600
  p95_latency: 2.5s
  error_rate: 5.2%
  bottleneck: "Database connection pool exhaustion"
```

**Capacity Planning:**
- Current capacity: 150-300 docs/hour (normal operation)
- Peak capacity: 450 docs/hour (traffic spike with degradation)
- Breaking point: 600 docs/hour (unacceptable latency)
- Recommended scaling: Add 2nd worker server at 400 docs/hour sustained

### 6. Performance Incidents & Learnings

**Incident: Celery Worker OOM (2025-01-12)**
- **[Incident Log](../../Dynamic_Knowledge/Logs/celery_worker_crash_log.md)**
- Root cause: Docker memory limit (8GB) too low
- Resolution: Increased to 12GB + dynamic batch sizing
- Learning: Always plan for 50% headroom on critical resources

**Performance Regressions:**
- Track performance changes with automated benchmarks
- Alert on P95 latency increase > 20% after deployment
- Rollback criteria: Performance degradation > 2× baseline

---

## Performance Optimization Checklist

### API Performance

- [x] Use async/await throughout (FastAPI + asyncpg)
- [x] Database connection pooling (20 connections)
- [x] Redis caching for frequently accessed data (1-hour TTL)
- [x] Response compression (gzip for > 1KB responses)
- [x] Rate limiting to prevent abuse
- [ ] CDN for static assets (future: if frontend grows)
- [ ] Query result pagination (> 100 results)

### Database Performance

- [x] Indexes on all foreign keys
- [x] Composite indexes for common queries
- [x] Async queries (asyncpg driver)
- [x] Connection pooling (SQLAlchemy async)
- [x] Query optimization (EXPLAIN ANALYZE for slow queries)
- [ ] Read replicas (future: if read load > 80%)
- [ ] Partitioning for audit_logs table (future: > 10M rows)

### GPU Performance

- [x] Dynamic batch sizing (2-16 documents)
- [x] Gradient checkpointing (reduces VRAM by 2-3GB)
- [x] VRAM monitoring (alert at 85%)
- [x] Model caching (lazy loading)
- [x] CPU fallback for GPU failures
- [ ] Model quantization (INT8) - reduces VRAM 50%, minimal accuracy loss
- [ ] Multi-GPU support (future: horizontal scaling)

### Celery/Worker Performance

- [x] Celery configuration: --pool=solo (GPU tasks)
- [x] Task timeouts (soft: 240s, hard: 300s)
- [x] Retry with exponential backoff
- [x] Task result expiration (24 hours)
- [x] Worker memory cleanup (torch.cuda.empty_cache())
- [ ] Task prioritization (enterprise > standard > free)
- [ ] Worker autoscaling (future: Kubernetes HPA)

---

## Performance Testing Procedures

### 1. Benchmark New Features

**Before Deploying:**
```bash
# Run performance benchmarks
pytest tests/performance/test_ocr_performance.py -v

# Compare with baseline
python scripts/compare_benchmarks.py --baseline=v1.4.0 --current=v1.5.0
```

**Acceptance Criteria:**
- P95 latency increase < 10%
- Throughput decrease < 5%
- No new performance alerts in staging

### 2. Load Testing (Pre-Release)

**Weekly Load Test:**
```bash
# Using Locust or k6
locust -f tests/load/locustfile.py --users 200 --spawn-rate 10 --run-time 30m

# Monitor Grafana dashboard during test
open https://grafana.ablage-system.local/d/load-test-overview
```

### 3. Production Performance Monitoring

**Daily Review:**
- Check P95 latency trends (compare week-over-week)
- Review error rate (should be < 1%)
- Verify GPU utilization (75-85% optimal)
- Check queue depth (< 50 normal, alert at 200)

**Weekly Report:**
- Performance SLI compliance (target vs actual)
- Capacity utilization (current vs breaking point)
- Incident count and MTTR
- Optimization opportunities

---

## Performance Tuning Guide

### Scenario: Slow API Responses

**Diagnosis:**
1. Check Prometheus: `http_request_duration_seconds{quantile="0.95"}`
2. Identify slow endpoints: `rate(http_request_duration_seconds_sum[5m]) / rate(http_request_duration_seconds_count[5m])`
3. Review application logs for slow queries

**Common Causes & Fixes:**
- **Database**: Add indexes, optimize queries, increase connection pool
- **Redis**: Check cache hit rate, increase TTL for frequently accessed data
- **CPU**: Scale horizontally (add workers)
- **Network**: Enable response compression, use CDN

### Scenario: Low Throughput

**Diagnosis:**
1. Check Celery queue depth: `celery_queue_length`
2. Monitor GPU utilization: `gpu_utilization_percent`
3. Check worker health: `celery_worker_up`

**Common Causes & Fixes:**
- **GPU underutilized**: Increase batch size (if VRAM < 70%)
- **Workers offline**: Restart Celery workers
- **Slow OCR backend**: Review backend selection logic
- **Network bottleneck**: Increase Redis/PostgreSQL connection limits

### Scenario: High Error Rate

**Diagnosis:**
1. Check error breakdown: `rate(http_requests_total{status=~"5.."}[5m])`
2. Review error logs: `docker-compose logs backend | grep ERROR`
3. Check dependency health: `health_check_status`

**Common Causes & Fixes:**
- **Database timeout**: Increase query timeout, optimize slow queries
- **GPU OOM**: Reduce batch size, clear VRAM cache
- **Worker crash**: Investigate logs, increase memory limits
- **Dependency down**: Restart failed service (Redis/PostgreSQL/MinIO)

---

## Related Documentation

**Architecture:**
- [Technology Stack Graph](../Knowledge_Graphs/technology_stack_graph.yaml)
- [Infrastructure Dependencies](../Knowledge_Graphs/infrastructure_dependencies.yaml)

**Operations:**
- [Deployment Workflow](../../Relations/Workflows/deployment_workflow.md)
- [Error Recovery Decision Tree](../../Relations/Decision_Trees/error_recovery_decision_tree.yaml)

**Monitoring:**
- [Monitoring Agent](../../Execution_Layer/Agents/monitoring_agent.py)
- [Troubleshooting Index](../Indexes/troubleshooting_index.yaml)

---

## Performance Goals (2025)

**Q1 2025:**
- ✅ Achieve 60% throughput improvement (COMPLETED: GPU optimization)
- [ ] Reduce P95 latency to < 300ms (currently 320ms)
- [ ] Implement query result caching (reduce DB load by 30%)

**Q2 2025:**
- [ ] INT8 quantization for GOT-OCR (30% faster, 50% less VRAM)
- [ ] Implement read replicas (support 2× read load)
- [ ] Worker autoscaling (automatic horizontal scaling)

**Q3 2025:**
- [ ] Multi-GPU support (2× RTX 4080 = 2× throughput)
- [ ] CDN integration for static assets
- [ ] Advanced caching (Redis Cluster)

**Q4 2025:**
- [ ] Performance SLO: 99.9% requests < 500ms P95
- [ ] Capacity: 1000 docs/hour sustained
- [ ] Cost efficiency: < €5 per 1000 documents

---

**MOC Version:** 1.0
**Next Review:** 2025-04-22 (Quarterly)
**Owner:** ML Engineering Team, DevOps Team
