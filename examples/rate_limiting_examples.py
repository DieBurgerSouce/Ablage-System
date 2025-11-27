"""
Rate Limiting Usage Examples for Ablage-System OCR API

This file demonstrates how to apply rate limiting to different endpoints.

Created: 2025-11-26
"""

from fastapi import APIRouter, Request, Depends, HTTPException
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.rate_limiting import (
    limiter,
    RateLimitTier,
    get_user_identifier,
    get_ip_identifier,
    user_tier_rate_limit,
    ip_based_rate_limit
)

router = APIRouter()


# ==================== Example 1: Simple Rate Limit ====================

@router.get("/simple")
@limiter.limit("10/minute")
async def simple_rate_limit_example(request: Request):
    """
    Simple rate limit: 10 requests per minute per user/IP.

    This is the simplest way to add rate limiting to an endpoint.
    """
    return {
        "message": "This endpoint has a simple rate limit of 10/minute",
        "info": "Rate limit applies per user (if authenticated) or per IP"
    }


# ==================== Example 2: IP-based Rate Limit ====================

@router.post("/auth/login")
@limiter.limit(RateLimitTier.LOGIN, key_func=get_ip_identifier)
async def login_example(request: Request, username: str, password: str):
    """
    IP-based rate limit: 5 attempts per 15 minutes per IP.

    This is useful for authentication endpoints to prevent brute force attacks.
    The rate limit is tied to the IP address, not the user.
    """
    # Your authentication logic here
    return {
        "message": f"Login attempt for {username}",
        "rate_limit": "5 per 15 minutes per IP"
    }


# ==================== Example 3: User-based Rate Limit ====================

@router.post("/ocr/process")
@limiter.limit(RateLimitTier.OCR_FREE_HOURLY, key_func=get_user_identifier)
async def ocr_process_example(request: Request):
    """
    User-based rate limit: Depends on user tier.

    - Free tier: 10 documents per hour
    - Premium tier: 100 documents per hour
    - Admin tier: 10,000 documents per hour

    Note: The actual tier-based limiting is handled by the middleware.
    This decorator sets the base rate limit.
    """
    # Your OCR processing logic here
    user = getattr(request.state, "user", None)
    tier = user.tier if user else "free"

    return {
        "message": "OCR processing started",
        "user_tier": tier,
        "rate_limit": f"{RateLimitTier.OCR_FREE_HOURLY} (base)"
    }


# ==================== Example 4: Multiple Rate Limits ====================

@router.post("/api/upload")
@limiter.limit("30/minute")  # 30 uploads per minute
@limiter.limit("500/hour")   # 500 uploads per hour
async def multiple_limits_example(request: Request):
    """
    Multiple rate limits: Both must be satisfied.

    This endpoint has two limits:
    - 30 requests per minute
    - 500 requests per hour

    Both limits must be satisfied for the request to proceed.
    """
    return {
        "message": "File upload endpoint",
        "rate_limits": [
            "30 per minute",
            "500 per hour"
        ]
    }


# ==================== Example 5: Exempt from Rate Limiting ====================

@router.get("/health")
async def health_check_example():
    """
    Exempt from rate limiting: No decorator needed.

    Certain paths are automatically excluded from rate limiting:
    - /health
    - /docs
    - /metrics
    - WebSocket endpoints

    No rate limit decorator is needed for these endpoints.
    """
    return {
        "status": "healthy",
        "rate_limit": "none (excluded path)"
    }


# ==================== Example 6: Custom Rate Limit Based on User Tier ====================

@router.post("/ocr/batch")
async def batch_ocr_example(request: Request):
    """
    Tier-based rate limit handled by middleware.

    The middleware automatically applies different limits based on user tier:
    - Free: 5 batch operations per hour
    - Premium: 50 batch operations per hour
    - Admin: 1,000 batch operations per hour

    No decorator needed - middleware handles it automatically.
    """
    user = getattr(request.state, "user", None)

    if user:
        tier = getattr(user, "tier", "free")
    else:
        tier = "free"

    return {
        "message": "Batch OCR processing",
        "user_tier": tier,
        "rate_limit": "Handled by middleware based on tier"
    }


# ==================== Example 7: Checking Rate Limit Budget ====================

@router.get("/ocr/quota")
async def check_quota_example(request: Request):
    """
    Check remaining rate limit quota.

    Useful for showing users how many requests they have remaining.
    """
    from app.core.rate_limiting import check_rate_limit_budget

    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Check OCR quota
    budget = await check_rate_limit_budget(
        user_id=user.id,
        limit_type="ocr"
    )

    return {
        "user_id": user.id,
        "tier": getattr(user, "tier", "free"),
        "quota": budget
    }


# ==================== Example 8: Rate Limit Info Endpoint ====================

@router.get("/ratelimit/myinfo")
async def my_rate_limit_info_example(request: Request):
    """
    Get rate limit information for current request.

    Shows the user their current rate limit status.
    """
    from app.core.rate_limiting import get_rate_limit_info

    info = get_rate_limit_info(request)

    return {
        "rate_limit_info": info,
        "explanation": {
            "user_tier": "Your account tier (free, premium, admin)",
            "is_whitelisted": "Whether your IP bypasses rate limits",
            "rate_limit_enabled": "Whether rate limiting is active"
        }
    }


# ==================== Example 9: Conditional Rate Limiting ====================

@router.post("/api/heavy-operation")
async def conditional_rate_limit_example(request: Request):
    """
    Conditional rate limiting based on request parameters.

    Note: This is handled by middleware based on endpoint path and user tier.
    The middleware automatically applies appropriate limits.
    """
    user = getattr(request.state, "user", None)

    # Check if user is admin (unlimited)
    if user and getattr(user, "is_admin", False):
        rate_limit_info = "Unlimited (admin)"
    elif user and getattr(user, "tier", "free") == "premium":
        rate_limit_info = "20 per minute (premium)"
    else:
        rate_limit_info = "5 per minute (free)"

    return {
        "message": "Heavy operation endpoint",
        "rate_limit": rate_limit_info
    }


# ==================== Example 10: WebSocket (No Rate Limiting) ====================

@router.websocket("/ws/updates")
async def websocket_example():
    """
    WebSocket endpoint - automatically excluded from rate limiting.

    WebSocket connections are excluded from rate limiting by default.
    The middleware detects WebSocket upgrade requests and skips rate limiting.
    """
    # WebSocket logic here
    pass


# ==================== Example 11: Programmatic Whitelist Management ====================

@router.post("/admin/whitelist/add")
async def add_to_whitelist_example(request: Request, ip_address: str):
    """
    Add IP to whitelist (admin only).

    Requires admin authentication.
    """
    from app.core.rate_limiting import ip_whitelist

    # Check if user is admin
    user = getattr(request.state, "user", None)
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    # Add IP to whitelist
    ip_whitelist.add(ip_address)

    return {
        "message": f"IP {ip_address} added to whitelist",
        "all_whitelisted_ips": list(ip_whitelist.get_all())
    }


# ==================== Example 12: Rate Limit Statistics ====================

@router.get("/admin/ratelimit/stats")
async def rate_limit_stats_example(request: Request):
    """
    Get rate limit statistics (admin only).

    Shows overall rate limiting metrics.
    """
    from app.middleware import get_rate_limit_stats

    # Check if user is admin
    user = getattr(request.state, "user", None)
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    stats = get_rate_limit_stats()

    return {
        "rate_limit_statistics": stats,
        "explanation": {
            "total_requests": "Total requests processed",
            "rate_limited_requests": "Requests blocked by rate limiting",
            "whitelisted_requests": "Requests from whitelisted IPs",
            "rate_limit_percentage": "Percentage of requests rate limited"
        }
    }


# ==================== Best Practices Summary ====================

"""
BEST PRACTICES FOR RATE LIMITING:

1. AUTHENTICATION ENDPOINTS
   - Use IP-based rate limiting
   - Lower limits (5-10 attempts)
   - Longer windows (15+ minutes)
   Example: @limiter.limit("5/15minutes", key_func=get_ip_identifier)

2. OCR/PROCESSING ENDPOINTS
   - Use user-based rate limiting
   - Tier-based limits (free < premium < admin)
   - Let middleware handle tier detection
   Example: Middleware automatically applies based on user.tier

3. GENERAL API ENDPOINTS
   - Use moderate limits (60-100/minute)
   - User-based for authenticated, IP-based for public
   Example: @limiter.limit("100/minute")

4. HEAVY OPERATIONS
   - Use stricter limits (10-20/minute)
   - Consider daily limits for expensive operations
   Example: @limiter.limit("10/minute")

5. MONITORING ENDPOINTS
   - Higher limits or exclude entirely
   - Add to EXCLUDED_PATHS in middleware
   Example: No decorator needed if path in EXCLUDED_PATHS

6. WEBSOCKET CONNECTIONS
   - Automatically excluded by middleware
   - No special handling needed
   Example: No decorator needed

7. ADMIN ENDPOINTS
   - Still apply rate limits (high limits)
   - Prevents accidental DoS by admins
   Example: @limiter.limit("1000/minute")

8. ERROR HANDLING
   - Rate limit errors return German messages
   - HTTP 429 status code
   - Include Retry-After header
   Example: Handled automatically by middleware

9. DEVELOPMENT
   - Disable rate limiting with DEBUG=true
   - Or use RATE_LIMIT_ENABLED=false
   Example: Set in .env file

10. MONITORING
    - Track rate limit metrics
    - Alert on high rate limit percentages
    - Review limits quarterly
    Example: Use get_rate_limit_stats() endpoint
"""


# ==================== Common Patterns ====================

# Pattern 1: Public endpoint with IP-based limit
@router.get("/public/data")
@limiter.limit("60/minute", key_func=get_ip_identifier)
async def public_endpoint(request: Request):
    """Public endpoint with IP-based rate limiting."""
    return {"data": "Public data"}


# Pattern 2: Authenticated endpoint with user-based limit
@router.get("/user/data")
@limiter.limit("100/minute", key_func=get_user_identifier)
async def authenticated_endpoint(request: Request):
    """Authenticated endpoint with user-based rate limiting."""
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return {"data": "User data"}


# Pattern 3: Heavy operation with multiple limits
@router.post("/api/analyze")
@limiter.limit("10/minute")  # Short-term protection
@limiter.limit("100/hour")   # Long-term protection
async def heavy_operation(request: Request):
    """Heavy operation with multiple rate limits."""
    return {"result": "Analysis complete"}


# Pattern 4: Tiered endpoint (middleware handles limits)
@router.post("/api/process")
async def tiered_endpoint(request: Request):
    """
    Tiered endpoint where middleware applies limits based on user tier.
    No decorator needed - middleware handles it automatically.
    """
    return {"status": "Processing"}


if __name__ == "__main__":
    print("Rate Limiting Examples for Ablage-System OCR API")
    print("\nSee inline documentation for usage examples.")
    print("\nKey points:")
    print("1. Use @limiter.limit() decorator for custom limits")
    print("2. Use key_func to control IP vs user-based limiting")
    print("3. Middleware handles tier-based limiting automatically")
    print("4. Check RATE_LIMITING.md for full documentation")
