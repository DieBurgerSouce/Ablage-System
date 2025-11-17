ACHING STRATEGY GUIDE - TEIL 1
Complete Caching Strategy for High-Performance Applications

📋 TABLE OF CONTENTS

Introduction
Redis Setup & Configuration
Application-Level Caching


🎯 INTRODUCTION
Why Caching Matters
┌─────────────────────────────────────────────────────────┐
│         CACHING BENEFITS & USE CASES                     │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ⚡ Performance                                          │
│     - 100x faster data access                           │
│     - Reduced database load                             │
│     - Lower API response times                          │
│     - Better user experience                            │
│                                                         │
│  💰 Cost Reduction                                       │
│     - Fewer database queries                            │
│     - Reduced compute resources                         │
│     - Lower cloud costs                                 │
│     - Decreased API calls                               │
│                                                         │
│  📈 Scalability                                          │
│     - Handle more concurrent users                      │
│     - Distribute load efficiently                       │
│     - Reduce backend pressure                           │
│     - Enable horizontal scaling                         │
│                                                         │
│  🎯 Use Cases for OCR Project                            │
│     - OCR results (expensive to compute)                │
│     - Document metadata                                 │
│     - User sessions & permissions                       │
│     - API rate limiting                                 │
│     - Database query results                            │
│     - File processing status                            │
│                                                         │
└─────────────────────────────────────────────────────────┘
Caching Architecture Overview
┌──────────────────────────────────────────────────────────────┐
│              MULTI-LAYER CACHING ARCHITECTURE                 │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  Layer 1: In-Memory Cache (Python LRU)                       │
│  ┌────────────────────────────────────────────────┐         │
│  │ • Fastest access (nanoseconds)                 │         │
│  │ • Function result caching                      │         │
│  │ • Limited size (per process)                   │         │
│  └────────────────────────────────────────────────┘         │
│                         ↓                                    │
│  Layer 2: Redis Cache (Distributed)                          │
│  ┌────────────────────────────────────────────────┐         │
│  │ • Fast access (< 1ms)                          │         │
│  │ • Shared across instances                      │         │
│  │ • Persistent & scalable                        │         │
│  │ • TTL support                                  │         │
│  └────────────────────────────────────────────────┘         │
│                         ↓                                    │
│  Layer 3: Database                                           │
│  ┌────────────────────────────────────────────────┐         │
│  │ • Slowest (10-100ms+)                          │         │
│  │ • Source of truth                              │         │
│  │ • Durable storage                              │         │
│  └────────────────────────────────────────────────┘         │
│                                                              │
└──────────────────────────────────────────────────────────────┘

🔧 REDIS SETUP & CONFIGURATION
1. Redis Docker Setup
yaml# docker-compose.yml

version: '3.9'

services:
  # ============================================
  # REDIS - PRIMARY CACHE
  # ============================================
  
  redis:
    image: redis:7.2-alpine
    container_name: redis
    restart: unless-stopped
    
    # Ports
    ports:
      - "6379:6379"
    
    # Configuration
    command: >
      redis-server
      --appendonly yes
      --requirepass ${REDIS_PASSWORD:-redis_password}
      --maxmemory 512mb
      --maxmemory-policy allkeys-lru
      --save 900 1
      --save 300 10
      --save 60 10000
    
    # Volumes
    volumes:
      - redis_data:/data
      - ./config/redis.conf:/usr/local/etc/redis/redis.conf
    
    # Health Check
    healthcheck:
      test: ["CMD", "redis-cli", "--raw", "incr", "ping"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s
    
    # Resources
    deploy:
      resources:
        limits:
          cpus: '1'
          memory: 512M
    
    # Network
    networks:
      - app_network


  # ============================================
  # REDIS COMMANDER - WEB UI (OPTIONAL)
  # ============================================
  
  redis-commander:
    image: rediscommander/redis-commander:latest
    container_name: redis-commander
    restart: unless-stopped
    
    ports:
      - "8081:8081"
    
    environment:
      - REDIS_HOSTS=local:redis:6379:0:${REDIS_PASSWORD:-redis_password}
    
    depends_on:
      - redis
    
    networks:
      - app_network


  # ============================================
  # REDIS SENTINEL - HIGH AVAILABILITY (OPTIONAL)
  # ============================================
  
  redis-sentinel-1:
    image: redis:7.2-alpine
    container_name: redis-sentinel-1
    restart: unless-stopped
    
    ports:
      - "26379:26379"
    
    command: redis-sentinel /usr/local/etc/redis/sentinel.conf
    
    volumes:
      - ./config/sentinel.conf:/usr/local/etc/redis/sentinel.conf
      - sentinel_data_1:/data
    
    depends_on:
      - redis
    
    networks:
      - app_network


volumes:
  redis_data:
    driver: local
  sentinel_data_1:
    driver: local


networks:
  app_network:
    driver: bridge
2. Redis Configuration Files
ini# config/redis.conf

# ============================================
# REDIS CONFIGURATION
# ============================================
#
# Production-ready Redis configuration
#
# ============================================

# ============================================
# NETWORK
# ============================================

# Bind to all interfaces
bind 0.0.0.0

# Port
port 6379

# TCP backlog
tcp-backlog 511

# Close connection after N seconds of idleness
timeout 300

# TCP keepalive
tcp-keepalive 300


# ============================================
# GENERAL
# ============================================

# Run as daemon
daemonize no

# PID file
pidfile /var/run/redis_6379.pid

# Log level: debug, verbose, notice, warning
loglevel notice

# Log file
logfile ""

# Number of databases
databases 16


# ============================================
# SNAPSHOTTING (PERSISTENCE)
# ============================================

# Save the DB on disk
save 900 1      # After 900 sec if at least 1 key changed
save 300 10     # After 300 sec if at least 10 keys changed
save 60 10000   # After 60 sec if at least 10000 keys changed

# Stop accepting writes if RDB snapshots fail
stop-writes-on-bgsave-error yes

# Compress string objects
rdbcompression yes

# Checksum
rdbchecksum yes

# DB filename
dbfilename dump.rdb

# Working directory
dir /data


# ============================================
# REPLICATION
# ============================================

# Master authentication password
# masterauth <password>

# Read-only replica
replica-read-only yes

# Disable TCP_NODELAY on replica socket
repl-disable-tcp-nodelay no

# Priority for replica promotion
replica-priority 100


# ============================================
# SECURITY
# ============================================

# Require password
requirepass redis_password

# Rename dangerous commands
rename-command FLUSHDB ""
rename-command FLUSHALL ""
rename-command KEYS ""
rename-command CONFIG ""


# ============================================
# MEMORY MANAGEMENT
# ============================================

# Max memory limit
maxmemory 512mb

# Eviction policy
# - noeviction: return errors when memory limit reached
# - allkeys-lru: evict any key, LRU algorithm
# - volatile-lru: evict keys with TTL set, LRU
# - allkeys-random: evict random keys
# - volatile-random: evict random keys with TTL
# - volatile-ttl: evict keys with shortest TTL
maxmemory-policy allkeys-lru

# LRU/LFU sample size
maxmemory-samples 5


# ============================================
# APPEND ONLY FILE (AOF)
# ============================================

# Enable AOF
appendonly yes

# AOF filename
appendfilename "appendonly.aof"

# Fsync policy: always, everysec, no
appendfsync everysec

# Rewrite AOF when it grows by this percentage
auto-aof-rewrite-percentage 100
auto-aof-rewrite-min-size 64mb


# ============================================
# SLOW LOG
# ============================================

# Execution time threshold (microseconds)
slowlog-log-slower-than 10000

# Max number of slow log entries
slowlog-max-len 128


# ============================================
# LATENCY MONITOR
# ============================================

# Latency threshold (milliseconds)
latency-monitor-threshold 100


# ============================================
# EVENT NOTIFICATION
# ============================================

# Keyspace notifications
# K = keyspace events
# E = keyevent events
# g = generic commands (DEL, EXPIRE, etc)
# x = expired events
# e = evicted events
notify-keyspace-events "Ex"


# ============================================
# ADVANCED CONFIG
# ============================================

# Hash max entries
hash-max-ziplist-entries 512
hash-max-ziplist-value 64

# List max size
list-max-ziplist-size -2

# Set max entries
set-max-intset-entries 512

# Sorted set max entries
zset-max-ziplist-entries 128
zset-max-ziplist-value 64

# HyperLogLog sparse representation
hll-sparse-max-bytes 3000

# Active rehashing
activerehashing yes

# Client output buffer limits
client-output-buffer-limit normal 0 0 0
client-output-buffer-limit replica 256mb 64mb 60
client-output-buffer-limit pubsub 32mb 8mb 60

# Frequency of active expiry
hz 10

# Enable active defrag
activedefrag yes
ini# config/sentinel.conf

# ============================================
# REDIS SENTINEL CONFIGURATION
# ============================================
#
# High availability configuration
#
# ============================================

# Port
port 26379

# Working directory
dir /tmp

# Monitor master
# sentinel monitor <master-name> <ip> <port> <quorum>
sentinel monitor mymaster redis 6379 2

# Auth password
sentinel auth-pass mymaster redis_password

# Down after milliseconds
sentinel down-after-milliseconds mymaster 5000

# Parallel syncs
sentinel parallel-syncs mymaster 1

# Failover timeout
sentinel failover-timeout mymaster 10000

# Notification script
# sentinel notification-script mymaster /path/to/script.sh

# Client reconfig script
# sentinel client-reconfig-script mymaster /path/to/script.sh
3. Redis Client Setup (Python)
python# core/cache/redis_client.py

"""
Redis Client Configuration

Provides Redis connection management and utilities
"""

import redis
from redis.sentinel import Sentinel
from redis.connection import ConnectionPool
from typing import Optional, Any, List
from functools import lru_cache
from loguru import logger
import pickle
import json

from config import settings


class RedisClient:
    """
    Redis client wrapper with advanced features
    
    Features:
    - Connection pooling
    - Automatic reconnection
    - Serialization helpers
    - Key namespacing
    - Health checks
    """
    
    def __init__(
        self,
        host: str = None,
        port: int = None,
        db: int = None,
        password: str = None,
        decode_responses: bool = True,
        max_connections: int = 50
    ):
        """
        Initialize Redis client
        
        Args:
            host: Redis host
            port: Redis port
            db: Database number
            password: Auth password
            decode_responses: Decode bytes to strings
            max_connections: Max connection pool size
        """
        
        self.host = host or settings.REDIS_HOST
        self.port = port or settings.REDIS_PORT
        self.db = db or settings.REDIS_DB
        self.password = password or settings.REDIS_PASSWORD
        self.decode_responses = decode_responses
        
        # Connection pool
        self.pool = ConnectionPool(
            host=self.host,
            port=self.port,
            db=self.db,
            password=self.password,
            decode_responses=self.decode_responses,
            max_connections=max_connections,
            socket_timeout=5,
            socket_connect_timeout=5,
            socket_keepalive=True,
            health_check_interval=30
        )
        
        # Redis client
        self._client = redis.Redis(connection_pool=self.pool)
        
        # Test connection
        self._test_connection()
        
        logger.info(f"Redis client initialized: {self.host}:{self.port}/{self.db}")
    
    def _test_connection(self):
        """Test Redis connection"""
        try:
            self._client.ping()
            logger.info("✓ Redis connection successful")
        except redis.ConnectionError as e:
            logger.error(f"✗ Redis connection failed: {e}")
            raise
    
    @property
    def client(self) -> redis.Redis:
        """Get Redis client"""
        return self._client
    
    # ============================================
    # KEY OPERATIONS
    # ============================================
    
    def make_key(self, *parts: str) -> str:
        """
        Create namespaced key
        
        Args:
            *parts: Key parts
        
        Returns:
            Namespaced key
        
        Example:
            make_key('user', '123', 'profile') -> 'ocr:user:123:profile'
        """
        namespace = getattr(settings, 'CACHE_NAMESPACE', 'ocr')
        return f"{namespace}:{':'.join(str(p) for p in parts)}"
    
    def exists(self, key: str) -> bool:
        """Check if key exists"""
        return bool(self._client.exists(key))
    
    def delete(self, *keys: str) -> int:
        """Delete one or more keys"""
        if not keys:
            return 0
        return self._client.delete(*keys)
    
    def expire(self, key: str, seconds: int) -> bool:
        """Set key expiration"""
        return bool(self._client.expire(key, seconds))
    
    def ttl(self, key: str) -> int:
        """Get time to live"""
        return self._client.ttl(key)
    
    def keys(self, pattern: str = "*") -> List[str]:
        """
        Get keys matching pattern
        
        ⚠️ Use with caution in production!
        """
        return self._client.keys(pattern)
    
    # ============================================
    # STRING OPERATIONS
    # ============================================
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get value"""
        value = self._client.get(key)
        return value if value is not None else default
    
    def set(
        self,
        key: str,
        value: Any,
        ex: Optional[int] = None,
        px: Optional[int] = None,
        nx: bool = False,
        xx: bool = False
    ) -> bool:
        """
        Set value
        
        Args:
            key: Key name
            value: Value to set
            ex: Expire time in seconds
            px: Expire time in milliseconds
            nx: Only set if key doesn't exist
            xx: Only set if key exists
        """
        return bool(self._client.set(key, value, ex=ex, px=px, nx=nx, xx=xx))
    
    def mget(self, *keys: str) -> List[Any]:
        """Get multiple values"""
        return self._client.mget(*keys)
    
    def mset(self, mapping: dict) -> bool:
        """Set multiple values"""
        return bool(self._client.mset(mapping))
    
    def incr(self, key: str, amount: int = 1) -> int:
        """Increment value"""
        return self._client.incr(key, amount)
    
    def decr(self, key: str, amount: int = 1) -> int:
        """Decrement value"""
        return self._client.decr(key, amount)
    
    # ============================================
    # JSON OPERATIONS
    # ============================================
    
    def get_json(self, key: str, default: Any = None) -> Any:
        """Get JSON value"""
        value = self.get(key)
        if value is None:
            return default
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            logger.error(f"Failed to decode JSON from key: {key}")
            return default
    
    def set_json(
        self,
        key: str,
        value: Any,
        ex: Optional[int] = None
    ) -> bool:
        """Set JSON value"""
        try:
            json_value = json.dumps(value)
            return self.set(key, json_value, ex=ex)
        except (TypeError, ValueError) as e:
            logger.error(f"Failed to encode JSON for key {key}: {e}")
            return False
    
    # ============================================
    # PICKLE OPERATIONS (For complex objects)
    # ============================================
    
    def get_pickle(self, key: str, default: Any = None) -> Any:
        """Get pickled object"""
        value = self._client.get(key)
        if value is None:
            return default
        try:
            return pickle.loads(value)
        except pickle.PickleError as e:
            logger.error(f"Failed to unpickle key {key}: {e}")
            return default
    
    def set_pickle(
        self,
        key: str,
        value: Any,
        ex: Optional[int] = None
    ) -> bool:
        """Set pickled object"""
        try:
            pickled_value = pickle.dumps(value)
            return bool(self._client.set(key, pickled_value, ex=ex))
        except pickle.PickleError as e:
            logger.error(f"Failed to pickle value for key {key}: {e}")
            return False
    
    # ============================================
    # HASH OPERATIONS
    # ============================================
    
    def hget(self, name: str, key: str) -> Optional[str]:
        """Get hash field"""
        return self._client.hget(name, key)
    
    def hset(
        self,
        name: str,
        key: str,
        value: Any,
        mapping: dict = None
    ) -> int:
        """Set hash field"""
        if mapping:
            return self._client.hset(name, mapping=mapping)
        return self._client.hset(name, key, value)
    
    def hgetall(self, name: str) -> dict:
        """Get all hash fields"""
        return self._client.hgetall(name)
    
    def hdel(self, name: str, *keys: str) -> int:
        """Delete hash fields"""
        return self._client.hdel(name, *keys)
    
    def hincrby(self, name: str, key: str, amount: int = 1) -> int:
        """Increment hash field"""
        return self._client.hincrby(name, key, amount)
    
    # ============================================
    # LIST OPERATIONS
    # ============================================
    
    def lpush(self, key: str, *values: Any) -> int:
        """Push to list (left)"""
        return self._client.lpush(key, *values)
    
    def rpush(self, key: str, *values: Any) -> int:
        """Push to list (right)"""
        return self._client.rpush(key, *values)
    
    def lpop(self, key: str) -> Optional[str]:
        """Pop from list (left)"""
        return self._client.lpop(key)
    
    def rpop(self, key: str) -> Optional[str]:
        """Pop from list (right)"""
        return self._client.rpop(key)
    
    def lrange(self, key: str, start: int, end: int) -> List[str]:
        """Get list range"""
        return self._client.lrange(key, start, end)
    
    def llen(self, key: str) -> int:
        """Get list length"""
        return self._client.llen(key)
    
    # ============================================
    # SET OPERATIONS
    # ============================================
    
    def sadd(self, key: str, *values: Any) -> int:
        """Add to set"""
        return self._client.sadd(key, *values)
    
    def srem(self, key: str, *values: Any) -> int:
        """Remove from set"""
        return self._client.srem(key, *values)
    
    def smembers(self, key: str) -> set:
        """Get set members"""
        return self._client.smembers(key)
    
    def sismember(self, key: str, value: Any) -> bool:
        """Check if member in set"""
        return bool(self._client.sismember(key, value))
    
    # ============================================
    # SORTED SET OPERATIONS
    # ============================================
    
    def zadd(
        self,
        key: str,
        mapping: dict,
        nx: bool = False,
        xx: bool = False
    ) -> int:
        """Add to sorted set"""
        return self._client.zadd(key, mapping, nx=nx, xx=xx)
    
    def zrange(
        self,
        key: str,
        start: int,
        end: int,
        withscores: bool = False
    ) -> List:
        """Get sorted set range"""
        return self._client.zrange(key, start, end, withscores=withscores)
    
    def zrem(self, key: str, *values: Any) -> int:
        """Remove from sorted set"""
        return self._client.zrem(key, *values)
    
    def zscore(self, key: str, value: Any) -> Optional[float]:
        """Get member score"""
        return self._client.zscore(key, value)
    
    # ============================================
    # PIPELINE & TRANSACTION
    # ============================================
    
    def pipeline(self, transaction: bool = True):
        """Create pipeline"""
        return self._client.pipeline(transaction=transaction)
    
    # ============================================
    # UTILITIES
    # ============================================
    
    def flush_db(self):
        """Flush current database (USE WITH CAUTION!)"""
        return self._client.flushdb()
    
    def info(self, section: str = None) -> dict:
        """Get server info"""
        return self._client.info(section=section)
    
    def dbsize(self) -> int:
        """Get database size (number of keys)"""
        return self._client.dbsize()
    
    def ping(self) -> bool:
        """Ping server"""
        return self._client.ping()
    
    def close(self):
        """Close connection"""
        self._client.close()
        logger.info("Redis connection closed")


# ============================================
# SINGLETON INSTANCE
# ============================================

@lru_cache()
def get_redis_client() -> RedisClient:
    """
    Get cached Redis client instance
    
    Returns:
        RedisClient instance
    """
    return RedisClient()


# Convenience
redis_client = get_redis_client()


# ============================================
# SENTINEL SUPPORT (High Availability)
# ============================================

class RedisSentinelClient:
    """Redis Sentinel client for high availability"""
    
    def __init__(
        self,
        sentinels: List[tuple],
        master_name: str = 'mymaster',
        password: str = None,
        db: int = 0
    ):
        """
        Initialize Sentinel client
        
        Args:
            sentinels: List of (host, port) tuples
            master_name: Master name
            password: Auth password
            db: Database number
        """
        
        self.sentinel = Sentinel(
            sentinels,
            socket_timeout=5,
            password=password
        )
        
        self.master_name = master_name
        self.password = password
        self.db = db
        
        # Get master client
        self._master = self.sentinel.master_for(
            master_name,
            socket_timeout=5,
            password=password,
            db=db
        )
        
        # Get replica client (for read-only operations)
        self._replica = self.sentinel.slave_for(
            master_name,
            socket_timeout=5,
            password=password,
            db=db
        )
        
        logger.info(f"Redis Sentinel client initialized: {master_name}")
    
    @property
    def master(self) -> redis.Redis:
        """Get master client (write operations)"""
        return self._master
    
    @property
    def replica(self) -> redis.Redis:
        """Get replica client (read operations)"""
        return self._replica
    
    def discover_master(self) -> tuple:
        """Discover current master"""
        return self.sentinel.discover_master(self.master_name)
    
    def discover_slaves(self) -> List[tuple]:
        """Discover current replicas"""
        return self.sentinel.discover_slaves(self.master_name)


# Example usage
if __name__ == "__main__":
    # Basic usage
    redis = get_redis_client()
    
    # Set/Get
    redis.set("test_key", "test_value", ex=60)
    value = redis.get("test_key")
    print(f"Value: {value}")
    
    # JSON
    redis.set_json("user:123", {"name": "John", "age": 30}, ex=300)
    user = redis.get_json("user:123")
    print(f"User: {user}")
    
    # Hash
    redis.hset("user:123:meta", mapping={
        "login_count": 5,
        "last_login": "2024-01-01"
    })
    meta = redis.hgetall("user:123:meta")
    print(f"Meta: {meta}")
    
    # Pipeline
    pipe = redis.pipeline()
    pipe.set("key1", "value1")
    pipe.set("key2", "value2")
    pipe.execute()
    
    # Info
    info = redis.info("stats")
    print(f"Total commands: {info.get('total_commands_processed')}")

💾 APPLICATION-LEVEL CACHING
1. Cache Manager
python# core/cache/cache_manager.py

"""
Cache Manager

Provides high-level caching interface with decorators
"""

from functools import wraps
from typing import Optional, Callable, Any, Union
import hashlib
import inspect
from datetime import timedelta
from loguru import logger

from core.cache.redis_client import get_redis_client


class CacheManager:
    """
    High-level cache management
    
    Features:
    - Decorator-based caching
    - Automatic key generation
    - TTL management
    - Cache invalidation
    - Statistics tracking
    """
    
    def __init__(self, redis_client=None, prefix: str = "cache"):
        """
        Initialize cache manager
        
        Args:
            redis_client: Redis client instance
            prefix: Key prefix for namespacing
        """
        self.redis = redis_client or get_redis_client()
        self.prefix = prefix
    
    def _make_key(self, func: Callable, args: tuple, kwargs: dict) -> str:
        """
        Generate cache key from function and arguments
        
        Args:
            func: Function
            args: Positional arguments
            kwargs: Keyword arguments
        
        Returns:
            Cache key
        """
        # Function identifier
        func_name = f"{func.__module__}.{func.__qualname__}"
        
        # Serialize arguments
        args_str = str(args) + str(sorted(kwargs.items()))
        
        # Hash for consistent key length
        args_hash = hashlib.md5(args_str.encode()).hexdigest()
        
        return self.redis.make_key(self.prefix, func_name, args_hash)
    
    def cache(
        self,
        ttl: Union[int, timedelta] = 300,
        key_prefix: str = None,
        unless: Callable = None,
        typed: bool = False
    ):
        """
        Cache decorator
        
        Args:
            ttl: Time to live (seconds or timedelta)
            key_prefix: Custom key prefix
            unless: Function that returns True to skip caching
            typed: Consider argument types in key generation
        
        Example:
            @cache_manager.cache(ttl=60)
            def get_user(user_id: int):
                return db.query(User).filter_by(id=user_id).first()
        """
        
        # Convert timedelta to seconds
        if isinstance(ttl, timedelta):
            ttl = int(ttl.total_seconds())
        
        def decorator(func: Callable) -> Callable:
            @wraps(func)
            def wrapper(*args, **kwargs):
                # Check unless condition
                if unless and unless():
                    return func(*args, **kwargs)
                
                # Generate cache key
                cache_key = self._make_key(func, args, kwargs)
                if key_prefix:
                    cache_key = f"{cache_key}:{key_prefix}"
                
                # Try to get from cache
                cached_value = self.redis.get_pickle(cache_key)
                
                if cached_value is not None:
                    logger.debug(f"Cache HIT: {cache_key}")
                    return cached_value
                
                # Cache miss - execute function
                logger.debug(f"Cache MISS: {cache_key}")
                result = func(*args, **kwargs)
                
                # Store in cache
                if result is not None:
                    self.redis.set_pickle(cache_key, result, ex=ttl)
                
                return result
            
            # Add cache control methods
            wrapper._cache_key_func = lambda *args, **kwargs: self._make_key(func, args, kwargs)
            wrapper._cache_manager = self
            
            return wrapper
        
        return decorator
    
    def cache_json(
        self,
        ttl: Union[int, timedelta] = 300,
        key_prefix: str = None
    ):
        """
        Cache decorator for JSON-serializable results
        
        More efficient than pickle for simple data structures
        """
        
        if isinstance(ttl, timedelta):
            ttl = int(ttl.total_seconds())
        
        def decorator(func: Callable) -> Callable:
            @wraps(func)
            def wrapper(*args, **kwargs):
                # Generate cache key
                cache_key = self._make_key(func, args, kwargs)
                if key_prefix:
                    cache_key = f"{cache_key}:{key_prefix}"
                
                # Try to get from cache
                cached_value = self.redis.get_json(cache_key)
                
                if cached_value is not None:
                    logger.debug(f"Cache HIT: {cache_key}")
                    return cached_value
                
                # Cache miss
                logger.debug(f"Cache MISS: {cache_key}")
                result = func(*args, **kwargs)
                
                # Store in cache
                if result is not None:
                    self.redis.set_json(cache_key, result, ex=ttl)
                
                return result
            
            return wrapper
        
        return decorator
    
    def invalidate(self, func: Callable, *args, **kwargs):
        """
        Invalidate cache for specific function call
        
        Args:
            func: Function to invalidate
            *args: Function arguments
            **kwargs: Function keyword arguments
        """
        cache_key = self._make_key(func, args, kwargs)
        deleted = self.redis.delete(cache_key)
        
        if deleted:
            logger.info(f"Cache invalidated: {cache_key}")
        
        return deleted
    
    def invalidate_pattern(self, pattern: str):
        """
        Invalidate all keys matching pattern
        
        ⚠️ Use with caution in production!
        
        Args:
            pattern: Key pattern (e.g., "cache:user:*")
        """
        keys = self.redis.keys(pattern)
        if keys:
            deleted = self.redis.delete(*keys)
            logger.info(f"Invalidated {deleted} keys matching: {pattern}")
            return deleted
        return 0
    
    def clear_all(self):
        """
        Clear all cache entries
        
        ⚠️ USE WITH EXTREME CAUTION!
        """
        pattern = self.redis.make_key(self.prefix, "*")
        return self.invalidate_pattern(pattern)
    
    def get_stats(self) -> dict:
        """
        Get cache statistics
        
        Returns:
            Statistics dict
        """
        info = self.redis.info("stats")
        
        return {
            "hits": info.get("keyspace_hits", 0),
            "misses": info.get("keyspace_misses", 0),
            "hit_rate": self._calculate_hit_rate(info),
            "total_keys": self.redis.dbsize(),
            "memory_used": info.get("used_memory_human"),
            "evicted_keys": info.get("evicted_keys", 0)
        }
    
    def _calculate_hit_rate(self, info: dict) -> float:
        """Calculate cache hit rate"""
        hits = info.get("keyspace_hits", 0)
        misses = info.get("keyspace_misses", 0)
        
        total = hits + misses
        if total == 0:
            return 0.0
        
        return (hits / total) * 100


# ============================================
# GLOBAL CACHE MANAGER
# ============================================

cache_manager = CacheManager()


# ============================================
# CONVENIENCE DECORATORS
# ============================================

def cache(ttl: Union[int, timedelta] = 300, **kwargs):
    """
    Convenience cache decorator
    
    Example:
        @cache(ttl=60)
        def get_user(user_id: int):
            return db.query(User).get(user_id)
    """
    return cache_manager.cache(ttl=ttl, **kwargs)


def cache_json(ttl: Union[int, timedelta] = 300, **kwargs):
    """
    Convenience JSON cache decorator
    
    Example:
        @cache_json(ttl=60)
        def get_user_data(user_id: int):
            return {"id": user_id, "name": "John"}
    """
    return cache_manager.cache_json(ttl=ttl, **kwargs)


# Example usage
if __name__ == "__main__":
    from time import sleep
    
    # Example 1: Simple caching
    @cache(ttl=10)
    def expensive_computation(n: int):
        """Simulate expensive operation"""
        print(f"Computing for n={n}...")
        sleep(2)
        return n ** 2
    
    # First call - cache miss
    result = expensive_computation(5)  # Takes 2 seconds
    print(f"Result: {result}")
    
    # Second call - cache hit
    result = expensive_computation(5)  # Instant!
    print(f"Result: {result}")
    
    # Example 2: JSON caching
    @cache_json(ttl=60)
    def get_api_data(endpoint: str):
        """Simulate API call"""
        print(f"Fetching {endpoint}...")
        return {
            "endpoint": endpoint,
            "data": [1, 2, 3]
        }
    
    data = get_api_data("/users")
    print(f"Data: {data}")
    
    # Example 3: Cache invalidation
    cache_manager.invalidate(expensive_computation, 5)
    
    # Example 4: Statistics
    stats = cache_manager.get_stats()
    print(f"Cache stats: {stats}")
2. Memoization (In-Memory Cache)
python# core/cache/memoize.py

"""
Memoization - In-Memory Caching

Fast, process-local caching using functools.lru_cache
"""

from functools import lru_cache, wraps
from typing import Callable, Optional
import time
from threading import RLock


class TTLCache:
    """
    LRU Cache with TTL (Time To Live)
    
    Combines LRU eviction with time-based expiration
    """
    
    def __init__(self, maxsize: int = 128, ttl: int = 300):
        """
        Initialize TTL cache
        
        Args:
            maxsize: Maximum number of cached items
            ttl: Time to live in seconds
        """
        self.maxsize = maxsize
        self.ttl = ttl
        self.cache = {}
        self.timestamps = {}
        self.lock = RLock()
    
    def __call__(self, func: Callable) -> Callable:
        """Decorator to cache function results"""
        
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Create cache key
            key = (args, tuple(sorted(kwargs.items())))
            
            with self.lock:
                # Check if in cache and not expired
                if key in self.cache:
                    timestamp = self.timestamps[key]
                    if time.time() - timestamp < self.ttl:
                        return self.cache[key]
                    else:
                        # Expired - remove
                        del self.cache[key]
                        del self.timestamps[key]
                
                # Execute function
                result = func(*args, **kwargs)
                
                # Store in cache
                self.cache[key] = result
                self.timestamps[key] = time.time()
                
                # Evict oldest if max size reached
                if len(self.cache) > self.maxsize:
                    oldest_key = min(self.timestamps, key=self.timestamps.get)
                    del self.cache[oldest_key]
                    del self.timestamps[oldest_key]
                
                return result
        
        # Add cache control methods
        def clear():
            """Clear cache"""
            with wrapper._lock:
                wrapper._cache.clear()
                wrapper._timestamps.clear()
        
        wrapper._cache = self.cache
        wrapper._timestamps = self.timestamps
        wrapper._lock = self.lock
        wrapper.clear = clear
        
        return wrapper


def memoize(maxsize: int = 128):
    """
    Simple memoization decorator using LRU cache
    
    Args:
        maxsize: Maximum cache size
    
    Example:
        @memoize(maxsize=256)
        def fibonacci(n: int) -> int:
            if n < 2:
                return n
            return fibonacci(n-1) + fibonacci(n-2)
    """
    return lru_cache(maxsize=maxsize)


def ttl_cache(ttl: int = 300, maxsize: int = 128):
    """
    Memoization with TTL
    
    Args:
        ttl: Time to live in seconds
        maxsize: Maximum cache size
    
    Example:
        @ttl_cache(ttl=60, maxsize=100)
        def get_current_price(symbol: str) -> float:
            # Fetch from API
            return price
    """
    return TTLCache(maxsize=maxsize, ttl=ttl)


# Example usage
if __name__ == "__main__":
    # Example 1: Simple memoization
    @memoize(maxsize=100)
    def fibonacci(n: int) -> int:
        """Calculate Fibonacci number"""
        if n < 2:
            return n
        return fibonacci(n-1) + fibonacci(n-2)
    
    print(f"fib(10) = {fibonacci(10)}")
    print(f"Cache info: {fibonacci.cache_info()}")
    
    # Example 2: TTL cache
    @ttl_cache(ttl=5, maxsize=50)
    def get_timestamp():
        """Get current timestamp"""
        return time.time()
    
    t1 = get_timestamp()
    time.sleep(1)
    t2 = get_timestamp()  # From cache
    print(f"Same timestamp: {t1 == t2}")
    
    time.sleep(5)
    t3 = get_timestamp()  # Cache expired
    print(f"Different timestamp: {t1 != t3}")


CACHING STRATEGY GUIDE - TEIL 2
Query Result Caching, Cache Invalidation & Cache Warming

📋 TABLE OF CONTENTS (TEIL 2)

Query Result Caching
Cache Invalidation
Cache Warming


🗄️ QUERY RESULT CACHING
1. SQLAlchemy Query Caching
python# core/cache/query_cache.py

"""
SQLAlchemy Query Result Caching

Features:
- Automatic query result caching
- Cache invalidation on model changes
- Relationship caching
- Query key generation
"""

from sqlalchemy import event
from sqlalchemy.orm import Session, Query
from sqlalchemy.orm.query import Query as QueryType
from typing import Any, Optional, List, Callable
import hashlib
import json
from datetime import timedelta
from loguru import logger

from core.cache.redis_client import get_redis_client
from database import Base


class QueryCache:
    """
    SQLAlchemy query result cache
    
    Automatically caches query results and invalidates
    when underlying data changes
    """
    
    def __init__(
        self,
        redis_client=None,
        default_ttl: int = 300,
        prefix: str = "query"
    ):
        """
        Initialize query cache
        
        Args:
            redis_client: Redis client instance
            default_ttl: Default TTL in seconds
            prefix: Cache key prefix
        """
        self.redis = redis_client or get_redis_client()
        self.default_ttl = default_ttl
        self.prefix = prefix
        
        # Track which models have invalidation listeners
        self._listeners_registered = set()
    
    def _generate_cache_key(
        self,
        query: Query,
        query_params: dict = None
    ) -> str:
        """
        Generate cache key from query
        
        Args:
            query: SQLAlchemy query
            query_params: Additional query parameters
        
        Returns:
            Cache key
        """
        # Get query statement
        statement = str(query.statement.compile(
            compile_kwargs={"literal_binds": True}
        ))
        
        # Add parameters if provided
        if query_params:
            statement += json.dumps(query_params, sort_keys=True)
        
        # Hash for consistent key length
        query_hash = hashlib.md5(statement.encode()).hexdigest()
        
        # Extract table name from query
        table_name = "unknown"
        if hasattr(query, "column_descriptions"):
            if query.column_descriptions:
                entity = query.column_descriptions[0].get("entity")
                if entity:
                    table_name = entity.__tablename__
        
        return self.redis.make_key(self.prefix, table_name, query_hash)
    
    def get_or_execute(
        self,
        query: Query,
        ttl: Optional[int] = None,
        force_refresh: bool = False
    ) -> List[Any]:
        """
        Get query results from cache or execute
        
        Args:
            query: SQLAlchemy query
            ttl: Cache TTL (uses default if None)
            force_refresh: Skip cache and refresh
        
        Returns:
            Query results
        """
        ttl = ttl or self.default_ttl
        
        # Generate cache key
        cache_key = self._generate_cache_key(query)
        
        # Check cache unless force refresh
        if not force_refresh:
            cached_result = self.redis.get_pickle(cache_key)
            if cached_result is not None:
                logger.debug(f"Query cache HIT: {cache_key}")
                return cached_result
        
        # Cache miss or force refresh - execute query
        logger.debug(f"Query cache MISS: {cache_key}")
        result = query.all()
        
        # Store in cache
        self.redis.set_pickle(cache_key, result, ex=ttl)
        
        return result
    
    def invalidate_model(self, model_class):
        """
        Invalidate all cached queries for a model
        
        Args:
            model_class: SQLAlchemy model class
        """
        table_name = model_class.__tablename__
        pattern = self.redis.make_key(self.prefix, table_name, "*")
        
        invalidated = self.redis.delete(*self.redis.keys(pattern))
        
        if invalidated:
            logger.info(
                f"Invalidated {invalidated} cached queries for {table_name}"
            )
        
        return invalidated
    
    def register_invalidation_listener(self, model_class):
        """
        Register automatic cache invalidation on model changes
        
        Args:
            model_class: SQLAlchemy model class
        """
        # Avoid duplicate listeners
        if model_class in self._listeners_registered:
            return
        
        # Invalidate on insert/update/delete
        @event.listens_for(model_class, 'after_insert')
        @event.listens_for(model_class, 'after_update')
        @event.listens_for(model_class, 'after_delete')
        def invalidate_cache(mapper, connection, target):
            """Invalidate cache when model changes"""
            self.invalidate_model(model_class)
        
        self._listeners_registered.add(model_class)
        
        logger.info(
            f"Registered cache invalidation listener for {model_class.__name__}"
        )
    
    def cached_query(
        self,
        ttl: Optional[int] = None,
        auto_invalidate: bool = True
    ):
        """
        Decorator for caching query results
        
        Args:
            ttl: Cache TTL
            auto_invalidate: Register auto-invalidation
        
        Example:
            @query_cache.cached_query(ttl=60)
            def get_active_users(db: Session):
                return db.query(User).filter(User.is_active == True)
        """
        def decorator(func: Callable) -> Callable:
            def wrapper(*args, **kwargs):
                # Execute function to get query
                query = func(*args, **kwargs)
                
                # Register auto-invalidation if enabled
                if auto_invalidate and hasattr(query, 'column_descriptions'):
                    if query.column_descriptions:
                        entity = query.column_descriptions[0].get("entity")
                        if entity:
                            self.register_invalidation_listener(entity)
                
                # Get from cache or execute
                return self.get_or_execute(query, ttl=ttl)
            
            return wrapper
        
        return decorator


# ============================================
# GLOBAL QUERY CACHE
# ============================================

query_cache = QueryCache()


# ============================================
# CACHED QUERY MIXIN
# ============================================

class CachedQueryMixin:
    """
    Mixin to add caching capabilities to models
    
    Example:
        class User(Base, CachedQueryMixin):
            __tablename__ = 'users'
            ...
        
        # Use cached queries
        users = User.get_cached(db, ttl=60)
    """
    
    @classmethod
    def get_cached(
        cls,
        db: Session,
        ttl: int = 300,
        **filters
    ) -> List[Any]:
        """
        Get all records with caching
        
        Args:
            db: Database session
            ttl: Cache TTL
            **filters: Filter conditions
        
        Returns:
            List of records
        """
        query = db.query(cls)
        
        # Apply filters
        for key, value in filters.items():
            if hasattr(cls, key):
                query = query.filter(getattr(cls, key) == value)
        
        return query_cache.get_or_execute(query, ttl=ttl)
    
    @classmethod
    def get_by_id_cached(
        cls,
        db: Session,
        id: int,
        ttl: int = 300
    ) -> Optional[Any]:
        """
        Get record by ID with caching
        
        Args:
            db: Database session
            id: Record ID
            ttl: Cache TTL
        
        Returns:
            Record or None
        """
        cache_key = f"model:{cls.__tablename__}:id:{id}"
        
        # Check cache
        cached = query_cache.redis.get_pickle(cache_key)
        if cached is not None:
            return cached
        
        # Query database
        result = db.query(cls).filter(cls.id == id).first()
        
        # Store in cache
        if result:
            query_cache.redis.set_pickle(cache_key, result, ex=ttl)
        
        return result
    
    @classmethod
    def invalidate_cache(cls):
        """Invalidate all cached queries for this model"""
        return query_cache.invalidate_model(cls)


# ============================================
# REPOSITORY PATTERN WITH CACHING
# ============================================

class CachedRepository:
    """
    Base repository with built-in caching
    
    Example:
        class UserRepository(CachedRepository):
            model = User
        
        user_repo = UserRepository(db)
        users = user_repo.get_all(ttl=60)
    """
    
    model = None  # Override in subclass
    
    def __init__(self, db: Session, cache_ttl: int = 300):
        """
        Initialize repository
        
        Args:
            db: Database session
            cache_ttl: Default cache TTL
        """
        if self.model is None:
            raise ValueError("model must be set in subclass")
        
        self.db = db
        self.cache_ttl = cache_ttl
        self.cache = query_cache
        
        # Register auto-invalidation
        self.cache.register_invalidation_listener(self.model)
    
    def get_all(self, ttl: Optional[int] = None) -> List[Any]:
        """
        Get all records
        
        Args:
            ttl: Cache TTL
        
        Returns:
            List of records
        """
        query = self.db.query(self.model)
        return self.cache.get_or_execute(query, ttl=ttl or self.cache_ttl)
    
    def get_by_id(self, id: int, ttl: Optional[int] = None) -> Optional[Any]:
        """
        Get record by ID
        
        Args:
            id: Record ID
            ttl: Cache TTL
        
        Returns:
            Record or None
        """
        cache_key = self.cache.redis.make_key(
            "model",
            self.model.__tablename__,
            "id",
            str(id)
        )
        
        # Check cache
        cached = self.cache.redis.get_pickle(cache_key)
        if cached is not None:
            return cached
        
        # Query database
        result = self.db.query(self.model).filter(
            self.model.id == id
        ).first()
        
        # Store in cache
        if result:
            self.cache.redis.set_pickle(
                cache_key,
                result,
                ex=ttl or self.cache_ttl
            )
        
        return result
    
    def get_by_filter(
        self,
        ttl: Optional[int] = None,
        **filters
    ) -> List[Any]:
        """
        Get records by filters
        
        Args:
            ttl: Cache TTL
            **filters: Filter conditions
        
        Returns:
            List of records
        """
        query = self.db.query(self.model)
        
        for key, value in filters.items():
            if hasattr(self.model, key):
                query = query.filter(getattr(self.model, key) == value)
        
        return self.cache.get_or_execute(query, ttl=ttl or self.cache_ttl)
    
    def create(self, **data) -> Any:
        """
        Create new record
        
        Args:
            **data: Record data
        
        Returns:
            Created record
        """
        record = self.model(**data)
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        
        # Cache is automatically invalidated by listener
        
        return record
    
    def update(self, id: int, **data) -> Optional[Any]:
        """
        Update record
        
        Args:
            id: Record ID
            **data: Updated data
        
        Returns:
            Updated record or None
        """
        record = self.get_by_id(id)
        if not record:
            return None
        
        for key, value in data.items():
            if hasattr(record, key):
                setattr(record, key, value)
        
        self.db.commit()
        self.db.refresh(record)
        
        # Cache is automatically invalidated by listener
        
        return record
    
    def delete(self, id: int) -> bool:
        """
        Delete record
        
        Args:
            id: Record ID
        
        Returns:
            True if deleted
        """
        record = self.get_by_id(id)
        if not record:
            return False
        
        self.db.delete(record)
        self.db.commit()
        
        # Cache is automatically invalidated by listener
        
        return True


# Example usage
if __name__ == "__main__":
    from database import SessionLocal
    from models.user import User
    from models.file import File
    
    db = SessionLocal()
    
    # Example 1: Direct query caching
    query = db.query(User).filter(User.is_active == True)
    users = query_cache.get_or_execute(query, ttl=60)
    print(f"Active users: {len(users)}")
    
    # Example 2: Using cached query decorator
    @query_cache.cached_query(ttl=60)
    def get_recent_files(db: Session):
        return db.query(File).order_by(File.created_at.desc()).limit(10)
    
    files = get_recent_files(db)
    print(f"Recent files: {len(files)}")
    
    # Example 3: Using repository pattern
    class UserRepository(CachedRepository):
        model = User
    
    user_repo = UserRepository(db, cache_ttl=300)
    all_users = user_repo.get_all()
    print(f"All users: {len(all_users)}")
    
    # Get by ID
    user = user_repo.get_by_id(1)
    print(f"User: {user.email if user else 'Not found'}")
    
    # Get by filter
    active_users = user_repo.get_by_filter(is_active=True)
    print(f"Active users: {len(active_users)}")
2. Dogpile Cache Integration
python# core/cache/dogpile_cache.py

"""
Dogpile Cache Integration

Advanced caching with dogpile.cache library

Features:
- Multiple backends (Redis, Memcached, File, Memory)
- Region-based caching
- Lock-based refresh
- Distributed locking
"""

from dogpile.cache import make_region
from dogpile.cache.api import NoValue
from typing import Callable, Any, Optional
from datetime import timedelta
import json

from config import settings


# ============================================
# CACHE REGIONS
# ============================================

# Default region (Redis backend)
default_region = make_region().configure(
    'dogpile.cache.redis',
    expiration_time=300,
    arguments={
        'host': settings.REDIS_HOST,
        'port': settings.REDIS_PORT,
        'db': settings.REDIS_DB,
        'password': settings.REDIS_PASSWORD,
        'distributed_lock': True,
        'redis_expiration_time': 300
    }
)

# Short-term cache (1 minute)
short_term_region = make_region().configure(
    'dogpile.cache.redis',
    expiration_time=60,
    arguments={
        'host': settings.REDIS_HOST,
        'port': settings.REDIS_PORT,
        'db': settings.REDIS_DB,
        'password': settings.REDIS_PASSWORD
    }
)

# Long-term cache (1 hour)
long_term_region = make_region().configure(
    'dogpile.cache.redis',
    expiration_time=3600,
    arguments={
        'host': settings.REDIS_HOST,
        'port': settings.REDIS_PORT,
        'db': settings.REDIS_DB,
        'password': settings.REDIS_PASSWORD
    }
)

# In-memory cache (for process-local data)
memory_region = make_region().configure(
    'dogpile.cache.memory',
    expiration_time=300
)


# ============================================
# CACHE DECORATORS
# ============================================

def cache_on_arguments(
    region=None,
    expiration_time: Optional[int] = None,
    namespace: Optional[str] = None,
    should_cache_fn: Optional[Callable] = None
):
    """
    Cache function results based on arguments
    
    Args:
        region: Cache region to use
        expiration_time: Override default expiration
        namespace: Cache key namespace
        should_cache_fn: Function to determine if result should be cached
    
    Example:
        @cache_on_arguments(namespace="user")
        def get_user(user_id: int):
            return db.query(User).get(user_id)
    """
    region = region or default_region
    
    return region.cache_on_arguments(
        expiration_time=expiration_time,
        namespace=namespace,
        should_cache_fn=should_cache_fn
    )


def cache_multi_on_arguments(
    region=None,
    expiration_time: Optional[int] = None,
    namespace: Optional[str] = None
):
    """
    Cache multiple results with single backend call
    
    Args:
        region: Cache region to use
        expiration_time: Override default expiration
        namespace: Cache key namespace
    
    Example:
        @cache_multi_on_arguments(namespace="user")
        def get_users(*user_ids):
            return {
                uid: db.query(User).get(uid)
                for uid in user_ids
            }
    """
    region = region or default_region
    
    return region.cache_multi_on_arguments(
        expiration_time=expiration_time,
        namespace=namespace
    )


# ============================================
# CACHE HELPERS
# ============================================

class CacheHelper:
    """Helper class for common caching patterns"""
    
    @staticmethod
    def get_or_create(
        key: str,
        creator_fn: Callable,
        expiration_time: int = 300,
        region=None
    ) -> Any:
        """
        Get from cache or create if missing
        
        Args:
            key: Cache key
            creator_fn: Function to create value if not cached
            expiration_time: Cache TTL
            region: Cache region
        
        Returns:
            Cached or created value
        """
        region = region or default_region
        
        # Try to get from cache
        value = region.get(key, expiration_time=expiration_time)
        
        if value is NoValue:
            # Not in cache - create
            value = creator_fn()
            region.set(key, value)
        
        return value
    
    @staticmethod
    def invalidate_key(key: str, region=None):
        """
        Invalidate specific cache key
        
        Args:
            key: Cache key
            region: Cache region
        """
        region = region or default_region
        region.delete(key)
    
    @staticmethod
    def invalidate_namespace(namespace: str, region=None):
        """
        Invalidate all keys in namespace
        
        Args:
            namespace: Namespace to invalidate
            region: Cache region
        """
        region = region or default_region
        
        # This depends on the backend supporting it
        if hasattr(region.backend, 'delete_multi'):
            # Get all keys with namespace prefix
            pattern = f"{namespace}:*"
            # Implementation varies by backend
            pass


# Example usage
if __name__ == "__main__":
    from time import sleep
    
    # Example 1: Simple caching
    @cache_on_arguments(namespace="fib")
    def fibonacci(n: int) -> int:
        """Calculate Fibonacci number"""
        if n < 2:
            return n
        return fibonacci(n-1) + fibonacci(n-2)
    
    result = fibonacci(10)
    print(f"fib(10) = {result}")
    
    # Example 2: Multi-argument caching
    @cache_multi_on_arguments(namespace="batch_user")
    def get_users_batch(*user_ids):
        """Get multiple users"""
        print(f"Fetching users: {user_ids}")
        return {
            uid: f"User {uid}"
            for uid in user_ids
        }
    
    users = get_users_batch(1, 2, 3)
    print(f"Users: {users}")
    
    # Second call uses cache
    users = get_users_batch(1, 2, 3)
    print(f"Users (cached): {users}")
    
    # Example 3: Region-specific caching
    @cache_on_arguments(region=short_term_region, namespace="temp")
    def get_temp_data():
        """Get temporary data"""
        print("Fetching temp data...")
        return {"timestamp": "now"}
    
    data = get_temp_data()
    print(f"Temp data: {data}")
3. OCR-Specific Query Caching
python# services/ocr_cache_service.py

"""
OCR-Specific Caching Service

Caches OCR results, document metadata, and processing status
"""

from typing import Optional, List, Dict, Any
from datetime import timedelta
from sqlalchemy.orm import Session

from core.cache.query_cache import CachedRepository
from core.cache.cache_manager import cache, cache_json
from models.document import Document
from models.file import File


class OCRCacheService:
    """
    OCR result caching service
    
    Features:
    - Cache OCR results (expensive to compute)
    - Cache document metadata
    - Cache processing status
    - Automatic invalidation
    """
    
    def __init__(self, db: Session):
        self.db = db
    
    @cache(ttl=timedelta(hours=24))
    def get_ocr_result(self, document_id: int) -> Optional[Dict[str, Any]]:
        """
        Get OCR result with long TTL
        
        OCR results are expensive to compute and rarely change
        
        Args:
            document_id: Document ID
        
        Returns:
            OCR result dict
        """
        document = self.db.query(Document).filter(
            Document.id == document_id,
            Document.status == 'completed'
        ).first()
        
        if not document:
            return None
        
        return {
            'id': document.id,
            'uuid': document.uuid,
            'text': document.ocr_text,
            'confidence': document.confidence,
            'language': document.language,
            'page_count': document.page_count,
            'metadata': document.metadata
        }
    
    @cache_json(ttl=300)
    def get_document_metadata(self, document_uuid: str) -> Optional[Dict]:
        """
        Get document metadata
        
        Args:
            document_uuid: Document UUID
        
        Returns:
            Metadata dict
        """
        document = self.db.query(Document).filter(
            Document.uuid == document_uuid
        ).first()
        
        if not document:
            return None
        
        return {
            'uuid': document.uuid,
            'title': document.title,
            'language': document.language,
            'status': document.status,
            'document_type': document.document_type,
            'page_count': document.page_count,
            'created_at': document.created_at.isoformat(),
            'processed_at': document.processed_at.isoformat() if document.processed_at else None
        }
    
    @cache_json(ttl=60)
    def get_processing_status(self, document_uuid: str) -> Optional[str]:
        """
        Get document processing status with short TTL
        
        Args:
            document_uuid: Document UUID
        
        Returns:
            Status string
        """
        document = self.db.query(Document).filter(
            Document.uuid == document_uuid
        ).first()
        
        return document.status if document else None
    
    @cache_json(ttl=300)
    def get_user_documents_summary(self, user_id: int) -> Dict[str, Any]:
        """
        Get user's document summary
        
        Args:
            user_id: User ID
        
        Returns:
            Summary dict
        """
        from sqlalchemy import func
        
        summary = self.db.query(
            func.count(Document.id).label('total'),
            func.count(
                func.nullif(Document.status != 'completed', True)
            ).label('completed'),
            func.count(
                func.nullif(Document.status != 'processing', True)
            ).label('processing'),
            func.count(
                func.nullif(Document.status != 'failed', True)
            ).label('failed')
        ).filter(
            Document.user_id == user_id
        ).first()
        
        return {
            'total': summary.total or 0,
            'completed': summary.completed or 0,
            'processing': summary.processing or 0,
            'failed': summary.failed or 0
        }
    
    @cache(ttl=timedelta(hours=1))
    def get_popular_document_types(
        self,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get popular document types
        
        Args:
            limit: Number of results
        
        Returns:
            List of document types with counts
        """
        from sqlalchemy import func
        
        results = self.db.query(
            Document.document_type,
            func.count(Document.id).label('count')
        ).filter(
            Document.document_type.isnot(None)
        ).group_by(
            Document.document_type
        ).order_by(
            func.count(Document.id).desc()
        ).limit(limit).all()
        
        return [
            {
                'document_type': doc_type,
                'count': count
            }
            for doc_type, count in results
        ]
    
    def invalidate_document_cache(self, document_id: int):
        """
        Invalidate all cache for a specific document
        
        Args:
            document_id: Document ID
        """
        from core.cache.cache_manager import cache_manager
        
        # Get document
        document = self.db.query(Document).get(document_id)
        if not document:
            return
        
        # Invalidate specific caches
        cache_manager.invalidate(
            self.get_ocr_result,
            document_id
        )
        cache_manager.invalidate(
            self.get_document_metadata,
            document.uuid
        )
        cache_manager.invalidate(
            self.get_processing_status,
            document.uuid
        )
        cache_manager.invalidate(
            self.get_user_documents_summary,
            document.user_id
        )


# Example: Document Repository with Caching
class DocumentRepository(CachedRepository):
    """Document repository with caching"""
    
    model = Document
    
    def get_by_uuid(self, uuid: str, ttl: int = 300) -> Optional[Document]:
        """
        Get document by UUID
        
        Args:
            uuid: Document UUID
            ttl: Cache TTL
        
        Returns:
            Document or None
        """
        cache_key = self.cache.redis.make_key(
            "document",
            "uuid",
            uuid
        )
        
        # Check cache
        cached = self.cache.redis.get_pickle(cache_key)
        if cached is not None:
            return cached
        
        # Query database
        result = self.db.query(Document).filter(
            Document.uuid == uuid
        ).first()
        
        # Store in cache
        if result:
            self.cache.redis.set_pickle(cache_key, result, ex=ttl)
        
        return result
    
    def get_user_documents(
        self,
        user_id: int,
        status: Optional[str] = None,
        ttl: int = 60
    ) -> List[Document]:
        """
        Get user's documents
        
        Args:
            user_id: User ID
            status: Optional status filter
            ttl: Cache TTL
        
        Returns:
            List of documents
        """
        query = self.db.query(Document).filter(
            Document.user_id == user_id
        )
        
        if status:
            query = query.filter(Document.status == status)
        
        query = query.order_by(Document.created_at.desc())
        
        return self.cache.get_or_execute(query, ttl=ttl)

🔄 CACHE INVALIDATION
1. Invalidation Strategies
python# core/cache/invalidation.py

"""
Cache Invalidation Strategies

"There are only two hard things in Computer Science:
cache invalidation and naming things." - Phil Karlton

Features:
- Time-based invalidation (TTL)
- Event-based invalidation
- Tag-based invalidation
- Dependency-based invalidation
"""

from typing import List, Set, Optional, Callable, Any
from datetime import datetime, timedelta
from enum import Enum
import fnmatch
from loguru import logger

from core.cache.redis_client import get_redis_client


class InvalidationStrategy(Enum):
    """Cache invalidation strategies"""
    TTL = "ttl"  # Time To Live
    EVENT = "event"  # On specific events
    TAG = "tag"  # Tag-based grouping
    DEPENDENCY = "dependency"  # Based on dependencies


class CacheInvalidator:
    """
    Cache invalidation manager
    
    Implements various invalidation strategies
    """
    
    def __init__(self, redis_client=None):
        """Initialize invalidator"""
        self.redis = redis_client or get_redis_client()
        
        # Track tags and dependencies
        self._tag_index = {}  # {tag: set(keys)}
        self._dependency_index = {}  # {key: set(dependent_keys)}
    
    # ============================================
    # TIME-BASED INVALIDATION (TTL)
    # ============================================
    
    def set_with_ttl(
        self,
        key: str,
        value: Any,
        ttl: int
    ):
        """
        Set value with TTL
        
        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds
        """
        self.redis.set_pickle(key, value, ex=ttl)
        logger.debug(f"Set {key} with TTL {ttl}s")
    
    def extend_ttl(self, key: str, additional_seconds: int):
        """
        Extend TTL of existing key
        
        Args:
            key: Cache key
            additional_seconds: Seconds to add
        """
        current_ttl = self.redis.ttl(key)
        if current_ttl > 0:
            new_ttl = current_ttl + additional_seconds
            self.redis.expire(key, new_ttl)
            logger.debug(f"Extended TTL for {key} by {additional_seconds}s")
    
    # ============================================
    # EVENT-BASED INVALIDATION
    # ============================================
    
    def invalidate_on_event(
        self,
        event_name: str,
        keys: List[str]
    ):
        """
        Register keys to invalidate on specific event
        
        Args:
            event_name: Event name
            keys: Keys to invalidate
        """
        # Store event mapping in Redis
        event_key = self.redis.make_key("events", event_name)
        for key in keys:
            self.redis.sadd(event_key, key)
        
        logger.info(f"Registered {len(keys)} keys for event: {event_name}")
    
    def trigger_event(self, event_name: str):
        """
        Trigger event and invalidate associated keys
        
        Args:
            event_name: Event name
        """
        event_key = self.redis.make_key("events", event_name)
        
        # Get all keys for this event
        keys = self.redis.smembers(event_key)
        
        if keys:
            # Invalidate all keys
            deleted = self.redis.delete(*keys)
            logger.info(
                f"Event '{event_name}' triggered, invalidated {deleted} keys"
            )
            
            # Clear event mapping
            self.redis.delete(event_key)
        
        return len(keys)
    
    # ============================================
    # TAG-BASED INVALIDATION
    # ============================================
    
    def add_tags(self, key: str, *tags: str):
        """
        Add tags to a cache key
        
        Args:
            key: Cache key
            *tags: Tags to associate
        """
        # Store tags in Redis set
        tag_key = self.redis.make_key("key_tags", key)
        self.redis.sadd(tag_key, *tags)
        
        # Store key in each tag's set
        for tag in tags:
            tag_index_key = self.redis.make_key("tag_index", tag)
            self.redis.sadd(tag_index_key, key)
        
        logger.debug(f"Added tags {tags} to {key}")
    
    def get_tags(self, key: str) -> Set[str]:
        """
        Get tags for a key
        
        Args:
            key: Cache key
        
        Returns:
            Set of tags
        """
        tag_key = self.redis.make_key("key_tags", key)
        return self.redis.smembers(tag_key)
    
    def invalidate_by_tag(self, *tags: str) -> int:
        """
        Invalidate all keys with specific tags
        
        Args:
            *tags: Tags to invalidate
        
        Returns:
            Number of keys invalidated
        """
        keys_to_delete = set()
        
        for tag in tags:
            tag_index_key = self.redis.make_key("tag_index", tag)
            keys = self.redis.smembers(tag_index_key)
            keys_to_delete.update(keys)
            
            # Clean up tag index
            self.redis.delete(tag_index_key)
        
        # Delete all keys and their tag mappings
        if keys_to_delete:
            # Delete actual cache keys
            deleted = self.redis.delete(*keys_to_delete)
            
            # Delete tag mappings
            tag_keys = [
                self.redis.make_key("key_tags", key)
                for key in keys_to_delete
            ]
            self.redis.delete(*tag_keys)
            
            logger.info(
                f"Invalidated {deleted} keys with tags: {tags}"
            )
            
            return deleted
        
        return 0
    
    # ============================================
    # DEPENDENCY-BASED INVALIDATION
    # ============================================
    
    def add_dependency(self, key: str, depends_on: str):
        """
        Add dependency relationship
        
        When depends_on is invalidated, key is also invalidated
        
        Args:
            key: Dependent key
            depends_on: Key this depends on
        """
        dep_key = self.redis.make_key("dependencies", depends_on)
        self.redis.sadd(dep_key, key)
        
        logger.debug(f"{key} depends on {depends_on}")
    
    def invalidate_with_dependencies(self, key: str) -> int:
        """
        Invalidate key and all dependent keys
        
        Args:
            key: Key to invalidate
        
        Returns:
            Number of keys invalidated
        """
        # Get all dependent keys
        dep_key = self.redis.make_key("dependencies", key)
        dependent_keys = self.redis.smembers(dep_key)
        
        # Recursively invalidate dependents
        total_deleted = 0
        for dep in dependent_keys:
            total_deleted += self.invalidate_with_dependencies(dep)
        
        # Delete the key itself
        deleted = self.redis.delete(key)
        total_deleted += deleted
        
        # Clean up dependency mapping
        self.redis.delete(dep_key)
        
        if total_deleted > 0:
            logger.info(
                f"Invalidated {key} and {total_deleted-1} dependent keys"
            )
        
        return total_deleted
    
    # ============================================
    # PATTERN-BASED INVALIDATION
    # ============================================
    
    def invalidate_pattern(self, pattern: str) -> int:
        """
        Invalidate keys matching pattern
        
        ⚠️ Use carefully in production!
        
        Args:
            pattern: Key pattern (e.g., "user:*:profile")
        
        Returns:
            Number of keys invalidated
        """
        keys = self.redis.keys(pattern)
        
        if keys:
            deleted = self.redis.delete(*keys)
            logger.warning(
                f"Pattern invalidation: deleted {deleted} keys matching '{pattern}'"
            )
            return deleted
        
        return 0
    
    # ============================================
    # CONDITIONAL INVALIDATION
    # ============================================
    
    def invalidate_if(
        self,
        condition: Callable[[str, Any], bool],
        pattern: str = "*"
    ) -> int:
        """
        Invalidate keys based on condition
        
        Args:
            condition: Function(key, value) -> bool
            pattern: Key pattern to check
        
        Returns:
            Number of keys invalidated
        """
        keys = self.redis.keys(pattern)
        keys_to_delete = []
        
        for key in keys:
            value = self.redis.get_pickle(key)
            if condition(key, value):
                keys_to_delete.append(key)
        
        if keys_to_delete:
            deleted = self.redis.delete(*keys_to_delete)
            logger.info(
                f"Conditional invalidation: deleted {deleted} keys"
            )
            return deleted
        
        return 0
    
    # ============================================
    # SCHEDULED INVALIDATION
    # ============================================
    
    def schedule_invalidation(
        self,
        key: str,
        invalidate_at: datetime
    ):
        """
        Schedule key invalidation at specific time
        
        Args:
            key: Cache key
            invalidate_at: When to invalidate
        """
        # Calculate seconds until invalidation
        now = datetime.now()
        seconds = (invalidate_at - now).total_seconds()
        
        if seconds > 0:
            self.redis.expire(key, int(seconds))
            logger.info(
                f"Scheduled {key} for invalidation at {invalidate_at}"
            )


# ============================================
# GLOBAL INVALIDATOR
# ============================================

cache_invalidator = CacheInvalidator()


# ============================================
# CONVENIENCE FUNCTIONS
# ============================================

def invalidate_user_cache(user_id: int):
    """Invalidate all cache for a user"""
    pattern = f"*:user:{user_id}:*"
    return cache_invalidator.invalidate_pattern(pattern)


def invalidate_model_cache(model_name: str):
    """Invalidate all cache for a model"""
    pattern = f"*:{model_name}:*"
    return cache_invalidator.invalidate_pattern(pattern)


# Example usage
if __name__ == "__main__":
    from time import sleep
    
    redis = get_redis_client()
    invalidator = CacheInvalidator(redis)
    
    # Example 1: Tag-based invalidation
    redis.set("user:1:profile", "Profile 1")
    redis.set("user:1:settings", "Settings 1")
    redis.set("user:2:profile", "Profile 2")
    
    invalidator.add_tags("user:1:profile", "user:1", "profile")
    invalidator.add_tags("user:1:settings", "user:1", "settings")
    invalidator.add_tags("user:2:profile", "user:2", "profile")
    
    # Invalidate all user:1 data
    invalidator.invalidate_by_tag("user:1")
    
    # Example 2: Event-based invalidation
    invalidator.invalidate_on_event(
        "user_logout",
        ["session:abc123", "permissions:user:1"]
    )
    
    # Trigger event
    invalidator.trigger_event("user_logout")
    
    # Example 3: Dependency-based
    redis.set("user:1:data", "User data")
    redis.set("user:1:cached_report", "Report")
    
    invalidator.add_dependency(
        "user:1:cached_report",
        depends_on="user:1:data"
    )
    
    # Invalidate with dependencies
    invalidator.invalidate_with_dependencies("user:1:data")
2. Automatic Invalidation Hooks
python# core/cache/auto_invalidation.py

"""
Automatic Cache Invalidation

Hooks into database events to automatically invalidate cache
"""

from sqlalchemy import event
from sqlalchemy.orm import Session
from typing import Type, List
from loguru import logger

from database import Base
from core.cache.invalidation import cache_invalidator


class AutoInvalidation:
    """
    Automatic cache invalidation on model changes
    
    Registers SQLAlchemy event listeners to invalidate cache
    when models are created, updated, or deleted
    """
    
    def __init__(self):
        self._registered_models = set()
    
    def register_model(
        self,
        model_class: Type[Base],
        invalidation_strategy: str = "tag"
    ):
        """
        Register model for auto-invalidation
        
        Args:
            model_class: SQLAlchemy model
            invalidation_strategy: Strategy to use
        """
        if model_class in self._registered_models:
            return
        
        table_name = model_class.__tablename__
        
        # Register listeners
        @event.listens_for(model_class, 'after_insert')
        def after_insert(mapper, connection, target):
            """Invalidate cache after insert"""
            self._invalidate_model(table_name, target.id, "insert")
        
        @event.listens_for(model_class, 'after_update')
        def after_update(mapper, connection, target):
            """Invalidate cache after update"""
            self._invalidate_model(table_name, target.id, "update")
        
        @event.listens_for(model_class, 'after_delete')
        def after_delete(mapper, connection, target):
            """Invalidate cache after delete"""
            self._invalidate_model(table_name, target.id, "delete")
        
        self._registered_models.add(model_class)
        
        logger.info(
            f"Registered auto-invalidation for {model_class.__name__}"
        )
    
    def _invalidate_model(
        self,
        table_name: str,
        record_id: int,
        operation: str
    ):
        """
        Invalidate cache for model
        
        Args:
            table_name: Database table name
            record_id: Record ID
            operation: Operation type (insert/update/delete)
        """
        # Invalidate by tag
        tags = [
            table_name,
            f"{table_name}:{record_id}",
            f"{table_name}:*"
        ]
        
        invalidated = cache_invalidator.invalidate_by_tag(*tags)
        
        logger.debug(
            f"Auto-invalidation: {operation} on {table_name}:{record_id}, "
            f"invalidated {invalidated} keys"
        )


# Global instance
auto_invalidation = AutoInvalidation()


# Register common models
def setup_auto_invalidation():
    """Setup automatic invalidation for all models"""
    from models.user import User
    from models.file import File
    from models.document import Document
    
    auto_invalidation.register_model(User)
    auto_invalidation.register_model(File)
    auto_invalidation.register_model(Document)
    
    logger.info("✓ Auto-invalidation configured")

🔥 CACHE WARMING
1. Cache Warming Service
python# core/cache/warming.py

"""
Cache Warming

Proactively load frequently accessed data into cache
"""

from typing import List, Callable, Optional, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from celery import shared_task
from loguru import logger

from core.cache.redis_client import get_redis_client
from core.cache.cache_manager import cache_manager
from database import SessionLocal


class CacheWarmer:
    """
    Cache warming service
    
    Preloads frequently accessed data into cache
    to improve response times
    """
    
    def __init__(self, redis_client=None):
        """Initialize cache warmer"""
        self.redis = redis_client or get_redis_client()
        self._warming_tasks = []
    
    def register_warming_task(
        self,
        name: str,
        task_fn: Callable,
        schedule: str = "hourly",
        priority: int = 5
    ):
        """
        Register cache warming task
        
        Args:
            name: Task name
            task_fn: Function to execute
            schedule: Schedule (hourly, daily, weekly)
            priority: Task priority (1-10)
        """
        self._warming_tasks.append({
            'name': name,
            'task_fn': task_fn,
            'schedule': schedule,
            'priority': priority
        })
        
        logger.info(f"Registered warming task: {name}")
    
    def warm_cache(self, task_name: Optional[str] = None):
        """
        Execute cache warming
        
        Args:
            task_name: Specific task to run (or all if None)
        """
        tasks_to_run = self._warming_tasks
        
        if task_name:
            tasks_to_run = [
                t for t in tasks_to_run
                if t['name'] == task_name
            ]
        
        # Sort by priority
        tasks_to_run = sorted(
            tasks_to_run,
            key=lambda t: t['priority'],
            reverse=True
        )
        
        logger.info(f"Starting cache warming: {len(tasks_to_run)} tasks")
        
        results = []
        for task in tasks_to_run:
            try:
                start = datetime.now()
                
                result = task['task_fn']()
                
                duration = (datetime.now() - start).total_seconds()
                
                results.append({
                    'name': task['name'],
                    'success': True,
                    'duration': duration,
                    'result': result
                })
                
                logger.info(
                    f"✓ Warmed {task['name']} in {duration:.2f}s"
                )
                
            except Exception as e:
                logger.error(f"✗ Warming failed for {task['name']}: {e}")
                results.append({
                    'name': task['name'],
                    'success': False,
                    'error': str(e)
                })
        
        return results
    
    def warm_queries(
        self,
        queries: List[tuple],
        db: Session,
        ttl: int = 3600
    ):
        """
        Warm cache with specific queries
        
        Args:
            queries: List of (name, query) tuples
            db: Database session
            ttl: Cache TTL
        """
        from core.cache.query_cache import query_cache
        
        for name, query in queries:
            try:
                results = query_cache.get_or_execute(
                    query,
                    ttl=ttl,
                    force_refresh=True
                )
                logger.info(f"Warmed query '{name}': {len(results)} results")
            except Exception as e:
                logger.error(f"Failed to warm query '{name}': {e}")


# ============================================
# GLOBAL WARMER
# ============================================

cache_warmer = CacheWarmer()


# ============================================
# OCR-SPECIFIC WARMING TASKS
# ============================================

def warm_popular_documents():
    """Warm cache with popular documents"""
    db = SessionLocal()
    
    try:
        from models.document import Document
        from sqlalchemy import func
        
        # Get most accessed documents (last 7 days)
        popular_docs = db.query(
            Document.id,
            Document.uuid
        ).filter(
            Document.accessed_at >= datetime.now() - timedelta(days=7)
        ).order_by(
            Document.access_count.desc()
        ).limit(100).all()
        
        # Warm OCR results for popular documents
        from services.ocr_cache_service import OCRCacheService
        ocr_cache = OCRCacheService(db)
        
        warmed = 0
        for doc_id, doc_uuid in popular_docs:
            ocr_cache.get_ocr_result(doc_id)
            ocr_cache.get_document_metadata(doc_uuid)
            warmed += 1
        
        logger.info(f"Warmed {warmed} popular documents")
        return {'warmed': warmed}
        
    finally:
        db.close()


def warm_user_summaries():
    """Warm cache with active user summaries"""
    db = SessionLocal()
    
    try:
        from models.user import User
        
        # Get active users (logged in last 24 hours)
        active_users = db.query(User.id).filter(
            User.last_login >= datetime.now() - timedelta(days=1)
        ).all()
        
        # Warm summaries
        from services.ocr_cache_service import OCRCacheService
        ocr_cache = OCRCacheService(db)
        
        warmed = 0
        for (user_id,) in active_users:
            ocr_cache.get_user_documents_summary(user_id)
            warmed += 1
        
        logger.info(f"Warmed {warmed} user summaries")
        return {'warmed': warmed}
        
    finally:
        db.close()


def warm_static_data():
    """Warm cache with static/reference data"""
    db = SessionLocal()
    
    try:
        from services.ocr_cache_service import OCRCacheService
        ocr_cache = OCRCacheService(db)
        
        # Popular document types
        ocr_cache.get_popular_document_types()
        
        # Other static data...
        
        logger.info("Warmed static data")
        return {'status': 'success'}
        
    finally:
        db.close()


# Register warming tasks
cache_warmer.register_warming_task(
    "popular_documents",
    warm_popular_documents,
    schedule="hourly",
    priority=10
)

cache_warmer.register_warming_task(
    "user_summaries",
    warm_user_summaries,
    schedule="hourly",
    priority=8
)

cache_warmer.register_warming_task(
    "static_data",
    warm_static_data,
    schedule="daily",
    priority=5
)


# ============================================
# CELERY TASKS
# ============================================

@shared_task(name='warm_cache_hourly')
def warm_cache_hourly_task():
    """Hourly cache warming task"""
    logger.info("Starting hourly cache warming")
    
    results = cache_warmer.warm_cache()
    
    successful = sum(1 for r in results if r['success'])
    logger.info(
        f"Hourly warming complete: {successful}/{len(results)} successful"
    )
    
    return results


@shared_task(name='warm_cache_daily')
def warm_cache_daily_task():
    """Daily cache warming task"""
    logger.info("Starting daily cache warming")
    
    # Warm all tasks
    results = cache_warmer.warm_cache()
    
    successful = sum(1 for r in results if r['success'])
    logger.info(
        f"Daily warming complete: {successful}/{len(results)} successful"
    )
    
    return results
2. Predictive Cache Warming
python# core/cache/predictive_warming.py

"""
Predictive Cache Warming

Uses access patterns to predict and preload data
"""

from typing import List, Dict, Any
from datetime import datetime, timedelta
from collections import defaultdict, Counter
from sqlalchemy.orm import Session
from sqlalchemy import func
from loguru import logger

from core.cache.redis_client import get_redis_client
from database import SessionLocal


class PredictiveWarmer:
    """
    Predictive cache warming based on access patterns
    
    Analyzes usage patterns to predict which data
    will be accessed and preloads it
    """
    
    def __init__(self, redis_client=None):
        """Initialize predictive warmer"""
        self.redis = redis_client or get_redis_client()
    
    def track_access(
        self,
        resource_type: str,
        resource_id: str,
        user_id: Optional[int] = None
    ):
        """
        Track resource access for pattern analysis
        
        Args:
            resource_type: Type of resource (document, user, etc.)
            resource_id: Resource ID
            user_id: Optional user ID
        """
        # Store access in sorted set with timestamp as score
        key = self.redis.make_key(
            "access_log",
            resource_type,
            resource_id
        )
        
        timestamp = datetime.now().timestamp()
        self.redis.zadd(key, {str(timestamp): timestamp})
        
        # Track user-specific access patterns
        if user_id:
            user_key = self.redis.make_key(
                "user_access",
                str(user_id),
                resource_type
            )
            self.redis.zincrby(user_key, 1, resource_id)
    
    def get_trending_resources(
        self,
        resource_type: str,
        hours: int = 24,
        limit: int = 50
    ) -> List[str]:
        """
        Get trending resources based on recent access
        
        Args:
            resource_type: Resource type
            hours: Hours to look back
            limit: Max results
        
        Returns:
            List of resource IDs
        """
        # Get all access keys for resource type
        pattern = self.redis.make_key("access_log", resource_type, "*")
        keys = self.redis.keys(pattern)
        
        # Count accesses in time window
        cutoff = (datetime.now() - timedelta(hours=hours)).timestamp()
        access_counts = Counter()
        
        for key in keys:
            # Extract resource ID from key
            resource_id = key.split(":")[-1]
            
            # Count recent accesses
            count = self.redis.zcount(key, cutoff, '+inf')
            if count > 0:
                access_counts[resource_id] = count
        
        # Return top resources
        return [
            resource_id
            for resource_id, count in access_counts.most_common(limit)
        ]
    
    def predict_user_needs(
        self,
        user_id: int,
        resource_type: str,
        limit: int = 20
    ) -> List[str]:
        """
        Predict what user will access next
        
        Args:
            user_id: User ID
            resource_type: Resource type
            limit: Max predictions
        
        Returns:
            List of predicted resource IDs
        """
        user_key = self.redis.make_key(
            "user_access",
            str(user_id),
            resource_type
        )
        
        # Get user's most accessed resources
        resources = self.redis.zrange(
            user_key,
            0,
            limit - 1,
            desc=True,
            withscores=False
        )
        
        return list(resources)
    
    def warm_predicted(
        self,
        resource_type: str,
        warming_fn: Callable
    ):
        """
        Warm cache with predicted resources
        
        Args:
            resource_type: Resource type
            warming_fn: Function to warm cache
        """
        # Get trending resources
        trending = self.get_trending_resources(resource_type)
        
        logger.info(
            f"Warming {len(trending)} trending {resource_type}s"
        )
        
        warmed = 0
        for resource_id in trending:
            try:
                warming_fn(resource_id)
                warmed += 1
            except Exception as e:
                logger.error(
                    f"Failed to warm {resource_type}:{resource_id}: {e}"
                )
        
        logger.info(f"Warmed {warmed}/{len(trending)} resources")
        
        return warmed


# Global instance
predictive_warmer = PredictiveWarmer()

CACHING STRATEGY GUIDE - TEIL 3 (FINAL)
Cache Monitoring, Distributed Caching, Patterns & Best Practices

📋 TABLE OF CONTENTS (TEIL 3)

Cache Monitoring
Distributed Caching
Cache Patterns
Best Practices & Troubleshooting


📊 CACHE MONITORING
1. Cache Metrics Collector
python# core/cache/metrics.py

"""
Cache Metrics Collection & Monitoring

Features:
- Hit/Miss rate tracking
- Latency monitoring
- Memory usage tracking
- Eviction monitoring
- Custom metrics
"""

from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
import time
from functools import wraps
from collections import defaultdict
from loguru import logger

from core.cache.redis_client import get_redis_client


@dataclass
class CacheMetrics:
    """Cache metrics data class"""
    
    # Hit/Miss metrics
    hits: int = 0
    misses: int = 0
    hit_rate: float = 0.0
    
    # Latency metrics (milliseconds)
    avg_latency: float = 0.0
    p50_latency: float = 0.0
    p95_latency: float = 0.0
    p99_latency: float = 0.0
    
    # Memory metrics
    memory_used: str = "0B"
    memory_peak: str = "0B"
    memory_fragmentation_ratio: float = 0.0
    
    # Key metrics
    total_keys: int = 0
    expired_keys: int = 0
    evicted_keys: int = 0
    
    # Connection metrics
    connected_clients: int = 0
    total_connections: int = 0
    
    # Performance metrics
    ops_per_sec: int = 0
    network_kb_in: float = 0.0
    network_kb_out: float = 0.0
    
    # Timestamp
    timestamp: str = ""
    
    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return asdict(self)


class CacheMetricsCollector:
    """
    Collect and track cache metrics
    
    Features:
    - Real-time metrics collection
    - Historical metrics storage
    - Aggregation and analysis
    - Alert triggering
    """
    
    def __init__(self, redis_client=None):
        """Initialize metrics collector"""
        self.redis = redis_client or get_redis_client()
        
        # Local metrics tracking
        self._operation_latencies = defaultdict(list)
        self._operation_counts = defaultdict(int)
        
    # ============================================
    # METRICS COLLECTION
    # ============================================
    
    def collect_metrics(self) -> CacheMetrics:
        """
        Collect current cache metrics
        
        Returns:
            CacheMetrics instance
        """
        info = self.redis.info()
        stats = self.redis.info('stats')
        memory = self.redis.info('memory')
        clients = self.redis.info('clients')
        
        # Calculate hit rate
        hits = stats.get('keyspace_hits', 0)
        misses = stats.get('keyspace_misses', 0)
        total = hits + misses
        hit_rate = (hits / total * 100) if total > 0 else 0.0
        
        metrics = CacheMetrics(
            # Hit/Miss
            hits=hits,
            misses=misses,
            hit_rate=hit_rate,
            
            # Memory
            memory_used=memory.get('used_memory_human', '0B'),
            memory_peak=memory.get('used_memory_peak_human', '0B'),
            memory_fragmentation_ratio=memory.get('mem_fragmentation_ratio', 0.0),
            
            # Keys
            total_keys=self.redis.dbsize(),
            expired_keys=stats.get('expired_keys', 0),
            evicted_keys=stats.get('evicted_keys', 0),
            
            # Connections
            connected_clients=clients.get('connected_clients', 0),
            total_connections=stats.get('total_connections_received', 0),
            
            # Performance
            ops_per_sec=stats.get('instantaneous_ops_per_sec', 0),
            network_kb_in=stats.get('total_net_input_bytes', 0) / 1024,
            network_kb_out=stats.get('total_net_output_bytes', 0) / 1024,
            
            # Timestamp
            timestamp=datetime.now().isoformat()
        )
        
        return metrics
    
    def track_operation(
        self,
        operation: str,
        latency_ms: float,
        success: bool = True
    ):
        """
        Track cache operation
        
        Args:
            operation: Operation name (get, set, delete, etc.)
            latency_ms: Operation latency in milliseconds
            success: Whether operation succeeded
        """
        # Store in local tracking
        self._operation_latencies[operation].append(latency_ms)
        self._operation_counts[operation] += 1
        
        # Keep only last 1000 measurements
        if len(self._operation_latencies[operation]) > 1000:
            self._operation_latencies[operation].pop(0)
        
        # Store in Redis for historical tracking
        key = self.redis.make_key('metrics', 'operations', operation)
        
        self.redis.lpush(
            key,
            f"{datetime.now().timestamp()}:{latency_ms}:{int(success)}"
        )
        
        # Keep only last 10000 entries
        self.redis.ltrim(key, 0, 9999)
    
    def get_operation_stats(self, operation: str) -> Dict[str, float]:
        """
        Get statistics for specific operation
        
        Args:
            operation: Operation name
        
        Returns:
            Stats dictionary
        """
        latencies = self._operation_latencies.get(operation, [])
        
        if not latencies:
            return {
                'count': 0,
                'avg': 0.0,
                'min': 0.0,
                'max': 0.0,
                'p50': 0.0,
                'p95': 0.0,
                'p99': 0.0
            }
        
        sorted_latencies = sorted(latencies)
        count = len(sorted_latencies)
        
        return {
            'count': count,
            'avg': sum(sorted_latencies) / count,
            'min': sorted_latencies[0],
            'max': sorted_latencies[-1],
            'p50': sorted_latencies[int(count * 0.5)],
            'p95': sorted_latencies[int(count * 0.95)],
            'p99': sorted_latencies[int(count * 0.99)]
        }
    
    # ============================================
    # MONITORING DECORATOR
    # ============================================
    
    def monitor(self, operation: str = None):
        """
        Decorator to monitor cache operations
        
        Args:
            operation: Operation name (auto-detected if None)
        
        Example:
            @metrics_collector.monitor('get_user')
            def get_user(user_id):
                return cache.get(f'user:{user_id}')
        """
        def decorator(func):
            op_name = operation or func.__name__
            
            @wraps(func)
            def wrapper(*args, **kwargs):
                start = time.time()
                success = True
                
                try:
                    result = func(*args, **kwargs)
                    return result
                    
                except Exception as e:
                    success = False
                    raise
                    
                finally:
                    latency_ms = (time.time() - start) * 1000
                    self.track_operation(op_name, latency_ms, success)
            
            return wrapper
        
        return decorator
    
    # ============================================
    # HISTORICAL METRICS
    # ============================================
    
    def store_snapshot(self, metrics: CacheMetrics):
        """
        Store metrics snapshot for historical analysis
        
        Args:
            metrics: Metrics to store
        """
        key = self.redis.make_key('metrics', 'snapshots')
        
        # Store as JSON with timestamp
        self.redis.zadd(
            key,
            {metrics.timestamp: datetime.fromisoformat(metrics.timestamp).timestamp()}
        )
        
        # Store detailed metrics
        detail_key = self.redis.make_key('metrics', 'detail', metrics.timestamp)
        self.redis.set_json(detail_key, metrics.to_dict(), ex=86400 * 7)  # 7 days
    
    def get_historical_metrics(
        self,
        hours: int = 24
    ) -> List[CacheMetrics]:
        """
        Get historical metrics
        
        Args:
            hours: Hours to look back
        
        Returns:
            List of metrics snapshots
        """
        cutoff = (datetime.now() - timedelta(hours=hours)).timestamp()
        
        key = self.redis.make_key('metrics', 'snapshots')
        
        # Get timestamps in range
        timestamps = self.redis.zrangebyscore(
            key,
            cutoff,
            '+inf',
            withscores=False
        )
        
        # Load detailed metrics
        metrics_list = []
        for ts in timestamps:
            detail_key = self.redis.make_key('metrics', 'detail', ts)
            data = self.redis.get_json(detail_key)
            if data:
                metrics_list.append(CacheMetrics(**data))
        
        return metrics_list
    
    # ============================================
    # ALERTING
    # ============================================
    
    def check_alerts(self, metrics: CacheMetrics) -> List[str]:
        """
        Check metrics for alert conditions
        
        Args:
            metrics: Current metrics
        
        Returns:
            List of alert messages
        """
        alerts = []
        
        # Low hit rate
        if metrics.hit_rate < 50.0:
            alerts.append(
                f"⚠️ Low cache hit rate: {metrics.hit_rate:.1f}%"
            )
        
        # High eviction rate
        if metrics.evicted_keys > 1000:
            alerts.append(
                f"⚠️ High eviction rate: {metrics.evicted_keys} keys"
            )
        
        # High memory fragmentation
        if metrics.memory_fragmentation_ratio > 1.5:
            alerts.append(
                f"⚠️ High memory fragmentation: {metrics.memory_fragmentation_ratio:.2f}"
            )
        
        # Many connected clients
        if metrics.connected_clients > 100:
            alerts.append(
                f"⚠️ High client count: {metrics.connected_clients}"
            )
        
        return alerts


# ============================================
# GLOBAL METRICS COLLECTOR
# ============================================

metrics_collector = CacheMetricsCollector()


# ============================================
# PROMETHEUS METRICS EXPORTER
# ============================================

class PrometheusExporter:
    """
    Export cache metrics to Prometheus
    
    Provides metrics endpoint for Prometheus scraping
    """
    
    def __init__(self, metrics_collector: CacheMetricsCollector):
        """Initialize exporter"""
        self.collector = metrics_collector
    
    def export_metrics(self) -> str:
        """
        Export metrics in Prometheus format
        
        Returns:
            Prometheus-formatted metrics
        """
        metrics = self.collector.collect_metrics()
        
        lines = [
            "# HELP cache_hits_total Total number of cache hits",
            "# TYPE cache_hits_total counter",
            f"cache_hits_total {metrics.hits}",
            "",
            "# HELP cache_misses_total Total number of cache misses",
            "# TYPE cache_misses_total counter",
            f"cache_misses_total {metrics.misses}",
            "",
            "# HELP cache_hit_rate Cache hit rate percentage",
            "# TYPE cache_hit_rate gauge",
            f"cache_hit_rate {metrics.hit_rate}",
            "",
            "# HELP cache_keys_total Total number of keys in cache",
            "# TYPE cache_keys_total gauge",
            f"cache_keys_total {metrics.total_keys}",
            "",
            "# HELP cache_evicted_keys_total Total evicted keys",
            "# TYPE cache_evicted_keys_total counter",
            f"cache_evicted_keys_total {metrics.evicted_keys}",
            "",
            "# HELP cache_connected_clients Current connected clients",
            "# TYPE cache_connected_clients gauge",
            f"cache_connected_clients {metrics.connected_clients}",
            "",
            "# HELP cache_ops_per_second Operations per second",
            "# TYPE cache_ops_per_second gauge",
            f"cache_ops_per_second {metrics.ops_per_sec}",
            ""
        ]
        
        return "\n".join(lines)


# ============================================
# FASTAPI METRICS ENDPOINT
# ============================================

from fastapi import APIRouter, Response

metrics_router = APIRouter(prefix="/metrics", tags=["metrics"])


@metrics_router.get("/cache")
async def get_cache_metrics():
    """Get current cache metrics"""
    metrics = metrics_collector.collect_metrics()
    return metrics.to_dict()


@metrics_router.get("/cache/operations/{operation}")
async def get_operation_stats(operation: str):
    """Get statistics for specific operation"""
    return metrics_collector.get_operation_stats(operation)


@metrics_router.get("/cache/history")
async def get_historical_metrics(hours: int = 24):
    """Get historical metrics"""
    metrics_list = metrics_collector.get_historical_metrics(hours)
    return [m.to_dict() for m in metrics_list]


@metrics_router.get("/prometheus")
async def prometheus_metrics():
    """Prometheus metrics endpoint"""
    exporter = PrometheusExporter(metrics_collector)
    return Response(
        content=exporter.export_metrics(),
        media_type="text/plain"
    )
2. Cache Monitoring Dashboard
python# core/cache/dashboard.py

"""
Cache Monitoring Dashboard

Real-time dashboard for cache metrics visualization
"""

from typing import Dict, Any, List
from datetime import datetime, timedelta
import asyncio
from loguru import logger

from core.cache.metrics import metrics_collector, CacheMetrics


class CacheDashboard:
    """
    Real-time cache monitoring dashboard
    
    Provides live metrics and visualization data
    """
    
    def __init__(self):
        """Initialize dashboard"""
        self.collector = metrics_collector
    
    async def get_dashboard_data(self) -> Dict[str, Any]:
        """
        Get complete dashboard data
        
        Returns:
            Dashboard data dictionary
        """
        # Current metrics
        current = self.collector.collect_metrics()
        
        # Historical data (last 24 hours)
        historical = self.collector.get_historical_metrics(hours=24)
        
        # Operation stats
        operations = {}
        for op in ['get', 'set', 'delete', 'exists']:
            operations[op] = self.collector.get_operation_stats(op)
        
        # Alerts
        alerts = self.collector.check_alerts(current)
        
        # Build time series data
        time_series = self._build_time_series(historical)
        
        return {
            'current': current.to_dict(),
            'time_series': time_series,
            'operations': operations,
            'alerts': alerts,
            'summary': self._build_summary(current, historical),
            'timestamp': datetime.now().isoformat()
        }
    
    def _build_time_series(
        self,
        historical: List[CacheMetrics]
    ) -> Dict[str, List]:
        """
        Build time series data for charts
        
        Args:
            historical: Historical metrics
        
        Returns:
            Time series data
        """
        return {
            'timestamps': [m.timestamp for m in historical],
            'hit_rate': [m.hit_rate for m in historical],
            'total_keys': [m.total_keys for m in historical],
            'ops_per_sec': [m.ops_per_sec for m in historical],
            'connected_clients': [m.connected_clients for m in historical]
        }
    
    def _build_summary(
        self,
        current: CacheMetrics,
        historical: List[CacheMetrics]
    ) -> Dict[str, Any]:
        """
        Build summary statistics
        
        Args:
            current: Current metrics
            historical: Historical metrics
        
        Returns:
            Summary data
        """
        # Calculate trends
        if len(historical) > 1:
            prev = historical[0]
            
            hit_rate_trend = current.hit_rate - prev.hit_rate
            keys_trend = current.total_keys - prev.total_keys
        else:
            hit_rate_trend = 0.0
            keys_trend = 0
        
        return {
            'status': 'healthy' if current.hit_rate > 70 else 'degraded',
            'uptime_hours': self._calculate_uptime(),
            'hit_rate_trend': hit_rate_trend,
            'keys_trend': keys_trend,
            'total_operations': current.hits + current.misses,
            'avg_hit_rate_24h': self._avg_hit_rate(historical)
        }
    
    def _calculate_uptime(self) -> float:
        """Calculate cache uptime in hours"""
        info = self.collector.redis.info('server')
        uptime_seconds = info.get('uptime_in_seconds', 0)
        return uptime_seconds / 3600
    
    def _avg_hit_rate(self, historical: List[CacheMetrics]) -> float:
        """Calculate average hit rate"""
        if not historical:
            return 0.0
        
        return sum(m.hit_rate for m in historical) / len(historical)


# ============================================
# DASHBOARD API ENDPOINTS
# ============================================

from fastapi import APIRouter

dashboard_router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@dashboard_router.get("/cache")
async def get_cache_dashboard():
    """Get cache dashboard data"""
    dashboard = CacheDashboard()
    return await dashboard.get_dashboard_data()


@dashboard_router.get("/cache/realtime")
async def get_realtime_metrics():
    """Get real-time metrics (updates every second)"""
    metrics = metrics_collector.collect_metrics()
    return {
        'hit_rate': metrics.hit_rate,
        'ops_per_sec': metrics.ops_per_sec,
        'connected_clients': metrics.connected_clients,
        'total_keys': metrics.total_keys,
        'timestamp': metrics.timestamp
    }
3. Automated Monitoring & Alerts
python# core/cache/monitoring_tasks.py

"""
Automated Cache Monitoring Tasks

Background tasks for continuous monitoring
"""

from celery import shared_task
from datetime import datetime
from loguru import logger

from core.cache.metrics import metrics_collector
from core.notifications import send_alert  # Your notification system


@shared_task(name='collect_cache_metrics')
def collect_cache_metrics_task():
    """
    Collect cache metrics periodically
    
    Run every minute via Celery Beat
    """
    try:
        # Collect metrics
        metrics = metrics_collector.collect_metrics()
        
        # Store snapshot
        metrics_collector.store_snapshot(metrics)
        
        # Check for alerts
        alerts = metrics_collector.check_alerts(metrics)
        
        # Send alerts if any
        if alerts:
            for alert in alerts:
                logger.warning(alert)
                # send_alert(alert)  # Uncomment to enable notifications
        
        logger.debug(f"Metrics collected: hit_rate={metrics.hit_rate:.1f}%")
        
        return {
            'status': 'success',
            'hit_rate': metrics.hit_rate,
            'alerts': len(alerts)
        }
        
    except Exception as e:
        logger.error(f"Failed to collect metrics: {e}")
        return {'status': 'error', 'error': str(e)}


@shared_task(name='analyze_cache_performance')
def analyze_cache_performance_task():
    """
    Analyze cache performance and trends
    
    Run hourly via Celery Beat
    """
    try:
        # Get historical metrics
        historical = metrics_collector.get_historical_metrics(hours=24)
        
        if not historical:
            return {'status': 'no_data'}
        
        # Calculate trends
        avg_hit_rate = sum(m.hit_rate for m in historical) / len(historical)
        avg_ops = sum(m.ops_per_sec for m in historical) / len(historical)
        
        # Detect anomalies
        current = metrics_collector.collect_metrics()
        
        anomalies = []
        
        # Hit rate dropped significantly
        if current.hit_rate < avg_hit_rate - 20:
            anomalies.append(
                f"Hit rate dropped: {current.hit_rate:.1f}% "
                f"(avg: {avg_hit_rate:.1f}%)"
            )
        
        # Operations spiked
        if current.ops_per_sec > avg_ops * 2:
            anomalies.append(
                f"Operations spiked: {current.ops_per_sec} ops/s "
                f"(avg: {avg_ops:.0f} ops/s)"
            )
        
        # Log anomalies
        if anomalies:
            logger.warning("Cache anomalies detected:")
            for anomaly in anomalies:
                logger.warning(f"  - {anomaly}")
        
        return {
            'status': 'success',
            'avg_hit_rate': avg_hit_rate,
            'anomalies': anomalies
        }
        
    except Exception as e:
        logger.error(f"Performance analysis failed: {e}")
        return {'status': 'error', 'error': str(e)}


@shared_task(name='cleanup_old_metrics')
def cleanup_old_metrics_task():
    """
    Clean up old metrics data
    
    Run daily via Celery Beat
    """
    try:
        redis = metrics_collector.redis
        
        # Remove snapshots older than 7 days
        cutoff = (datetime.now() - timedelta(days=7)).timestamp()
        
        key = redis.make_key('metrics', 'snapshots')
        removed = redis.zremrangebyscore(key, '-inf', cutoff)
        
        logger.info(f"Cleaned up {removed} old metric snapshots")
        
        return {'status': 'success', 'removed': removed}
        
    except Exception as e:
        logger.error(f"Metrics cleanup failed: {e}")
        return {'status': 'error', 'error': str(e)}


# ============================================
# CELERY BEAT SCHEDULE
# ============================================

CACHE_MONITORING_SCHEDULE = {
    'collect-cache-metrics': {
        'task': 'collect_cache_metrics',
        'schedule': 60.0,  # Every minute
    },
    'analyze-cache-performance': {
        'task': 'analyze_cache_performance',
        'schedule': 3600.0,  # Every hour
    },
    'cleanup-old-metrics': {
        'task': 'cleanup_old_metrics',
        'schedule': 86400.0,  # Daily
    }
}

🌐 DISTRIBUTED CACHING
1. Multi-Instance Cache Coordination
python# core/cache/distributed.py

"""
Distributed Caching Support

Features:
- Cache synchronization across instances
- Distributed locks
- Cache warming coordination
- Consistent hashing
"""

from typing import Optional, Any, Callable, List
import hashlib
import time
from contextlib import contextmanager
from loguru import logger

from core.cache.redis_client import get_redis_client


class DistributedLock:
    """
    Distributed lock using Redis
    
    Ensures only one process executes critical section
    across multiple instances
    """
    
    def __init__(
        self,
        redis_client=None,
        lock_timeout: int = 30
    ):
        """
        Initialize distributed lock
        
        Args:
            redis_client: Redis client
            lock_timeout: Lock timeout in seconds
        """
        self.redis = redis_client or get_redis_client()
        self.lock_timeout = lock_timeout
    
    @contextmanager
    def acquire(
        self,
        lock_name: str,
        blocking: bool = True,
        timeout: Optional[int] = None
    ):
        """
        Acquire distributed lock
        
        Args:
            lock_name: Lock identifier
            blocking: Wait for lock if True
            timeout: Max wait time
        
        Example:
            with distributed_lock.acquire('critical_section'):
                # Only one instance executes this
                expensive_operation()
        """
        lock_key = self.redis.make_key('lock', lock_name)
        lock_value = f"{time.time()}"
        
        # Try to acquire lock
        acquired = False
        start_time = time.time()
        
        while not acquired:
            # Set lock with NX (only if not exists)
            acquired = self.redis.set(
                lock_key,
                lock_value,
                ex=self.lock_timeout,
                nx=True
            )
            
            if acquired:
                break
            
            if not blocking:
                raise RuntimeError(f"Could not acquire lock: {lock_name}")
            
            if timeout and (time.time() - start_time) > timeout:
                raise TimeoutError(f"Lock acquisition timeout: {lock_name}")
            
            # Wait before retry
            time.sleep(0.1)
        
        logger.debug(f"Acquired lock: {lock_name}")
        
        try:
            yield
        finally:
            # Release lock
            self.redis.delete(lock_key)
            logger.debug(f"Released lock: {lock_name}")
    
    def is_locked(self, lock_name: str) -> bool:
        """
        Check if lock is currently held
        
        Args:
            lock_name: Lock identifier
        
        Returns:
            True if locked
        """
        lock_key = self.redis.make_key('lock', lock_name)
        return self.redis.exists(lock_key)


class DistributedCache:
    """
    Distributed cache with multi-instance support
    
    Features:
    - Cache invalidation broadcast
    - Consistent hashing for key distribution
    - Cache warming coordination
    """
    
    def __init__(self, redis_client=None, instance_id: str = None):
        """
        Initialize distributed cache
        
        Args:
            redis_client: Redis client
            instance_id: Unique instance identifier
        """
        self.redis = redis_client or get_redis_client()
        self.instance_id = instance_id or self._generate_instance_id()
        self.lock = DistributedLock(self.redis)
        
        # Subscribe to invalidation channel
        self._setup_pubsub()
        
        logger.info(f"Distributed cache initialized: {self.instance_id}")
    
    def _generate_instance_id(self) -> str:
        """Generate unique instance ID"""
        import socket
        import os
        
        hostname = socket.gethostname()
        pid = os.getpid()
        timestamp = int(time.time())
        
        return f"{hostname}:{pid}:{timestamp}"
    
    def _setup_pubsub(self):
        """Setup Redis pub/sub for cache invalidation"""
        # This would be handled by a background task
        # subscribing to invalidation messages
        pass
    
    def broadcast_invalidation(self, key: str):
        """
        Broadcast cache invalidation to all instances
        
        Args:
            key: Cache key to invalidate
        """
        channel = self.redis.make_key('invalidation')
        
        message = {
            'key': key,
            'instance_id': self.instance_id,
            'timestamp': time.time()
        }
        
        self.redis.client.publish(
            channel,
            self.redis.client.json.dumps(message)
        )
        
        logger.debug(f"Broadcast invalidation: {key}")
    
    def consistent_hash(self, key: str, num_nodes: int = 3) -> int:
        """
        Consistent hashing for key distribution
        
        Args:
            key: Key to hash
            num_nodes: Number of cache nodes
        
        Returns:
            Node index (0 to num_nodes-1)
        """
        hash_value = int(hashlib.md5(key.encode()).hexdigest(), 16)
        return hash_value % num_nodes
    
    def get_or_compute(
        self,
        key: str,
        compute_fn: Callable,
        ttl: int = 300,
        lock_timeout: int = 30
    ) -> Any:
        """
        Get from cache or compute with distributed locking
        
        Prevents cache stampede across multiple instances
        
        Args:
            key: Cache key
            compute_fn: Function to compute value
            ttl: Cache TTL
            lock_timeout: Lock timeout
        
        Returns:
            Cached or computed value
        """
        # Try to get from cache
        value = self.redis.get_pickle(key)
        if value is not None:
            return value
        
        # Acquire lock to prevent stampede
        lock_name = f"compute:{key}"
        
        with self.lock.acquire(lock_name, timeout=lock_timeout):
            # Double-check cache (another instance may have computed)
            value = self.redis.get_pickle(key)
            if value is not None:
                return value
            
            # Compute value
            logger.debug(f"Computing value for: {key}")
            value = compute_fn()
            
            # Store in cache
            self.redis.set_pickle(key, value, ex=ttl)
            
            return value


# ============================================
# GLOBAL INSTANCES
# ============================================

distributed_lock = DistributedLock()
distributed_cache = DistributedCache()
2. Cache Clustering
python# core/cache/cluster.py

"""
Redis Cluster Support

Features:
- Redis Cluster client
- Key sharding
- Failover handling
- Cluster monitoring
"""

from redis.cluster import RedisCluster
from typing import List, Dict, Any, Optional
from loguru import logger

from config import settings


class CacheCluster:
    """
    Redis Cluster management
    
    Provides Redis Cluster support with automatic
    sharding and failover
    """
    
    def __init__(
        self,
        startup_nodes: List[Dict[str, Any]] = None,
        decode_responses: bool = True,
        max_connections: int = 50
    ):
        """
        Initialize cluster client
        
        Args:
            startup_nodes: List of cluster nodes
            decode_responses: Decode bytes to strings
            max_connections: Max connections per node
        """
        # Default nodes from settings
        if startup_nodes is None:
            startup_nodes = [
                {
                    'host': settings.REDIS_HOST,
                    'port': settings.REDIS_PORT
                }
            ]
        
        self.cluster = RedisCluster(
            startup_nodes=startup_nodes,
            decode_responses=decode_responses,
            max_connections=max_connections,
            password=settings.REDIS_PASSWORD,
            skip_full_coverage_check=True
        )
        
        logger.info(f"Redis Cluster initialized with {len(startup_nodes)} nodes")
    
    @property
    def client(self) -> RedisCluster:
        """Get cluster client"""
        return self.cluster
    
    def get_cluster_info(self) -> Dict[str, Any]:
        """
        Get cluster information
        
        Returns:
            Cluster info dict
        """
        info = self.cluster.cluster_info()
        nodes = self.cluster.cluster_nodes()
        
        return {
            'state': info.get('cluster_state'),
            'slots_assigned': info.get('cluster_slots_assigned'),
            'slots_ok': info.get('cluster_slots_ok'),
            'nodes_count': len(nodes),
            'nodes': self._parse_cluster_nodes(nodes)
        }
    
    def _parse_cluster_nodes(self, nodes_str: str) -> List[Dict]:
        """Parse cluster nodes string"""
        nodes = []
        
        for line in nodes_str.split('\n'):
            if not line:
                continue
            
            parts = line.split()
            if len(parts) < 8:
                continue
            
            node = {
                'id': parts[0],
                'address': parts[1],
                'flags': parts[2].split(','),
                'master_id': parts[3] if parts[3] != '-' else None,
                'ping_sent': parts[4],
                'pong_recv': parts[5],
                'config_epoch': parts[6],
                'link_state': parts[7]
            }
            
            nodes.append(node)
        
        return nodes
    
    def get_key_slot(self, key: str) -> int:
        """
        Get hash slot for key
        
        Args:
            key: Cache key
        
        Returns:
            Slot number (0-16383)
        """
        return self.cluster.cluster_keyslot(key)
    
    def get_nodes_for_slot(self, slot: int) -> List[str]:
        """
        Get nodes serving a specific slot
        
        Args:
            slot: Slot number
        
        Returns:
            List of node addresses
        """
        # Implementation depends on cluster setup
        pass


# Example: Using cluster for distributed caching
if __name__ == "__main__":
    # Initialize cluster
    cluster = CacheCluster()
    
    # Get cluster info
    info = cluster.get_cluster_info()
    print(f"Cluster state: {info['state']}")
    print(f"Nodes: {info['nodes_count']}")
    
    # Use cluster client
    cluster.client.set('test_key', 'test_value')
    value = cluster.client.get('test_key')
    print(f"Value: {value}")

🎯 CACHE PATTERNS
1. Cache-Aside Pattern
python# core/cache/patterns/cache_aside.py

"""
Cache-Aside Pattern (Lazy Loading)

Application is responsible for:
1. Check cache
2. If miss, load from database
3. Store in cache
4. Return data
"""

from typing import Optional, Any, Callable
from loguru import logger

from core.cache.redis_client import get_redis_client


class CacheAside:
    """
    Cache-Aside pattern implementation
    
    Most common caching pattern
    """
    
    def __init__(self, redis_client=None, default_ttl: int = 300):
        """Initialize cache-aside"""
        self.redis = redis_client or get_redis_client()
        self.default_ttl = default_ttl
    
    def get(
        self,
        key: str,
        loader_fn: Callable,
        ttl: Optional[int] = None
    ) -> Any:
        """
        Get data with cache-aside pattern
        
        Args:
            key: Cache key
            loader_fn: Function to load data if cache miss
            ttl: Cache TTL
        
        Returns:
            Data from cache or database
        
        Example:
            def load_user(user_id):
                return db.query(User).get(user_id)
            
            user = cache_aside.get(
                f'user:{user_id}',
                lambda: load_user(user_id)
            )
        """
        ttl = ttl or self.default_ttl
        
        # Try cache first
        cached = self.redis.get_pickle(key)
        
        if cached is not None:
            logger.debug(f"Cache HIT: {key}")
            return cached
        
        # Cache miss - load from source
        logger.debug(f"Cache MISS: {key}")
        data = loader_fn()
        
        # Store in cache
        if data is not None:
            self.redis.set_pickle(key, data, ex=ttl)
            logger.debug(f"Cached: {key}")
        
        return data
    
    def invalidate(self, key: str):
        """
        Invalidate cache entry
        
        Args:
            key: Cache key
        """
        self.redis.delete(key)
        logger.debug(f"Invalidated: {key}")


# Example usage
if __name__ == "__main__":
    from database import SessionLocal
    from models.user import User
    
    db = SessionLocal()
    cache_aside = CacheAside()
    
    # Get user with cache-aside
    def load_user():
        return db.query(User).filter(User.id == 1).first()
    
    user = cache_aside.get('user:1', load_user)
    print(f"User: {user.email}")
2. Read-Through Pattern
python# core/cache/patterns/read_through.py

"""
Read-Through Pattern

Cache is responsible for loading data from database
Application only interacts with cache
"""

from typing import Optional, Any, Callable, Dict
from loguru import logger

from core.cache.redis_client import get_redis_client


class ReadThroughCache:
    """
    Read-Through cache implementation
    
    Cache handles data loading automatically
    """
    
    def __init__(self, redis_client=None, default_ttl: int = 300):
        """Initialize read-through cache"""
        self.redis = redis_client or get_redis_client()
        self.default_ttl = default_ttl
        
        # Register data loaders
        self._loaders: Dict[str, Callable] = {}
    
    def register_loader(
        self,
        key_pattern: str,
        loader_fn: Callable,
        ttl: Optional[int] = None
    ):
        """
        Register data loader for key pattern
        
        Args:
            key_pattern: Key pattern (e.g., 'user:*')
            loader_fn: Function to load data
            ttl: Cache TTL
        
        Example:
            def load_user(user_id):
                return db.query(User).get(user_id)
            
            cache.register_loader(
                'user:*',
                lambda key: load_user(key.split(':')[1])
            )
        """
        self._loaders[key_pattern] = {
            'loader': loader_fn,
            'ttl': ttl or self.default_ttl
        }
        
        logger.info(f"Registered loader for: {key_pattern}")
    
    def get(self, key: str) -> Optional[Any]:
        """
        Get data (loads automatically if not cached)
        
        Args:
            key: Cache key
        
        Returns:
            Data from cache or loaded from source
        """
        # Try cache
        cached = self.redis.get_pickle(key)
        
        if cached is not None:
            logger.debug(f"Read-through HIT: {key}")
            return cached
        
        # Find matching loader
        loader_config = self._find_loader(key)
        
        if not loader_config:
            logger.warning(f"No loader registered for: {key}")
            return None
        
        # Load data
        logger.debug(f"Read-through MISS: {key}")
        data = loader_config['loader'](key)
        
        # Cache result
        if data is not None:
            self.redis.set_pickle(
                key,
                data,
                ex=loader_config['ttl']
            )
        
        return data
    
    def _find_loader(self, key: str) -> Optional[Dict]:
        """Find loader for key"""
        import fnmatch
        
        for pattern, config in self._loaders.items():
            if fnmatch.fnmatch(key, pattern):
                return config
        
        return None


# Example usage
if __name__ == "__main__":
    from database import SessionLocal
    from models.user import User
    
    db = SessionLocal()
    cache = ReadThroughCache()
    
    # Register loader
    def load_user(key):
        user_id = int(key.split(':')[1])
        return db.query(User).get(user_id)
    
    cache.register_loader('user:*', load_user)
    
    # Application only interacts with cache
    user = cache.get('user:1')
    print(f"User: {user.email if user else 'Not found'}")
3. Write-Through Pattern
python# core/cache/patterns/write_through.py

"""
Write-Through Pattern

Writes go through cache to database
Cache is always consistent with database
"""

from typing import Any, Callable
from loguru import logger

from core.cache.redis_client import get_redis_client


class WriteThroughCache:
    """
    Write-Through cache implementation
    
    Writes are synchronous:
    1. Write to cache
    2. Write to database
    3. Return success
    """
    
    def __init__(self, redis_client=None, default_ttl: int = 300):
        """Initialize write-through cache"""
        self.redis = redis_client or get_redis_client()
        self.default_ttl = default_ttl
    
    def write(
        self,
        key: str,
        value: Any,
        writer_fn: Callable,
        ttl: Optional[int] = None
    ) -> bool:
        """
        Write data through cache to database
        
        Args:
            key: Cache key
            value: Data to write
            writer_fn: Function to write to database
            ttl: Cache TTL
        
        Returns:
            True if successful
        
        Example:
            def save_user(user_data):
                user = User(**user_data)
                db.add(user)
                db.commit()
                return user
            
            success = cache.write(
                'user:123',
                user_data,
                lambda: save_user(user_data)
            )
        """
        ttl = ttl or self.default_ttl
        
        try:
            # Write to database first
            logger.debug(f"Writing to database: {key}")
            result = writer_fn(value)
            
            # Then write to cache
            self.redis.set_pickle(key, result, ex=ttl)
            logger.debug(f"Cached: {key}")
            
            return True
            
        except Exception as e:
            logger.error(f"Write-through failed for {key}: {e}")
            # Rollback cache if database write failed
            self.redis.delete(key)
            raise
    
    def update(
        self,
        key: str,
        value: Any,
        updater_fn: Callable,
        ttl: Optional[int] = None
    ) -> bool:
        """
        Update data through cache to database
        
        Args:
            key: Cache key
            value: Updated data
            updater_fn: Function to update database
            ttl: Cache TTL
        
        Returns:
            True if successful
        """
        return self.write(key, value, updater_fn, ttl)


# Example usage
if __name__ == "__main__":
    from database import SessionLocal
    from models.user import User
    
    db = SessionLocal()
    cache = WriteThroughCache()
    
    # Write through cache
    def save_user(data):
        user = User(**data)
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
    
    user_data = {
        'email': 'test@example.com',
        'username': 'testuser'
    }
    
    success = cache.write(
        'user:new',
        user_data,
        lambda _: save_user(user_data)
    )
    
    print(f"Write successful: {success}")
4. Write-Behind Pattern
python# core/cache/patterns/write_behind.py

"""
Write-Behind Pattern (Write-Back)

Writes are asynchronous:
1. Write to cache immediately
2. Queue write to database
3. Return success
4. Database write happens in background
"""

from typing import Any, Callable, Dict
from queue import Queue
from threading import Thread
import time
from loguru import logger

from core.cache.redis_client import get_redis_client


class WriteBehindCache:
    """
    Write-Behind cache implementation
    
    Provides better write performance with
    eventual consistency
    """
    
    def __init__(
        self,
        redis_client=None,
        default_ttl: int = 300,
        batch_size: int = 10,
        flush_interval: int = 5
    ):
        """
        Initialize write-behind cache
        
        Args:
            redis_client: Redis client
            default_ttl: Cache TTL
            batch_size: Batch size for database writes
            flush_interval: Seconds between flushes
        """
        self.redis = redis_client or get_redis_client()
        self.default_ttl = default_ttl
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        
        # Write queue
        self._write_queue = Queue()
        
        # Start background writer
        self._writer_thread = Thread(
            target=self._background_writer,
            daemon=True
        )
        self._writer_thread.start()
        
        logger.info("Write-behind cache initialized")
    
    def write(
        self,
        key: str,
        value: Any,
        writer_fn: Callable,
        ttl: Optional[int] = None
    ) -> bool:
        """
        Write data (cache immediately, database async)
        
        Args:
            key: Cache key
            value: Data to write
            writer_fn: Function to write to database
            ttl: Cache TTL
        
        Returns:
            True (cache write succeeded)
        """
        ttl = ttl or self.default_ttl
        
        try:
            # Write to cache immediately
            self.redis.set_pickle(key, value, ex=ttl)
            logger.debug(f"Cached (write-behind): {key}")
            
            # Queue database write
            self._write_queue.put({
                'key': key,
                'value': value,
                'writer_fn': writer_fn,
                'timestamp': time.time()
            })
            
            return True
            
        except Exception as e:
            logger.error(f"Write-behind cache failed for {key}: {e}")
            return False
    
    def _background_writer(self):
        """
        Background thread for database writes
        
        Processes write queue in batches
        """
        batch = []
        last_flush = time.time()
        
        while True:
            try:
                # Get item from queue (with timeout)
                try:
                    item = self._write_queue.get(timeout=1)
                    batch.append(item)
                except:
                    pass
                
                # Flush if batch is full or interval elapsed
                should_flush = (
                    len(batch) >= self.batch_size or
                    (time.time() - last_flush) >= self.flush_interval
                )
                
                if should_flush and batch:
                    self._flush_batch(batch)
                    batch = []
                    last_flush = time.time()
                    
            except Exception as e:
                logger.error(f"Background writer error: {e}")
    
    def _flush_batch(self, batch: list):
        """
        Flush batch of writes to database
        
        Args:
            batch: List of write operations
        """
        logger.debug(f"Flushing {len(batch)} writes to database")
        
        for item in batch:
            try:
                # Execute database write
                item['writer_fn'](item['value'])
                
            except Exception as e:
                logger.error(
                    f"Database write failed for {item['key']}: {e}"
                )
                # Could implement retry logic here
        
        logger.debug(f"Flushed {len(batch)} writes")
    
    def flush(self):
        """Force flush of pending writes"""
        # Wait for queue to empty
        self._write_queue.join()


# Example usage with Celery for better scalability
from celery import shared_task

@shared_task(name='flush_write_behind_cache')
def flush_write_behind_cache_task():
    """
    Celery task to flush write-behind cache
    
    Better than thread for production use
    """
    # Implementation would batch and write to database
    pass

Das war Teil 3! 🎉 Aber wir sind noch nicht fertig - ich füge noch den Best Practices & Troubleshooting Abschnitt hinzu:
✅ BEST PRACTICES & TROUBLESHOOTING
Best Practices Summary
python# docs/caching_best_practices.py

"""
Caching Best Practices

Comprehensive guide to production-ready caching
"""

CACHING_BEST_PRACTICES = {
    # ============================================
    # KEY DESIGN
    # ============================================
    "key_design": {
        "DO": [
            "Use namespaced keys (e.g., 'app:user:123')",
            "Include version in keys for breaking changes",
            "Use meaningful, readable key names",
            "Keep keys short but descriptive",
            "Use consistent naming conventions",
            "Include type hints in key patterns"
        ],
        "DON'T": [
            "Use very long keys (>256 chars)",
            "Include user data in keys",
            "Use random or cryptic key names",
            "Mix naming conventions",
            "Use special characters that need escaping"
        ]
    },
    
    # ============================================
    # TTL MANAGEMENT
    # ============================================
    "ttl_management": {
        "DO": [
            "Always set TTL to prevent memory bloat",
            "Use longer TTL for stable data",
            "Use shorter TTL for frequently changing data",
            "Match TTL to data change frequency",
            "Use different TTLs for different data types",
            "Monitor expired keys metrics"
        ],
        "DON'T": [
            "Cache without TTL (leads to stale data)",
            "Use very short TTL (<10s) for expensive ops",
            "Use same TTL for all data",
            "Set TTL based on gut feeling (measure!)"
        ]
    },
    
    # ============================================
    # INVALIDATION
    # ============================================
    "invalidation": {
        "DO": [
            "Invalidate on write operations",
            "Use tags for bulk invalidation",
            "Implement event-based invalidation",
            "Use TTL as primary invalidation",
            "Track invalidation patterns",
            "Test invalidation logic thoroughly"
        ],
        "DON'T": [
            "Rely only on TTL for critical data",
            "Use KEYS command in production",
            "Forget to invalidate related data",
            "Over-invalidate (cache thrashing)"
        ]
    },
    
    # ============================================
    # PERFORMANCE
    # ============================================
    "performance": {
        "DO": [
            "Monitor hit/miss rates",
            "Use connection pooling",
            "Batch operations when possible",
            "Use pipelining for multiple ops",
            "Cache expensive operations",
            "Measure cache vs database latency"
        ],
        "DON'T": [
            "Cache cheap operations",
            "Create new connections per request",
            "Use cache for rapidly changing data",
            "Cache large objects unnecessarily",
            "Ignore cache performance metrics"
        ]
    },
    
    # ============================================
    # SECURITY
    # ============================================
    "security": {
        "DO": [
            "Use authentication (requirepass)",
            "Encrypt sensitive data before caching",
            "Use network encryption (TLS)",
            "Restrict network access",
            "Rotate passwords regularly",
            "Audit cache access logs"
        ],
        "DON'T": [
            "Cache passwords or secrets",
            "Cache PII without encryption",
            "Expose Redis to public internet",
            "Use default passwords",
            "Store session tokens unencrypted"
        ]
    },
    
    # ============================================
    # MONITORING
    # ============================================
    "monitoring": {
        "DO": [
            "Track hit/miss rates",
            "Monitor memory usage",
            "Alert on high eviction rates",
            "Monitor connection count",
            "Track operation latencies",
            "Set up dashboards"
        ],
        "DON'T": [
            "Ignore cache metrics",
            "Run without monitoring",
            "Miss high eviction warnings",
            "Forget to set up alerts"
        ]
    }
}


# Recommended TTL values
RECOMMENDED_TTLS = {
    # Static data
    "configuration": 3600,  # 1 hour
    "feature_flags": 300,   # 5 minutes
    "reference_data": 86400,  # 24 hours
    
    # User data
    "user_profile": 1800,  # 30 minutes
    "user_session": 3600,  # 1 hour
    "user_permissions": 900,  # 15 minutes
    
    # OCR data
    "ocr_result": 86400 * 7,  # 7 days (expensive!)
    "document_metadata": 3600,  # 1 hour
    "processing_status": 60,  # 1 minute
    
    # API responses
    "api_list_results": 300,  # 5 minutes
    "api_detail": 600,  # 10 minutes
    "api_search": 180,  # 3 minutes
    
    # Expensive computations
    "report_generation": 3600,  # 1 hour
    "analytics": 1800,  # 30 minutes
    "aggregations": 600  # 10 minutes
}
Common Issues & Solutions
markdown# Caching Troubleshooting Guide
# ============================================

## Issue 1: Low Hit Rate

**Symptoms:**
- Hit rate < 50%
- Many cache misses
- Poor response times

**Possible Causes:**

1. **TTL too short**
   - Data expires before being reused
   - Solution: Increase TTL for stable data

2. **Caching wrong data**
   - Caching data that's rarely accessed twice
   - Solution: Profile access patterns, cache frequently accessed data

3. **Poor key design**
   - Keys not matching between set and get
   - Solution: Review key generation logic

4. **High eviction rate**
   - Memory full, evicting before use
   - Solution: Increase memory or reduce cache size

**Diagnosis:**
```python
# Check hit rate
metrics = metrics_collector.collect_metrics()
print(f"Hit rate: {metrics.hit_rate}%")

# Check evictions
if metrics.evicted_keys > 1000:
    print("High eviction rate!")
```


## Issue 2: High Memory Usage

**Symptoms:**
- Memory near limit
- High eviction rate
- OOM errors

**Solutions:**

1. **Reduce TTL**
```python
   # Before
   cache.set(key, value, ex=86400)  # 24 hours
   
   # After
   cache.set(key, value, ex=3600)   # 1 hour
```

2. **Implement size limits**
```python
   # Only cache if under size limit
   if len(value) < MAX_CACHE_SIZE:
       cache.set(key, value)
```

3. **Use compression**
```python
   import zlib
   
   compressed = zlib.compress(pickle.dumps(value))
   cache.set(key, compressed)
```

4. **Increase max memory**
```ini
   # redis.conf
   maxmemory 1gb  # Increase from 512mb
```


## Issue 3: Cache Stampede

**Symptoms:**
- Sudden spike in database load
- Multiple identical queries
- Occurs when popular cache expires

**Solutions:**

1. **Use distributed locks**
```python
   with distributed_lock.acquire(f'compute:{key}'):
       value = expensive_computation()
       cache.set(key, value)
```

2. **Probabilistic early recomputation**
```python
   import random
   
   ttl_remaining = cache.ttl(key)
   if ttl_remaining < 60 and random.random() < 0.1:
       # Recompute early (10% chance in last minute)
       value = expensive_computation()
       cache.set(key, value, ex=300)
```

3. **Use cache warming**
```python
   # Warm cache before expiry
   @shared_task
   def warm_popular_caches():
       for key in popular_keys:
           refresh_cache(key)
```


## Issue 4: Stale Data

**Symptoms:**
- Users see old data
- Data not updating
- Inconsistency between cache and database

**Solutions:**

1. **Implement proper invalidation**
```python
   # After update
   def update_user(user_id, data):
       user = db.query(User).get(user_id)
       # Update...
       db.commit()
       
       # Invalidate cache
       cache.delete(f'user:{user_id}')
```

2. **Use shorter TTL for critical data**
```python
   # Critical data: 1 minute
   cache.set(key, value, ex=60)
```

3. **Use write-through pattern**
```python
   # Update cache and database together
   write_through_cache.write(key, value, db_writer)
```


## Issue 5: Connection Errors

**Symptoms:**
- "Connection refused"
- "Too many clients"
- Timeout errors

**Solutions:**

1. **Check Redis is running**
```bash
   docker ps | grep redis
   redis-cli ping
```

2. **Increase connection pool**
```python
   redis_client = RedisClient(max_connections=100)
```

3. **Implement retry logic**
```python
   from tenacity import retry, stop_after_attempt
   
   @retry(stop=stop_after_attempt(3))
   def get_from_cache(key):
       return cache.get(key)
```


## Issue 6: Slow Cache Operations

**Symptoms:**
- Cache slower than expected
- Increasing latency
- Timeouts

**Solutions:**

1. **Use pipelining**
```python
   pipe = cache.pipeline()
   for key in keys:
       pipe.get(key)
   results = pipe.execute()
```

2. **Check network latency**
```bash
   redis-cli --latency
```

3. **Use local cache for hot data**
```python
   @lru_cache(maxsize=1000)
   def get_user(user_id):
       # Redis cache
       return cache.get(f'user:{user_id}')
```


## Issue 7: Memory Fragmentation

**Symptoms:**
- High mem_fragmentation_ratio (>1.5)
- More memory used than expected

**Solutions:**

1. **Restart Redis periodically**
```bash
   # Schedule during low traffic
   redis-cli SHUTDOWN SAVE
```

2. **Enable active defragmentation**
```ini
   # redis.conf
   activedefrag yes
```


## Diagnostic Commands
```bash
# Monitor Redis in real-time
redis-cli --stat

# Get server info
redis-cli INFO

# Monitor commands
redis-cli MONITOR

# Check slow log
redis-cli SLOWLOG GET 10

# Memory analysis
redis-cli --bigkeys

# Memory breakdown
redis-cli MEMORY STATS
```
```

---

## 📚 FINAL SUMMARY
```
┌──────────────────────────────────────────────────────────────┐
│           COMPLETE CACHING STRATEGY COVERAGE                  │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ✅ Redis Setup & Configuration                              │
│     - Docker Compose setup                                   │
│     - Production configuration                               │
│     - Sentinel support (HA)                                  │
│     - Complete Python client                                 │
│                                                              │
│  ✅ Application-Level Caching                                │
│     - Cache manager with decorators                          │
│     - TTL cache with memoization                             │
│     - JSON and Pickle support                                │
│     - Automatic key generation                               │
│                                                              │
│  ✅ Query Result Caching                                     │
│     - SQLAlchemy integration                                 │
│     - Dogpile cache support                                  │
│     - Repository pattern with caching                        │
│     - Automatic invalidation listeners                       │
│                                                              │
│  ✅ Cache Invalidation                                       │
│     - All strategies (TTL, Event, Tag, Dependency)           │
│     - Automatic invalidation hooks                           │
│     - Pattern-based invalidation                             │
│     - Conditional invalidation                               │
│                                                              │
│  ✅ Cache Warming                                            │
│     - Warming service                                        │
│     - OCR-specific tasks                                     │
│     - Predictive warming                                     │
│     - Celery integration                                     │
│                                                              │
│  ✅ Cache Monitoring                                         │
│     - Comprehensive metrics collection                       │
│     - Real-time dashboard                                    │
│     - Prometheus export                                      │
│     - Automated alerts                                       │
│                                                              │
│  ✅ Distributed Caching                                      │
│     - Distributed locks                                      │
│     - Multi-instance coordination                            │
│     - Cluster support                                        │
│     - Consistent hashing                                     │
│                                                              │
│  ✅ Cache Patterns                                           │
│     - Cache-Aside (Lazy Loading)                             │
│     - Read-Through                                           │
│     - Write-Through                                          │
│     - Write-Behind (Write-Back)                              │
│                                                              │
│  ✅ Best Practices & Troubleshooting                         │
│     - Complete guidelines                                    │
│     - Common issues & solutions                              │
│     - Diagnostic commands                                    │
│     - Production recommendations                             │
│                                                              │
└──────────────────────────────────────────────────────────────┘