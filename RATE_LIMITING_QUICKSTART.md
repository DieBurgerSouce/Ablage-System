# Rate Limiting Quick Start Guide

Quick reference for developers working with Ablage-System rate limiting.

## Installation

```bash
# Install dependencies
pip install slowapi==0.1.9 limits==3.6.0

# Ensure Redis is running
docker-compose up -d redis
```

## Configuration (`.env`)

```bash
# Enable rate limiting
RATE_LIMIT_ENABLED=true

# Redis connection
REDIS_URL=redis://localhost:6380/0

# Optional: Whitelist IPs
RATE_LIMIT_WHITELIST=127.0.0.1,::1
```

## Rate Limit Tiers at a Glance

| Tier | OCR/hour | Batch/hour | API/minute |
|------|----------|------------|------------|
| Free | 10 | 5 | 100 |
| Premium | 100 | 50 | 100 |
| Admin | 10,000 | 1,000 | 10,000 |

## Common Endpoints

### Check Rate Limit Status
```bash
curl http://localhost:8000/ratelimit/status
```

### Check Your Rate Limit Info
```bash
curl http://localhost:8000/ratelimit/info \
  -H "Authorization: Bearer YOUR_TOKEN"
```

## Rate Limit Response (429)

```json
{
  "fehler": "Ratenlimit überschritten",
  "nachricht": "Sie haben zu viele Anfragen gesendet. Bitte versuchen Sie es in 60 Sekunden erneut.",
  "details": {
    "wiederholen_nach_sekunden": 60
  }
}
```

## Development Mode

Disable rate limiting for local development:

```bash
# In .env
DEBUG=true
RATE_LIMIT_ENABLED=false
```

## Testing

```bash
# Run rate limiting tests
pytest tests/test_rate_limiting.py -v

# Test a specific endpoint
for i in {1..10}; do curl -X POST http://localhost:8000/api/v1/auth/login -d '{"username":"test","password":"test"}'; done
```

## Troubleshooting

**Rate limits not working?**
1. Check `RATE_LIMIT_ENABLED=true` in `.env`
2. Verify Redis is running: `redis-cli ping`
3. Check logs for "rate_limit" entries

**Getting 429 too quickly?**
1. Check your user tier
2. Verify IP not accidentally whitelisted
3. Check rate limit configuration in `.env`

## Key Files

- `app/core/rate_limiting.py` - Core configuration
- `app/middleware/rate_limit.py` - Middleware implementation
- `RATE_LIMITING.md` - Full documentation
- `tests/test_rate_limiting.py` - Test suite

## Excluded Paths

These paths are **NOT** rate limited:
- `/health`
- `/docs`, `/redoc`
- `/metrics`
- `/ws/*` (WebSockets)

## IP Whitelisting

Add to `.env`:
```bash
RATE_LIMIT_WHITELIST=10.0.0.1,192.168.1.100
```

Or programmatically:
```python
from app.core.rate_limiting import ip_whitelist
ip_whitelist.add("10.0.0.100")
```

## Monitoring

Check metrics:
```python
from app.core.rate_limiting import rate_limit_metrics
stats = rate_limit_metrics.get_stats()
```

View logs:
```bash
docker-compose logs -f backend | grep rate_limit
```

---

For detailed documentation, see [RATE_LIMITING.md](RATE_LIMITING.md)
