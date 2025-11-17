SCALABILITY & PERFORMANCE GUIDE - TEIL 1
Complete Scaling Strategy for Production Systems

📋 TABLE OF CONTENTS

Introduction
Horizontal Scaling
Load Balancing
Database Read Replicas


🎯 INTRODUCTION
Why Scalability Matters
┌─────────────────────────────────────────────────────────┐
│         SCALABILITY BENEFITS                             │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  📈 Growth Support                                       │
│     - Handle increasing traffic                         │
│     - Support more users                                │
│     - Process more data                                 │
│     - Maintain performance at scale                     │
│                                                         │
│  🛡️ Reliability                                          │
│     - No single point of failure                        │
│     - Better fault tolerance                            │
│     - Graceful degradation                              │
│     - High availability (99.9%+)                        │
│                                                         │
│  ⚡ Performance                                           │
│     - Faster response times                             │
│     - Parallel processing                               │
│     - Efficient resource utilization                    │
│     - Better user experience                            │
│                                                         │
│  💰 Cost Efficiency                                      │
│     - Pay for what you need                             │
│     - Auto-scaling capabilities                         │
│     - Optimize resource usage                           │
│     - Reduce infrastructure costs                       │
│                                                         │
└─────────────────────────────────────────────────────────┘
Scaling Approaches
┌──────────────────────────────────────────────────────────────┐
│              VERTICAL VS HORIZONTAL SCALING                   │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  VERTICAL SCALING (Scale Up)                                 │
│  ┌────────────────────────────────────────────┐             │
│  │  Single Server → Bigger Server             │             │
│  │                                            │             │
│  │  Before:  4 CPU,  16GB RAM                 │             │
│  │  After:  16 CPU,  64GB RAM                 │             │
│  │                                            │             │
│  │  Pros:                                     │             │
│  │  ✓ Simple to implement                     │             │
│  │  ✓ No code changes needed                  │             │
│  │  ✓ No distributed complexity                │             │
│  │                                            │             │
│  │  Cons:                                     │             │
│  │  ✗ Hardware limits                         │             │
│  │  ✗ Single point of failure                 │             │
│  │  ✗ Downtime for upgrades                   │             │
│  │  ✗ Expensive at scale                      │             │
│  └────────────────────────────────────────────┘             │
│                                                              │
│  HORIZONTAL SCALING (Scale Out)                              │
│  ┌────────────────────────────────────────────┐             │
│  │  Single Server → Multiple Servers          │             │
│  │                                            │             │
│  │  Before:  [Server 1]                       │             │
│  │  After:   [Server 1][Server 2][Server 3]   │             │
│  │                                            │             │
│  │  Pros:                                     │             │
│  │  ✓ Nearly unlimited scaling                 │             │
│  │  ✓ High availability                       │             │
│  │  ✓ No single point of failure              │             │
│  │  ✓ Cost-effective                          │             │
│  │                                            │             │
│  │  Cons:                                     │             │
│  │  ✗ Complex architecture                    │             │
│  │  ✗ Requires code changes                   │             │
│  │  ✗ Data consistency challenges             │             │
│  │  ✗ More infrastructure to manage           │             │
│  └────────────────────────────────────────────┘             │
│                                                              │
└──────────────────────────────────────────────────────────────┘
System Architecture Evolution
┌──────────────────────────────────────────────────────────────┐
│           ARCHITECTURE EVOLUTION PATH                         │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  STAGE 1: Monolith (Single Server)                           │
│  ┌─────────────────────┐                                    │
│  │  [Web + App + DB]   │ ← All in one                        │
│  └─────────────────────┘                                    │
│  Traffic: < 1,000 users/day                                  │
│                                                              │
│  STAGE 2: Separated Database                                 │
│  ┌──────────────┐     ┌──────────────┐                      │
│  │  [Web + App] │────→│  [Database]  │                      │
│  └──────────────┘     └──────────────┘                      │
│  Traffic: 1,000 - 10,000 users/day                           │
│                                                              │
│  STAGE 3: Load Balancer + Multiple Servers                   │
│              ┌──────────────┐                               │
│              │Load Balancer │                               │
│              └──────┬───────┘                               │
│         ┌───────────┼───────────┐                           │
│    ┌────▼────┐ ┌────▼────┐ ┌───▼─────┐                     │
│    │ Server1 │ │ Server2 │ │ Server3 │                     │
│    └────┬────┘ └────┬────┘ └────┬────┘                     │
│         └───────────┼───────────┘                           │
│              ┌──────▼───────┐                               │
│              │  [Database]  │                               │
│              └──────────────┘                               │
│  Traffic: 10,000 - 100,000 users/day                         │
│                                                              │
│  STAGE 4: Database Replication                               │
│              ┌──────────────┐                               │
│              │Load Balancer │                               │
│              └──────┬───────┘                               │
│         ┌───────────┼───────────┐                           │
│    ┌────▼────┐ ┌────▼────┐ ┌───▼─────┐                     │
│    │ Server1 │ │ Server2 │ │ Server3 │                     │
│    └────┬────┘ └────┬────┘ └────┬────┘                     │
│         │           │            │                          │
│    Write│           │Read   Read │                          │
│         │           │            │                          │
│    ┌────▼────┐ ┌───▼────┐ ┌────▼────┐                     │
│    │ Master  │→│ Slave1 │ │ Slave2  │                     │
│    │   DB    │ │   DB   │ │   DB    │                     │
│    └─────────┘ └────────┘ └─────────┘                     │
│  Traffic: 100,000 - 1M users/day                             │
│                                                              │
│  STAGE 5: Microservices + Caching + Message Queue            │
│              ┌──────────────┐                               │
│              │Load Balancer │                               │
│              └──────┬───────┘                               │
│         ┌───────────┼────────────┐                          │
│    ┌────▼────┐ ┌────▼─────┐ ┌───▼──────┐                  │
│    │ Auth    │ │   OCR    │ │  User    │                  │
│    │ Service │ │ Service  │ │ Service  │                  │
│    └────┬────┘ └────┬─────┘ └────┬─────┘                  │
│         │           │             │                         │
│         └───────────┼─────────────┘                         │
│              ┌──────▼───────┐                               │
│              │ Message Queue│                               │
│              └──────┬───────┘                               │
│         ┌───────────┼────────────┐                          │
│    ┌────▼────┐ ┌───▼────┐  ┌────▼────┐                    │
│    │  Redis  │ │ Master │  │ Workers │                    │
│    │  Cache  │ │   DB   │  │  Pool   │                    │
│    └─────────┘ └───┬────┘  └─────────┘                    │
│                    │                                        │
│              ┌─────▼──────┐                                │
│              │ Read DBs   │                                │
│              └────────────┘                                │
│  Traffic: 1M+ users/day                                      │
│                                                              │
└──────────────────────────────────────────────────────────────┘

📊 HORIZONTAL SCALING
1. Stateless Application Design
python# app/stateless_design.py

"""
Stateless Application Design

Critical for horizontal scaling
"""

from typing import Optional, Dict, Any
from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import JSONResponse
from redis import Redis
from datetime import datetime, timedelta
import jwt
import uuid

# ============================================
# BAD: Stateful Design (Don't do this!)
# ============================================

class StatefulApp:
    """
    ❌ BAD EXAMPLE: Stores session in memory
    
    Problems:
    - Can't scale horizontally
    - Session lost on restart
    - Sticky sessions required
    - Load balancing difficult
    """
    
    def __init__(self):
        # ❌ In-memory session storage
        self.sessions: Dict[str, Dict] = {}
        self.user_carts: Dict[str, list] = {}
        self.upload_cache: Dict[str, bytes] = {}
    
    def login(self, username: str, password: str) -> str:
        """Login and store session in memory"""
        session_id = str(uuid.uuid4())
        
        # ❌ Session data stored in application memory
        self.sessions[session_id] = {
            "username": username,
            "logged_in_at": datetime.now()
        }
        
        return session_id
    
    def add_to_cart(self, user_id: str, item: Dict):
        """Add item to cart (stored in memory)"""
        # ❌ Cart data in application memory
        if user_id not in self.user_carts:
            self.user_carts[user_id] = []
        
        self.user_carts[user_id].append(item)


# ============================================
# GOOD: Stateless Design (Do this!)
# ============================================

class StatelessApp:
    """
    ✅ GOOD EXAMPLE: Stateless application
    
    Benefits:
    - Can scale horizontally
    - Any server can handle any request
    - No sticky sessions needed
    - Easy load balancing
    """
    
    def __init__(self, redis_client: Redis):
        """
        Initialize with external state storage.
        
        Args:
            redis_client: Redis for session/state storage
        """
        self.redis = redis_client
        self.jwt_secret = "your-secret-key"  # Use env var!
    
    def login(self, username: str, password: str) -> str:
        """
        Login and return JWT token.
        
        ✅ No server-side session storage
        ✅ Token contains all needed info
        ✅ Can be validated by any server
        """
        # Create JWT token
        payload = {
            "username": username,
            "exp": datetime.utcnow() + timedelta(hours=24),
            "iat": datetime.utcnow()
        }
        
        token = jwt.encode(payload, self.jwt_secret, algorithm="HS256")
        
        # Optional: Store token hash in Redis for revocation
        # ✅ Stored in shared Redis, not local memory
        token_hash = hash(token)
        self.redis.setex(
            f"token:{token_hash}",
            86400,  # 24 hours
            username
        )
        
        return token
    
    def validate_token(self, token: str) -> Optional[Dict]:
        """
        Validate JWT token.
        
        ✅ Stateless validation
        ✅ Any server can validate
        """
        try:
            payload = jwt.decode(
                token,
                self.jwt_secret,
                algorithms=["HS256"]
            )
            return payload
        except jwt.InvalidTokenError:
            return None
    
    def add_to_cart(self, user_id: str, item: Dict):
        """
        Add item to cart.
        
        ✅ Stored in Redis (shared storage)
        ✅ Available to all servers
        """
        # Store in Redis
        cart_key = f"cart:{user_id}"
        
        # Get current cart
        cart = self.redis.get(cart_key)
        if cart:
            import json
            cart_items = json.loads(cart)
        else:
            cart_items = []
        
        # Add item
        cart_items.append(item)
        
        # Save back
        import json
        self.redis.setex(
            cart_key,
            86400,  # 24 hours
            json.dumps(cart_items)
        )
    
    def get_cart(self, user_id: str) -> list:
        """Get user's cart from Redis"""
        cart_key = f"cart:{user_id}"
        cart = self.redis.get(cart_key)
        
        if cart:
            import json
            return json.loads(cart)
        
        return []


# ============================================
# STATELESS FASTAPI APPLICATION
# ============================================

def create_stateless_app(redis_client: Redis) -> FastAPI:
    """
    Create stateless FastAPI application.
    
    ✅ All state in Redis/Database
    ✅ JWT for authentication
    ✅ Can run multiple instances
    """
    app = FastAPI(title="Stateless OCR API")
    stateless = StatelessApp(redis_client)
    
    def get_current_user(request: Request) -> Optional[Dict]:
        """Extract user from JWT token"""
        auth_header = request.headers.get("Authorization")
        
        if not auth_header or not auth_header.startswith("Bearer "):
            return None
        
        token = auth_header.split(" ")[1]
        return stateless.validate_token(token)
    
    @app.post("/auth/login")
    async def login(username: str, password: str):
        """
        Login endpoint.
        
        Returns JWT token (stateless)
        """
        # Validate credentials (check database)
        # ... authentication logic ...
        
        token = stateless.login(username, password)
        
        return {"access_token": token, "token_type": "bearer"}
    
    @app.post("/cart/add")
    async def add_to_cart(
        item: Dict,
        user: Dict = Depends(get_current_user)
    ):
        """
        Add item to cart.
        
        Cart stored in Redis (shared state)
        """
        if not user:
            raise HTTPException(401, "Not authenticated")
        
        stateless.add_to_cart(user["username"], item)
        
        return {"status": "added"}
    
    @app.get("/cart")
    async def get_cart(user: Dict = Depends(get_current_user)):
        """Get user's cart"""
        if not user:
            raise HTTPException(401, "Not authenticated")
        
        cart = stateless.get_cart(user["username"])
        
        return {"items": cart}
    
    @app.get("/health")
    async def health():
        """
        Health check endpoint.
        
        ✅ Stateless - no stored state to check
        ✅ Can be called on any instance
        """
        # Check Redis connection
        try:
            redis_client.ping()
            redis_healthy = True
        except:
            redis_healthy = False
        
        return {
            "status": "healthy" if redis_healthy else "degraded",
            "redis": redis_healthy,
            "instance_id": str(uuid.uuid4())  # Shows which instance handled request
        }
    
    return app


# ============================================
# SESSION MANAGEMENT IN REDIS
# ============================================

class RedisSessionManager:
    """
    Centralized session management using Redis.
    
    ✅ Shared across all instances
    ✅ Persistent and fast
    ✅ Supports expiration
    """
    
    def __init__(self, redis_client: Redis):
        self.redis = redis_client
    
    def create_session(
        self,
        user_id: str,
        data: Dict[str, Any],
        ttl: int = 86400
    ) -> str:
        """
        Create new session.
        
        Args:
            user_id: User identifier
            data: Session data
            ttl: Time to live in seconds
        
        Returns:
            Session ID
        """
        import json
        
        session_id = str(uuid.uuid4())
        key = f"session:{session_id}"
        
        session_data = {
            "user_id": user_id,
            "created_at": datetime.now().isoformat(),
            **data
        }
        
        self.redis.setex(
            key,
            ttl,
            json.dumps(session_data)
        )
        
        return session_id
    
    def get_session(self, session_id: str) -> Optional[Dict]:
        """Get session data"""
        import json
        
        key = f"session:{session_id}"
        data = self.redis.get(key)
        
        if data:
            return json.loads(data)
        
        return None
    
    def update_session(
        self,
        session_id: str,
        data: Dict[str, Any]
    ):
        """Update session data"""
        import json
        
        key = f"session:{session_id}"
        current = self.get_session(session_id)
        
        if current:
            current.update(data)
            
            # Preserve TTL
            ttl = self.redis.ttl(key)
            if ttl > 0:
                self.redis.setex(key, ttl, json.dumps(current))
    
    def delete_session(self, session_id: str):
        """Delete session (logout)"""
        key = f"session:{session_id}"
        self.redis.delete(key)


# ============================================
# EXAMPLE USAGE
# ============================================

if __name__ == "__main__":
    from redis import Redis
    import uvicorn
    
    # Setup
    redis = Redis(host='localhost', port=6379, decode_responses=True)
    
    # Create app
    app = create_stateless_app(redis)
    
    print("="*60)
    print("STATELESS APPLICATION")
    print("="*60)
    print("\n✅ Stateless design benefits:")
    print("  - Can run multiple instances")
    print("  - No sticky sessions needed")
    print("  - Easy horizontal scaling")
    print("  - State in Redis (shared)")
    print("\nStarting server...")
    print("Try running multiple instances on different ports!")
    print("="*60)
    
    # Run multiple instances:
    # uvicorn main:app --port 8000
    # uvicorn main:app --port 8001
    # uvicorn main:app --port 8002
    
    uvicorn.run(app, host="0.0.0.0", port=8000)
2. Auto-Scaling Configuration
python# infrastructure/autoscaling.py

"""
Auto-Scaling Configuration

Automatic horizontal scaling based on metrics
"""

from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum


class ScalingMetric(Enum):
    """Metrics for auto-scaling"""
    CPU_USAGE = "cpu_usage"
    MEMORY_USAGE = "memory_usage"
    REQUEST_RATE = "request_rate"
    QUEUE_DEPTH = "queue_depth"
    RESPONSE_TIME = "response_time"


@dataclass
class ScalingRule:
    """Auto-scaling rule"""
    metric: ScalingMetric
    threshold: float
    comparison: str  # ">", "<", ">=", "<="
    duration: int  # seconds
    scale_action: str  # "scale_up", "scale_down"
    scale_amount: int  # number of instances


@dataclass
class AutoScalingConfig:
    """
    Auto-scaling configuration.
    
    Example for Kubernetes HPA (Horizontal Pod Autoscaler):
    
    apiVersion: autoscaling/v2
    kind: HorizontalPodAutoscaler
    metadata:
      name: ocr-api-hpa
    spec:
      scaleTargetRef:
        apiVersion: apps/v1
        kind: Deployment
        name: ocr-api
      minReplicas: 3
      maxReplicas: 10
      metrics:
      - type: Resource
        resource:
          name: cpu
          target:
            type: Utilization
            averageUtilization: 70
      - type: Resource
        resource:
          name: memory
          target:
            type: Utilization
            averageUtilization: 80
      behavior:
        scaleDown:
          stabilizationWindowSeconds: 300
          policies:
          - type: Percent
            value: 50
            periodSeconds: 60
        scaleUp:
          stabilizationWindowSeconds: 0
          policies:
          - type: Percent
            value: 100
            periodSeconds: 30
          - type: Pods
            value: 2
            periodSeconds: 60
    """
    
    min_instances: int = 2
    max_instances: int = 10
    target_cpu_percent: float = 70.0
    target_memory_percent: float = 80.0
    scale_up_cooldown: int = 180  # seconds
    scale_down_cooldown: int = 300  # seconds


# ============================================
# KUBERNETES MANIFESTS
# ============================================

KUBERNETES_DEPLOYMENT = """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ocr-api
  labels:
    app: ocr-api
spec:
  replicas: 3  # Initial replicas
  selector:
    matchLabels:
      app: ocr-api
  template:
    metadata:
      labels:
        app: ocr-api
    spec:
      containers:
      - name: ocr-api
        image: your-registry/ocr-api:latest
        ports:
        - containerPort: 8000
        env:
        - name: REDIS_HOST
          value: redis-service
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: db-secret
              key: url
        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "2Gi"
            cpu: "2000m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: ocr-api-service
spec:
  selector:
    app: ocr-api
  ports:
  - protocol: TCP
    port: 80
    targetPort: 8000
  type: LoadBalancer
"""

# ============================================
# AWS AUTO SCALING
# ============================================

AWS_AUTOSCALING_CONFIG = """
# AWS Auto Scaling Group configuration

{
  "AutoScalingGroupName": "ocr-api-asg",
  "LaunchTemplate": {
    "LaunchTemplateId": "lt-xxxxx",
    "Version": "$Latest"
  },
  "MinSize": 2,
  "MaxSize": 10,
  "DesiredCapacity": 3,
  "DefaultCooldown": 300,
  "HealthCheckType": "ELB",
  "HealthCheckGracePeriod": 300,
  "VPCZoneIdentifier": "subnet-xxxxx,subnet-yyyyy",
  "TargetGroupARNs": ["arn:aws:elasticloadbalancing:..."],
  "Tags": [
    {
      "Key": "Name",
      "Value": "ocr-api-instance",
      "PropagateAtLaunch": true
    }
  ]
}

# Scaling Policies

# Scale Up Policy
{
  "PolicyName": "scale-up-policy",
  "PolicyType": "TargetTrackingScaling",
  "TargetTrackingConfiguration": {
    "PredefinedMetricSpecification": {
      "PredefinedMetricType": "ASGAverageCPUUtilization"
    },
    "TargetValue": 70.0
  }
}

# Scale Down Policy
{
  "PolicyName": "scale-down-policy",
  "PolicyType": "StepScaling",
  "StepAdjustments": [
    {
      "MetricIntervalUpperBound": 0,
      "ScalingAdjustment": -1
    }
  ],
  "AdjustmentType": "ChangeInCapacity",
  "Cooldown": 300
}

# CloudWatch Alarms

# High CPU Alarm
{
  "AlarmName": "ocr-api-high-cpu",
  "ComparisonOperator": "GreaterThanThreshold",
  "EvaluationPeriods": 2,
  "MetricName": "CPUUtilization",
  "Namespace": "AWS/EC2",
  "Period": 60,
  "Statistic": "Average",
  "Threshold": 70.0,
  "ActionsEnabled": true,
  "AlarmActions": ["arn:aws:autoscaling:..."]
}
"""

# ============================================
# DOCKER SWARM AUTO SCALING
# ============================================

DOCKER_SWARM_CONFIG = """
version: '3.8'

services:
  ocr-api:
    image: your-registry/ocr-api:latest
    deploy:
      replicas: 3
      update_config:
        parallelism: 1
        delay: 10s
      restart_policy:
        condition: on-failure
      resources:
        limits:
          cpus: '2'
          memory: 2G
        reservations:
          cpus: '0.5'
          memory: 512M
    ports:
      - "8000:8000"
    networks:
      - app-network
    environment:
      - REDIS_HOST=redis
      - DATABASE_URL=${DATABASE_URL}

networks:
  app-network:
    driver: overlay
"""


# ============================================
# METRICS COLLECTOR FOR AUTO-SCALING
# ============================================

class MetricsCollector:
    """
    Collect metrics for auto-scaling decisions.
    
    Integrates with Prometheus, CloudWatch, etc.
    """
    
    def __init__(self):
        self.metrics_history: List[Dict] = []
    
    def collect_metrics(self) -> Dict[str, float]:
        """
        Collect current metrics.
        
        Returns:
            Dictionary of current metrics
        """
        import psutil
        
        # System metrics
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        memory_percent = memory.percent
        
        # Network metrics (simplified)
        # In production, get from Prometheus/CloudWatch
        request_rate = self._get_request_rate()
        avg_response_time = self._get_avg_response_time()
        queue_depth = self._get_queue_depth()
        
        metrics = {
            "cpu_usage": cpu_percent,
            "memory_usage": memory_percent,
            "request_rate": request_rate,
            "response_time": avg_response_time,
            "queue_depth": queue_depth,
            "timestamp": datetime.now().isoformat()
        }
        
        # Store history
        self.metrics_history.append(metrics)
        
        # Keep last hour
        cutoff = datetime.now() - timedelta(hours=1)
        self.metrics_history = [
            m for m in self.metrics_history
            if datetime.fromisoformat(m["timestamp"]) > cutoff
        ]
        
        return metrics
    
    def should_scale(
        self,
        config: AutoScalingConfig
    ) -> Optional[str]:
        """
        Determine if scaling is needed.
        
        Args:
            config: Auto-scaling configuration
        
        Returns:
            "scale_up", "scale_down", or None
        """
        metrics = self.collect_metrics()
        
        # Check scale up conditions
        if (metrics["cpu_usage"] > config.target_cpu_percent or
            metrics["memory_usage"] > config.target_memory_percent):
            return "scale_up"
        
        # Check scale down conditions
        if (metrics["cpu_usage"] < config.target_cpu_percent * 0.5 and
            metrics["memory_usage"] < config.target_memory_percent * 0.5):
            return "scale_down"
        
        return None
    
    def _get_request_rate(self) -> float:
        """Get current request rate (req/s)"""
        # In production: query from metrics system
        return 100.0
    
    def _get_avg_response_time(self) -> float:
        """Get average response time (ms)"""
        # In production: query from metrics system
        return 50.0
    
    def _get_queue_depth(self) -> int:
        """Get current queue depth"""
        # In production: query from message queue
        return 10


if __name__ == "__main__":
    print("="*60)
    print("AUTO-SCALING CONFIGURATION")
    print("="*60)
    
    config = AutoScalingConfig(
        min_instances=2,
        max_instances=10,
        target_cpu_percent=70.0,
        target_memory_percent=80.0
    )
    
    print(f"\nConfiguration:")
    print(f"  Min instances: {config.min_instances}")
    print(f"  Max instances: {config.max_instances}")
    print(f"  Target CPU: {config.target_cpu_percent}%")
    print(f"  Target Memory: {config.target_memory_percent}%")
    
    # Test metrics collection
    collector = MetricsCollector()
    metrics = collector.collect_metrics()
    
    print(f"\nCurrent Metrics:")
    print(f"  CPU: {metrics['cpu_usage']:.1f}%")
    print(f"  Memory: {metrics['memory_usage']:.1f}%")
    print(f"  Request rate: {metrics['request_rate']:.1f} req/s")
    print(f"  Response time: {metrics['response_time']:.1f} ms")
    
    # Check scaling decision
    decision = collector.should_scale(config)
    print(f"\nScaling Decision: {decision or 'No action needed'}")

⚖️ LOAD BALANCING
1. Nginx Configuration
nginx# nginx/load_balancer.conf

# ============================================
# NGINX LOAD BALANCER CONFIGURATION
# ============================================

# Upstream servers (backend instances)
upstream ocr_api_backend {
    # Load balancing method: least_conn, ip_hash, round_robin (default)
    least_conn;  # Route to server with least connections
    
    # Backend servers
    server 10.0.1.10:8000 weight=3 max_fails=3 fail_timeout=30s;
    server 10.0.1.11:8000 weight=3 max_fails=3 fail_timeout=30s;
    server 10.0.1.12:8000 weight=2 max_fails=3 fail_timeout=30s;  # Lower weight (less capacity)
    
    # Backup server (only used when all others fail)
    server 10.0.1.20:8000 backup;
    
    # Health check (Nginx Plus feature)
    # For open-source Nginx, use external health checks
    
    # Keep-alive connections to upstream
    keepalive 32;
    keepalive_timeout 60s;
}

# HTTP Server
server {
    listen 80;
    listen [::]:80;
    server_name api.example.com;
    
    # Redirect HTTP to HTTPS
    return 301 https://$server_name$request_uri;
}

# HTTPS Server
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name api.example.com;
    
    # SSL Configuration
    ssl_certificate /etc/nginx/ssl/cert.pem;
    ssl_certificate_key /etc/nginx/ssl/key.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;
    
    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Content-Type-Options nosniff always;
    add_header X-Frame-Options DENY always;
    add_header X-XSS-Protection "1; mode=block" always;
    
    # Client body size limit
    client_max_body_size 100M;
    
    # Timeouts
    proxy_connect_timeout 60s;
    proxy_send_timeout 60s;
    proxy_read_timeout 60s;
    
    # Buffering
    proxy_buffering on;
    proxy_buffer_size 4k;
    proxy_buffers 8 4k;
    proxy_busy_buffers_size 8k;
    
    # Logging
    access_log /var/log/nginx/api_access.log combined;
    error_log /var/log/nginx/api_error.log warn;
    
    # Health check endpoint (bypass load balancer)
    location /health {
        access_log off;
        return 200 "healthy\n";
        add_header Content-Type text/plain;
    }
    
    # API endpoints
    location / {
        # Proxy to backend
        proxy_pass http://ocr_api_backend;
        
        # Headers
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Request-ID $request_id;
        
        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        
        # Keep-alive
        proxy_set_header Connection "";
        
        # Enable response compression
        gzip on;
        gzip_types application/json text/plain text/css application/javascript;
        gzip_min_length 1000;
    }
    
    # Static files (served directly by Nginx)
    location /static/ {
        alias /var/www/static/;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
    
    # Rate limiting for API
    limit_req_zone $binary_remote_addr zone=api_limit:10m rate=100r/s;
    limit_req_zone $binary_remote_addr zone=ocr_limit:10m rate=10r/s;
    
    location /api/ {
        limit_req zone=api_limit burst=200 nodelay;
        proxy_pass http://ocr_api_backend;
        
        # Standard proxy headers
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
    
    location /ocr/process {
        # Stricter rate limit for expensive OCR endpoint
        limit_req zone=ocr_limit burst=20 nodelay;
        proxy_pass http://ocr_api_backend;
        
        # Longer timeout for OCR processing
        proxy_read_timeout 300s;
        
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}

# ============================================
# ADVANCED: STICKY SESSIONS (if needed)
# ============================================

# Note: Only use if you MUST have stateful sessions
# Better approach: Make application stateless!

upstream ocr_api_sticky {
    # IP hash - same client always goes to same server
    ip_hash;
    
    server 10.0.1.10:8000;
    server 10.0.1.11:8000;
    server 10.0.1.12:8000;
}

# Alternative: Cookie-based sticky sessions (Nginx Plus)
# upstream ocr_api_sticky {
#     server 10.0.1.10:8000;
#     server 10.0.1.11:8000;
#     server 10.0.1.12:8000;
#     
#     sticky cookie srv_id expires=1h domain=.example.com path=/;
# }
2. HAProxy Configuration
haproxy# haproxy/haproxy.cfg

# ============================================
# HAPROXY LOAD BALANCER CONFIGURATION
# ============================================

global
    # Maximum connections
    maxconn 4096
    
    # Logging
    log /dev/log local0
    log /dev/log local1 notice
    
    # SSL
    ssl-default-bind-ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256
    ssl-default-bind-options ssl-min-ver TLSv1.2 no-tls-tickets
    
    # Process/thread settings
    nbproc 1
    nbthread 4
    cpu-map auto:1/1-4 0-3
    
    # Stats socket
    stats socket /var/run/haproxy.sock mode 600 level admin
    stats timeout 30s

defaults
    # Mode
    mode http
    
    # Logging
    log global
    option httplog
    option dontlognull
    
    # Timeouts
    timeout connect 5s
    timeout client 50s
    timeout server 50s
    timeout http-request 10s
    timeout http-keep-alive 10s
    
    # Error files
    errorfile 400 /etc/haproxy/errors/400.http
    errorfile 403 /etc/haproxy/errors/403.http
    errorfile 408 /etc/haproxy/errors/408.http
    errorfile 500 /etc/haproxy/errors/500.http
    errorfile 502 /etc/haproxy/errors/502.http
    errorfile 503 /etc/haproxy/errors/503.http
    errorfile 504 /etc/haproxy/errors/504.http
    
    # Compression
    compression algo gzip
    compression type text/html text/plain text/css application/javascript application/json

# ============================================
# FRONTEND (Entry point)
# ============================================

frontend http_frontend
    # Bind to port 80
    bind *:80
    
    # Redirect HTTP to HTTPS
    redirect scheme https code 301 if !{ ssl_fc }

frontend https_frontend
    # Bind to port 443 with SSL
    bind *:443 ssl crt /etc/haproxy/certs/api.example.com.pem
    
    # Security headers
    http-response set-header Strict-Transport-Security "max-age=31536000; includeSubDomains"
    http-response set-header X-Content-Type-Options nosniff
    http-response set-header X-Frame-Options DENY
    http-response set-header X-XSS-Protection "1; mode=block"
    
    # Request ID
    unique-id-format %{+X}o\ %ci:%cp_%fi:%fp_%Ts_%rt:%pid
    unique-id-header X-Request-ID
    
    # ACLs (Access Control Lists)
    acl is_health_check path /health
    acl is_api path_beg /api/
    acl is_ocr path_beg /ocr/
    acl is_static path_beg /static/
    
    # Rate limiting
    stick-table type ip size 100k expire 30s store http_req_rate(10s)
    http-request track-sc0 src
    http-request deny if { sc_http_req_rate(0) gt 100 }
    
    # Routing
    use_backend health_backend if is_health_check
    use_backend api_backend if is_api
    use_backend ocr_backend if is_ocr
    use_backend static_backend if is_static
    default_backend api_backend

# ============================================
# BACKENDS (Server pools)
# ============================================

backend health_backend
    # Health check returns OK without hitting backends
    mode http
    http-request return status 200 content-type text/plain string "OK"

backend api_backend
    # Load balancing algorithm
    balance leastconn  # Route to server with least connections
    
    # Health checks
    option httpchk GET /health HTTP/1.1\r\nHost:\ api.example.com
    http-check expect status 200
    
    # Server options
    default-server inter 3s fall 3 rise 2
    
    # Servers
    server app1 10.0.1.10:8000 check weight 100 maxconn 1000
    server app2 10.0.1.11:8000 check weight 100 maxconn 1000
    server app3 10.0.1.12:8000 check weight 80 maxconn 800
    server app4 10.0.1.13:8000 check backup  # Backup server
    
    # Headers
    http-request set-header X-Forwarded-Proto https if { ssl_fc }
    http-request set-header X-Forwarded-For %[src]
    
    # Connection pooling
    option http-server-close
    option forwardfor

backend ocr_backend
    # OCR processing backend
    balance roundrobin
    
    # Longer timeout for OCR processing
    timeout server 300s
    
    # Health checks
    option httpchk GET /health
    http-check expect status 200
    
    # Servers
    server ocr1 10.0.2.10:8000 check weight 100
    server ocr2 10.0.2.11:8000 check weight 100
    server ocr3 10.0.2.12:8000 check weight 100
    
    # Rate limiting per server
    stick-table type ip size 100k expire 30s store http_req_rate(10s)
    http-request track-sc1 src
    http-request deny if { sc_http_req_rate(1) gt 10 }

backend static_backend
    # Static file serving
    balance roundrobin
    
    server static1 10.0.3.10:80 check
    server static2 10.0.3.11:80 check
    
    # Caching headers
    http-response set-header Cache-Control "public, max-age=31536000"

# ============================================
# STATISTICS PAGE
# ============================================

listen stats
    bind *:8404
    stats enable
    stats uri /stats
    stats refresh 30s
    stats admin if TRUE
    
    # Authentication
    stats auth admin:your-secure-password
    
    # Hide version
    stats hide-version

# ============================================
# ADVANCED: STICKY SESSIONS
# ============================================

backend api_backend_sticky
    # Cookie-based sticky sessions
    balance roundrobin
    cookie SERVERID insert indirect nocache
    
    server app1 10.0.1.10:8000 check cookie app1
    server app2 10.0.1.11:8000 check cookie app2
    server app3 10.0.1.12:8000 check cookie app3



 SCALABILITY & PERFORMANCE GUIDE - TEIL 2
Database Optimization, Connection Pooling & Async Processing

📋 TABLE OF CONTENTS (TEIL 2)

Database Read Replicas
Connection Pooling
Async Processing


💾 DATABASE READ REPLICAS
1. PostgreSQL Master-Slave Replication
python# database/replication.py

"""
Database Read Replicas

Master-slave replication for read scaling
"""

from typing import Optional, List, Dict, Any
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool
from contextlib import contextmanager
from enum import Enum
import random
from loguru import logger


class DatabaseRole(Enum):
    """Database role"""
    MASTER = "master"  # Write operations
    SLAVE = "slave"    # Read operations


class DatabaseConfig:
    """
    Database configuration with replication.
    
    Architecture:
    
    ┌──────────────────────────────────────────┐
    │         Application Layer                │
    └──────────┬───────────────────────────────┘
               │
               ├─── Writes ────────────────────┐
               │                               │
               │                          ┌────▼─────┐
               │                          │  Master  │
               │                          │    DB    │
               │                          └────┬─────┘
               │                               │
               │                    Replication│
               │                          (async)
               │                               │
               │              ┌────────────────┼────────────┐
               │              │                │            │
               │         ┌────▼─────┐    ┌────▼─────┐ ┌───▼──────┐
               └─Reads──│  Slave 1 │    │ Slave 2  │ │ Slave 3  │
                        │    DB    │    │   DB     │ │   DB     │
                        └──────────┘    └──────────┘ └──────────┘
    
    Benefits:
    - Scale read operations horizontally
    - Offload analytics/reports to slaves
    - High availability (failover to slave)
    - Geographic distribution
    """
    
    def __init__(
        self,
        master_url: str,
        slave_urls: List[str],
        pool_size: int = 20,
        max_overflow: int = 10
    ):
        """
        Initialize database config with replication.
        
        Args:
            master_url: Master database URL (write)
            slave_urls: List of slave database URLs (read)
            pool_size: Connection pool size per database
            max_overflow: Max overflow connections
        """
        self.master_url = master_url
        self.slave_urls = slave_urls
        
        # Create engines
        self.master_engine = create_engine(
            master_url,
            poolclass=QueuePool,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_pre_ping=True,  # Verify connections
            echo=False
        )
        
        self.slave_engines = [
            create_engine(
                url,
                poolclass=QueuePool,
                pool_size=pool_size,
                max_overflow=max_overflow,
                pool_pre_ping=True,
                echo=False
            )
            for url in slave_urls
        ]
        
        # Session makers
        self.MasterSession = sessionmaker(bind=self.master_engine)
        self.SlaveSession = sessionmaker(bind=self._get_slave_engine())
        
        logger.info(
            f"Database replication configured: "
            f"1 master, {len(slave_urls)} slaves"
        )
    
    def _get_slave_engine(self):
        """
        Get slave engine with load balancing.
        
        Uses round-robin by default.
        Could implement weighted random, least connections, etc.
        """
        if not self.slave_engines:
            logger.warning("No slave DBs, using master for reads")
            return self.master_engine
        
        # Simple round-robin
        # In production: use more sophisticated load balancing
        return random.choice(self.slave_engines)
    
    @contextmanager
    def get_session(
        self,
        role: DatabaseRole = DatabaseRole.SLAVE
    ) -> Session:
        """
        Get database session.
        
        Args:
            role: Database role (master for writes, slave for reads)
        
        Yields:
            SQLAlchemy session
        
        Example:
            # Read operation
            with db.get_session(DatabaseRole.SLAVE) as session:
                users = session.query(User).all()
            
            # Write operation
            with db.get_session(DatabaseRole.MASTER) as session:
                session.add(new_user)
                session.commit()
        """
        if role == DatabaseRole.MASTER:
            session = self.MasterSession()
        else:
            # Get random slave for read
            engine = self._get_slave_engine()
            SessionMaker = sessionmaker(bind=engine)
            session = SessionMaker()
        
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            session.close()


# ============================================
# ROUTING READS/WRITES AUTOMATICALLY
# ============================================

class RoutingSession(Session):
    """
    SQLAlchemy session that automatically routes reads/writes.
    
    - SELECT queries → Slave
    - INSERT/UPDATE/DELETE → Master
    """
    
    def __init__(self, db_config: DatabaseConfig, **kwargs):
        self.db_config = db_config
        self._in_transaction = False
        
        # Start with slave engine for reads
        super().__init__(bind=db_config._get_slave_engine(), **kwargs)
    
    def execute(self, statement, *args, **kwargs):
        """Override execute to route based on operation"""
        
        # Convert to string to check operation type
        sql = str(statement).strip().upper()
        
        # Check if write operation
        is_write = any(
            sql.startswith(op)
            for op in ['INSERT', 'UPDATE', 'DELETE', 'CREATE', 'ALTER', 'DROP']
        )
        
        # If write operation or in transaction, use master
        if is_write or self._in_transaction:
            if self.bind != self.db_config.master_engine:
                self.bind = self.db_config.master_engine
                logger.debug("Routing to master for write operation")
        
        return super().execute(statement, *args, **kwargs)
    
    def begin(self, *args, **kwargs):
        """Begin transaction - always use master"""
        self._in_transaction = True
        self.bind = self.db_config.master_engine
        return super().begin(*args, **kwargs)
    
    def commit(self):
        """Commit transaction"""
        result = super().commit()
        self._in_transaction = False
        return result
    
    def rollback(self):
        """Rollback transaction"""
        result = super().rollback()
        self._in_transaction = False
        return result


# ============================================
# REPOSITORY PATTERN WITH REPLICATION
# ============================================

from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String, DateTime, Text
from datetime import datetime

Base = declarative_base()


class Document(Base):
    """Document model"""
    __tablename__ = 'documents'
    
    id = Column(Integer, primary_key=True)
    filename = Column(String(255), nullable=False)
    content = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class DocumentRepository:
    """
    Repository pattern with read/write separation.
    
    Automatically routes operations to correct database.
    """
    
    def __init__(self, db_config: DatabaseConfig):
        self.db = db_config
    
    def create(self, document: Document) -> Document:
        """
        Create document (write → master).
        
        Args:
            document: Document to create
        
        Returns:
            Created document
        """
        with self.db.get_session(DatabaseRole.MASTER) as session:
            session.add(document)
            session.flush()
            session.refresh(document)
            return document
    
    def get_by_id(self, doc_id: int) -> Optional[Document]:
        """
        Get document by ID (read → slave).
        
        Args:
            doc_id: Document ID
        
        Returns:
            Document or None
        """
        with self.db.get_session(DatabaseRole.SLAVE) as session:
            return session.query(Document).filter(
                Document.id == doc_id
            ).first()
    
    def get_all(
        self,
        limit: int = 100,
        offset: int = 0
    ) -> List[Document]:
        """
        Get all documents (read → slave).
        
        Args:
            limit: Max results
            offset: Skip results
        
        Returns:
            List of documents
        """
        with self.db.get_session(DatabaseRole.SLAVE) as session:
            return session.query(Document)\
                .limit(limit)\
                .offset(offset)\
                .all()
    
    def update(
        self,
        doc_id: int,
        updates: Dict[str, Any]
    ) -> Optional[Document]:
        """
        Update document (write → master).
        
        Args:
            doc_id: Document ID
            updates: Fields to update
        
        Returns:
            Updated document or None
        """
        with self.db.get_session(DatabaseRole.MASTER) as session:
            document = session.query(Document).filter(
                Document.id == doc_id
            ).first()
            
            if document:
                for key, value in updates.items():
                    setattr(document, key, value)
                
                session.flush()
                session.refresh(document)
            
            return document
    
    def delete(self, doc_id: int) -> bool:
        """
        Delete document (write → master).
        
        Args:
            doc_id: Document ID
        
        Returns:
            True if deleted
        """
        with self.db.get_session(DatabaseRole.MASTER) as session:
            document = session.query(Document).filter(
                Document.id == doc_id
            ).first()
            
            if document:
                session.delete(document)
                return True
            
            return False
    
    def search(
        self,
        query: str,
        limit: int = 50
    ) -> List[Document]:
        """
        Search documents (read → slave).
        
        Heavy read operation - perfect for slave.
        
        Args:
            query: Search query
            limit: Max results
        
        Returns:
            Matching documents
        """
        with self.db.get_session(DatabaseRole.SLAVE) as session:
            return session.query(Document)\
                .filter(Document.content.ilike(f'%{query}%'))\
                .limit(limit)\
                .all()


# ============================================
# POSTGRESQL REPLICATION SETUP
# ============================================

POSTGRESQL_REPLICATION_SETUP = """
# ============================================
# PostgreSQL Streaming Replication Setup
# ============================================

# MASTER SERVER Configuration (postgresql.conf)
# ----------------------------------------------

# Enable WAL archiving
wal_level = replica

# Max number of replication connections
max_wal_senders = 10

# WAL segments to keep
wal_keep_size = 1GB

# Synchronous replication (optional, for zero data loss)
synchronous_commit = on
synchronous_standby_names = 'slave1,slave2'

# Connection settings
listen_addresses = '*'
max_connections = 200


# MASTER SERVER Access (pg_hba.conf)
# ----------------------------------------------

# Allow replication connections
host    replication     replicator      10.0.1.0/24         md5


# Create replication user
# ----------------------------------------------

CREATE ROLE replicator WITH REPLICATION LOGIN PASSWORD 'secure_password';


# SLAVE SERVER Configuration (postgresql.conf)
# ----------------------------------------------

# Hot standby allows read queries
hot_standby = on

# Replication settings
primary_conninfo = 'host=10.0.1.10 port=5432 user=replicator password=secure_password'
primary_slot_name = 'slave1_slot'


# Initialize Slave (on slave server)
# ----------------------------------------------

# 1. Stop PostgreSQL on slave
systemctl stop postgresql

# 2. Backup existing data
mv /var/lib/postgresql/14/main /var/lib/postgresql/14/main.bak

# 3. Base backup from master
pg_basebackup -h 10.0.1.10 -D /var/lib/postgresql/14/main -U replicator -P -v -R

# 4. Start PostgreSQL on slave
systemctl start postgresql


# Create replication slot on master (optional but recommended)
# ----------------------------------------------

SELECT pg_create_physical_replication_slot('slave1_slot');


# Check replication status
# ----------------------------------------------

# On master
SELECT * FROM pg_stat_replication;

# On slave
SELECT * FROM pg_stat_wal_receiver;


# Monitoring queries
# ----------------------------------------------

-- Check replication lag (on slave)
SELECT 
    CASE 
        WHEN pg_last_wal_receive_lsn() = pg_last_wal_replay_lsn() 
        THEN 0 
        ELSE EXTRACT(EPOCH FROM now() - pg_last_xact_replay_timestamp())::INT 
    END AS lag_seconds;

-- List all slaves (on master)
SELECT 
    client_addr,
    state,
    sync_state,
    pg_wal_lsn_diff(pg_current_wal_lsn(), sent_lsn) AS send_lag,
    pg_wal_lsn_diff(pg_current_wal_lsn(), write_lsn) AS write_lag,
    pg_wal_lsn_diff(pg_current_wal_lsn(), flush_lsn) AS flush_lag,
    pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn) AS replay_lag
FROM pg_stat_replication;
"""


# ============================================
# DOCKER COMPOSE FOR REPLICATION
# ============================================

DOCKER_COMPOSE_REPLICATION = """
version: '3.8'

services:
  # Master Database
  postgres-master:
    image: postgres:15
    environment:
      POSTGRES_USER: admin
      POSTGRES_PASSWORD: admin_password
      POSTGRES_DB: ocr_db
    volumes:
      - master-data:/var/lib/postgresql/data
      - ./init-master.sh:/docker-entrypoint-initdb.d/init-master.sh
    ports:
      - "5432:5432"
    networks:
      - db-network
    command: 
      - postgres
      - -c
      - wal_level=replica
      - -c
      - max_wal_senders=10
      - -c
      - wal_keep_size=1GB

  # Slave Database 1
  postgres-slave1:
    image: postgres:15
    environment:
      POSTGRES_USER: admin
      POSTGRES_PASSWORD: admin_password
      PGUSER: replicator
      PGPASSWORD: replicator_password
    depends_on:
      - postgres-master
    volumes:
      - slave1-data:/var/lib/postgresql/data
      - ./init-slave.sh:/docker-entrypoint-initdb.d/init-slave.sh
    ports:
      - "5433:5432"
    networks:
      - db-network
    command:
      - bash
      - -c
      - |
        # Wait for master
        until pg_isready -h postgres-master -p 5432; do
          sleep 1
        done
        
        # Base backup
        rm -rf /var/lib/postgresql/data/*
        pg_basebackup -h postgres-master -D /var/lib/postgresql/data -U replicator -P -R
        
        # Start postgres
        postgres -c hot_standby=on

  # Slave Database 2
  postgres-slave2:
    image: postgres:15
    environment:
      POSTGRES_USER: admin
      POSTGRES_PASSWORD: admin_password
      PGUSER: replicator
      PGPASSWORD: replicator_password
    depends_on:
      - postgres-master
    volumes:
      - slave2-data:/var/lib/postgresql/data
    ports:
      - "5434:5432"
    networks:
      - db-network
    command:
      - bash
      - -c
      - |
        until pg_isready -h postgres-master -p 5432; do
          sleep 1
        done
        rm -rf /var/lib/postgresql/data/*
        pg_basebackup -h postgres-master -D /var/lib/postgresql/data -U replicator -P -R
        postgres -c hot_standby=on

volumes:
  master-data:
  slave1-data:
  slave2-data:

networks:
  db-network:
    driver: bridge
"""


# ============================================
# EXAMPLE USAGE
# ============================================

if __name__ == "__main__":
    # Setup database configuration
    db_config = DatabaseConfig(
        master_url="postgresql://admin:password@localhost:5432/ocr_db",
        slave_urls=[
            "postgresql://admin:password@localhost:5433/ocr_db",
            "postgresql://admin:password@localhost:5434/ocr_db"
        ]
    )
    
    # Create repository
    repo = DocumentRepository(db_config)
    
    print("="*60)
    print("DATABASE REPLICATION EXAMPLE")
    print("="*60)
    
    # Create document (write → master)
    print("\n1. Creating document (WRITE → MASTER)...")
    doc = Document(
        filename="test.pdf",
        content="Test content"
    )
    created_doc = repo.create(doc)
    print(f"   Created document ID: {created_doc.id}")
    
    # Read document (read → slave)
    print("\n2. Reading document (READ → SLAVE)...")
    fetched_doc = repo.get_by_id(created_doc.id)
    if fetched_doc:
        print(f"   Fetched: {fetched_doc.filename}")
    
    # Search (heavy read → slave)
    print("\n3. Searching documents (READ → SLAVE)...")
    results = repo.search("test")
    print(f"   Found {len(results)} documents")
    
    # Update (write → master)
    print("\n4. Updating document (WRITE → MASTER)...")
    repo.update(created_doc.id, {"content": "Updated content"})
    print("   Updated")
    
    print("\n" + "="*60)
    print("All operations routed correctly!")
    print("Writes → Master | Reads → Slaves")
    print("="*60)

🔌 CONNECTION POOLING
1. Advanced Connection Pool Configuration
python# database/connection_pool.py

"""
Advanced Connection Pooling

Optimize database connections for high concurrency
"""

from typing import Optional, Dict, Any
from sqlalchemy import create_engine, event, pool
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool, NullPool, StaticPool
import time
from contextlib import contextmanager
from loguru import logger


class OptimizedConnectionPool:
    """
    Optimized connection pool configuration.
    
    Connection Pool Benefits:
    - Reuse connections (avoid connection overhead)
    - Limit concurrent connections
    - Handle connection failures gracefully
    - Improve application performance
    
    Pool Types:
    - QueuePool: Standard, best for most cases
    - NullPool: No pooling, create new connection each time
    - StaticPool: Single connection, good for SQLite
    - AsyncPool: For async frameworks
    """
    
    def __init__(
        self,
        database_url: str,
        pool_size: int = 20,
        max_overflow: int = 10,
        pool_timeout: float = 30.0,
        pool_recycle: int = 3600,
        pool_pre_ping: bool = True,
        echo_pool: bool = False
    ):
        """
        Initialize optimized connection pool.
        
        Args:
            database_url: Database URL
            pool_size: Number of persistent connections
            max_overflow: Additional connections when pool exhausted
            pool_timeout: Seconds to wait for connection
            pool_recycle: Recycle connections after N seconds
            pool_pre_ping: Check connection health before use
            echo_pool: Log pool events
        
        Connection Limits:
        - Total connections = pool_size + max_overflow
        - Example: pool_size=20, max_overflow=10 → max 30 connections
        
        Choosing Pool Size:
        - Consider: CPU cores, database max connections, app instances
        - Formula: (cpu_cores * 2) + effective_spindle_count
        - For 4 cores: ~10-20 connections
        - For 16 cores: ~40-80 connections
        
        Example Scenarios:
        
        1. Small API (1 server, 4 cores):
           pool_size=10, max_overflow=5
        
        2. Medium API (3 servers, 8 cores each):
           pool_size=15, max_overflow=10 (per server)
           Total: 3 * (15+10) = 75 max connections
        
        3. Large API (10 servers, 16 cores each):
           pool_size=20, max_overflow=10 (per server)
           Total: 10 * (20+10) = 300 max connections
           Database must support 300+ connections!
        """
        self.database_url = database_url
        
        # Create engine with optimized pool
        self.engine = create_engine(
            database_url,
            
            # Pool configuration
            poolclass=QueuePool,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_timeout=pool_timeout,
            pool_recycle=pool_recycle,
            pool_pre_ping=pool_pre_ping,
            
            # Connection options
            connect_args={
                "connect_timeout": 10,
                "application_name": "ocr_api",
                # PostgreSQL specific optimizations
                "options": "-c statement_timeout=30000"  # 30 seconds
            },
            
            # Execution options
            execution_options={
                "isolation_level": "READ COMMITTED"
            },
            
            # Logging
            echo=False,
            echo_pool=echo_pool
        )
        
        # Setup event listeners
        self._setup_event_listeners()
        
        # Create session factory
        self.SessionFactory = sessionmaker(bind=self.engine)
        
        logger.info(
            f"Connection pool initialized: "
            f"size={pool_size}, max_overflow={max_overflow}"
        )
    
    def _setup_event_listeners(self):
        """Setup SQLAlchemy event listeners for monitoring"""
        
        @event.listens_for(self.engine, "connect")
        def receive_connect(dbapi_conn, connection_record):
            """Event: New connection created"""
            logger.debug("New database connection created")
        
        @event.listens_for(self.engine, "checkout")
        def receive_checkout(dbapi_conn, connection_record, connection_proxy):
            """Event: Connection checked out from pool"""
            # Get pool stats
            pool = self.engine.pool
            logger.debug(
                f"Connection checkout: "
                f"size={pool.size()}, "
                f"checked_out={pool.checkedout()}, "
                f"overflow={pool.overflow()}"
            )
        
        @event.listens_for(self.engine, "checkin")
        def receive_checkin(dbapi_conn, connection_record):
            """Event: Connection returned to pool"""
            logger.debug("Connection returned to pool")
        
        @event.listens_for(self.engine, "reset")
        def receive_reset(dbapi_conn, connection_record):
            """Event: Connection reset"""
            logger.debug("Connection reset")
        
        @event.listens_for(self.engine, "close")
        def receive_close(dbapi_conn, connection_record):
            """Event: Connection closed"""
            logger.debug("Connection closed")
    
    @contextmanager
    def get_session(self) -> Session:
        """
        Get database session with automatic cleanup.
        
        Yields:
            SQLAlchemy session
        
        Example:
            with pool.get_session() as session:
                user = session.query(User).first()
        """
        session = self.SessionFactory()
        
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Session error: {e}")
            raise
        finally:
            session.close()
    
    def get_pool_status(self) -> Dict[str, Any]:
        """
        Get connection pool statistics.
        
        Returns:
            Pool status dictionary
        """
        pool = self.engine.pool
        
        return {
            "size": pool.size(),
            "checked_out": pool.checkedout(),
            "overflow": pool.overflow(),
            "total_connections": pool.size() + pool.overflow(),
            "available": pool.size() - pool.checkedout(),
            "queue_size": getattr(pool, '_queue', []) and len(pool._queue.queue) or 0
        }
    
    def dispose(self):
        """Dispose all connections in pool"""
        self.engine.dispose()
        logger.info("Connection pool disposed")


# ============================================
# CONNECTION POOL SIZING CALCULATOR
# ============================================

class PoolSizeCalculator:
    """
    Calculate optimal connection pool size.
    
    Based on:
    - Number of CPU cores
    - Expected concurrent requests
    - Database capabilities
    - Application instances
    """
    
    @staticmethod
    def calculate(
        cpu_cores: int,
        app_instances: int = 1,
        db_max_connections: int = 100,
        safety_margin: float = 0.8
    ) -> Dict[str, int]:
        """
        Calculate optimal pool settings.
        
        Args:
            cpu_cores: CPU cores per instance
            app_instances: Number of app instances
            db_max_connections: Database max connections
            safety_margin: Use 80% of max connections
        
        Returns:
            Pool configuration dictionary
        """
        # Formula: (cores * 2) + effective_spindle_count
        # For modern SSDs, spindle count ≈ 1
        base_pool_size = (cpu_cores * 2) + 1
        
        # Add overflow for bursts (50% of base)
        overflow = int(base_pool_size * 0.5)
        
        # Total connections per instance
        total_per_instance = base_pool_size + overflow
        
        # Total across all instances
        total_connections = total_per_instance * app_instances
        
        # Check against database limit
        db_limit = int(db_max_connections * safety_margin)
        
        if total_connections > db_limit:
            # Scale down
            total_per_instance = db_limit // app_instances
            base_pool_size = int(total_per_instance * 0.67)
            overflow = total_per_instance - base_pool_size
        
        return {
            "pool_size": base_pool_size,
            "max_overflow": overflow,
            "total_per_instance": base_pool_size + overflow,
            "total_all_instances": (base_pool_size + overflow) * app_instances,
            "recommendation": f"pool_size={base_pool_size}, max_overflow={overflow}"
        }


# ============================================
# ASYNC CONNECTION POOL (for FastAPI/asyncio)
# ============================================

from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker
)


class AsyncConnectionPool:
    """
    Async connection pool for async frameworks.
    
    Use with FastAPI, aiohttp, etc.
    """
    
    def __init__(
        self,
        database_url: str,
        pool_size: int = 20,
        max_overflow: int = 10
    ):
        """
        Initialize async connection pool.
        
        Args:
            database_url: Async database URL (postgresql+asyncpg://)
            pool_size: Pool size
            max_overflow: Max overflow
        """
        # Convert URL to async
        if database_url.startswith("postgresql://"):
            database_url = database_url.replace(
                "postgresql://",
                "postgresql+asyncpg://"
            )
        
        self.engine = create_async_engine(
            database_url,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_pre_ping=True,
            echo=False
        )
        
        self.AsyncSessionFactory = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False
        )
        
        logger.info(f"Async connection pool initialized")
    
    async def get_session(self) -> AsyncSession:
        """
        Get async session.
        
        Returns:
            Async session
        
        Example:
            async with pool.get_session() as session:
                result = await session.execute(query)
        """
        async with self.AsyncSessionFactory() as session:
            try:
                yield session
                await session.commit()
            except Exception as e:
                await session.rollback()
                logger.error(f"Async session error: {e}")
                raise


# ============================================
# FASTAPI INTEGRATION
# ============================================

from fastapi import FastAPI, Depends
from typing import AsyncGenerator


# Global connection pool
db_pool: Optional[OptimizedConnectionPool] = None


def get_db_pool() -> OptimizedConnectionPool:
    """Get database pool (dependency injection)"""
    global db_pool
    
    if db_pool is None:
        db_pool = OptimizedConnectionPool(
            database_url="postgresql://user:pass@localhost/ocr_db",
            pool_size=20,
            max_overflow=10
        )
    
    return db_pool


async def get_db_session(
    pool: OptimizedConnectionPool = Depends(get_db_pool)
) -> AsyncGenerator[Session, None]:
    """
    FastAPI dependency for database session.
    
    Usage:
        @app.get("/users")
        async def get_users(db: Session = Depends(get_db_session)):
            return db.query(User).all()
    """
    with pool.get_session() as session:
        yield session


def create_app() -> FastAPI:
    """Create FastAPI app with connection pool"""
    app = FastAPI()
    
    @app.on_event("startup")
    async def startup():
        """Initialize connection pool on startup"""
        global db_pool
        db_pool = OptimizedConnectionPool(
            database_url="postgresql://user:pass@localhost/ocr_db",
            pool_size=20,
            max_overflow=10
        )
        logger.info("Database connection pool started")
    
    @app.on_event("shutdown")
    async def shutdown():
        """Dispose connection pool on shutdown"""
        if db_pool:
            db_pool.dispose()
        logger.info("Database connection pool disposed")
    
    @app.get("/pool/status")
    async def pool_status(pool: OptimizedConnectionPool = Depends(get_db_pool)):
        """Get connection pool status"""
        return pool.get_pool_status()
    
    return app


# ============================================
# EXAMPLE USAGE
# ============================================

if __name__ == "__main__":
    print("="*60)
    print("CONNECTION POOL OPTIMIZATION")
    print("="*60)
    
    # Calculate optimal pool size
    print("\n1. POOL SIZE CALCULATOR")
    print("-"*60)
    
    scenarios = [
        {"name": "Small API", "cores": 4, "instances": 1},
        {"name": "Medium API", "cores": 8, "instances": 3},
        {"name": "Large API", "cores": 16, "instances": 10}
    ]
    
    for scenario in scenarios:
        print(f"\n{scenario['name']}:")
        print(f"  CPU Cores: {scenario['cores']}")
        print(f"  Instances: {scenario['instances']}")
        
        config = PoolSizeCalculator.calculate(
            cpu_cores=scenario['cores'],
            app_instances=scenario['instances'],
            db_max_connections=200
        )
        
        print(f"  → {config['recommendation']}")
        print(f"  → Per instance: {config['total_per_instance']} max connections")
        print(f"  → All instances: {config['total_all_instances']} total")
    
    # Test connection pool
    print("\n" + "="*60)
    print("2. CONNECTION POOL TEST")
    print("-"*60)
    
    pool = OptimizedConnectionPool(
        database_url="sqlite:///test.db",  # SQLite for demo
        pool_size=5,
        max_overflow=2
    )
    
    # Check initial status
    status = pool.get_pool_status()
    print(f"\nInitial pool status:")
    print(f"  Size: {status['size']}")
    print(f"  Checked out: {status['checked_out']}")
    print(f"  Available: {status['available']}")
    
    # Use some connections
    print("\nChecking out connections...")
    sessions = []
    for i in range(3):
        session = pool.SessionFactory()
        sessions.append(session)
        status = pool.get_pool_status()
        print(f"  Connection {i+1}: {status['checked_out']} checked out, "
              f"{status['available']} available")
    
    # Return connections
    print("\nReturning connections...")
    for session in sessions:
        session.close()
    
    status = pool.get_pool_status()
    print(f"  Final: {status['checked_out']} checked out, "
          f"{status['available']} available")
    
    pool.dispose()

⚙️ ASYNC PROCESSING
1. Celery Task Queue
python# async_processing/celery_tasks.py

"""
Async Processing with Celery

Offload heavy work to background workers
"""

from celery import Celery, Task, group, chord, chain
from celery.result import AsyncResult
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from loguru import logger
import time


# ============================================
# CELERY CONFIGURATION
# ============================================

# Initialize Celery
app = Celery(
    'ocr_tasks',
    broker='redis://localhost:6379/0',      # Message broker
    backend='redis://localhost:6379/1'      # Result backend
)

# Configuration
app.conf.update(
    # Task settings
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    
    # Task execution
    task_acks_late=True,              # Acknowledge after completion
    task_reject_on_worker_lost=True,  # Reject on worker crash
    task_track_started=True,          # Track task start
    
    # Result settings
    result_expires=3600,              # Results expire after 1 hour
    result_backend_transport_options={
        'master_name': 'mymaster'     # Redis Sentinel
    },
    
    # Worker settings
    worker_prefetch_multiplier=4,     # Prefetch 4 tasks per worker
    worker_max_tasks_per_child=1000,  # Restart worker after 1000 tasks
    worker_disable_rate_limits=False,
    
    # Retry settings
    task_default_retry_delay=60,      # 60 seconds
    task_max_retries=3,
    
    # Time limits
    task_time_limit=3600,             # Hard limit: 1 hour
    task_soft_time_limit=3000,        # Soft limit: 50 minutes
    
    # Routing
    task_routes={
        'ocr_tasks.process_document': {'queue': 'ocr'},
        'ocr_tasks.batch_process': {'queue': 'batch'},
        'ocr_tasks.send_email': {'queue': 'notifications'}
    },
    
    # Beat schedule (periodic tasks)
    beat_schedule={
        'cleanup-old-results': {
            'task': 'ocr_tasks.cleanup_old_results',
            'schedule': timedelta(hours=1),
        },
        'health-check': {
            'task': 'ocr_tasks.health_check',
            'schedule': timedelta(minutes=5),
        },
    }
)


# ============================================
# BASE TASK CLASS
# ============================================

class CallbackTask(Task):
    """
    Base task class with callbacks.
    
    Provides hooks for task lifecycle events.
    """
    
    def on_success(self, retval, task_id, args, kwargs):
        """Called when task succeeds"""
        logger.info(f"Task {task_id} succeeded: {retval}")
    
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Called when task fails"""
        logger.error(f"Task {task_id} failed: {exc}")
    
    def on_retry(self, exc, task_id, args, kwargs, einfo):
        """Called when task is retried"""
        logger.warning(f"Task {task_id} retrying: {exc}")


# ============================================
# OCR PROCESSING TASKS
# ============================================

@app.task(
    base=CallbackTask,
    bind=True,
    name='ocr_tasks.process_document',
    max_retries=3,
    default_retry_delay=60
)
def process_document(
    self,
    document_id: str,
    language: str = 'de',
    preprocessing: bool = True
) -> Dict[str, Any]:
    """
    Process document with OCR (async).
    
    Args:
        self: Task instance (when bind=True)
        document_id: Document to process
        language: OCR language
        preprocessing: Apply preprocessing
    
    Returns:
        OCR result dictionary
    
    Example:
        # Call async
        result = process_document.delay('doc_123', language='de')
        
        # Check status
        if result.ready():
            print(result.get())
    """
    try:
        logger.info(f"Processing document {document_id}")
        
        # Update task state
        self.update_state(
            state='PROCESSING',
            meta={'current': 0, 'total': 100, 'status': 'Starting...'}
        )
        
        # Simulate OCR processing
        # In production: call actual OCR service
        for i in range(10):
            time.sleep(0.5)
            
            # Update progress
            self.update_state(
                state='PROCESSING',
                meta={
                    'current': (i + 1) * 10,
                    'total': 100,
                    'status': f'Processing page {i+1}/10'
                }
            )
        
        # Result
        result = {
            'document_id': document_id,
            'text': 'Extracted text content...',
            'confidence': 98.5,
            'pages': 10,
            'processing_time': 5.0
        }
        
        logger.info(f"Document {document_id} processed successfully")
        
        return result
        
    except Exception as exc:
        # Retry on failure
        logger.error(f"Error processing {document_id}: {exc}")
        raise self.retry(exc=exc)


@app.task(name='ocr_tasks.batch_process')
def batch_process(document_ids: List[str]) -> List[Dict]:
    """
    Process multiple documents in parallel.
    
    Args:
        document_ids: List of document IDs
    
    Returns:
        List of results
    
    Example:
        result = batch_process.delay(['doc1', 'doc2', 'doc3'])
    """
    # Create group of parallel tasks
    job = group(
        process_document.s(doc_id)
        for doc_id in document_ids
    )
    
    result = job.apply_async()
    
    # Wait for all tasks
    return result.get()


@app.task(name='ocr_tasks.process_with_callback')
def process_with_callback(document_id: str, callback_url: str) -> Dict:
    """
    Process document and call webhook on completion.
    
    Args:
        document_id: Document to process
        callback_url: URL to call on completion
    
    Returns:
        Processing result
    """
    # Chain: process → callback
    workflow = chain(
        process_document.s(document_id),
        send_webhook.s(callback_url)
    )
    
    return workflow.apply_async().get()


@app.task(name='ocr_tasks.send_webhook')
def send_webhook(result: Dict, callback_url: str):
    """
    Send webhook with result.
    
    Args:
        result: Task result
        callback_url: Webhook URL
    """
    import requests
    
    try:
        response = requests.post(
            callback_url,
            json=result,
            timeout=10
        )
        response.raise_for_status()
        
        logger.info(f"Webhook sent to {callback_url}")
        
    except Exception as e:
        logger.error(f"Webhook failed: {e}")


# ============================================
# PERIODIC TASKS
# ============================================

@app.task(name='ocr_tasks.cleanup_old_results')
def cleanup_old_results():
    """Clean up old task results (runs hourly)"""
    logger.info("Cleaning up old task results...")
    
    # Delete results older than 24 hours
    # In production: query result backend and delete
    
    return {"cleaned": 0}


@app.task(name='ocr_tasks.health_check')
def health_check():
    """Health check task (runs every 5 minutes)"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat()
    }


# ============================================
# TASK MONITORING
# ============================================

class TaskMonitor:
    """Monitor Celery tasks"""
    
    @staticmethod
    def get_task_status(task_id: str) -> Dict[str, Any]:
        """
        Get task status.
        
        Args:
            task_id: Task ID
        
        Returns:
            Task status dictionary
        """
        result = AsyncResult(task_id, app=app)
        
        response = {
            'task_id': task_id,
            'state': result.state,
            'ready': result.ready(),
            'successful': result.successful() if result.ready() else None,
            'failed': result.failed() if result.ready() else None,
        }
        
        if result.state == 'PROCESSING':
            response['progress'] = result.info
        elif result.ready():
            if result.successful():
                response['result'] = result.result
            else:
                response['error'] = str(result.info)
        
        return response
    
    @staticmethod
    def cancel_task(task_id: str) -> bool:
        """
        Cancel running task.
        
        Args:
            task_id: Task ID
        
        Returns:
            True if cancelled
        """
        result = AsyncResult(task_id, app=app)
        result.revoke(terminate=True)
        
        logger.info(f"Task {task_id} cancelled")
        
        return True
    
    @staticmethod
    def get_queue_length(queue_name: str = 'celery') -> int:
        """
        Get queue length.
        
        Args:
            queue_name: Queue name
        
        Returns:
            Number of tasks in queue
        """
        from celery import current_app
        
        with current_app.connection_or_acquire() as conn:
            return conn.default_channel.queue_declare(
                queue=queue_name,
                passive=True
            ).message_count


# ============================================
# FASTAPI INTEGRATION
# ============================================

from fastapi import FastAPI, BackgroundTasks, HTTPException

def create_celery_app() -> FastAPI:
    """Create FastAPI app with Celery"""
    api = FastAPI(title="OCR API with Celery")
    
    @api.post("/ocr/process")
    async def process_document_endpoint(
        document_id: str,
        background_tasks: BackgroundTasks
    ):
        """
        Process document asynchronously.
        
        Returns task ID immediately, processing happens in background.
        """
        # Submit to Celery
        task = process_document.delay(document_id)
        
        return {
            "task_id": task.id,
            "status": "queued",
            "message": "Document processing started"
        }
    
    @api.get("/ocr/status/{task_id}")
    async def get_status(task_id: str):
        """Get task status"""
        status = TaskMonitor.get_task_status(task_id)
        
        if not status:
            raise HTTPException(404, "Task not found")
        
        return status
    
    @api.delete("/ocr/cancel/{task_id}")
    async def cancel_task(task_id: str):
        """Cancel task"""
        cancelled = TaskMonitor.cancel_task(task_id)
        
        return {"cancelled": cancelled}
    
    @api.get("/queue/stats")
    async def queue_stats():
        """Get queue statistics"""
        return {
            "ocr_queue": TaskMonitor.get_queue_length('ocr'),
            "batch_queue": TaskMonitor.get_queue_length('batch'),
            "default_queue": TaskMonitor.get_queue_length('celery')
        }
    
    return api


# ============================================
# EXAMPLE USAGE
# ============================================

if __name__ == "__main__":
    print("="*60)
    print("CELERY ASYNC PROCESSING")
    print("="*60)
    
    # Start Celery worker:
    # celery -A async_processing.celery_tasks worker --loglevel=info
    
    # Start Celery beat (scheduler):
    # celery -A async_processing.celery_tasks beat --loglevel=info
    
    # Monitor with Flower:
    # celery -A async_processing.celery_tasks flower
    
    print("\nSubmitting async task...")
    task = process_document.delay('doc_123', language='de')
    
    print(f"Task ID: {task.id}")
    print(f"State: {task.state}")
    
    # Wait for result
    print("\nWaiting for result...")
    result = task.get(timeout=30)
    
    print(f"Result: {result}")
    
    # Batch processing
    print("\n" + "="*60)
    print("BATCH PROCESSING")
    print("n"*60)
    
    batch_task = batch_process.delay(['doc1', 'doc2', 'doc3'])
    print(f"Batch task ID: {batch_task.id}")
    
    results = batch_task.get(timeout=60)
    print(f"Batch results: {len(results)} documents processed")



SCALABILITY & PERFORMANCE GUIDE - TEIL 3 (FINAL)
Microservices, Message Queues, Benchmarking & Best Practices

📋 TABLE OF CONTENTS (TEIL 3)

Microservices Architecture
Message Queues
Performance Benchmarking
Best Practices & Complete Setup


🏗️ MICROSERVICES ARCHITECTURE
1. Service Decomposition
python# microservices/architecture.py

"""
Microservices Architecture

Breaking monolith into independent services
"""

from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum


@dataclass
class Service:
    """Service definition"""
    name: str
    description: str
    port: int
    responsibilities: List[str]
    dependencies: List[str]
    database: Optional[str] = None


class MicroservicesArchitecture:
    """
    OCR System Microservices Architecture
    
    ┌────────────────────────────────────────────────────────┐
    │                API GATEWAY                              │
    │         (Load Balancing, Routing, Auth)                 │
    └──────────┬─────────────┬──────────────┬────────────────┘
               │             │              │
    ┌──────────▼──────┐ ┌───▼──────┐ ┌─────▼──────┐
    │  Auth Service   │ │   User   │ │  Document  │
    │   Port: 8001    │ │  Service │ │  Service   │
    │                 │ │Port: 8002│ │Port: 8003  │
    │ - JWT tokens    │ │- User    │ │- Upload    │
    │ - Permissions   │ │  CRUD    │ │- Metadata  │
    │ - API keys      │ │- Profile │ │- Storage   │
    └─────────────────┘ └──────────┘ └─────┬──────┘
                                           │
                        ┌──────────────────┼──────────────┐
                        │                  │              │
                   ┌────▼──────┐    ┌──────▼───┐   ┌─────▼──────┐
                   │    OCR    │    │  Queue   │   │  Results   │
                   │  Service  │    │ Service  │   │  Service   │
                   │Port: 8004 │    │Port: 8005│   │Port: 8006  │
                   │           │    │          │   │            │
                   │- Process  │◄───┤- Job     │   │- Storage   │
                   │- Extract  │    │  queue   │   │- Retrieval │
                   │- Analyze  │    │- Status  │   │- Export    │
                   └───────────┘    └──────────┘   └────────────┘
    
    Benefits:
    - Independent deployment
    - Technology flexibility
    - Fault isolation
    - Easier scaling
    - Team autonomy
    
    Challenges:
    - Distributed complexity
    - Data consistency
    - Service communication
    - Monitoring overhead
    """
    
    SERVICES = {
        'auth': Service(
            name='auth-service',
            description='Authentication & Authorization',
            port=8001,
            responsibilities=[
                'User authentication',
                'JWT token management',
                'API key validation',
                'Permission checks'
            ],
            dependencies=[],
            database='auth_db'
        ),
        
        'user': Service(
            name='user-service',
            description='User Management',
            port=8002,
            responsibilities=[
                'User CRUD operations',
                'Profile management',
                'User preferences',
                'Account settings'
            ],
            dependencies=['auth'],
            database='user_db'
        ),
        
        'document': Service(
            name='document-service',
            description='Document Management',
            port=8003,
            responsibilities=[
                'Document upload',
                'Metadata storage',
                'File storage integration',
                'Document versioning'
            ],
            dependencies=['auth', 'user'],
            database='document_db'
        ),
        
        'ocr': Service(
            name='ocr-service',
            description='OCR Processing',
            port=8004,
            responsibilities=[
                'Text extraction',
                'Language detection',
                'Image preprocessing',
                'OCR engine integration'
            ],
            dependencies=['document', 'queue'],
            database='ocr_db'
        ),
        
        'queue': Service(
            name='queue-service',
            description='Job Queue Management',
            port=8005,
            responsibilities=[
                'Job queuing',
                'Task scheduling',
                'Status tracking',
                'Priority management'
            ],
            dependencies=[],
            database='queue_db'
        ),
        
        'results': Service(
            name='results-service',
            description='Results Storage & Retrieval',
            port=8006,
            responsibilities=[
                'Result storage',
                'Result retrieval',
                'Export functionality',
                'Result caching'
            ],
            dependencies=['ocr'],
            database='results_db'
        ),
        
        'notifications': Service(
            name='notification-service',
            description='Notifications',
            port=8007,
            responsibilities=[
                'Email notifications',
                'Webhook callbacks',
                'Event publishing',
                'Alert management'
            ],
            dependencies=['user'],
            database=None  # Stateless
        )
    }


# ============================================
# AUTH SERVICE
# ============================================

# auth_service/main.py

from fastapi import FastAPI, HTTPException, Depends, Header
from pydantic import BaseModel
import jwt
from datetime import datetime, timedelta

auth_app = FastAPI(title="Auth Service", version="1.0.0")

# JWT Configuration
SECRET_KEY = "your-secret-key"
ALGORITHM = "HS256"


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in: int


@auth_app.post("/auth/login", response_model=TokenResponse)
async def login(request: LoginRequest):
    """
    Authenticate user and return JWT token.
    
    Service communication:
    User Service → Auth Service (validate credentials)
    """
    # In production: validate against database
    if request.username == "admin" and request.password == "password":
        # Create JWT token
        payload = {
            "sub": request.username,
            "exp": datetime.utcnow() + timedelta(hours=24),
            "iat": datetime.utcnow()
        }
        
        token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
        
        return TokenResponse(
            access_token=token,
            token_type="bearer",
            expires_in=86400
        )
    
    raise HTTPException(401, "Invalid credentials")


@auth_app.post("/auth/validate")
async def validate_token(authorization: str = Header(...)):
    """
    Validate JWT token (used by other services).
    
    Service communication:
    Any Service → Auth Service (validate token)
    """
    try:
        # Extract token
        token = authorization.replace("Bearer ", "")
        
        # Decode and validate
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        
        return {
            "valid": True,
            "user": payload["sub"],
            "expires": payload["exp"]
        }
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Invalid token")


@auth_app.get("/health")
async def health():
    """Health check"""
    return {"status": "healthy", "service": "auth"}


# ============================================
# DOCUMENT SERVICE
# ============================================

# document_service/main.py

from fastapi import FastAPI, UploadFile, File, Depends, HTTPException
from typing import List, Optional
import httpx
import uuid

document_app = FastAPI(title="Document Service", version="1.0.0")

# Service URLs
AUTH_SERVICE_URL = "http://auth-service:8001"
OCR_SERVICE_URL = "http://ocr-service:8004"
QUEUE_SERVICE_URL = "http://queue-service:8005"


async def verify_token(authorization: str = Header(...)) -> dict:
    """Verify token with Auth Service"""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{AUTH_SERVICE_URL}/auth/validate",
            headers={"Authorization": authorization}
        )
        
        if response.status_code != 200:
            raise HTTPException(401, "Invalid token")
        
        return response.json()


@document_app.post("/documents/upload")
async def upload_document(
    file: UploadFile = File(...),
    user: dict = Depends(verify_token)
):
    """
    Upload document for OCR processing.
    
    Service communication:
    1. Document Service → Auth Service (validate token)
    2. Document Service → Queue Service (queue job)
    3. Queue Service → OCR Service (process)
    """
    # Generate document ID
    doc_id = str(uuid.uuid4())
    
    # Save file (in production: to S3/object storage)
    content = await file.read()
    
    # Store metadata in database
    # ... database logic ...
    
    # Queue for OCR processing
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{QUEUE_SERVICE_URL}/queue/submit",
            json={
                "document_id": doc_id,
                "filename": file.filename,
                "user_id": user["user"]
            }
        )
    
    return {
        "document_id": doc_id,
        "filename": file.filename,
        "status": "queued",
        "job_id": response.json()["job_id"]
    }


@document_app.get("/documents/{document_id}")
async def get_document(
    document_id: str,
    user: dict = Depends(verify_token)
):
    """Get document metadata"""
    # In production: query database
    return {
        "id": document_id,
        "filename": "document.pdf",
        "status": "completed"
    }


@document_app.get("/health")
async def health():
    """Health check"""
    return {"status": "healthy", "service": "document"}


# ============================================
# OCR SERVICE
# ============================================

# ocr_service/main.py

from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel

ocr_app = FastAPI(title="OCR Service", version="1.0.0")


class OCRRequest(BaseModel):
    document_id: str
    language: str = "de"
    preprocessing: bool = True


class OCRResult(BaseModel):
    document_id: str
    text: str
    confidence: float
    pages: int


@ocr_app.post("/ocr/process", response_model=OCRResult)
async def process_ocr(request: OCRRequest):
    """
    Process document with OCR.
    
    This is called by Queue Service.
    """
    # In production: actual OCR processing
    # Using DeepSeek, GOT-OCR, or Surya
    
    # Simulate processing
    result = OCRResult(
        document_id=request.document_id,
        text="Extracted text content...",
        confidence=98.5,
        pages=5
    )
    
    # Store result in Results Service
    # async with httpx.AsyncClient() as client:
    #     await client.post(
    #         f"{RESULTS_SERVICE_URL}/results/store",
    #         json=result.dict()
    #     )
    
    return result


@ocr_app.get("/health")
async def health():
    """Health check"""
    return {"status": "healthy", "service": "ocr"}


# ============================================
# DOCKER COMPOSE FOR MICROSERVICES
# ============================================

DOCKER_COMPOSE_MICROSERVICES = """
version: '3.8'

services:
  # API Gateway (Nginx)
  gateway:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
    depends_on:
      - auth-service
      - document-service
      - ocr-service
    networks:
      - microservices

  # Auth Service
  auth-service:
    build: ./auth_service
    environment:
      - DATABASE_URL=postgresql://user:pass@auth-db:5432/auth_db
      - JWT_SECRET=${JWT_SECRET}
    depends_on:
      - auth-db
    networks:
      - microservices
    deploy:
      replicas: 2

  # Document Service
  document-service:
    build: ./document_service
    environment:
      - DATABASE_URL=postgresql://user:pass@document-db:5432/document_db
      - AUTH_SERVICE_URL=http://auth-service:8001
      - QUEUE_SERVICE_URL=http://queue-service:8005
    depends_on:
      - document-db
      - auth-service
    networks:
      - microservices
    deploy:
      replicas: 3

  # OCR Service
  ocr-service:
    build: ./ocr_service
    environment:
      - DATABASE_URL=postgresql://user:pass@ocr-db:5432/ocr_db
      - GPU_ENABLED=true
    depends_on:
      - ocr-db
    networks:
      - microservices
    deploy:
      replicas: 2
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]

  # Queue Service
  queue-service:
    build: ./queue_service
    environment:
      - REDIS_URL=redis://redis:6379
      - OCR_SERVICE_URL=http://ocr-service:8004
    depends_on:
      - redis
    networks:
      - microservices
    deploy:
      replicas: 2

  # Results Service
  results-service:
    build: ./results_service
    environment:
      - DATABASE_URL=postgresql://user:pass@results-db:5432/results_db
      - S3_BUCKET=${S3_BUCKET}
    depends_on:
      - results-db
    networks:
      - microservices
    deploy:
      replicas: 2

  # Notification Service
  notification-service:
    build: ./notification_service
    environment:
      - SMTP_HOST=${SMTP_HOST}
      - SMTP_PORT=${SMTP_PORT}
    networks:
      - microservices
    deploy:
      replicas: 1

  # Databases
  auth-db:
    image: postgres:15
    environment:
      POSTGRES_DB: auth_db
      POSTGRES_USER: user
      POSTGRES_PASSWORD: pass
    volumes:
      - auth-db-data:/var/lib/postgresql/data
    networks:
      - microservices

  document-db:
    image: postgres:15
    environment:
      POSTGRES_DB: document_db
      POSTGRES_USER: user
      POSTGRES_PASSWORD: pass
    volumes:
      - document-db-data:/var/lib/postgresql/data
    networks:
      - microservices

  ocr-db:
    image: postgres:15
    environment:
      POSTGRES_DB: ocr_db
      POSTGRES_USER: user
      POSTGRES_PASSWORD: pass
    volumes:
      - ocr-db-data:/var/lib/postgresql/data
    networks:
      - microservices

  results-db:
    image: postgres:15
    environment:
      POSTGRES_DB: results_db
      POSTGRES_USER: user
      POSTGRES_PASSWORD: pass
    volumes:
      - results-db-data:/var/lib/postgresql/data
    networks:
      - microservices

  # Redis (for queuing and caching)
  redis:
    image: redis:7-alpine
    networks:
      - microservices
    volumes:
      - redis-data:/data

  # Service Discovery (Consul)
  consul:
    image: consul:latest
    ports:
      - "8500:8500"
    networks:
      - microservices

volumes:
  auth-db-data:
  document-db-data:
  ocr-db-data:
  results-db-data:
  redis-data:

networks:
  microservices:
    driver: bridge
"""


# ============================================
# SERVICE COMMUNICATION PATTERNS
# ============================================

class ServiceCommunication:
    """
    Service Communication Patterns
    
    1. Synchronous (REST/HTTP):
       - Direct HTTP calls between services
       - Simple, request-response
       - Tight coupling
    
    2. Asynchronous (Message Queue):
       - Services communicate via message broker
       - Loose coupling
       - Better for long-running tasks
    
    3. Event-Driven:
       - Publish-subscribe pattern
       - Services react to events
       - Maximum decoupling
    """
    
    @staticmethod
    async def call_service_sync(
        service_url: str,
        endpoint: str,
        method: str = "GET",
        **kwargs
    ):
        """
        Synchronous service call.
        
        Example:
            result = await call_service_sync(
                "http://auth-service:8001",
                "/auth/validate",
                method="POST",
                headers={"Authorization": "Bearer ..."}
            )
        """
        async with httpx.AsyncClient() as client:
            if method == "GET":
                response = await client.get(f"{service_url}{endpoint}", **kwargs)
            elif method == "POST":
                response = await client.post(f"{service_url}{endpoint}", **kwargs)
            
            response.raise_for_status()
            return response.json()


if __name__ == "__main__":
    print("="*60)
    print("MICROSERVICES ARCHITECTURE")
    print("="*60)
    
    print("\nServices:")
    for key, service in MicroservicesArchitecture.SERVICES.items():
        print(f"\n{service.name} (Port {service.port}):")
        print(f"  {service.description}")
        print(f"  Responsibilities:")
        for resp in service.responsibilities:
            print(f"    - {resp}")
        if service.dependencies:
            print(f"  Dependencies: {', '.join(service.dependencies)}")

📨 MESSAGE QUEUES
1. RabbitMQ Implementation
python# messaging/rabbitmq_queue.py

"""
RabbitMQ Message Queue

Enterprise-grade message broker
"""

import pika
import json
from typing import Callable, Dict, Any, Optional
from dataclasses import dataclass
from loguru import logger
import time


@dataclass
class QueueConfig:
    """RabbitMQ queue configuration"""
    name: str
    durable: bool = True           # Survive broker restart
    exclusive: bool = False        # Only this connection
    auto_delete: bool = False      # Delete when unused
    arguments: Optional[Dict] = None


class RabbitMQQueue:
    """
    RabbitMQ Queue Manager
    
    Features:
    - Reliable message delivery
    - Message persistence
    - Acknowledgments
    - Dead letter queues
    - Priority queues
    - Message routing
    
    Architecture:
    
    Producer → [Exchange] → [Queue] → Consumer
                  ↓
              Routing Key
                  ↓
            [Dead Letter Queue]
    
    Exchange Types:
    - Direct: Route by exact routing key
    - Topic: Route by pattern (*.ocr.*)
    - Fanout: Broadcast to all queues
    - Headers: Route by message headers
    """
    
    def __init__(
        self,
        host: str = 'localhost',
        port: int = 5672,
        username: str = 'guest',
        password: str = 'guest',
        virtual_host: str = '/'
    ):
        """
        Initialize RabbitMQ connection.
        
        Args:
            host: RabbitMQ host
            port: RabbitMQ port
            username: Username
            password: Password
            virtual_host: Virtual host
        """
        self.host = host
        self.port = port
        
        # Connection parameters
        credentials = pika.PlainCredentials(username, password)
        self.parameters = pika.ConnectionParameters(
            host=host,
            port=port,
            virtual_host=virtual_host,
            credentials=credentials,
            heartbeat=600,
            blocked_connection_timeout=300
        )
        
        # Connection and channel
        self.connection = None
        self.channel = None
        
        self._connect()
        
        logger.info(f"RabbitMQ connected: {host}:{port}")
    
    def _connect(self):
        """Establish connection to RabbitMQ"""
        self.connection = pika.BlockingConnection(self.parameters)
        self.channel = self.connection.channel()
    
    def declare_queue(
        self,
        config: QueueConfig
    ) -> str:
        """
        Declare a queue.
        
        Args:
            config: Queue configuration
        
        Returns:
            Queue name
        """
        # Declare queue
        self.channel.queue_declare(
            queue=config.name,
            durable=config.durable,
            exclusive=config.exclusive,
            auto_delete=config.auto_delete,
            arguments=config.arguments or {}
        )
        
        logger.info(f"Queue declared: {config.name}")
        
        return config.name
    
    def declare_exchange(
        self,
        exchange: str,
        exchange_type: str = 'direct',
        durable: bool = True
    ):
        """
        Declare an exchange.
        
        Args:
            exchange: Exchange name
            exchange_type: Type (direct, topic, fanout, headers)
            durable: Survive restart
        """
        self.channel.exchange_declare(
            exchange=exchange,
            exchange_type=exchange_type,
            durable=durable
        )
        
        logger.info(f"Exchange declared: {exchange} ({exchange_type})")
    
    def bind_queue(
        self,
        queue: str,
        exchange: str,
        routing_key: str = ''
    ):
        """
        Bind queue to exchange.
        
        Args:
            queue: Queue name
            exchange: Exchange name
            routing_key: Routing key pattern
        """
        self.channel.queue_bind(
            queue=queue,
            exchange=exchange,
            routing_key=routing_key
        )
        
        logger.info(f"Queue bound: {queue} → {exchange} ({routing_key})")
    
    def publish(
        self,
        message: Dict[str, Any],
        queue: str = None,
        exchange: str = '',
        routing_key: str = '',
        priority: int = 0,
        persistent: bool = True
    ):
        """
        Publish message to queue.
        
        Args:
            message: Message data
            queue: Queue name (if not using exchange)
            exchange: Exchange name
            routing_key: Routing key
            priority: Message priority (0-9)
            persistent: Persist to disk
        """
        # If queue specified, use it as routing key
        if queue:
            routing_key = queue
        
        # Message properties
        properties = pika.BasicProperties(
            delivery_mode=2 if persistent else 1,  # 2 = persistent
            priority=priority,
            content_type='application/json'
        )
        
        # Publish
        self.channel.basic_publish(
            exchange=exchange,
            routing_key=routing_key,
            body=json.dumps(message),
            properties=properties
        )
        
        logger.debug(f"Message published to {routing_key}")
    
    def consume(
        self,
        queue: str,
        callback: Callable,
        auto_ack: bool = False,
        prefetch_count: int = 1
    ):
        """
        Consume messages from queue.
        
        Args:
            queue: Queue name
            callback: Callback function(ch, method, properties, body)
            auto_ack: Auto-acknowledge messages
            prefetch_count: Number of messages to prefetch
        """
        # Set QoS (Quality of Service)
        self.channel.basic_qos(prefetch_count=prefetch_count)
        
        # Start consuming
        self.channel.basic_consume(
            queue=queue,
            on_message_callback=callback,
            auto_ack=auto_ack
        )
        
        logger.info(f"Consuming from {queue}")
        
        try:
            self.channel.start_consuming()
        except KeyboardInterrupt:
            self.channel.stop_consuming()
    
    def close(self):
        """Close connection"""
        if self.connection and self.connection.is_open:
            self.connection.close()
            logger.info("RabbitMQ connection closed")


# ============================================
# OCR JOB QUEUE WITH RABBITMQ
# ============================================

class OCRJobQueue:
    """
    OCR Job Queue using RabbitMQ
    
    Queues:
    - ocr.jobs: New OCR jobs
    - ocr.jobs.priority: High priority jobs
    - ocr.results: Completed results
    - ocr.failed: Failed jobs (DLQ)
    """
    
    def __init__(self, rabbitmq: RabbitMQQueue):
        self.mq = rabbitmq
        
        # Declare dead letter exchange
        self.mq.declare_exchange('dlx', 'direct')
        
        # Declare dead letter queue
        dlq_config = QueueConfig(name='ocr.failed', durable=True)
        self.mq.declare_queue(dlq_config)
        self.mq.bind_queue('ocr.failed', 'dlx', 'ocr.failed')
        
        # Declare main job queue with DLQ
        job_config = QueueConfig(
            name='ocr.jobs',
            durable=True,
            arguments={
                'x-dead-letter-exchange': 'dlx',
                'x-dead-letter-routing-key': 'ocr.failed',
                'x-max-priority': 9  # Enable priority
            }
        )
        self.mq.declare_queue(job_config)
        
        # Declare priority queue
        priority_config = QueueConfig(
            name='ocr.jobs.priority',
            durable=True,
            arguments={
                'x-dead-letter-exchange': 'dlx',
                'x-dead-letter-routing-key': 'ocr.failed'
            }
        )
        self.mq.declare_queue(priority_config)
        
        # Declare results queue
        results_config = QueueConfig(name='ocr.results', durable=True)
        self.mq.declare_queue(results_config)
        
        logger.info("OCR job queues initialized")
    
    def submit_job(
        self,
        document_id: str,
        language: str = 'de',
        priority: int = 0
    ) -> str:
        """
        Submit OCR job.
        
        Args:
            document_id: Document to process
            language: OCR language
            priority: Job priority (0-9, higher = more priority)
        
        Returns:
            Job ID
        """
        import uuid
        
        job_id = str(uuid.uuid4())
        
        message = {
            'job_id': job_id,
            'document_id': document_id,
            'language': language,
            'submitted_at': time.time()
        }
        
        # High priority jobs to separate queue
        queue = 'ocr.jobs.priority' if priority >= 7 else 'ocr.jobs'
        
        self.mq.publish(
            message=message,
            queue=queue,
            priority=priority,
            persistent=True
        )
        
        logger.info(f"Job submitted: {job_id} (priority={priority})")
        
        return job_id
    
    def process_jobs(self, ocr_processor: Callable):
        """
        Process OCR jobs (worker).
        
        Args:
            ocr_processor: Function to process OCR
        """
        def callback(ch, method, properties, body):
            """Job callback"""
            try:
                # Parse message
                job = json.loads(body)
                
                logger.info(f"Processing job: {job['job_id']}")
                
                # Process OCR
                result = ocr_processor(
                    job['document_id'],
                    job['language']
                )
                
                # Publish result
                self.mq.publish(
                    message={
                        'job_id': job['job_id'],
                        'result': result,
                        'completed_at': time.time()
                    },
                    queue='ocr.results'
                )
                
                # Acknowledge message
                ch.basic_ack(delivery_tag=method.delivery_tag)
                
                logger.info(f"Job completed: {job['job_id']}")
                
            except Exception as e:
                logger.error(f"Job failed: {e}")
                
                # Reject message (send to DLQ)
                ch.basic_nack(
                    delivery_tag=method.delivery_tag,
                    requeue=False  # Don't requeue, send to DLQ
                )
        
        # Consume from both queues (priority first)
        logger.info("Starting job processor...")
        
        # Process priority queue first
        self.mq.consume(
            queue='ocr.jobs.priority',
            callback=callback,
            auto_ack=False,
            prefetch_count=1
        )


# ============================================
# REDIS STREAMS (Alternative)
# ============================================

import redis
from typing import List, Tuple


class RedisStreamQueue:
    """
    Redis Streams for message queuing.
    
    Lighter alternative to RabbitMQ.
    
    Features:
    - Append-only log structure
    - Consumer groups
    - Automatic acknowledgment
    - Message persistence
    
    Good for:
    - Simple pub/sub
    - Event sourcing
    - Activity streams
    - Time-series data
    """
    
    def __init__(
        self,
        host: str = 'localhost',
        port: int = 6379,
        db: int = 0
    ):
        """Initialize Redis connection"""
        self.redis = redis.Redis(
            host=host,
            port=port,
            db=db,
            decode_responses=True
        )
        
        logger.info(f"Redis Streams connected: {host}:{port}")
    
    def create_consumer_group(
        self,
        stream: str,
        group: str
    ):
        """
        Create consumer group.
        
        Args:
            stream: Stream name
            group: Consumer group name
        """
        try:
            self.redis.xgroup_create(
                name=stream,
                groupname=group,
                id='0',
                mkstream=True
            )
            logger.info(f"Consumer group created: {group} on {stream}")
        except redis.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise
    
    def add_message(
        self,
        stream: str,
        message: Dict[str, Any]
    ) -> str:
        """
        Add message to stream.
        
        Args:
            stream: Stream name
            message: Message data
        
        Returns:
            Message ID
        """
        # Flatten nested dict
        flat_message = {}
        for key, value in message.items():
            if isinstance(value, (dict, list)):
                flat_message[key] = json.dumps(value)
            else:
                flat_message[key] = str(value)
        
        message_id = self.redis.xadd(stream, flat_message)
        
        logger.debug(f"Message added to {stream}: {message_id}")
        
        return message_id
    
    def read_messages(
        self,
        stream: str,
        group: str,
        consumer: str,
        count: int = 10,
        block: int = 5000
    ) -> List[Tuple[str, Dict]]:
        """
        Read messages from stream.
        
        Args:
            stream: Stream name
            group: Consumer group
            consumer: Consumer name
            count: Max messages to read
            block: Block time in milliseconds
        
        Returns:
            List of (message_id, message_data)
        """
        messages = self.redis.xreadgroup(
            groupname=group,
            consumername=consumer,
            streams={stream: '>'},
            count=count,
            block=block
        )
        
        if not messages:
            return []
        
        # Parse messages
        result = []
        for stream_name, stream_messages in messages:
            for message_id, data in stream_messages:
                # Parse JSON fields
                parsed_data = {}
                for key, value in data.items():
                    try:
                        parsed_data[key] = json.loads(value)
                    except (json.JSONDecodeError, TypeError):
                        parsed_data[key] = value
                
                result.append((message_id, parsed_data))
        
        return result
    
    def acknowledge(
        self,
        stream: str,
        group: str,
        *message_ids: str
    ):
        """
        Acknowledge messages.
        
        Args:
            stream: Stream name
            group: Consumer group
            message_ids: Message IDs to acknowledge
        """
        self.redis.xack(stream, group, *message_ids)


# ============================================
# EXAMPLE USAGE
# ============================================

if __name__ == "__main__":
    print("="*60)
    print("MESSAGE QUEUE COMPARISON")
    print("="*60)
    
    # RabbitMQ
    print("\n1. RabbitMQ")
    print("-"*60)
    
    try:
        rabbitmq = RabbitMQQueue(host='localhost')
        
        # Create OCR queue
        ocr_queue = OCRJobQueue(rabbitmq)
        
        # Submit job
        job_id = ocr_queue.submit_job('doc_123', priority=5)
        print(f"Job submitted: {job_id}")
        
        rabbitmq.close()
        
    except Exception as e:
        print(f"RabbitMQ error: {e}")
    
    # Redis Streams
    print("\n2. Redis Streams")
    print("-"*60)
    
    try:
        redis_queue = RedisStreamQueue()
        
        # Create stream
        stream = 'ocr:jobs'
        group = 'workers'
        
        redis_queue.create_consumer_group(stream, group)
        
        # Add message
        message_id = redis_queue.add_message(
            stream,
            {
                'document_id': 'doc_123',
                'language': 'de'
            }
        )
        print(f"Message added: {message_id}")
        
        # Read messages
        messages = redis_queue.read_messages(
            stream,
            group,
            consumer='worker1',
            count=1
        )
        
        if messages:
            msg_id, data = messages[0]
            print(f"Message read: {data}")
            
            # Acknowledge
            redis_queue.acknowledge(stream, group, msg_id)
            print("Message acknowledged")
        
    except Exception as e:
        print(f"Redis Streams error: {e}")

📊 PERFORMANCE BENCHMARKING
1. Load Testing
python# benchmarking/load_test.py

"""
Performance Benchmarking & Load Testing

Measure system performance under load
"""

import asyncio
import aiohttp
import time
from typing import List, Dict, Any
from dataclasses import dataclass
from statistics import mean, median, stdev
from loguru import logger


@dataclass
class BenchmarkResult:
    """Benchmark result"""
    total_requests: int
    successful: int
    failed: int
    duration: float
    requests_per_second: float
    avg_response_time: float
    median_response_time: float
    p95_response_time: float
    p99_response_time: float
    min_response_time: float
    max_response_time: float


class LoadTester:
    """
    Load testing tool.
    
    Simulates concurrent users making requests.
    
    Metrics:
    - Throughput (req/s)
    - Response time (avg, median, p95, p99)
    - Success/failure rate
    - Concurrent connections
    """
    
    def __init__(self, base_url: str):
        """
        Initialize load tester.
        
        Args:
            base_url: Base URL to test
        """
        self.base_url = base_url
        self.results: List[float] = []
        self.errors: List[str] = []
    
    async def make_request(
        self,
        session: aiohttp.ClientSession,
        method: str = "GET",
        endpoint: str = "/",
        **kwargs
    ) -> float:
        """
        Make single request.
        
        Returns:
            Response time in seconds
        """
        url = f"{self.base_url}{endpoint}"
        start = time.time()
        
        try:
            async with session.request(method, url, **kwargs) as response:
                await response.text()
                response.raise_for_status()
                
                return time.time() - start
                
        except Exception as e:
            self.errors.append(str(e))
            return -1
    
    async def run_concurrent_requests(
        self,
        num_requests: int,
        concurrency: int,
        method: str = "GET",
        endpoint: str = "/",
        **kwargs
    ) -> BenchmarkResult:
        """
        Run concurrent requests.
        
        Args:
            num_requests: Total requests to make
            concurrency: Concurrent requests
            method: HTTP method
            endpoint: API endpoint
            **kwargs: Request arguments
        
        Returns:
            BenchmarkResult
        """
        self.results = []
        self.errors = []
        
        # Create session with connection pool
        connector = aiohttp.TCPConnector(limit=concurrency)
        timeout = aiohttp.ClientTimeout(total=30)
        
        async with aiohttp.ClientSession(
            connector=connector,
            timeout=timeout
        ) as session:
            # Create tasks
            tasks = []
            for _ in range(num_requests):
                task = self.make_request(
                    session,
                    method,
                    endpoint,
                    **kwargs
                )
                tasks.append(task)
            
            # Run with progress
            start_time = time.time()
            
            results = await asyncio.gather(*tasks)
            
            total_duration = time.time() - start_time
        
        # Filter successful requests
        successful_times = [r for r in results if r > 0]
        
        # Calculate percentiles
        sorted_times = sorted(successful_times)
        
        def percentile(data: List[float], p: float) -> float:
            if not data:
                return 0
            k = (len(data) - 1) * p / 100
            f = int(k)
            c = f + 1 if f < len(data) - 1 else f
            return data[f] + (k - f) * (data[c] - data[f])
        
        return BenchmarkResult(
            total_requests=num_requests,
            successful=len(successful_times),
            failed=len(self.errors),
            duration=total_duration,
            requests_per_second=num_requests / total_duration,
            avg_response_time=mean(successful_times) if successful_times else 0,
            median_response_time=median(successful_times) if successful_times else 0,
            p95_response_time=percentile(sorted_times, 95),
            p99_response_time=percentile(sorted_times, 99),
            min_response_time=min(successful_times) if successful_times else 0,
            max_response_time=max(successful_times) if successful_times else 0
        )
    
    def print_results(self, result: BenchmarkResult):
        """Print benchmark results"""
        print("\n" + "="*60)
        print("BENCHMARK RESULTS")
        print("="*60)
        
        print(f"\nRequests:")
        print(f"  Total: {result.total_requests}")
        print(f"  Successful: {result.successful}")
        print(f"  Failed: {result.failed}")
        print(f"  Success rate: {(result.successful/result.total_requests)*100:.1f}%")
        
        print(f"\nThroughput:")
        print(f"  Requests/sec: {result.requests_per_second:.2f}")
        print(f"  Duration: {result.duration:.2f}s")
        
        print(f"\nResponse Times (seconds):")
        print(f"  Average: {result.avg_response_time:.4f}")
        print(f"  Median: {result.median_response_time:.4f}")
        print(f"  p95: {result.p95_response_time:.4f}")
        print(f"  p99: {result.p99_response_time:.4f}")
        print(f"  Min: {result.min_response_time:.4f}")
        print(f"  Max: {result.max_response_time:.4f}")


# ============================================
# STRESS TESTING
# ============================================

class StressTester:
    """
    Stress testing tool.
    
    Gradually increase load to find breaking point.
    """
    
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.load_tester = LoadTester(base_url)
    
    async def run_stress_test(
        self,
        start_users: int = 10,
        max_users: int = 1000,
        step: int = 50,
        requests_per_user: int = 10,
        endpoint: str = "/"
    ) -> List[Dict[str, Any]]:
        """
        Run stress test.
        
        Args:
            start_users: Initial concurrent users
            max_users: Maximum concurrent users
            step: User increment per iteration
            requests_per_user: Requests per user
            endpoint: Endpoint to test
        
        Returns:
            List of results per load level
        """
        results = []
        
        for users in range(start_users, max_users + 1, step):
            print(f"\nTesting with {users} concurrent users...")
            
            result = await self.load_tester.run_concurrent_requests(
                num_requests=users * requests_per_user,
                concurrency=users,
                endpoint=endpoint
            )
            
            results.append({
                'users': users,
                'rps': result.requests_per_second,
                'avg_time': result.avg_response_time,
                'p95_time': result.p95_response_time,
                'success_rate': (result.successful / result.total_requests) * 100
            })
            
            # Stop if success rate drops below 95%
            if results[-1]['success_rate'] < 95:
                print(f"\n⚠️  Breaking point reached at {users} users!")
                print(f"    Success rate: {results[-1]['success_rate']:.1f}%")
                break
            
            # Brief pause between iterations
            await asyncio.sleep(2)
        
        return results


# ============================================
# LOCUST LOAD TESTING (Python)
# ============================================

LOCUST_FILE = """
# locustfile.py

from locust import HttpUser, task, between
import random


class OCRUser(HttpUser):
    '''
    Simulate OCR API user.
    
    Run with:
    locust -f locustfile.py --host=http://localhost:8000
    
    Then open: http://localhost:8089
    '''
    
    wait_time = between(1, 3)  # Wait 1-3 seconds between requests
    
    @task(3)  # Weight: 3
    def list_documents(self):
        '''List documents (common operation)'''
        self.client.get("/documents")
    
    @task(1)  # Weight: 1
    def upload_document(self):
        '''Upload document (less common)'''
        files = {
            'file': ('test.pdf', b'PDF content...', 'application/pdf')
        }
        self.client.post("/documents/upload", files=files)
    
    @task(2)  # Weight: 2
    def get_document(self):
        '''Get specific document'''
        doc_id = random.randint(1, 1000)
        self.client.get(f"/documents/{doc_id}")
    
    @task(1)  # Weight: 1
    def process_ocr(self):
        '''Process OCR (expensive)'''
        self.client.post(
            "/ocr/process",
            json={"document_id": "doc_123", "language": "de"}
        )
    
    def on_start(self):
        '''Called when user starts'''
        # Login
        response = self.client.post(
            "/auth/login",
            json={"username": "test", "password": "test"}
        )
        
        if response.status_code == 200:
            token = response.json()["access_token"]
            self.client.headers = {"Authorization": f"Bearer {token}"}
"""


# ============================================
# K6 LOAD TESTING (JavaScript)
# ============================================

K6_SCRIPT = """
// k6_test.js

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate } from 'k6/metrics';

// Custom metrics
const errorRate = new Rate('errors');

// Test configuration
export const options = {
    // Stages (ramp up/down)
    stages: [
        { duration: '2m', target: 100 },  // Ramp up to 100 users
        { duration: '5m', target: 100 },  // Stay at 100 users
        { duration: '2m', target: 200 },  // Ramp up to 200 users
        { duration: '5m', target: 200 },  // Stay at 200 users
        { duration: '2m', target: 0 },    // Ramp down to 0
    ],
    
    // Thresholds (SLAs)
    thresholds: {
        http_req_duration: ['p(95)<500'],  // 95% requests < 500ms
        http_req_failed: ['rate<0.01'],    // Error rate < 1%
        errors: ['rate<0.1'],              // Custom error rate < 10%
    },
};

const BASE_URL = 'http://localhost:8000';

export function setup() {
    // Login and get token
    const loginRes = http.post(`${BASE_URL}/auth/login`, JSON.stringify({
        username: 'test',
        password: 'test'
    }), {
        headers: { 'Content-Type': 'application/json' },
    });
    
    return { token: loginRes.json('access_token') };
}

export default function(data) {
    const headers = {
        'Authorization': `Bearer ${data.token}`,
        'Content-Type': 'application/json',
    };
    
    // Scenario: List documents
    let res = http.get(`${BASE_URL}/documents`, { headers });
    check(res, {
        'list documents status 200': (r) => r.status === 200,
    }) || errorRate.add(1);
    
    sleep(1);
    
    // Scenario: Get document
    res = http.get(`${BASE_URL}/documents/123`, { headers });
    check(res, {
        'get document status 200': (r) => r.status === 200,
    }) || errorRate.add(1);
    
    sleep(2);
}

export function teardown(data) {
    // Cleanup
}

// Run with:
// k6 run k6_test.js
"""


# ============================================
# EXAMPLE USAGE
# ============================================

async def main():
    print("="*60)
    print("LOAD TESTING EXAMPLES")
    print("="*60)
    
    # Simple load test
    print("\n1. Simple Load Test")
    print("-"*60)
    
    tester = LoadTester("http://localhost:8000")
    
    result = await tester.run_concurrent_requests(
        num_requests=1000,
        concurrency=50,
        endpoint="/health"
    )
    
    tester.print_results(result)
    
    # Stress test
    print("\n" + "="*60)
    print("2. Stress Test")
    print("="*60)
    
    stress_tester = StressTester("http://localhost:8000")
    
    results = await stress_tester.run_stress_test(
        start_users=10,
        max_users=200,
        step=20,
        requests_per_user=10,
        endpoint="/health"
    )
    
    print("\nStress Test Results:")
    print(f"{'Users':<10} {'RPS':<15} {'Avg Time':<15} {'Success Rate'}")
    print("-"*60)
    for r in results:
        print(
            f"{r['users']:<10} "
            f"{r['rps']:<15.2f} "
            f"{r['avg_time']:<15.4f} "
            f"{r['success_rate']:.1f}%"
        )


if __name__ == "__main__":
    asyncio.run(main())



 SCALABILITY & PERFORMANCE GUIDE - TEIL 3 (FINAL)
Best Practices, Complete Setup & Troubleshooting

📋 TABLE OF CONTENTS (FINAL)

Best Practices & Complete Setup


🎯 BEST PRACTICES & COMPLETE SETUP
1. Performance Optimization Checklist
python# best_practices/optimization_checklist.py

"""
Performance Optimization Checklist

Complete guide for production optimization
"""

from typing import Dict, List
from dataclasses import dataclass
from enum import Enum


class OptimizationLevel(Enum):
    """Optimization priority"""
    CRITICAL = "critical"      # Must have
    HIGH = "high"             # Should have
    MEDIUM = "medium"         # Nice to have
    LOW = "low"              # Optional


@dataclass
class OptimizationItem:
    """Optimization checklist item"""
    category: str
    item: str
    level: OptimizationLevel
    description: str
    implementation: str
    impact: str


class PerformanceChecklist:
    """
    Complete performance optimization checklist.
    
    Categories:
    1. Application Layer
    2. Database Layer
    3. Caching Layer
    4. Network Layer
    5. Infrastructure Layer
    """
    
    CHECKLIST = [
        # ==========================================
        # APPLICATION LAYER
        # ==========================================
        
        OptimizationItem(
            category="Application",
            item="Async I/O",
            level=OptimizationLevel.CRITICAL,
            description="Use async/await for I/O operations",
            implementation="""
# ✅ Good: Async I/O
async def get_user(user_id: str):
    async with aiohttp.ClientSession() as session:
        async with session.get(f'/users/{user_id}') as response:
            return await response.json()

# ❌ Bad: Blocking I/O
def get_user(user_id: str):
    response = requests.get(f'/users/{user_id}')
    return response.json()
            """,
            impact="10x+ throughput improvement for I/O-bound operations"
        ),
        
        OptimizationItem(
            category="Application",
            item="Connection Pooling",
            level=OptimizationLevel.CRITICAL,
            description="Reuse database/HTTP connections",
            implementation="""
# ✅ Good: Connection pool
engine = create_engine(
    DATABASE_URL,
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True
)

# ❌ Bad: New connection every time
def query():
    engine = create_engine(DATABASE_URL)
    # ... query ...
    engine.dispose()
            """,
            impact="50-70% reduction in connection overhead"
        ),
        
        OptimizationItem(
            category="Application",
            item="Stateless Design",
            level=OptimizationLevel.CRITICAL,
            description="No session data in application memory",
            implementation="""
# ✅ Good: Stateless with Redis
def get_cart(user_id: str):
    return redis.get(f'cart:{user_id}')

# ❌ Bad: Stateful with local memory
user_carts = {}  # In-memory state
def get_cart(user_id: str):
    return user_carts.get(user_id)
            """,
            impact="Enables horizontal scaling"
        ),
        
        OptimizationItem(
            category="Application",
            item="Request Compression",
            level=OptimizationLevel.HIGH,
            description="Compress HTTP responses",
            implementation="""
# FastAPI middleware
from fastapi.middleware.gzip import GZipMiddleware

app.add_middleware(GZipMiddleware, minimum_size=1000)
            """,
            impact="60-80% bandwidth reduction for text content"
        ),
        
        OptimizationItem(
            category="Application",
            item="Response Streaming",
            level=OptimizationLevel.MEDIUM,
            description="Stream large responses",
            implementation="""
# Stream large file
from fastapi.responses import StreamingResponse

@app.get("/export")
async def export_data():
    async def generate():
        for chunk in data_chunks():
            yield chunk
    
    return StreamingResponse(generate())
            """,
            impact="Constant memory usage for large responses"
        ),
        
        # ==========================================
        # DATABASE LAYER
        # ==========================================
        
        OptimizationItem(
            category="Database",
            item="Indexing",
            level=OptimizationLevel.CRITICAL,
            description="Add indexes on frequently queried columns",
            implementation="""
-- ✅ Good: Indexed query
CREATE INDEX idx_users_email ON users(email);
SELECT * FROM users WHERE email = 'test@example.com';

-- ❌ Bad: Full table scan
SELECT * FROM users WHERE email = 'test@example.com';
            """,
            impact="100x+ faster queries on large tables"
        ),
        
        OptimizationItem(
            category="Database",
            item="Query Optimization",
            level=OptimizationLevel.CRITICAL,
            description="Optimize slow queries",
            implementation="""
-- ✅ Good: Specific columns
SELECT id, name, email FROM users WHERE active = true;

-- ❌ Bad: SELECT *
SELECT * FROM users WHERE active = true;

-- ✅ Good: JOIN with conditions
SELECT u.name, d.title 
FROM users u 
INNER JOIN documents d ON u.id = d.user_id 
WHERE u.active = true;

-- ❌ Bad: Subquery in SELECT
SELECT name, (SELECT COUNT(*) FROM documents WHERE user_id = u.id) 
FROM users u;
            """,
            impact="50-90% query time reduction"
        ),
        
        OptimizationItem(
            category="Database",
            item="Read Replicas",
            level=OptimizationLevel.HIGH,
            description="Separate read and write databases",
            implementation="""
# Master for writes
with db.get_session(DatabaseRole.MASTER) as session:
    session.add(new_user)

# Slave for reads
with db.get_session(DatabaseRole.SLAVE) as session:
    users = session.query(User).all()
            """,
            impact="5x+ read scalability"
        ),
        
        OptimizationItem(
            category="Database",
            item="Connection Pooling",
            level=OptimizationLevel.CRITICAL,
            description="Optimize pool size",
            implementation="""
# Formula: (cpu_cores * 2) + effective_spindle_count
pool_size = (4 * 2) + 1  # = 9
max_overflow = 5

engine = create_engine(
    DATABASE_URL,
    pool_size=pool_size,
    max_overflow=max_overflow
)
            """,
            impact="30-50% reduction in connection overhead"
        ),
        
        OptimizationItem(
            category="Database",
            item="Batch Operations",
            level=OptimizationLevel.HIGH,
            description="Batch inserts/updates",
            implementation="""
# ✅ Good: Batch insert
session.bulk_insert_mappings(User, user_dicts)

# ❌ Bad: Individual inserts
for user_dict in user_dicts:
    session.add(User(**user_dict))
    session.commit()
            """,
            impact="10-100x faster bulk operations"
        ),
        
        # ==========================================
        # CACHING LAYER
        # ==========================================
        
        OptimizationItem(
            category="Caching",
            item="Redis Caching",
            level=OptimizationLevel.CRITICAL,
            description="Cache frequently accessed data",
            implementation="""
# Cache pattern
def get_user(user_id: str):
    # Check cache
    cached = redis.get(f'user:{user_id}')
    if cached:
        return json.loads(cached)
    
    # Query database
    user = db.query(User).filter_by(id=user_id).first()
    
    # Store in cache
    redis.setex(
        f'user:{user_id}',
        3600,  # 1 hour
        json.dumps(user.dict())
    )
    
    return user
            """,
            impact="100-1000x faster data access"
        ),
        
        OptimizationItem(
            category="Caching",
            item="CDN for Static Assets",
            level=OptimizationLevel.HIGH,
            description="Use CDN for images, CSS, JS",
            implementation="""
# CloudFront, Cloudflare, Fastly
# Nginx config
location /static/ {
    expires 1y;
    add_header Cache-Control "public, immutable";
}
            """,
            impact="90% reduction in static asset latency"
        ),
        
        OptimizationItem(
            category="Caching",
            item="HTTP Caching Headers",
            level=OptimizationLevel.HIGH,
            description="Set proper cache headers",
            implementation="""
@app.get("/documents/{doc_id}")
async def get_document(doc_id: str, response: Response):
    response.headers["Cache-Control"] = "max-age=3600"
    response.headers["ETag"] = generate_etag(doc_id)
    return document
            """,
            impact="Reduces server load by 50-80%"
        ),
        
        OptimizationItem(
            category="Caching",
            item="Cache Warming",
            level=OptimizationLevel.MEDIUM,
            description="Pre-populate cache on startup",
            implementation="""
@app.on_event("startup")
async def warm_cache():
    # Load frequently accessed data
    popular_users = db.query(User).limit(100).all()
    for user in popular_users:
        redis.setex(f'user:{user.id}', 3600, user.json())
            """,
            impact="Eliminates cold start delays"
        ),
        
        # ==========================================
        # NETWORK LAYER
        # ==========================================
        
        OptimizationItem(
            category="Network",
            item="Load Balancing",
            level=OptimizationLevel.CRITICAL,
            description="Distribute traffic across servers",
            implementation="""
# Nginx upstream
upstream backend {
    least_conn;
    server app1:8000 weight=3;
    server app2:8000 weight=3;
    server app3:8000 weight=2;
}
            """,
            impact="Enables horizontal scaling"
        ),
        
        OptimizationItem(
            category="Network",
            item="HTTP/2",
            level=OptimizationLevel.HIGH,
            description="Use HTTP/2 for multiplexing",
            implementation="""
# Nginx
listen 443 ssl http2;
            """,
            impact="30-50% faster page loads"
        ),
        
        OptimizationItem(
            category="Network",
            item="Keep-Alive Connections",
            level=OptimizationLevel.HIGH,
            description="Reuse TCP connections",
            implementation="""
# Nginx
keepalive_timeout 65;
keepalive_requests 100;

# Upstream
keepalive 32;
            """,
            impact="Reduces connection overhead by 40-60%"
        ),
        
        OptimizationItem(
            category="Network",
            item="Rate Limiting",
            level=OptimizationLevel.CRITICAL,
            description="Protect against abuse",
            implementation="""
# Token bucket algorithm
limiter = TokenBucketRateLimiter(
    capacity=100,
    refill_rate=10.0  # 10 tokens/second
)
            """,
            impact="Prevents resource exhaustion"
        ),
        
        # ==========================================
        # INFRASTRUCTURE LAYER
        # ==========================================
        
        OptimizationItem(
            category="Infrastructure",
            item="Auto-Scaling",
            level=OptimizationLevel.CRITICAL,
            description="Scale based on metrics",
            implementation="""
# Kubernetes HPA
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
spec:
  minReplicas: 3
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
            """,
            impact="Automatic capacity adjustment"
        ),
        
        OptimizationItem(
            category="Infrastructure",
            item="Container Optimization",
            level=OptimizationLevel.HIGH,
            description="Optimize Docker images",
            implementation="""
# Multi-stage build
FROM python:3.11-slim as builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM python:3.11-slim
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY . .
CMD ["uvicorn", "main:app"]
            """,
            impact="50-80% smaller image size"
        ),
        
        OptimizationItem(
            category="Infrastructure",
            item="Resource Limits",
            level=OptimizationLevel.CRITICAL,
            description="Set CPU/memory limits",
            implementation="""
# Kubernetes
resources:
  requests:
    memory: "512Mi"
    cpu: "500m"
  limits:
    memory: "2Gi"
    cpu: "2000m"
            """,
            impact="Prevents resource starvation"
        ),
        
        OptimizationItem(
            category="Infrastructure",
            item="Health Checks",
            level=OptimizationLevel.CRITICAL,
            description="Implement liveness/readiness",
            implementation="""
@app.get("/health")
async def health():
    # Check dependencies
    redis_ok = redis.ping()
    db_ok = db.execute("SELECT 1").scalar()
    
    return {
        "status": "healthy" if all([redis_ok, db_ok]) else "unhealthy",
        "redis": redis_ok,
        "database": db_ok
    }
            """,
            impact="Enables automatic recovery"
        ),
    ]
    
    @classmethod
    def print_checklist(cls, category: str = None):
        """Print optimization checklist"""
        items = cls.CHECKLIST
        
        if category:
            items = [i for i in items if i.category == category]
        
        print("="*80)
        print("PERFORMANCE OPTIMIZATION CHECKLIST")
        print("="*80)
        
        current_category = None
        
        for item in items:
            if item.category != current_category:
                print(f"\n{'='*80}")
                print(f"  {item.category.upper()}")
                print(f"{'='*80}")
                current_category = item.category
            
            priority_emoji = {
                OptimizationLevel.CRITICAL: "🔴",
                OptimizationLevel.HIGH: "🟠",
                OptimizationLevel.MEDIUM: "🟡",
                OptimizationLevel.LOW: "🟢"
            }
            
            print(f"\n{priority_emoji[item.level]} {item.item} [{item.level.value.upper()}]")
            print(f"   {item.description}")
            print(f"   💡 Impact: {item.impact}")
    
    @classmethod
    def get_quick_wins(cls) -> List[OptimizationItem]:
        """Get high-impact, easy items"""
        return [
            item for item in cls.CHECKLIST
            if item.level in [OptimizationLevel.CRITICAL, OptimizationLevel.HIGH]
        ]


# ============================================
# COMPLETE PRODUCTION SETUP
# ============================================

class ProductionSetupGuide:
    """
    Complete production setup guide.
    
    Step-by-step deployment checklist.
    """
    
    SETUP_STEPS = """
# ============================================
# PRODUCTION SETUP GUIDE
# ============================================

## PHASE 1: Infrastructure Setup
## ============================================

### 1.1 Server Provisioning

# Minimum requirements per server:
- CPU: 4+ cores
- RAM: 16GB+
- Storage: 100GB+ SSD
- Network: 1Gbps+

# Recommended: 3 servers minimum
Server 1: Application + Load Balancer
Server 2: Application + Database Master
Server 3: Application + Database Slave


### 1.2 Database Setup

# PostgreSQL Master
# /etc/postgresql/15/main/postgresql.conf
wal_level = replica
max_wal_senders = 10
max_connections = 200

# Create replication user
CREATE ROLE replicator WITH REPLICATION LOGIN PASSWORD 'secure_password';

# PostgreSQL Slaves (2+)
pg_basebackup -h master -D /var/lib/postgresql/15/main -U replicator -P -R


### 1.3 Redis Setup

# Redis Master
# /etc/redis/redis.conf
maxmemory 4gb
maxmemory-policy allkeys-lru
save 900 1
save 300 10

# Redis Sentinel (3 instances for HA)
sentinel monitor mymaster 10.0.1.10 6379 2
sentinel down-after-milliseconds mymaster 5000
sentinel failover-timeout mymaster 60000


### 1.4 Nginx/HAProxy Setup

# Nginx Load Balancer
upstream backend {
    least_conn;
    server 10.0.1.10:8000 weight=3;
    server 10.0.1.11:8000 weight=3;
    server 10.0.1.12:8000 weight=2;
}


## PHASE 2: Application Deployment
## ============================================

### 2.1 Docker Build

# Optimized Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Non-root user
RUN useradd -m appuser
USER appuser

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]


### 2.2 Environment Variables

# .env.production
DATABASE_URL=postgresql://user:pass@master:5432/ocr_db
DATABASE_SLAVE_URLS=postgresql://user:pass@slave1:5432/ocr_db,postgresql://user:pass@slave2:5432/ocr_db
REDIS_URL=redis://sentinel1:26379,redis://sentinel2:26379
JWT_SECRET=your-super-secret-key-change-this
CORS_ORIGINS=https://yourdomain.com


### 2.3 Kubernetes Deployment

# deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ocr-api
spec:
  replicas: 3
  template:
    spec:
      containers:
      - name: ocr-api
        image: your-registry/ocr-api:latest
        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "2Gi"
            cpu: "2000m"


## PHASE 3: Monitoring & Logging
## ============================================

### 3.1 Prometheus + Grafana

# prometheus.yml
scrape_configs:
  - job_name: 'ocr-api'
    static_configs:
      - targets: ['app1:8000', 'app2:8000', 'app3:8000']


### 3.2 ELK Stack (Elasticsearch, Logstash, Kibana)

# Centralized logging
- Application logs → Logstash → Elasticsearch → Kibana


### 3.3 Alerts

# alert.rules
- alert: HighErrorRate
  expr: rate(http_requests_total{status=~"5.."}[5m]) > 0.05
  for: 5m
  annotations:
    summary: High error rate detected


## PHASE 4: Security
## ============================================

### 4.1 SSL/TLS

# Let's Encrypt
certbot --nginx -d api.yourdomain.com


### 4.2 Firewall

# UFW
ufw allow 22/tcp    # SSH
ufw allow 80/tcp    # HTTP
ufw allow 443/tcp   # HTTPS
ufw deny 5432/tcp   # PostgreSQL (internal only)


### 4.3 Secrets Management

# HashiCorp Vault
vault kv put secret/ocr-api \\
    database_password="..." \\
    jwt_secret="..." \\
    api_key="..."


## PHASE 5: Backup & Recovery
## ============================================

### 5.1 Database Backups

# PostgreSQL automated backups
0 2 * * * pg_dump ocr_db | gzip > /backups/ocr_db_$(date +\\%Y\\%m\\%d).sql.gz

# Retention: 7 daily, 4 weekly, 12 monthly


### 5.2 Disaster Recovery Plan

1. RPO (Recovery Point Objective): 1 hour
2. RTO (Recovery Time Objective): 4 hours
3. Backup verification: Weekly
4. Disaster recovery drill: Quarterly


## PHASE 6: Performance Testing
## ============================================

### 6.1 Load Testing

# K6 stress test
k6 run --vus 1000 --duration 10m load_test.js


### 6.2 Performance Benchmarks

Target Metrics:
- Response time (p95): < 200ms
- Response time (p99): < 500ms
- Throughput: > 1000 req/s
- Error rate: < 0.1%
- Uptime: > 99.9%


## PHASE 7: Go Live
## ============================================

### 7.1 Pre-launch Checklist

☑ All tests passing
☑ Load testing completed
☑ Monitoring configured
☑ Backups verified
☑ SSL certificates valid
☑ DNS configured
☑ Rate limiting active
☑ Documentation updated


### 7.2 Launch

1. Enable maintenance mode
2. Deploy to production
3. Run database migrations
4. Smoke tests
5. Disable maintenance mode
6. Monitor closely for 24 hours


### 7.3 Post-launch

- Monitor error rates
- Check performance metrics
- Review logs
- Validate backups
- Update runbook
    """


# ============================================
# TROUBLESHOOTING GUIDE
# ============================================

class TroubleshootingGuide:
    """Common issues and solutions"""
    
    ISSUES = {
        "high_latency": {
            "symptom": "Slow response times (> 1 second)",
            "possible_causes": [
                "Database queries not indexed",
                "Missing connection pooling",
                "No caching layer",
                "Blocking I/O operations",
                "Network latency"
            ],
            "solutions": [
                "Add database indexes: CREATE INDEX idx_users_email ON users(email)",
                "Implement connection pooling: pool_size=20, max_overflow=10",
                "Add Redis caching for frequently accessed data",
                "Use async/await for I/O operations",
                "Enable HTTP/2 and keep-alive"
            ],
            "debugging": """
# Check slow queries
SELECT query, mean_exec_time, calls 
FROM pg_stat_statements 
ORDER BY mean_exec_time DESC 
LIMIT 10;

# Check connection pool status
SELECT count(*) as total, 
       sum(CASE WHEN state = 'active' THEN 1 ELSE 0 END) as active
FROM pg_stat_activity;

# Profile application
import cProfile
cProfile.run('your_function()')
            """
        },
        
        "database_connection_exhaustion": {
            "symptom": "FATAL: sorry, too many clients already",
            "possible_causes": [
                "Pool size too large",
                "Connections not being released",
                "Too many application instances",
                "Connection leaks"
            ],
            "solutions": [
                "Reduce pool size: pool_size = (cpu_cores * 2) + 1",
                "Use context managers for sessions",
                "Implement connection pooling correctly",
                "Check for connection leaks in code"
            ],
            "debugging": """
# Check active connections
SELECT datname, count(*) 
FROM pg_stat_activity 
GROUP BY datname;

# Find long-running queries
SELECT pid, query, state, age(clock_timestamp(), query_start)
FROM pg_stat_activity
WHERE state != 'idle'
ORDER BY query_start;

# Kill connection
SELECT pg_terminate_backend(pid);
            """
        },
        
        "memory_leak": {
            "symptom": "Memory usage constantly increasing",
            "possible_causes": [
                "Objects not being garbage collected",
                "Large response caching",
                "Circular references",
                "Event listeners not removed"
            ],
            "solutions": [
                "Use memory profiler: pip install memory_profiler",
                "Implement proper cleanup in __del__ methods",
                "Use weak references where appropriate",
                "Clear caches periodically"
            ],
            "debugging": """
# Memory profiler
from memory_profiler import profile

@profile
def my_function():
    # Your code
    pass

# Tracemalloc
import tracemalloc
tracemalloc.start()
# ... your code ...
snapshot = tracemalloc.take_snapshot()
top_stats = snapshot.statistics('lineno')
for stat in top_stats[:10]:
    print(stat)
            """
        },
        
        "high_cpu_usage": {
            "symptom": "CPU at 100%",
            "possible_causes": [
                "Inefficient algorithms",
                "Too many workers",
                "Infinite loops",
                "Heavy synchronous processing"
            ],
            "solutions": [
                "Profile code with cProfile",
                "Optimize algorithms (O(n²) → O(n log n))",
                "Move heavy work to background tasks",
                "Use async for I/O-bound work"
            ],
            "debugging": """
# CPU profiling
python -m cProfile -s cumtime your_script.py

# py-spy (live profiling)
py-spy record -o profile.svg -- python your_script.py

# Check CPU per process
top -p $(pgrep -f "uvicorn")
            """
        },
        
        "rate_limit_too_aggressive": {
            "symptom": "Legitimate users getting 429 errors",
            "possible_causes": [
                "Limits set too low",
                "All requests from same IP (proxy)",
                "Bot traffic mixed with real users",
                "Incorrect identifier (IP vs user)"
            ],
            "solutions": [
                "Increase rate limits gradually",
                "Use X-Forwarded-For header correctly",
                "Implement tiered rate limiting",
                "Whitelist known good IPs"
            ],
            "debugging": """
# Check rate limit metrics
SELECT identifier, COUNT(*) as blocked_requests
FROM rate_limit_logs
WHERE blocked = true
GROUP BY identifier
ORDER BY blocked_requests DESC
LIMIT 10;

# Analyze request patterns
SELECT DATE_TRUNC('hour', timestamp) as hour,
       COUNT(*) as requests
FROM access_logs
GROUP BY hour
ORDER BY hour DESC;
            """
        }
    }
    
    @classmethod
    def print_guide(cls, issue: str = None):
        """Print troubleshooting guide"""
        if issue and issue in cls.ISSUES:
            items = {issue: cls.ISSUES[issue]}
        else:
            items = cls.ISSUES
        
        print("="*80)
        print("TROUBLESHOOTING GUIDE")
        print("="*80)
        
        for name, info in items.items():
            print(f"\n{'='*80}")
            print(f"ISSUE: {name.replace('_', ' ').title()}")
            print(f"{'='*80}")
            
            print(f"\n📋 Symptom:")
            print(f"   {info['symptom']}")
            
            print(f"\n🔍 Possible Causes:")
            for cause in info['possible_causes']:
                print(f"   • {cause}")
            
            print(f"\n✅ Solutions:")
            for i, solution in enumerate(info['solutions'], 1):
                print(f"   {i}. {solution}")
            
            print(f"\n🐛 Debugging:")
            print(info['debugging'])


# ============================================
# EXAMPLE USAGE
# ============================================

if __name__ == "__main__":
    # Print optimization checklist
    print("\n" + "="*80)
    print("PERFORMANCE OPTIMIZATION CHECKLIST")
    print("="*80)
    
    PerformanceChecklist.print_checklist()
    
    # Quick wins
    print("\n" + "="*80)
    print("QUICK WINS (High Impact)")
    print("="*80)
    
    quick_wins = PerformanceChecklist.get_quick_wins()
    for item in quick_wins[:5]:
        print(f"\n✨ {item.item}")
        print(f"   {item.description}")
        print(f"   💡 {item.impact}")
    
    # Production setup
    print("\n" + "="*80)
    print("PRODUCTION SETUP GUIDE")
    print("="*80)
    print(ProductionSetupGuide.SETUP_STEPS)
    
    # Troubleshooting
    print("\n" + "="*80)
    print("TROUBLESHOOTING GUIDE")
    print("="*80)
    
    TroubleshootingGuide.print_guide()
2. Complete Architecture Diagram
python# architecture/complete_system.py

"""
Complete System Architecture

Production-ready OCR system
"""

COMPLETE_ARCHITECTURE = """
┌─────────────────────────────────────────────────────────────────────────────┐
│                         COMPLETE OCR SYSTEM ARCHITECTURE                     │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│  LAYER 1: CLIENT LAYER                                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  [Web Browser]  [Mobile App]  [Desktop App]  [Third-Party Integration]     │
│        │             │              │                    │                   │
│        └─────────────┴──────────────┴────────────────────┘                   │
│                             │                                                │
│                        HTTPS/WSS                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                               │
┌─────────────────────────────────────────────────────────────────────────────┐
│  LAYER 2: CDN & WAF                                                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐                │
│  │   CloudFlare   │  │   CloudFront   │  │      WAF       │                │
│  │   (CDN/DDoS)   │  │   (CDN/Edge)   │  │ (Firewall)     │                │
│  └────────────────┘  └────────────────┘  └────────────────┘                │
└─────────────────────────────────────────────────────────────────────────────┘
                               │
┌─────────────────────────────────────────────────────────────────────────────┐
│  LAYER 3: LOAD BALANCING                                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│              ┌────────────────────────────────┐                             │
│              │   HAProxy / Nginx              │                             │
│              │   - SSL Termination             │                             │
│              │   - Rate Limiting               │                             │
│              │   - Health Checks               │                             │
│              └──────────────┬─────────────────┘                             │
│                             │                                                │
│         ┌───────────────────┼───────────────────┐                           │
└─────────┼───────────────────┼───────────────────┼───────────────────────────┘
          │                   │                   │
┌─────────┼───────────────────┼───────────────────┼───────────────────────────┐
│  LAYER 4: API GATEWAY                          │                            │
├─────────┼───────────────────┼───────────────────┼───────────────────────────┤
│         │                   │                   │                            │
│  ┌──────▼──────┐     ┌──────▼──────┐     ┌────▼───────┐                    │
│  │ Gateway 1   │     │ Gateway 2   │     │ Gateway 3  │                    │
│  │ - Auth      │     │ - Auth      │     │ - Auth     │                    │
│  │ - Routing   │     │ - Routing   │     │ - Routing  │                    │
│  │ - Logging   │     │ - Logging   │     │ - Logging  │                    │
│  └──────┬──────┘     └──────┬──────┘     └────┬───────┘                    │
└─────────┼───────────────────┼───────────────────┼───────────────────────────┘
          │                   │                   │
┌─────────┼───────────────────┼───────────────────┼───────────────────────────┐
│  LAYER 5: MICROSERVICES                        │                            │
├─────────┼───────────────────┼───────────────────┼───────────────────────────┤
│         │                   │                   │                            │
│  ┌──────▼──────┐     ┌──────▼──────┐     ┌────▼───────┐                    │
│  │   Auth      │     │    User     │     │  Document  │                    │
│  │  Service    │     │  Service    │     │  Service   │                    │
│  │  Port:8001  │     │  Port:8002  │     │  Port:8003 │                    │
│  └──────┬──────┘     └──────┬──────┘     └────┬───────┘                    │
│         │                   │                   │                            │
│         └───────────────────┼───────────────────┘                            │
│                             │                                                │
│  ┌──────────────────────────▼───────────────────────────┐                   │
│  │              Message Queue (RabbitMQ)                │                   │
│  │  - Job Queue    - Results Queue    - Events         │                   │
│  └──────────────────────────┬───────────────────────────┘                   │
│                             │                                                │
│         ┌───────────────────┼───────────────────┐                           │
│         │                   │                   │                            │
│  ┌──────▼──────┐     ┌──────▼──────┐     ┌────▼───────┐                    │
│  │    OCR      │     │   Queue     │     │  Results   │                    │
│  │  Service    │     │  Service    │     │  Service   │                    │
│  │  Port:8004  │     │  Port:8005  │     │  Port:8006 │                    │
│  │  (GPU)      │     │             │     │            │                    │
│  └──────┬──────┘     └──────┬──────┘     └────┬───────┘                    │
└─────────┼───────────────────┼───────────────────┼───────────────────────────┘
          │                   │                   │
┌─────────┼───────────────────┼───────────────────┼───────────────────────────┐
│  LAYER 6: DATA LAYER                           │                            │
├─────────┼───────────────────┼───────────────────┼───────────────────────────┤
│         │                   │                   │                            │
│  ┌──────▼──────────────┐   │   ┌───────────────▼──────────┐                │
│  │  PostgreSQL Master  │───┼──→│  PostgreSQL Slaves       │                │
│  │  - Auth DB          │   │   │  - Read Replicas (2+)    │                │
│  │  - User DB          │   │   │  - Auto-failover         │                │
│  │  - Document DB      │   │   └──────────────────────────┘                │
│  │  - OCR DB           │   │                                                │
│  │  - Results DB       │   │                                                │
│  └─────────────────────┘   │                                                │
│                             │                                                │
│  ┌─────────────────────────▼────────────────────┐                           │
│  │         Redis Cluster                        │                           │
│  │  Master → Slave → Slave                      │                           │
│  │  - Session Storage                           │                           │
│  │  - Caching Layer                             │                           │
│  │  - Rate Limiting                             │                           │
│  │  - Queue Backend                             │                           │
│  └──────────────────────────────────────────────┘                           │
│                                                                              │
│  ┌──────────────────────────────────────────────┐                           │
│  │         Object Storage (S3/MinIO)            │                           │
│  │  - Document Storage                          │                           │
│  │  - OCR Results                               │                           │
│  │  - Backups                                   │                           │
│  └──────────────────────────────────────────────┘                           │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│  LAYER 7: MONITORING & OBSERVABILITY                                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │
│  │  Prometheus  │  │   Grafana    │  │     ELK      │  │   Sentry     │   │
│  │  (Metrics)   │  │  (Dashboards)│  │   (Logs)     │  │   (Errors)   │   │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘   │
│                                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                      │
│  │   Jaeger     │  │  AlertManager│  │   PagerDuty  │                      │
│  │  (Tracing)   │  │   (Alerts)   │  │  (On-call)   │                      │
│  └──────────────┘  └──────────────┘  └──────────────┘                      │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│  CROSS-CUTTING CONCERNS                                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Security:                                                                   │
│  - SSL/TLS encryption                                                        │
│  - JWT authentication                                                        │
│  - Rate limiting                                                             │
│  - WAF rules                                                                 │
│  - Secrets management (Vault)                                                │
│                                                                              │
│  Reliability:                                                                │
│  - Auto-scaling (3-10 instances)                                             │
│  - Health checks                                                             │
│  - Circuit breakers                                                          │
│  - Retry logic with exponential backoff                                      │
│  - Database replication                                                      │
│                                                                              │
│  Performance:                                                                │
│  - Connection pooling                                                        │
│  - Caching (Redis)                                                           │
│  - Async processing (Celery)                                                 │
│  - CDN for static assets                                                     │
│  - Database indexes                                                          │
│                                                                              │
│  Backup & Recovery:                                                          │
│  - Daily automated backups                                                   │
│  - Point-in-time recovery                                                    │
│  - Off-site backup replication                                               │
│  - Disaster recovery plan (RPO: 1h, RTO: 4h)                                 │
└─────────────────────────────────────────────────────────────────────────────┘

CAPACITY:
- Throughput: 10,000+ requests/second
- Concurrent Users: 50,000+
- Database: 500M+ documents
- Uptime: 99.9%+ (< 9 hours downtime/year)
"""

print(COMPLETE_ARCHITECTURE)
3. Final Summary
python# summary/key_takeaways.py

"""
Key Takeaways - Scalability & Performance
"""

KEY_TAKEAWAYS = """
╔═══════════════════════════════════════════════════════════════════════════╗
║                    SCALABILITY & PERFORMANCE - KEY TAKEAWAYS               ║
╚═══════════════════════════════════════════════════════════════════════════╝

┌───────────────────────────────────────────────────────────────────────────┐
│  1. HORIZONTAL SCALING                                                     │
├───────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│  ✅ Stateless application design                                           │
│     • No session data in application memory                                │
│     • JWT tokens for authentication                                        │
│     • External state storage (Redis/Database)                              │
│                                                                            │
│  ✅ Auto-scaling configuration                                             │
│     • Kubernetes HPA: min=3, max=10                                        │
│     • Target CPU: 70%, Memory: 80%                                         │
│     • Scale based on metrics                                               │
│                                                                            │
│  📊 Expected Result: 10x scalability                                       │
└───────────────────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────────────────┐
│  2. LOAD BALANCING                                                         │
├───────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│  ✅ Nginx/HAProxy configuration                                            │
│     • Least connections algorithm                                          │
│     • Health checks every 3s                                               │
│     • Session persistence if needed                                        │
│                                                                            │
│  ✅ Multiple layers                                                        │
│     • L7: Application load balancer                                        │
│     • L4: Network load balancer                                            │
│     • CDN: Edge caching                                                    │
│                                                                            │
│  📊 Expected Result: No single point of failure                            │
└───────────────────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────────────────┐
│  3. DATABASE OPTIMIZATION                                                  │
├───────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│  ✅ Read replicas                                                          │
│     • 1 Master (writes) + 2+ Slaves (reads)                                │
│     • Automatic failover with Sentinel                                     │
│     • Connection pooling: pool_size=20                                     │
│                                                                            │
│  ✅ Query optimization                                                     │
│     • Indexes on all foreign keys                                          │
│     • No SELECT * queries                                                  │
│     • Batch operations where possible                                      │
│                                                                            │
│  📊 Expected Result: 5x read scalability                                   │
└───────────────────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────────────────┐
│  4. CACHING STRATEGY                                                       │
├───────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│  ✅ Redis caching                                                          │
│     • Cache frequently accessed data                                       │
│     • TTL: 1-24 hours depending on data                                    │
│     • Cache warming on startup                                             │
│                                                                            │
│  ✅ CDN for static assets                                                  │
│     • CloudFlare/CloudFront                                                │
│     • 1 year cache for immutable files                                     │
│     • Automatic compression                                                │
│                                                                            │
│  📊 Expected Result: 100x faster data access                               │
└───────────────────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────────────────┐
│  5. ASYNC PROCESSING                                                       │
├───────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│  ✅ Celery task queue                                                      │
│     • Background OCR processing                                            │
│     • Multiple worker pools                                                │
│     • Priority queues for urgent jobs                                      │
│                                                                            │
│  ✅ Message broker                                                         │
│     • RabbitMQ for reliability                                             │
│     • Redis Streams for simplicity                                         │
│     • Dead letter queues for failures                                      │
│                                                                            │
│  📊 Expected Result: Zero blocking operations                              │
└───────────────────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────────────────┐
│  6. MICROSERVICES                                                          │
├───────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│  ✅ Service separation                                                     │
│     • Auth Service (8001)                                                  │
│     • User Service (8002)                                                  │
│     • Document Service (8003)                                              │
│     • OCR Service (8004)                                                   │
│     • Queue Service (8005)                                                 │
│     • Results Service (8006)                                               │
│                                                                            │
│  ✅ Independent deployment                                                 │
│     • Each service scales independently                                    │
│     • Separate databases per service                                       │
│     • Fault isolation                                                      │
│                                                                            │
│  📊 Expected Result: Independent scaling per service                       │
└───────────────────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────────────────┐
│  7. PERFORMANCE BENCHMARKS                                                 │
├───────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│  Target Metrics:                                                           │
│  ✅ Response time (p95): < 200ms                                           │
│  ✅ Response time (p99): < 500ms                                           │
│  ✅ Throughput: > 10,000 req/s                                             │
│  ✅ Error rate: < 0.1%                                                     │
│  ✅ Uptime: > 99.9%                                                        │
│                                                                            │
│  Load Testing Tools:                                                       │
│  • K6 for stress testing                                                   │
│  • Locust for user simulation                                              │
│  • Custom async load tester                                                │
│                                                                            │
│  📊 Expected Result: Consistent performance under load                     │
└───────────────────────────────────────────────────────────────────────────┘

╔═══════════════════════════════════════════════════════════════════════════╗
║                           IMPLEMENTATION PRIORITIES                        ║
╚═══════════════════════════════════════════════════════════════════════════╝

PHASE 1 (Week 1-2): Foundation
  🔴 Stateless application design
  🔴 Connection pooling
  🔴 Basic caching (Redis)
  🔴 Load balancer setup

PHASE 2 (Week 3-4): Database Optimization
  🟠 Read replicas
  🟠 Query optimization
  🟠 Index creation
  🟠 Connection pool tuning

PHASE 3 (Week 5-6): Async & Queuing
  🟡 Celery setup
  🟡 RabbitMQ configuration
  🟡 Background workers
  🟡 Priority queues

PHASE 4 (Week 7-8): Microservices
  🟢 Service decomposition
  🟢 Service mesh
  🟢 API gateway
  🟢 Service discovery

PHASE 5 (Week 9-10): Production Ready
  ⚪ Monitoring (Prometheus/Grafana)
  ⚪ Logging (ELK)
  ⚪ Alerting
  ⚪ Load testing

PHASE 6 (Week 11-12): Optimization
  ⚪ Performance tuning
  ⚪ Cost optimization
  ⚪ Documentation
  ⚪ Training

╔═══════════════════════════════════════════════════════════════════════════╗
║                              SUCCESS METRICS                               ║
╚═══════════════════════════════════════════════════════════════════════════╝

Before Optimization:
  • Throughput: 100 req/s
  • Response time: 2-5 seconds
  • Max concurrent users: 100
  • Uptime: 95%

After Optimization:
  • Throughput: 10,000+ req/s (100x improvement)
  • Response time: 50-200ms (20x improvement)
  • Max concurrent users: 50,000+ (500x improvement)
  • Uptime: 99.9%+ (5x improvement)

ROI:
  • Infrastructure costs: +50%
  • User capacity: +5000%
  • Customer satisfaction: +300%
  • Revenue potential: +1000%
"""

print(KEY_TAKEAWAYS)

