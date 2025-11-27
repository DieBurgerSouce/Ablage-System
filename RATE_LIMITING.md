# Rate Limiting Documentation - Ablage-System OCR API

## Overview

Comprehensive rate limiting implementation using SlowAPI with Redis backend for distributed rate limiting. All error messages are in German to maintain the German-first approach of the Ablage-System.

**Created:** 2025-11-26
**Status:** Production-ready
**Dependencies:** SlowAPI 0.1.9, Redis 5.0.1, limits 3.6.0

## Features

- **Multi-tier Rate Limiting**: Different limits for free, premium, and admin users
- **IP-based Rate Limiting**: Prevent brute force attacks on authentication endpoints
- **User-based Rate Limiting**: Track limits per authenticated user
- **Redis Backend**: Distributed rate limiting across multiple servers
- **Graceful Degradation**: Fail-open when Redis is unavailable
- **German Error Messages**: All user-facing messages in German
- **IP Whitelisting**: Bypass rate limits for trusted IPs
- **WebSocket Exclusion**: WebSocket endpoints excluded from rate limiting
- **Comprehensive Monitoring**: Prometheus metrics and detailed logging

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     FastAPI Application                      │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌───────────────────────────────────────────────────────┐  │
│  │         Rate Limit Middleware (middleware/)           │  │
│  │  - Request interception                                │  │
│  │  - Tier detection (free/premium/admin)                 │  │
│  │  - Whitelist checking                                  │  │
│  │  - WebSocket exclusion                                 │  │
│  └───────────────────────────────────────────────────────┘  │
│                           │                                   │
│                           ▼                                   │
│  ┌───────────────────────────────────────────────────────┐  │
│  │       Rate Limit Core (core/rate_limiting.py)         │  │
│  │  - SlowAPI limiter configuration                       │  │
│  │  - Key functions (user_id, IP)                         │  │
│  │  - German error handlers                               │  │
│  │  - Whitelist management                                │  │
│  └───────────────────────────────────────────────────────┘  │
│                           │                                   │
│                           ▼                                   │
│  ┌───────────────────────────────────────────────────────┐  │
│  │           Redis Storage Backend                        │  │
│  │  - Atomic counter operations                           │  │
│  │  - Automatic expiry (TTL)                              │  │
│  │  - High availability support                           │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

## Rate Limit Tiers

### Authentication Endpoints (IP-based)

| Endpoint | Limit | Window | Purpose |
|----------|-------|--------|---------|
| `/api/v1/auth/login` | 5 | 15 minutes | Prevent brute force attacks |
| `/api/v1/auth/register` | 3 | 1 hour | Prevent spam registrations |
| `/api/v1/auth/refresh` | 20 | 1 minute | Allow frequent token refresh |

### OCR Processing Endpoints (User-based)

#### Free Tier
| Endpoint | Limit | Window |
|----------|-------|--------|
| `/ocr/process` | 10 | 1 hour |
| `/ocr/batch` | 5 | 1 hour |
| General API | 100 | 1 minute |

#### Premium Tier
| Endpoint | Limit | Window |
|----------|-------|--------|
| `/ocr/process` | 100 | 1 hour |
| `/ocr/batch` | 50 | 1 hour |
| General API | 100 | 1 minute |

#### Admin Tier
| Endpoint | Limit | Window |
|----------|-------|--------|
| All endpoints | 10,000 | 1 hour |

### Status/Monitoring Endpoints

| Endpoint | Limit | Window | Notes |
|----------|-------|--------|-------|
| `/health` | Unlimited | - | Excluded from rate limiting |
| `/gpu/status` | 60 | 1 minute | Monitoring friendly |
| `/docs`, `/redoc` | Unlimited | - | Documentation excluded |

## Configuration

### Environment Variables

Add to `.env` file:

```bash
# Rate Limiting
RATE_LIMIT_ENABLED=true
RATE_LIMIT_REQUESTS_PER_MINUTE=100
RATE_LIMIT_DOCUMENTS_PER_HOUR=10
DEFAULT_USER_DAILY_QUOTA=100

# Rate Limit Tiers
RATE_LIMIT_FREE_HOURLY=10
RATE_LIMIT_FREE_DAILY=50
RATE_LIMIT_PREMIUM_HOURLY=100
RATE_LIMIT_PREMIUM_DAILY=1000
RATE_LIMIT_ADMIN_HOURLY=10000

# Rate Limit Windows (in seconds)
RATE_LIMIT_LOGIN_ATTEMPTS=5
RATE_LIMIT_LOGIN_WINDOW=900
RATE_LIMIT_REGISTER_ATTEMPTS=3
RATE_LIMIT_REGISTER_WINDOW=3600

# Rate Limit Whitelist (comma-separated IPs)
RATE_LIMIT_WHITELIST=127.0.0.1,::1
```

### Redis Configuration

Redis is required for distributed rate limiting:

```bash
# Redis connection
REDIS_HOST=localhost
REDIS_PORT=6380
REDIS_DB=0
REDIS_URL=redis://localhost:6380/0
```

## Usage

### Basic Setup

The rate limiting is automatically enabled when `RATE_LIMIT_ENABLED=true`. No code changes required in endpoints.

### Check Rate Limit Status

```bash
curl http://localhost:8000/ratelimit/status
```

Response:
```json
{
  "metrics": {
    "total_requests": 1000,
    "rate_limited_requests": 50,
    "whitelisted_requests": 10,
    "errors": 0,
    "rate_limit_percentage": 5.0
  },
  "whitelist": {
    "total_ips": 2,
    "ips": ["127.0.0.1", "::1"]
  },
  "configuration": {
    "enabled": true,
    "redis_available": true,
    "default_limit": 100
  },
  "timestamp": "2025-11-26T12:00:00.000Z"
}
```

### Check Current User's Rate Limit Info

```bash
curl http://localhost:8000/ratelimit/info \
  -H "Authorization: Bearer YOUR_TOKEN"
```

Response:
```json
{
  "user_id": "user123",
  "user_tier": "premium",
  "ip_address": "192.168.1.100",
  "is_whitelisted": false,
  "rate_limit_enabled": true
}
```

## Error Handling

### Rate Limit Exceeded Response

When rate limit is exceeded, API returns **HTTP 429** with German error message:

```json
{
  "fehler": "Ratenlimit überschritten",
  "nachricht": "Sie haben zu viele Anfragen gesendet. Bitte versuchen Sie es in 60 Sekunden erneut.",
  "details": {
    "pfad": "/api/v1/ocr/process",
    "wiederholen_nach_sekunden": 60,
    "zeitstempel": "2025-11-26T12:00:00.000Z"
  },
  "hinweis": "Wenn Sie häufiger auf diese API zugreifen müssen, erwägen Sie ein Upgrade auf einen Premium-Account."
}
```

### HTTP Headers

Rate limit responses include standard headers:

```
X-RateLimit-Limit: 100
X-RateLimit-Window: 3600
X-RateLimit-Reset: 1732622400
Retry-After: 60
```

## IP Whitelisting

### Add IP to Whitelist

Whitelist IPs bypass all rate limits. Add to `.env`:

```bash
RATE_LIMIT_WHITELIST=127.0.0.1,::1,10.0.0.100,192.168.1.50
```

### Programmatic Whitelist Management

```python
from app.core.rate_limiting import ip_whitelist

# Add IP
ip_whitelist.add("10.0.0.100")

# Remove IP
ip_whitelist.remove("10.0.0.100")

# Check if whitelisted
is_whitelisted = ip_whitelist.is_whitelisted("10.0.0.100")

# Get all whitelisted IPs
all_ips = ip_whitelist.get_all()
```

## Development Mode

In development mode (`DEBUG=true`), rate limiting is bypassed:

```python
# In .env for development
DEBUG=true
RATE_LIMIT_ENABLED=false  # Optional: disable completely
```

The `DevelopmentRateLimitBypass` middleware automatically skips rate limiting when `DEBUG=true`.

## Excluded Paths

The following paths are **automatically excluded** from rate limiting:

- `/health` - Health check endpoint
- `/docs` - API documentation
- `/redoc` - Alternative API documentation
- `/openapi.json` - OpenAPI schema
- `/metrics` - Prometheus metrics
- `/ws/*` - WebSocket endpoints
- `/websocket/*` - WebSocket endpoints

## User Tier Management

Users can have different tiers affecting their rate limits:

### User Model Requirements

```python
class User:
    id: str
    tier: str  # "free", "premium", or "admin"
    is_admin: bool = False
```

### Tier Detection Logic

1. If `user.is_admin == True` → **Admin tier** (unlimited)
2. If `user.tier == "premium"` → **Premium tier** (100/hour)
3. Default → **Free tier** (10/hour)

## Monitoring

### Prometheus Metrics

Rate limiting metrics are tracked and can be exported to Prometheus:

```python
from app.core.rate_limiting import rate_limit_metrics

stats = rate_limit_metrics.get_stats()
# {
#   "total_requests": 1000,
#   "rate_limited_requests": 50,
#   "whitelisted_requests": 10,
#   "errors": 0,
#   "rate_limit_percentage": 5.0
# }
```

### Logging

All rate limit events are logged with structured logging:

```python
# Rate limit exceeded
logger.warning(
    "rate_limit_exceeded",
    path="/api/v1/ocr/process",
    user_id="user123",
    ip="192.168.1.100",
    retry_after=60
)

# Whitelisted request
logger.debug(
    "rate_limit_whitelisted",
    ip="127.0.0.1",
    path="/api/v1/ocr/process"
)

# Redis unavailable
logger.warning(
    "rate_limit_redis_unavailable",
    path="/api/v1/ocr/process",
    action="allowing_request"
)
```

## Redis Backend

### Connection

Rate limiting uses Redis for distributed storage:

```python
from app.core.rate_limiting import RedisRateLimitStorage

storage = RedisRateLimitStorage("redis://localhost:6380/0")
await storage.connect()

# Check availability
if storage.is_available:
    print("Redis connected")
```

### Graceful Degradation

If Redis is unavailable:

1. Rate limiting **fails open** (allows requests)
2. Warning is logged
3. Application continues functioning
4. Rate limits are not enforced until Redis reconnects

### Key Structure

Redis keys follow this pattern:

```
ratelimit:{user_id|ip}:{endpoint}:{window_start}
```

Examples:
```
ratelimit:user:user123:/api/v1/ocr/process:1732622400
ratelimit:ip:192.168.1.100:/api/v1/auth/login:1732622400
```

### Automatic Expiry

All rate limit keys have TTL matching the rate limit window:
- Login attempts: 900 seconds (15 minutes)
- OCR hourly: 3600 seconds (1 hour)
- General API: 60 seconds (1 minute)

## Testing

### Run Rate Limiting Tests

```bash
# All rate limiting tests
pytest tests/test_rate_limiting.py -v

# Specific test categories
pytest tests/test_rate_limiting.py -k "test_redis" -v
pytest tests/test_rate_limiting.py -k "test_german" -v
pytest tests/test_rate_limiting.py -k "test_middleware" -v

# Integration tests (requires Redis)
pytest tests/test_rate_limiting.py -m integration -v

# Performance tests
pytest tests/test_rate_limiting.py -m performance -v
```

### Manual Testing

```bash
# Test rate limit on login endpoint
for i in {1..10}; do
  curl -X POST http://localhost:8000/api/v1/auth/login \
    -H "Content-Type: application/json" \
    -d '{"username":"test","password":"test"}' \
    -w "\nStatus: %{http_code}\n"
done

# Should see 429 responses after 5 attempts

# Test rate limit info
curl http://localhost:8000/ratelimit/info
```

## Troubleshooting

### Redis Connection Errors

**Problem:** Rate limiting not working, logs show "redis_unavailable"

**Solution:**
1. Check Redis is running: `redis-cli ping`
2. Verify Redis URL in `.env`: `REDIS_URL=redis://localhost:6380/0`
3. Check Redis port: `docker ps | grep redis`
4. Test connection: `redis-cli -h localhost -p 6380 ping`

### Rate Limits Not Enforced

**Problem:** Requests not being rate limited

**Possible causes:**
1. `RATE_LIMIT_ENABLED=false` in `.env` → Set to `true`
2. `DEBUG=true` bypassing limits → Set to `false` for production
3. IP is whitelisted → Check whitelist configuration
4. Redis unavailable → Check Redis connection

### German Error Messages Not Showing

**Problem:** Error messages in English instead of German

**Solution:**
1. Check `rate_limit_exceeded_handler_german` is registered in `main.py`
2. Verify exception handler registration:
   ```python
   app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler_german)
   ```

## Performance Considerations

### Redis Performance

- Redis operations are **atomic** (INCR + EXPIRE)
- Average latency: **< 5ms** per rate limit check
- Redis can handle **100,000+ ops/second** easily
- Use Redis Cluster for high availability

### Middleware Overhead

- Rate limit check overhead: **< 1ms** per request (when Redis is local)
- Excluded paths have **zero overhead** (early return)
- Whitelisted IPs skip Redis check (**< 0.1ms**)

### Optimization Tips

1. **Use Redis locally** or on same network (minimize latency)
2. **Whitelist internal services** to reduce Redis load
3. **Exclude monitoring endpoints** from rate limiting
4. **Use Redis persistence** for rate limit continuity across restarts
5. **Monitor Redis memory** usage (typically < 100MB for rate limiting)

## Security Considerations

### Preventing Bypass

1. **Trust X-Forwarded-For carefully**
   - Only trust when behind trusted proxy
   - Validate IP addresses
   - Consider using rightmost IP in X-Forwarded-For chain

2. **Protect whitelist**
   - Store whitelist in environment variables (not database)
   - Log whitelist changes
   - Regularly audit whitelisted IPs

3. **Rate limit authentication**
   - Use IP-based limits for auth endpoints
   - Longer windows for login attempts (15 minutes)
   - Consider CAPTCHA after multiple failed attempts

### DDoS Protection

Rate limiting provides **basic DDoS protection**:

- IP-based limits prevent single-source attacks
- User-based limits prevent authenticated abuse
- Fail-open prevents rate limiting itself from becoming DoS vector

For comprehensive DDoS protection, combine with:
- Cloudflare or similar CDN
- Network-level rate limiting (nginx, HAProxy)
- Geographic restrictions if applicable

## Migration Guide

### From No Rate Limiting

1. **Install dependencies:**
   ```bash
   pip install slowapi==0.1.9 limits==3.6.0
   ```

2. **Configure Redis:**
   Add Redis URL to `.env`

3. **Enable rate limiting:**
   ```bash
   RATE_LIMIT_ENABLED=true
   ```

4. **Deploy gradually:**
   - Start with high limits to monitor
   - Gradually reduce to target limits
   - Monitor 429 error rates

### From Other Rate Limiting Solutions

If migrating from other rate limiting (e.g., nginx, HAProxy):

1. **Run parallel for monitoring:**
   - Keep existing rate limiting active
   - Enable SlowAPI rate limiting
   - Compare metrics

2. **Adjust limits:**
   - Map existing limits to new tiers
   - Consider per-user vs per-IP differences

3. **Cutover:**
   - Disable old rate limiting
   - Monitor for issues
   - Keep rollback plan ready

## Best Practices

1. **Set realistic limits**
   - Based on actual usage patterns
   - Leave headroom for spikes
   - Monitor 95th percentile usage

2. **Communicate limits**
   - Document in API documentation
   - Include in user dashboard
   - Provide upgrade paths

3. **Monitor continuously**
   - Track rate limit hit rates
   - Alert on unusual patterns
   - Review limits quarterly

4. **Fail gracefully**
   - Never hard-fail on Redis errors
   - Log but allow requests
   - Alert on Redis unavailability

5. **Test thoroughly**
   - Load test with rate limits
   - Test Redis failover
   - Verify German error messages

## References

- **SlowAPI Documentation:** https://slowapi.readthedocs.io/
- **Redis Rate Limiting Patterns:** https://redis.io/docs/reference/patterns/
- **HTTP 429 Status Code:** https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/429
- **Rate Limiting Best Practices:** https://cloud.google.com/architecture/rate-limiting-strategies-techniques

## Support

For issues or questions about rate limiting:

1. Check this documentation
2. Review logs for errors
3. Test Redis connection
4. Verify configuration in `.env`
5. Run test suite: `pytest tests/test_rate_limiting.py -v`

---

**Last Updated:** 2025-11-26
**Version:** 1.0.0
**Maintainer:** Development Team
