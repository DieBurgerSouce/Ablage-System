TROUBLESHOOTING & DEBUGGING GUIDE
Complete Guide for Debugging Production Systems

📋 TABLE OF CONTENTS

Introduction
Common Issues & Solutions
Debug Mode Configuration
Database Connection Issues
Memory Leaks Detection
Performance Bottlenecks
Log Analysis
Production Debugging


🎯 INTRODUCTION
Debugging Philosophy
┌────────────────────────────────────────────────────────────┐
│              DEBUGGING PROCESS FLOW                         │
├────────────────────────────────────────────────────────────┤
│                                                            │
│  1. OBSERVE                                                │
│     └─→ Collect symptoms, metrics, logs                   │
│                                                            │
│  2. HYPOTHESIZE                                            │
│     └─→ Form theories about root cause                    │
│                                                            │
│  3. TEST                                                   │
│     └─→ Validate hypotheses systematically                │
│                                                            │
│  4. FIX                                                    │
│     └─→ Implement solution                                │
│                                                            │
│  5. VERIFY                                                 │
│     └─→ Confirm issue is resolved                         │
│                                                            │
│  6. DOCUMENT                                               │
│     └─→ Record problem & solution                         │
│                                                            │
└────────────────────────────────────────────────────────────┘
Essential Debugging Tools
python# debugging/essential_tools.py

"""
Essential Debugging Tools

Must-have tools for every developer
"""

DEBUGGING_TOOLKIT = {
    'Python Debugging': {
        'pdb': 'Built-in Python debugger',
        'ipdb': 'IPython-enhanced debugger',
        'pudb': 'Full-screen console debugger',
        'pdb++': 'Enhanced pdb with syntax highlighting'
    },
    
    'Profiling': {
        'cProfile': 'Built-in Python profiler',
        'line_profiler': 'Line-by-line profiling',
        'memory_profiler': 'Memory usage profiling',
        'py-spy': 'Sampling profiler (production-safe)'
    },
    
    'Monitoring': {
        'htop': 'Interactive process viewer',
        'iotop': 'I/O monitoring',
        'nethogs': 'Network bandwidth per process',
        'glances': 'All-in-one monitoring'
    },
    
    'Database': {
        'pg_stat_statements': 'PostgreSQL query statistics',
        'pgBadger': 'PostgreSQL log analyzer',
        'mysqltuner': 'MySQL performance tuning',
        'redis-cli': 'Redis debugging'
    },
    
    'Network': {
        'tcpdump': 'Network packet analyzer',
        'wireshark': 'Network protocol analyzer',
        'curl': 'HTTP debugging',
        'netstat': 'Network statistics'
    },
    
    'System': {
        'strace': 'System call tracer',
        'lsof': 'List open files',
        'dmesg': 'Kernel messages',
        'journalctl': 'Systemd logs'
    }
}

# Quick installation
INSTALL_COMMANDS = """
# Python debugging tools
pip install ipdb pudb pdbpp
pip install line-profiler memory-profiler py-spy

# System monitoring
apt-get install htop iotop nethogs glances

# Network tools
apt-get install tcpdump wireshark curl net-tools

# Database tools
apt-get install postgresql-contrib
"""

🚨 COMMON ISSUES & SOLUTIONS
1. Application Won't Start
python# troubleshooting/startup_issues.py

"""
Application Startup Issues

Common problems preventing application from starting
"""

from typing import Dict, List
from dataclasses import dataclass


@dataclass
class StartupIssue:
    """Startup issue definition"""
    symptom: str
    causes: List[str]
    solutions: List[str]
    debugging_steps: List[str]


STARTUP_ISSUES = {
    'port_already_in_use': StartupIssue(
        symptom="Error: Address already in use / Port 8000 is already allocated",
        
        causes=[
            "Another process using the same port",
            "Previous process didn't terminate cleanly",
            "Multiple instances started accidentally"
        ],
        
        solutions=[
            """
# Find process using port
lsof -i :8000
# or
netstat -tulpn | grep 8000
# or
ss -tulpn | grep 8000

# Kill the process
kill -9 <PID>

# Change port in configuration
uvicorn main:app --port 8001
            """,
            """
# Use systemd to manage properly
systemctl stop your-app
systemctl start your-app
            """,
            """
# Allow port reuse in code
import socket

sock = socket.socket()
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
sock.bind(('0.0.0.0', 8000))
            """
        ],
        
        debugging_steps=[
            "Check which process owns the port: lsof -i :8000",
            "Verify application configuration for port number",
            "Check if process is managed by systemd/supervisor",
            "Review startup logs: journalctl -u your-app -n 50"
        ]
    ),
    
    'database_connection_failed': StartupIssue(
        symptom="Could not connect to database / Connection refused",
        
        causes=[
            "Database not running",
            "Wrong connection credentials",
            "Network connectivity issues",
            "Database at capacity (max connections)",
            "Firewall blocking connection"
        ],
        
        solutions=[
            """
# Check database is running
systemctl status postgresql
# or
pg_isready -h localhost -p 5432

# Test connection manually
psql -h localhost -U username -d database_name

# Check database logs
tail -f /var/log/postgresql/postgresql-15-main.log
            """,
            """
# Verify connection string
DATABASE_URL=postgresql://user:pass@localhost:5432/dbname

# Test with psql
psql "$DATABASE_URL"
            """,
            """
# Check max connections
SELECT max_conn,used,res_for_super 
FROM (
  SELECT count(*) used 
  FROM pg_stat_activity
) t1,
(
  SELECT setting::int res_for_super 
  FROM pg_settings 
  WHERE name='superuser_reserved_connections'
) t2,
(
  SELECT setting::int max_conn 
  FROM pg_settings 
  WHERE name='max_connections'
) t3;

# Increase max_connections if needed
ALTER SYSTEM SET max_connections = 200;
SELECT pg_reload_conf();
            """,
            """
# Check firewall
sudo ufw status
sudo iptables -L -n

# Allow PostgreSQL
sudo ufw allow 5432/tcp
            """
        ],
        
        debugging_steps=[
            "Verify DATABASE_URL environment variable",
            "Test connection with psql CLI",
            "Check database server is running",
            "Review database server logs",
            "Verify network connectivity (ping, telnet)",
            "Check connection pool settings"
        ]
    ),
    
    'import_error': StartupIssue(
        symptom="ModuleNotFoundError / ImportError",
        
        causes=[
            "Package not installed",
            "Wrong virtual environment",
            "Circular imports",
            "Python path issues",
            "Package version conflict"
        ],
        
        solutions=[
            """
# Check installed packages
pip list
pip show package-name

# Install missing package
pip install package-name

# Install from requirements
pip install -r requirements.txt
            """,
            """
# Verify correct venv is activated
which python
python --version

# Check Python path
python -c "import sys; print(sys.path)"
            """,
            """
# Fix circular imports
# main.py
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from module_b import ClassB  # Only for type hints

class ClassA:
    def method(self, obj: 'ClassB'):  # String annotation
        pass
            """,
            """
# Check for version conflicts
pip check

# Create fresh environment
python -m venv venv_new
source venv_new/bin/activate
pip install -r requirements.txt
            """
        ],
        
        debugging_steps=[
            "Confirm virtual environment is activated",
            "Check requirements.txt vs installed packages",
            "Look for circular import patterns",
            "Review import statements in error traceback",
            "Test imports in Python REPL"
        ]
    ),
    
    'configuration_error': StartupIssue(
        symptom="Configuration file not found / Invalid configuration",
        
        causes=[
            "Missing .env file",
            "Wrong environment variables",
            "Invalid configuration syntax",
            "Missing required settings"
        ],
        
        solutions=[
            """
# Create .env file
cp .env.example .env

# Edit with correct values
nano .env

# Load environment variables
export $(cat .env | xargs)

# Verify loaded
env | grep DATABASE_URL
            """,
            """
# Validate configuration
python -c "
from config import settings
print(settings.dict())
"
            """,
            """
# Use configuration validation
from pydantic import BaseSettings, validator

class Settings(BaseSettings):
    DATABASE_URL: str
    REDIS_URL: str
    
    @validator('DATABASE_URL')
    def validate_db_url(cls, v):
        if not v.startswith('postgresql://'):
            raise ValueError('Invalid database URL')
        return v
    
    class Config:
        env_file = '.env'

settings = Settings()  # Will raise error if invalid
            """,
            """
# Provide defaults for optional settings
import os

DATABASE_URL = os.getenv(
    'DATABASE_URL',
    'postgresql://localhost/default_db'
)
            """
        ],
        
        debugging_steps=[
            "Check if .env file exists",
            "Verify environment variables are loaded",
            "Review configuration schema",
            "Test configuration parsing separately",
            "Check file permissions on config files"
        ]
    )
}


def diagnose_startup_issue(symptom: str):
    """
    Diagnose startup issue based on symptom.
    
    Args:
        symptom: Error message or symptom
    """
    print("="*80)
    print("STARTUP ISSUE DIAGNOSIS")
    print("="*80)
    
    # Find matching issue
    for issue_key, issue in STARTUP_ISSUES.items():
        if any(keyword in symptom.lower() for keyword in issue_key.split('_')):
            print(f"\n📋 Issue: {issue_key.replace('_', ' ').title()}")
            print(f"\n🔍 Symptom:")
            print(f"   {issue.symptom}")
            
            print(f"\n❓ Possible Causes:")
            for i, cause in enumerate(issue.causes, 1):
                print(f"   {i}. {cause}")
            
            print(f"\n✅ Solutions:")
            for i, solution in enumerate(issue.solutions, 1):
                print(f"\n   Solution {i}:")
                print(solution)
            
            print(f"\n🔧 Debugging Steps:")
            for i, step in enumerate(issue.debugging_steps, 1):
                print(f"   {i}. {step}")
            
            return
    
    print("\n❌ No matching issue found. Check logs for more details.")


# Example usage
if __name__ == "__main__":
    # Diagnose common issues
    diagnose_startup_issue("Address already in use")
2. Runtime Errors
python# troubleshooting/runtime_errors.py

"""
Runtime Error Debugging

Handle errors that occur during operation
"""

import traceback
import sys
from functools import wraps
from loguru import logger


# ============================================
# ERROR HANDLING DECORATOR
# ============================================

def handle_errors(reraise=True, log=True):
    """
    Decorator to handle and log errors.
    
    Args:
        reraise: Re-raise exception after handling
        log: Log exception details
    
    Example:
        @handle_errors(reraise=False)
        def risky_function():
            # ... code that might fail ...
            pass
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if log:
                    logger.error(
                        f"Error in {func.__name__}: {e}",
                        exc_info=True
                    )
                
                # Print detailed traceback
                print("\n" + "="*80)
                print("EXCEPTION DETAILS")
                print("="*80)
                print(f"\nFunction: {func.__name__}")
                print(f"Exception: {type(e).__name__}")
                print(f"Message: {str(e)}")
                print(f"\nTraceback:")
                traceback.print_exc()
                print("="*80)
                
                if reraise:
                    raise
                
                return None
        
        return wrapper
    return decorator


# ============================================
# DETAILED ERROR INFORMATION
# ============================================

def print_exception_details(exc_info=None):
    """
    Print detailed exception information.
    
    Args:
        exc_info: Exception info tuple (type, value, traceback)
    """
    if exc_info is None:
        exc_info = sys.exc_info()
    
    exc_type, exc_value, exc_traceback = exc_info
    
    print("\n" + "="*80)
    print("DETAILED EXCEPTION ANALYSIS")
    print("="*80)
    
    # Exception type and message
    print(f"\n📛 Exception Type: {exc_type.__name__}")
    print(f"💬 Message: {exc_value}")
    
    # Stack trace
    print(f"\n📚 Stack Trace:")
    tb_lines = traceback.format_tb(exc_traceback)
    for i, line in enumerate(tb_lines, 1):
        print(f"\n   Frame {i}:")
        print(f"   {line}")
    
    # Local variables in each frame
    print(f"\n🔍 Local Variables:")
    tb = exc_traceback
    frame_num = 1
    while tb is not None:
        frame = tb.tb_frame
        print(f"\n   Frame {frame_num} - {frame.f_code.co_filename}:{tb.tb_lineno}")
        print(f"   Function: {frame.f_code.co_name}")
        
        # Print local variables
        for var_name, var_value in frame.f_locals.items():
            try:
                value_str = repr(var_value)
                if len(value_str) > 100:
                    value_str = value_str[:100] + "..."
                print(f"      {var_name} = {value_str}")
            except:
                print(f"      {var_name} = <unable to repr>")
        
        tb = tb.tb_next
        frame_num += 1
    
    print("\n" + "="*80)


# ============================================
# COMMON RUNTIME ERRORS
# ============================================

RUNTIME_ERROR_SOLUTIONS = {
    'KeyError': {
        'description': 'Accessing non-existent dictionary key',
        'common_causes': [
            'Key doesn\'t exist in dictionary',
            'Typo in key name',
            'Expecting key that wasn\'t set'
        ],
        'solutions': [
            """
# ❌ Bad: Direct access
value = my_dict['key']

# ✅ Good: Use .get() with default
value = my_dict.get('key', default_value)

# ✅ Good: Check before access
if 'key' in my_dict:
    value = my_dict['key']

# ✅ Good: Use defaultdict
from collections import defaultdict
my_dict = defaultdict(list)
my_dict['key'].append(item)  # No KeyError
            """
        ]
    },
    
    'AttributeError': {
        'description': 'Accessing non-existent attribute',
        'common_causes': [
            'Object is None',
            'Attribute name typo',
            'Object type different than expected'
        ],
        'solutions': [
            """
# ❌ Bad: Assume object exists
user.name = "John"

# ✅ Good: Check for None
if user is not None:
    user.name = "John"

# ✅ Good: Use getattr with default
name = getattr(user, 'name', 'Unknown')

# ✅ Good: Use hasattr
if hasattr(user, 'name'):
    user.name = "John"
            """
        ]
    },
    
    'IndexError': {
        'description': 'List index out of range',
        'common_causes': [
            'Empty list',
            'Index beyond list length',
            'Off-by-one error'
        ],
        'solutions': [
            """
# ❌ Bad: Assume list has items
first_item = my_list[0]

# ✅ Good: Check length
if len(my_list) > 0:
    first_item = my_list[0]

# ✅ Good: Use try-except
try:
    first_item = my_list[0]
except IndexError:
    first_item = None

# ✅ Good: Use slice (returns empty list if out of range)
first_items = my_list[:1]
            """
        ]
    },
    
    'TypeError': {
        'description': 'Operation on incompatible types',
        'common_causes': [
            'Calling non-callable',
            'Wrong number of arguments',
            'Type mismatch in operation'
        ],
        'solutions': [
            """
# ❌ Bad: Assume type
result = value + 10

# ✅ Good: Type checking
if isinstance(value, (int, float)):
    result = value + 10

# ✅ Good: Type conversion
result = int(value) + 10

# ✅ Good: Type hints + validation
from typing import Union

def process(value: Union[int, float]) -> float:
    if not isinstance(value, (int, float)):
        raise TypeError(f"Expected int or float, got {type(value)}")
    return float(value) + 10
            """
        ]
    },
    
    'ValueError': {
        'description': 'Invalid value for operation',
        'common_causes': [
            'Invalid format for conversion',
            'Value out of valid range',
            'Unexpected input format'
        ],
        'solutions': [
            """
# ❌ Bad: Assume valid format
number = int(user_input)

# ✅ Good: Validate before conversion
try:
    number = int(user_input)
except ValueError:
    print(f"Invalid number: {user_input}")
    number = 0

# ✅ Good: Validate with regex
import re
if re.match(r'^\\d+$', user_input):
    number = int(user_input)

# ✅ Good: Pydantic validation
from pydantic import BaseModel, validator

class UserInput(BaseModel):
    age: int
    
    @validator('age')
    def validate_age(cls, v):
        if not 0 <= v <= 150:
            raise ValueError('Age must be 0-150')
        return v
            """
        ]
    }
}


# ============================================
# EXAMPLE: COMPREHENSIVE ERROR HANDLING
# ============================================

@handle_errors(reraise=False, log=True)
def example_function_with_error():
    """Example function that demonstrates error handling"""
    data = {'name': 'John', 'age': 30}
    
    # This will cause KeyError
    email = data['email']
    
    return email


if __name__ == "__main__":
    # Test error handling
    print("Testing error handling...")
    result = example_function_with_error()
    print(f"Result: {result}")
    
    # Print error solutions
    print("\n" + "="*80)
    print("COMMON RUNTIME ERROR SOLUTIONS")
    print("="*80)
    
    for error_type, info in RUNTIME_ERROR_SOLUTIONS.items():
        print(f"\n{error_type}")
        print(f"  Description: {info['description']}")
        print(f"\n  Common Causes:")
        for cause in info['common_causes']:
            print(f"    • {cause}")
        print(f"\n  Solutions:")
        for solution in info['solutions']:
            print(solution)

🐛 DEBUG MODE CONFIGURATION
1. FastAPI Debug Configuration
python# config/debug_config.py

"""
Debug Mode Configuration

Configure debugging for development and production
"""

from pydantic import BaseSettings
from typing import Optional
import logging
from loguru import logger
import sys


class DebugSettings(BaseSettings):
    """
    Debug configuration settings.
    
    Environment variables:
    - DEBUG: Enable debug mode
    - LOG_LEVEL: Logging level
    - ENABLE_PROFILING: Enable profiling
    - ENABLE_TRACING: Enable distributed tracing
    """
    
    # Debug mode
    DEBUG: bool = False
    
    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"  # or "text"
    LOG_FILE: Optional[str] = None
    
    # Profiling
    ENABLE_PROFILING: bool = False
    PROFILE_DIR: str = "./profiles"
    
    # Tracing
    ENABLE_TRACING: bool = False
    JAEGER_HOST: str = "localhost"
    JAEGER_PORT: int = 6831
    
    # Database query logging
    LOG_SQL_QUERIES: bool = False
    
    # Request/Response logging
    LOG_REQUESTS: bool = False
    LOG_RESPONSES: bool = False
    
    class Config:
        env_file = ".env"


def setup_logging(settings: DebugSettings):
    """
    Configure logging based on settings.
    
    Args:
        settings: Debug settings
    """
    # Remove default logger
    logger.remove()
    
    # Console logging
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
               "<level>{level: <8}</level> | "
               "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
               "<level>{message}</level>",
        level=settings.LOG_LEVEL,
        colorize=True
    )
    
    # File logging
    if settings.LOG_FILE:
        logger.add(
            settings.LOG_FILE,
            rotation="500 MB",
            retention="10 days",
            compression="zip",
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
            level=settings.LOG_LEVEL
        )
    
    # JSON logging for production
    if settings.LOG_FORMAT == "json":
        logger.add(
            sys.stderr,
            format="{message}",
            level=settings.LOG_LEVEL,
            serialize=True  # Output as JSON
        )
    
    logger.info(f"Logging configured: level={settings.LOG_LEVEL}, format={settings.LOG_FORMAT}")


# ============================================
# FASTAPI DEBUG MIDDLEWARE
# ============================================

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from time import time
import json


def setup_debug_middleware(app: FastAPI, settings: DebugSettings):
    """
    Add debug middleware to FastAPI app.
    
    Args:
        app: FastAPI application
        settings: Debug settings
    """
    
    # Request/Response logging
    if settings.LOG_REQUESTS or settings.LOG_RESPONSES:
        @app.middleware("http")
        async def log_requests(request: Request, call_next):
            """Log HTTP requests and responses"""
            request_id = request.headers.get("X-Request-ID", "unknown")
            
            # Log request
            if settings.LOG_REQUESTS:
                logger.info(
                    f"Request: {request.method} {request.url.path}",
                    extra={
                        "request_id": request_id,
                        "method": request.method,
                        "path": request.url.path,
                        "query_params": dict(request.query_params),
                        "client_ip": request.client.host
                    }
                )
            
            # Process request
            start_time = time()
            response = await call_next(request)
            duration = time() - start_time
            
            # Log response
            if settings.LOG_RESPONSES:
                logger.info(
                    f"Response: {response.status_code} ({duration:.3f}s)",
                    extra={
                        "request_id": request_id,
                        "status_code": response.status_code,
                        "duration": duration
                    }
                )
            
            # Add debug headers
            if settings.DEBUG:
                response.headers["X-Debug-Duration"] = f"{duration:.3f}"
                response.headers["X-Request-ID"] = request_id
            
            return response
    
    # SQL query logging
    if settings.LOG_SQL_QUERIES:
        from sqlalchemy import event
        from sqlalchemy.engine import Engine
        
        @event.listens_for(Engine, "before_cursor_execute")
        def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
            conn.info.setdefault('query_start_time', []).append(time())
            logger.debug(f"SQL Query: {statement}")
            logger.debug(f"Parameters: {parameters}")
        
        @event.listens_for(Engine, "after_cursor_execute")
        def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
            total = time() - conn.info['query_start_time'].pop(-1)
            logger.debug(f"SQL Query completed in {total:.3f}s")


# ============================================
# PROFILING DECORATOR
# ============================================

from functools import wraps
import cProfile
import pstats
from io import StringIO


def profile(output_file=None):
    """
    Profile function execution.
    
    Args:
        output_file: Output file for profile data
    
    Example:
        @profile(output_file="profile.prof")
        def slow_function():
            # ... code ...
            pass
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            profiler = cProfile.Profile()
            profiler.enable()
            
            try:
                result = func(*args, **kwargs)
            finally:
                profiler.disable()
                
                # Print stats
                s = StringIO()
                stats = pstats.Stats(profiler, stream=s)
                stats.sort_stats('cumulative')
                stats.print_stats(20)  # Top 20
                
                logger.info(f"\nProfile for {func.__name__}:\n{s.getvalue()}")
                
                # Save to file
                if output_file:
                    stats.dump_stats(output_file)
                    logger.info(f"Profile saved to {output_file}")
            
            return result
        
        return wrapper
    return decorator


# ============================================
# DEBUG ENDPOINTS
# ============================================

def add_debug_endpoints(app: FastAPI, settings: DebugSettings):
    """
    Add debug endpoints (only in debug mode).
    
    Args:
        app: FastAPI application
        settings: Debug settings
    """
    if not settings.DEBUG:
        return
    
    @app.get("/_debug/config")
    async def debug_config():
        """Show current configuration"""
        return {
            "debug": settings.DEBUG,
            "log_level": settings.LOG_LEVEL,
            "profiling": settings.ENABLE_PROFILING,
            "tracing": settings.ENABLE_TRACING
        }
    
    @app.get("/_debug/health")
    async def debug_health():
        """Detailed health check"""
        import psutil
        
        return {
            "status": "healthy",
            "cpu_percent": psutil.cpu_percent(interval=1),
            "memory_percent": psutil.virtual_memory().percent,
            "disk_percent": psutil.disk_usage('/').percent
        }
    
    @app.get("/_debug/routes")
    async def debug_routes():
        """List all registered routes"""
        routes = []
        for route in app.routes:
            routes.append({
                "path": route.path,
                "methods": list(route.methods) if hasattr(route, 'methods') else [],
                "name": route.name
            })
        return {"routes": routes}
    
    logger.warning("Debug endpoints enabled! Disable in production!")


# ============================================
# COMPLETE DEBUG APP SETUP
# ============================================

def create_debug_app() -> FastAPI:
    """
    Create FastAPI app with full debug configuration.
    
    Returns:
        Configured FastAPI app
    """
    settings = DebugSettings()
    
    # Setup logging
    setup_logging(settings)
    
    # Create app
    app = FastAPI(
        title="OCR API",
        debug=settings.DEBUG,
        docs_url="/docs" if settings.DEBUG else None,  # Disable docs in production
        redoc_url="/redoc" if settings.DEBUG else None
    )
    
    # Setup middleware
    setup_debug_middleware(app, settings)
    
    # Add debug endpoints
    add_debug_endpoints(app, settings)
    
    # CORS (more permissive in debug)
    if settings.DEBUG:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"]
        )
    
    logger.info(f"Application created (DEBUG={settings.DEBUG})")
    
    return app


# ============================================
# EXAMPLE USAGE
# ============================================

if __name__ == "__main__":
    import uvicorn
    
    # Create app with debug configuration
    app = create_debug_app()
    
    @app.get("/")
    async def root():
        logger.debug("Root endpoint called")
        return {"message": "Hello World"}
    
    @app.get("/slow")
    @profile(output_file="slow_endpoint.prof")
    async def slow_endpoint():
        """Profiled endpoint"""
        import time
        time.sleep(1)
        return {"message": "Done"}
    
    # Run with debug
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="debug",
        reload=True  # Auto-reload on code changes
    )



 BACKUP & DISASTER RECOVERY GUIDE - TEIL 2
Testing, Validation & Recovery Procedures

📋 TABLE OF CONTENTS (TEIL 2)

Backup Testing & Validation
Disaster Recovery Plan
RTO/RPO Definitions
Restoration Procedures
Monitoring & Alerting


✅ BACKUP TESTING & VALIDATION
1. Why Test Backups?
┌─────────────────────────────────────────────────────────┐
│         "UNTESTED BACKUPS = NO BACKUPS"                  │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  Common Backup Failures:                                │
│  ❌ Corrupted backup files                              │
│  ❌ Missing WAL files                                   │
│  ❌ Incomplete backups                                  │
│  ❌ Wrong permissions                                   │
│  ❌ Insufficient storage                                │
│  ❌ Network failures during backup                      │
│  ❌ Backup script errors                                │
│  ❌ Encryption key lost                                 │
│                                                         │
│  Without Testing:                                       │
│  ⚠️  You only find out during disaster                  │
│  ⚠️  Recovery time is unknown                           │
│  ⚠️  Team doesn't know procedures                       │
│  ⚠️  Dependencies might be missing                      │
│                                                         │
└─────────────────────────────────────────────────────────┘
2. Automated Backup Testing Script
bash#!/bin/bash
# scripts/test_backup.sh

# ============================================
# AUTOMATED BACKUP TESTING SCRIPT
# ============================================
#
# This script automatically tests backups by:
# 1. Selecting latest backup
# 2. Restoring to test database
# 3. Running validation queries
# 4. Checking data integrity
# 5. Generating test report
#
# Run: ./test_backup.sh
# Cron: 0 2 * * 0 (Every Sunday at 2 AM)
# ============================================

set -euo pipefail

# Configuration
BACKUP_DIR="/var/backups/postgres"
TEST_DB="myapp_test_restore"
PROD_DB="myapp"
LOG_FILE="/var/log/postgres/backup_test.log"
REPORT_FILE="/var/log/postgres/backup_test_report.txt"

# Logging
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

log "========================================="
log "Starting Backup Test"
log "========================================="

# ============================================
# 1. SELECT LATEST BACKUP
# ============================================

log "Finding latest backup..."
LATEST_BACKUP=$(ls -1t "$BACKUP_DIR"/*.sql.gz 2>/dev/null | head -n1)

if [ -z "$LATEST_BACKUP" ]; then
    log "ERROR: No backup files found!"
    exit 1
fi

log "Testing backup: $LATEST_BACKUP"
BACKUP_SIZE=$(du -h "$LATEST_BACKUP" | cut -f1)
log "Backup size: $BACKUP_SIZE"

# ============================================
# 2. VERIFY BACKUP FILE INTEGRITY
# ============================================

log "Checking file integrity..."

# Test if file can be uncompressed
if gunzip -t "$LATEST_BACKUP" 2>/dev/null; then
    log "✅ Backup file is valid (gzip integrity OK)"
else
    log "❌ ERROR: Backup file is corrupted!"
    exit 1
fi

# ============================================
# 3. DROP AND RECREATE TEST DATABASE
# ============================================

log "Preparing test database..."

# Drop test database if exists
psql -U postgres -c "DROP DATABASE IF EXISTS $TEST_DB;" 2>&1 | tee -a "$LOG_FILE"

# Create fresh test database
psql -U postgres -c "CREATE DATABASE $TEST_DB;" 2>&1 | tee -a "$LOG_FILE"

# ============================================
# 4. RESTORE BACKUP TO TEST DATABASE
# ============================================

log "Restoring backup to test database..."
START_TIME=$(date +%s)

gunzip -c "$LATEST_BACKUP" | psql -U postgres -d "$TEST_DB" \
    2>&1 | tee -a "$LOG_FILE"

RESTORE_EXIT_CODE=${PIPESTATUS[1]}
END_TIME=$(date +%s)
RESTORE_DURATION=$((END_TIME - START_TIME))

if [ $RESTORE_EXIT_CODE -eq 0 ]; then
    log "✅ Restore completed in ${RESTORE_DURATION}s"
else
    log "❌ ERROR: Restore failed!"
    exit 1
fi

# ============================================
# 5. VALIDATE DATA INTEGRITY
# ============================================

log "Running data validation checks..."

# Count tables
TABLE_COUNT=$(psql -U postgres -d "$TEST_DB" -t -c \
    "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';")
log "Tables found: $TABLE_COUNT"

# Count total rows (example - adjust to your schema)
TOTAL_ROWS=$(psql -U postgres -d "$TEST_DB" -t -c \
    "SELECT SUM(n_live_tup) FROM pg_stat_user_tables;")
log "Total rows: ${TOTAL_ROWS:-0}"

# Check if critical tables exist (customize for your schema)
CRITICAL_TABLES=("users" "invoices" "documents")

for table in "${CRITICAL_TABLES[@]}"; do
    EXISTS=$(psql -U postgres -d "$TEST_DB" -t -c \
        "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = '$table');")
    
    if [[ "$EXISTS" == *"t"* ]]; then
        ROW_COUNT=$(psql -U postgres -d "$TEST_DB" -t -c "SELECT COUNT(*) FROM $table;")
        log "✅ Table '$table' exists with $ROW_COUNT rows"
    else
        log "❌ ERROR: Critical table '$table' is missing!"
        exit 1
    fi
done

# ============================================
# 6. VALIDATE SCHEMA INTEGRITY
# ============================================

log "Validating schema..."

# Check for foreign keys
FK_COUNT=$(psql -U postgres -d "$TEST_DB" -t -c \
    "SELECT COUNT(*) FROM information_schema.table_constraints WHERE constraint_type = 'FOREIGN KEY';")
log "Foreign keys: $FK_COUNT"

# Check for indexes
INDEX_COUNT=$(psql -U postgres -d "$TEST_DB" -t -c \
    "SELECT COUNT(*) FROM pg_indexes WHERE schemaname = 'public';")
log "Indexes: $INDEX_COUNT"

# ============================================
# 7. COMPARE WITH PRODUCTION (OPTIONAL)
# ============================================

log "Comparing with production database..."

# Compare table counts
PROD_TABLE_COUNT=$(psql -U postgres -d "$PROD_DB" -t -c \
    "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';")

if [ "$TABLE_COUNT" -eq "$PROD_TABLE_COUNT" ]; then
    log "✅ Table count matches production"
else
    log "⚠️  WARNING: Table count mismatch (Prod: $PROD_TABLE_COUNT, Test: $TABLE_COUNT)"
fi

# ============================================
# 8. GENERATE TEST REPORT
# ============================================

log "Generating test report..."

cat > "$REPORT_FILE" << EOF
================================================================================
BACKUP TEST REPORT
================================================================================

Test Date:           $(date '+%Y-%m-%d %H:%M:%S')
Backup File:         $LATEST_BACKUP
Backup Size:         $BACKUP_SIZE
Backup Date:         $(stat -c %y "$LATEST_BACKUP")

RESTORE METRICS:
- Restore Duration:  ${RESTORE_DURATION}s
- Restore Status:    SUCCESS

DATA VALIDATION:
- Tables Count:      $TABLE_COUNT
- Total Rows:        ${TOTAL_ROWS:-0}
- Foreign Keys:      $FK_COUNT
- Indexes:           $INDEX_COUNT

CRITICAL TABLES:
$(for table in "${CRITICAL_TABLES[@]}"; do
    COUNT=$(psql -U postgres -d "$TEST_DB" -t -c "SELECT COUNT(*) FROM $table;" 2>/dev/null || echo "0")
    printf "  %-20s %s rows\n" "$table:" "$COUNT"
done)

PRODUCTION COMPARISON:
- Prod Tables:       $PROD_TABLE_COUNT
- Test Tables:       $TABLE_COUNT
- Match:             $([ "$TABLE_COUNT" -eq "$PROD_TABLE_COUNT" ] && echo "YES" || echo "NO")

OVERALL STATUS:      ✅ PASSED

Notes:
- Backup is valid and restorable
- All critical tables present
- Data integrity verified

================================================================================
EOF

cat "$REPORT_FILE"

# ============================================
# 9. CLEANUP
# ============================================

log "Cleaning up test database..."
psql -U postgres -c "DROP DATABASE $TEST_DB;" 2>&1 | tee -a "$LOG_FILE"

log "========================================="
log "Backup Test Completed Successfully!"
log "========================================="
log "Report saved to: $REPORT_FILE"

# ============================================
# 10. SEND NOTIFICATION (OPTIONAL)
# ============================================

# Email notification
# cat "$REPORT_FILE" | mail -s "Backup Test Report - $(date '+%Y-%m-%d')" admin@example.com

# Slack notification
# curl -X POST -H 'Content-type: application/json' \
#   --data '{"text":"✅ Backup test completed successfully"}' \
#   $SLACK_WEBHOOK_URL
3. Backup Validation Levels
python# scripts/validate_backup.py

"""
Multi-level backup validation system
"""

import os
import gzip
import hashlib
import psycopg2
from datetime import datetime
from typing import Dict, List, Tuple

class BackupValidator:
    """
    Validates backups at multiple levels:
    - Level 1: File integrity
    - Level 2: SQL syntax
    - Level 3: Restore test
    - Level 4: Data validation
    - Level 5: Performance test
    """
    
    def __init__(self, backup_file: str, db_config: Dict):
        self.backup_file = backup_file
        self.db_config = db_config
        self.results = {}
    
    def validate_level_1_file_integrity(self) -> bool:
        """
        Level 1: Basic file checks
        - File exists
        - File size > 0
        - Gzip integrity
        - Checksum validation (if available)
        """
        print("🔍 Level 1: File Integrity Check")
        
        # Check file exists
        if not os.path.exists(self.backup_file):
            print("  ❌ File not found")
            return False
        
        # Check file size
        size = os.path.getsize(self.backup_file)
        if size == 0:
            print("  ❌ File is empty")
            return False
        
        print(f"  ✅ File size: {size / (1024**2):.2f} MB")
        
        # Test gzip integrity
        try:
            with gzip.open(self.backup_file, 'rb') as f:
                # Read first 1MB to test
                f.read(1024 * 1024)
            print("  ✅ Gzip integrity OK")
        except Exception as e:
            print(f"  ❌ Gzip error: {e}")
            return False
        
        # Calculate checksum
        md5 = hashlib.md5()
        with open(self.backup_file, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b''):
                md5.update(chunk)
        checksum = md5.hexdigest()
        print(f"  ✅ MD5 checksum: {checksum}")
        
        self.results['level_1'] = 'PASSED'
        return True
    
    def validate_level_2_sql_syntax(self) -> bool:
        """
        Level 2: SQL content validation
        - Check for SQL syntax errors
        - Verify critical statements present
        """
        print("\n🔍 Level 2: SQL Syntax Check")
        
        try:
            with gzip.open(self.backup_file, 'rt', encoding='utf-8') as f:
                content = f.read()
            
            # Check for critical SQL statements
            checks = {
                'CREATE TABLE': 'CREATE TABLE' in content,
                'INSERT': 'INSERT INTO' in content or 'COPY' in content,
                'Foreign Keys': 'FOREIGN KEY' in content or 'REFERENCES' in content,
            }
            
            for check_name, passed in checks.items():
                status = "✅" if passed else "❌"
                print(f"  {status} {check_name}: {'Found' if passed else 'Not found'}")
            
            if all(checks.values()):
                self.results['level_2'] = 'PASSED'
                return True
            else:
                self.results['level_2'] = 'FAILED'
                return False
                
        except Exception as e:
            print(f"  ❌ Error reading SQL: {e}")
            self.results['level_2'] = 'ERROR'
            return False
    
    def validate_level_3_restore_test(self, test_db: str = 'backup_test') -> bool:
        """
        Level 3: Actual restore test
        - Create test database
        - Restore backup
        - Verify completion
        """
        print("\n🔍 Level 3: Restore Test")
        
        conn = None
        try:
            # Connect to postgres database
            conn = psycopg2.connect(**self.db_config, database='postgres')
            conn.autocommit = True
            cur = conn.cursor()
            
            # Drop test database if exists
            cur.execute(f"DROP DATABASE IF EXISTS {test_db}")
            print(f"  ✅ Cleaned up old test database")
            
            # Create test database
            cur.execute(f"CREATE DATABASE {test_db}")
            print(f"  ✅ Created test database: {test_db}")
            
            cur.close()
            conn.close()
            
            # Restore backup
            import subprocess
            start = datetime.now()
            
            cmd = f"gunzip -c {self.backup_file} | psql -h {self.db_config['host']} -U {self.db_config['user']} -d {test_db}"
            result = subprocess.run(cmd, shell=True, capture_output=True)
            
            duration = (datetime.now() - start).total_seconds()
            
            if result.returncode == 0:
                print(f"  ✅ Restore completed in {duration:.2f}s")
                self.results['level_3'] = 'PASSED'
                self.results['restore_duration'] = duration
                return True
            else:
                print(f"  ❌ Restore failed")
                print(result.stderr.decode())
                self.results['level_3'] = 'FAILED'
                return False
                
        except Exception as e:
            print(f"  ❌ Restore error: {e}")
            self.results['level_3'] = 'ERROR'
            return False
        finally:
            if conn:
                conn.close()
    
    def validate_level_4_data_integrity(self, test_db: str = 'backup_test') -> bool:
        """
        Level 4: Data validation
        - Row counts
        - Table structure
        - Constraints
        """
        print("\n🔍 Level 4: Data Integrity Check")
        
        try:
            conn = psycopg2.connect(**self.db_config, database=test_db)
            cur = conn.cursor()
            
            # Count tables
            cur.execute("""
                SELECT COUNT(*) 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
            """)
            table_count = cur.fetchone()[0]
            print(f"  ✅ Tables: {table_count}")
            
            # Count total rows
            cur.execute("SELECT SUM(n_live_tup) FROM pg_stat_user_tables")
            row_count = cur.fetchone()[0] or 0
            print(f"  ✅ Total rows: {row_count}")
            
            # Check foreign keys
            cur.execute("""
                SELECT COUNT(*) 
                FROM information_schema.table_constraints 
                WHERE constraint_type = 'FOREIGN KEY'
            """)
            fk_count = cur.fetchone()[0]
            print(f"  ✅ Foreign keys: {fk_count}")
            
            cur.close()
            conn.close()
            
            self.results['level_4'] = 'PASSED'
            self.results['table_count'] = table_count
            self.results['row_count'] = row_count
            return True
            
        except Exception as e:
            print(f"  ❌ Validation error: {e}")
            self.results['level_4'] = 'ERROR'
            return False
    
    def cleanup(self, test_db: str = 'backup_test'):
        """Clean up test database"""
        try:
            conn = psycopg2.connect(**self.db_config, database='postgres')
            conn.autocommit = True
            cur = conn.cursor()
            cur.execute(f"DROP DATABASE IF EXISTS {test_db}")
            cur.close()
            conn.close()
            print("\n✅ Cleanup completed")
        except Exception as e:
            print(f"\n⚠️  Cleanup error: {e}")
    
    def run_full_validation(self) -> Dict:
        """Run all validation levels"""
        print("=" * 60)
        print("BACKUP VALIDATION REPORT")
        print(f"File: {self.backup_file}")
        print(f"Time: {datetime.now()}")
        print("=" * 60)
        
        # Level 1
        if not self.validate_level_1_file_integrity():
            return self.results
        
        # Level 2
        if not self.validate_level_2_sql_syntax():
            return self.results
        
        # Level 3
        if not self.validate_level_3_restore_test():
            return self.results
        
        # Level 4
        self.validate_level_4_data_integrity()
        
        # Cleanup
        self.cleanup()
        
        print("\n" + "=" * 60)
        print("VALIDATION COMPLETE")
        print("=" * 60)
        
        return self.results


# Usage
if __name__ == "__main__":
    config = {
        'host': 'localhost',
        'user': 'postgres',
        'password': 'your_password'
    }
    
    validator = BackupValidator(
        backup_file='/var/backups/postgres/backup_20240115.sql.gz',
        db_config=config
    )
    
    results = validator.run_full_validation()
    print("\nFinal Results:", results)
4. Schedule Regular Testing
bash# /etc/cron.d/backup-testing

# Test backups every Sunday at 2 AM
0 2 * * 0 postgres /opt/scripts/test_backup.sh >> /var/log/postgres/backup_test.log 2>&1

# Quick validation every night
0 3 * * * postgres /opt/scripts/validate_latest_backup.sh >> /var/log/postgres/validation.log 2>&1
```

---

## 🆘 DISASTER RECOVERY PLAN

### 1. DR Framework
```
┌─────────────────────────────────────────────────────────┐
│            DISASTER RECOVERY FRAMEWORK                   │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  Phase 1: DETECTION (0-5 min)                          │
│  ├─ Monitoring alerts triggered                        │
│  ├─ Initial incident assessment                        │
│  └─ Severity classification                            │
│                                                         │
│  Phase 2: NOTIFICATION (5-15 min)                      │
│  ├─ Alert team members                                 │
│  ├─ Activate DR team                                   │
│  └─ Notify stakeholders                                │
│                                                         │
│  Phase 3: ASSESSMENT (15-30 min)                       │
│  ├─ Determine extent of damage                         │
│  ├─ Identify affected systems                          │
│  └─ Select recovery strategy                           │
│                                                         │
│  Phase 4: RECOVERY (30 min - RTO)                      │
│  ├─ Execute recovery procedures                        │
│  ├─ Restore from backups                               │
│  └─ Verify system functionality                        │
│                                                         │
│  Phase 5: VALIDATION (Post-Recovery)                   │
│  ├─ Data integrity checks                              │
│  ├─ Application testing                                │
│  └─ Performance verification                           │
│                                                         │
│  Phase 6: POST-MORTEM (24-48h later)                   │
│  ├─ Root cause analysis                                │
│  ├─ Document lessons learned                           │
│  └─ Update DR procedures                               │
│                                                         │
└─────────────────────────────────────────────────────────┘
2. Disaster Scenarios & Responses
python# config/disaster_scenarios.py

"""
Predefined disaster scenarios and recovery procedures
"""

DISASTER_SCENARIOS = {
    "database_corruption": {
        "severity": "CRITICAL",
        "rto": "2 hours",
        "rpo": "15 minutes",
        "detection": [
            "Database won't start",
            "Corruption errors in logs",
            "Data inconsistency reported"
        ],
        "immediate_actions": [
            "1. Stop application to prevent further corruption",
            "2. Verify backup integrity",
            "3. Assess corruption extent"
        ],
        "recovery_procedure": [
            "1. Restore from latest backup",
            "2. Apply WAL files if available",
            "3. Run REINDEX and VACUUM",
            "4. Verify data integrity",
            "5. Restart application"
        ],
        "validation": [
            "Run data integrity checks",
            "Compare row counts with monitoring",
            "Test critical queries"
        ],
        "runbook": "/docs/runbooks/database_corruption.md"
    },
    
    "hardware_failure": {
        "severity": "HIGH",
        "rto": "4 hours",
        "rpo": "30 minutes",
        "detection": [
            "Server unresponsive",
            "Disk failure alerts",
            "Hardware monitoring errors"
        ],
        "immediate_actions": [
            "1. Confirm hardware failure",
            "2. Provision replacement hardware",
            "3. Prepare for full restore"
        ],
        "recovery_procedure": [
            "1. Install OS on new hardware",
            "2. Install PostgreSQL",
            "3. Restore base backup",
            "4. Apply WAL files",
            "5. Update DNS/load balancer"
        ],
        "validation": [
            "Hardware diagnostics",
            "Performance benchmarks",
            "Full application test"
        ],
        "runbook": "/docs/runbooks/hardware_failure.md"
    },
    
    "data_center_outage": {
        "severity": "CRITICAL",
        "rto": "1 hour",
        "rpo": "5 minutes",
        "detection": [
            "Complete site unavailability",
            "Network unreachable",
            "Power failure"
        ],
        "immediate_actions": [
            "1. Activate DR site",
            "2. Verify backup availability",
            "3. Update DNS to DR site"
        ],
        "recovery_procedure": [
            "1. Restore latest backup to DR site",
            "2. Update connection strings",
            "3. Redirect traffic",
            "4. Monitor performance"
        ],
        "validation": [
            "End-to-end testing",
            "Load testing",
            "Data consistency check"
        ],
        "runbook": "/docs/runbooks/datacenter_outage.md"
    },
    
    "ransomware_attack": {
        "severity": "CRITICAL",
        "rto": "8 hours",
        "rpo": "24 hours",  # Use older backup
        "detection": [
            "Files encrypted",
            "Ransom note found",
            "Unusual file modifications"
        ],
        "immediate_actions": [
            "1. DISCONNECT from network immediately",
            "2. DO NOT pay ransom",
            "3. Contact security team",
            "4. Preserve evidence",
            "5. Notify authorities"
        ],
        "recovery_procedure": [
            "1. Wipe affected systems",
            "2. Scan all backups for malware",
            "3. Use backup from BEFORE infection",
            "4. Restore to clean environment",
            "5. Update security measures"
        ],
        "validation": [
            "Full malware scan",
            "Security audit",
            "Network isolation test"
        ],
        "runbook": "/docs/runbooks/ransomware.md"
    },
    
    "accidental_deletion": {
        "severity": "MEDIUM",
        "rto": "30 minutes",
        "rpo": "5 minutes",
        "detection": [
            "User reports missing data",
            "Unexpected row count drop",
            "Application errors"
        ],
        "immediate_actions": [
            "1. Identify what was deleted",
            "2. Check transaction logs",
            "3. Determine recovery point"
        ],
        "recovery_procedure": [
            "1. Use PITR to just before deletion",
            "2. Extract deleted data",
            "3. Re-import to production",
            "4. Verify completeness"
        ],
        "validation": [
            "Row count verification",
            "Data integrity check",
            "User acceptance testing"
        ],
        "runbook": "/docs/runbooks/accidental_deletion.md"
    }
}


def get_recovery_plan(scenario: str) -> dict:
    """Get recovery plan for a specific scenario"""
    return DISASTER_SCENARIOS.get(scenario, {})


def print_recovery_checklist(scenario: str):
    """Print recovery checklist for given scenario"""
    plan = get_recovery_plan(scenario)
    
    if not plan:
        print(f"No plan found for scenario: {scenario}")
        return
    
    print("=" * 60)
    print(f"DISASTER RECOVERY CHECKLIST: {scenario.upper()}")
    print("=" * 60)
    print(f"\nSeverity: {plan['severity']}")
    print(f"RTO: {plan['rto']}")
    print(f"RPO: {plan['rpo']}")
    
    print("\n📍 DETECTION SIGNS:")
    for sign in plan['detection']:
        print(f"  - {sign}")
    
    print("\n⚡ IMMEDIATE ACTIONS:")
    for i, action in enumerate(plan['immediate_actions'], 1):
        print(f"  {action}")
    
    print("\n🔧 RECOVERY PROCEDURE:")
    for step in plan['recovery_procedure']:
        print(f"  {step}")
    
    print("\n✅ VALIDATION:")
    for check in plan['validation']:
        print(f"  - {check}")
    
    print(f"\n📖 Detailed Runbook: {plan['runbook']}")
    print("=" * 60)


if __name__ == "__main__":
    # Example usage
    print_recovery_checklist("database_corruption")
3. DR Team & Responsibilities
yaml# config/dr_team.yaml

disaster_recovery_team:
  incident_commander:
    name: "Senior DevOps Lead"
    role: "Overall coordination and decision making"
    phone: "+49-xxx-xxx-xxxx"
    email: "devops-lead@company.com"
    responsibilities:
      - "Declare disaster state"
      - "Activate DR team"
      - "Make go/no-go decisions"
      - "Communicate with stakeholders"
  
  database_recovery_lead:
    name: "Database Administrator"
    role: "Database restoration"
    phone: "+49-xxx-xxx-xxxx"
    email: "dba@company.com"
    responsibilities:
      - "Assess database damage"
      - "Execute backup restoration"
      - "Verify data integrity"
      - "Performance tuning post-recovery"
  
  application_lead:
    name: "Backend Team Lead"
    role: "Application recovery"
    phone: "+49-xxx-xxx-xxxx"
    email: "backend-lead@company.com"
    responsibilities:
      - "Update application configs"
      - "Test application functionality"
      - "Deploy application updates"
      - "Monitor application health"
  
  infrastructure_lead:
    name: "Infrastructure Engineer"
    role: "Infrastructure provisioning"
    phone: "+49-xxx-xxx-xxxx"
    email: "infra@company.com"
    responsibilities:
      - "Provision replacement hardware"
      - "Configure network"
      - "Manage DNS/load balancers"
      - "Monitor system resources"
  
  communications_lead:
    name: "Product Manager"
    role: "Stakeholder communication"
    phone: "+49-xxx-xxx-xxxx"
    email: "pm@company.com"
    responsibilities:
      - "Update status page"
      - "Communicate with customers"
      - "Internal team updates"
      - "Post-incident report"

escalation_matrix:
  tier_1:
    time: "0-15 minutes"
    team: ["incident_commander", "database_recovery_lead"]
    
  tier_2:
    time: "15-60 minutes"
    team: ["All DR team members"]
    
  tier_3:
    time: "60+ minutes"
    team: ["Executive leadership"]

contact_procedures:
  primary: "PagerDuty incident page"
  backup_1: "Phone tree"
  backup_2: "Emergency Slack channel"
  backup_3: "Email"

communication_templates:
  initial_alert: |
    🚨 DISASTER RECOVERY ACTIVATED
    Incident: {incident_type}
    Severity: {severity}
    Detected: {timestamp}
    Impact: {impact_description}
    Status: Investigation in progress
    
  status_update: |
    📊 DR STATUS UPDATE - {timestamp}
    Current Phase: {phase}
    Progress: {progress_percentage}%
    ETA for Recovery: {eta}
    Next Steps: {next_steps}
    
  recovery_complete: |
    ✅ RECOVERY COMPLETE
    Incident: {incident_type}
    Recovery Time: {actual_recovery_time}
    Data Loss: {data_loss_summary}
    Status: System operational
    Post-mortem: Scheduled for {postmortem_date}
4. Incident Report Template
markdown# DISASTER RECOVERY INCIDENT REPORT

## Incident Overview
- **Incident ID**: DR-2024-001
- **Date/Time**: 2024-01-15 14:30 UTC
- **Severity**: CRITICAL
- **Type**: Database Corruption
- **Duration**: 2h 15m
- **Systems Affected**: Production Database

## Timeline

### Detection (14:30 - 14:35)
- 14:30: Monitoring alerts: Database connection failures
- 14:32: Application errors reported by users
- 14:35: Incident commander paged

### Assessment (14:35 - 14:50)
- 14:37: Database logs show corruption errors
- 14:42: Confirmed: pg_controldata shows invalid checksum
- 14:48: Decision: Full restore required
- 14:50: DR team fully activated

### Recovery (14:50 - 16:30)
- 14:52: Latest backup identified: 14:15 backup
- 15:00: Application stopped, users notified
- 15:05: Database restore initiated
- 15:45: Base restore completed
- 16:00: WAL replay completed
- 16:15: Data integrity checks passed
- 16:25: Application testing completed
- 16:30: System back online

### Validation (16:30 - 16:45)
- 16:32: All critical queries tested
- 16:38: Data count verification passed
- 16:42: Performance baseline restored
- 16:45: Incident closed

## Impact Analysis

### Data Loss
- **RPO Achievement**: 15 minutes (met target)
- **Transactions Lost**: Approximately 12 transactions
- **Affected Users**: 3 users (contacted individually)
- **Data Recovery**: Manual recovery of lost transactions completed

### Business Impact
- **Downtime**: 2 hours
- **RTO Achievement**: 2 hours (met target)
- **Revenue Impact**: Estimated €1,200 in lost sales
- **Customer Impact**: 45 active sessions interrupted

## Root Cause Analysis

### Primary Cause
Hardware fault in RAID controller caused intermittent write failures, leading to corrupted data blocks in PostgreSQL data files.

### Contributing Factors
1. Aging hardware (controller was 4 years old)
2. No predictive failure detection
3. Delayed hardware monitoring alert (15 min delay)

### Why It Wasn't Prevented
- Hardware was within normal MTBF range
- No early warning signs
- SMART data showed no degradation

## Recovery Performance

### What Went Well
✅ Backup was valid and recent (15 min old)
✅ Team responded within SLA (5 min)
✅ Recovery procedure was clear and followed
✅ Communication was effective
✅ Met both RTO and RPO targets

### What Could Be Improved
⚠️ Hardware monitoring could be more aggressive
⚠️ RAID controller should have been replaced proactively
⚠️ Restore took longer than recent tests (expected 1.5h, actual 2h)

## Action Items

| ID | Action | Owner | Priority | Due Date | Status |
|----|--------|-------|----------|----------|--------|
| DR-001 | Replace RAID controller on all production servers | Infrastructure | HIGH | 2024-01-20 | OPEN |
| DR-002 | Implement predictive hardware monitoring | DevOps | MEDIUM | 2024-02-01 | OPEN |
| DR-003 | Update restore time estimates in DR plan | DBA | LOW | 2024-01-25 | OPEN |
| DR-004 | Schedule DR drill to test new hardware | Incident Commander | MEDIUM | 2024-02-15 | OPEN |

## Lessons Learned

1. **Backup Strategy**: Our backup strategy worked perfectly. The 15-minute WAL archiving prevented significant data loss.

2. **Team Preparedness**: Regular DR drills paid off. Team executed flawlessly under pressure.

3. **Hardware Lifecycle**: Need more aggressive hardware replacement policy for critical components.

4. **Monitoring**: Current monitoring detected the issue but could provide earlier warnings.

## Recommendations

### Short Term (< 1 month)
1. Replace all RAID controllers in production environment
2. Increase hardware monitoring sensitivity
3. Update RTO estimates based on actual performance

### Medium Term (1-3 months)
4. Implement predictive hardware failure detection
5. Add more aggressive hardware lifecycle management
6. Schedule quarterly DR drills

### Long Term (3-6 months)
7. Consider moving to cloud infrastructure with managed backups
8. Implement real-time replication for critical databases
9. Build fully automated DR failover

## Appendix

### Commands Executed
```bash
# Stop application
systemctl stop myapp

# Verify backup
gunzip -t /var/backups/postgres/backup_20240115_1415.sql.gz

# Restore database
dropdb myapp
createdb myapp
gunzip -c /var/backups/postgres/backup_20240115_1415.sql.gz | psql myapp

# Apply WAL files
# (automated via recovery.conf)

# Verify
psql myapp -c "SELECT COUNT(*) FROM users;"
```

### Metrics
- Detection Time: 5 minutes
- Notification Time: 7 minutes
- Recovery Time: 2 hours 15 minutes
- Total Downtime: 2 hours
- Data Loss: 15 minutes (12 transactions)

---

**Report Prepared By**: Database Administrator  
**Reviewed By**: Incident Commander  
**Date**: 2024-01-16  
**Status**: Final

📊 RTO/RPO DEFINITIONS
1. Understanding RTO and RPO
python# config/rto_rpo.py

"""
RTO (Recovery Time Objective) vs RPO (Recovery Point Objective)
================================================================

RTO: How long can you afford to be down?
RPO: How much data can you afford to lose?

Example:
- RTO = 4 hours: System must be back online within 4 hours
- RPO = 15 minutes: Can lose max 15 minutes of data
"""

# ============================================
# RTO/RPO MATRIX BY SYSTEM CRITICALITY
# ============================================

RTO_RPO_MATRIX = {
    # Mission Critical Systems
    "tier_1_critical": {
        "description": "Core business systems, revenue-generating",
        "examples": ["E-commerce database", "Payment processing"],
        "rto": "15 minutes",
        "rpo": "< 1 minute",
        "backup_strategy": {
            "primary": "Hot standby with streaming replication",
            "secondary": "Continuous WAL archiving",
            "testing": "Weekly failover tests"
        },
        "cost_impact": "HIGH - Requires redundancy"
    },
    
    # Business Critical
    "tier_2_important": {
        "description": "Important business systems",
        "examples": ["CRM", "Inventory system", "Customer portal"],
        "rto": "1 hour",
        "rpo": "5 minutes",
        "backup_strategy": {
            "primary": "WAL archiving every 5 minutes",
            "secondary": "Daily full backup",
            "testing": "Monthly restore tests"
        },
        "cost_impact": "MEDIUM - Balanced approach"
    },
    
    # Important but not critical
    "tier_3_standard": {
        "description": "Standard business systems",
        "examples": ["Internal tools", "Reporting systems"],
        "rto": "4 hours",
        "rpo": "15 minutes",
        "backup_strategy": {
            "primary": "Daily full backup",
            "secondary": "WAL archiving",
            "testing": "Quarterly restore tests"
        },
        "cost_impact": "LOW - Cost-effective"
    },
    
    # Non-critical
    "tier_4_non_critical": {
        "description": "Development, testing, analytics",
        "examples": ["Dev databases", "Test environments"],
        "rto": "24 hours",
        "rpo": "24 hours",
        "backup_strategy": {
            "primary": "Daily backup",
            "secondary": "None",
            "testing": "Annual restore test"
        },
        "cost_impact": "VERY LOW - Minimal investment"
    }
}
2. RTO/RPO Cost Analysis
python# scripts/rto_rpo_cost_calculator.py

"""
Calculate the cost of achieving different RTO/RPO targets
"""

from typing import Dict, Tuple

def calculate_backup_costs(rto_hours: float, rpo_minutes: float) -> Dict:
    """
    Estimate monthly costs for achieving target RTO/RPO
    
    Returns estimated costs for:
    - Storage
    - Bandwidth
    - Compute (for standby systems)
    - Personnel
    """
    
    costs = {
        "storage_gb_month": 0,
        "bandwidth_gb_month": 0,
        "compute_hours_month": 0,
        "personnel_hours_month": 0
    }
    
    # Storage cost increases with lower RPO (more frequent backups)
    if rpo_minutes <= 1:
        # Continuous archiving + multiple standbys
        costs["storage_gb_month"] = 1000  # WAL + full backups
    elif rpo_minutes <= 15:
        # Frequent WAL archiving
        costs["storage_gb_month"] = 500
    elif rpo_minutes <= 60:
        # Hourly backups
        costs["storage_gb_month"] = 200
    else:
        # Daily backups
        costs["storage_gb_month"] = 50
    
    # Bandwidth for backup transfer
    costs["bandwidth_gb_month"] = costs["storage_gb_month"] * 0.5
    
    # Compute costs for standby systems (lower RTO = hot standbys)
    if rto_hours < 0.5:
        # Hot standby running 24/7
        costs["compute_hours_month"] = 730  # Full month
    elif rto_hours < 2:
        # Warm standby (partial compute)
        costs["compute_hours_month"] = 200
    elif rto_hours < 8:
        # Cold standby (minimal compute)
        costs["compute_hours_month"] = 50
    else:
        # No standby required
        costs["compute_hours_month"] = 0
    
    # Personnel time for setup/maintenance
    if rto_hours < 1 and rpo_minutes < 5:
        costs["personnel_hours_month"] = 40  # High complexity
    elif rto_hours < 4 and rpo_minutes < 30:
        costs["personnel_hours_month"] = 20  # Medium complexity
    else:
        costs["personnel_hours_month"] = 5   # Low complexity
    
    # Calculate dollar costs (example rates)
    costs["total_usd_month"] = (
        costs["storage_gb_month"] * 0.023 +      # S3 pricing
        costs["bandwidth_gb_month"] * 0.09 +      # Data transfer
        costs["compute_hours_month"] * 0.10 +     # EC2 pricing
        costs["personnel_hours_month"] * 50       # Staff time
    )
    
    return costs


def compare_rto_rpo_scenarios() -> None:
    """Compare costs across different RTO/RPO scenarios"""
    
    scenarios = [
        ("Mission Critical", 0.25, 1),
        ("Business Critical", 1, 5),
        ("Important", 4, 15),
        ("Standard", 8, 60),
        ("Low Priority", 24, 1440)
    ]
    
    print("=" * 80)
    print("RTO/RPO COST COMPARISON")
    print("=" * 80)
    print(f"{'Tier':<20} {'RTO':<10} {'RPO':<10} {'Storage':<12} {'Compute':<12} {'Total/Month':<15}")
    print("-" * 80)
    
    for name, rto, rpo in scenarios:
        costs = calculate_backup_costs(rto, rpo)
        print(f"{name:<20} {rto}h{'':<8} {rpo}min{'':<6} "
              f"${costs['storage_gb_month']*0.023:<11.2f} "
              f"${costs['compute_hours_month']*0.10:<11.2f} "
              f"${costs['total_usd_month']:<14.2f}")
    
    print("=" * 80)


if __name__ == "__main__":
    compare_rto_rpo_scenarios()
3. Monitoring RTO/RPO Compliance
python# monitoring/rto_rpo_monitor.py

"""
Monitor and alert on RTO/RPO compliance
"""

import time
from datetime import datetime, timedelta
from typing import Dict, List
import psycopg2

class RTORPOMonitor:
    """
    Monitors backup and recovery metrics to ensure
    RTO/RPO targets are being met
    """
    
    def __init__(self, config: Dict):
        self.config = config
        self.metrics = {
            "last_backup_time": None,
            "last_backup_duration": None,
            "backup_size_gb": None,
            "test_restore_duration": None,
            "wal_archive_lag": None
        }
    
    def check_rpo_compliance(self, target_rpo_minutes: int) -> Dict:
        """
        Check if RPO target is being met
        Based on time since last backup
        """
        last_backup = self.get_last_backup_time()
        
        if not last_backup:
            return {
                "compliant": False,
                "reason": "No backup found",
                "severity": "CRITICAL"
            }
        
        age_minutes = (datetime.now() - last_backup).total_seconds() / 60
        
        compliant = age_minutes <= target_rpo_minutes
        
        return {
            "compliant": compliant,
            "last_backup_age_minutes": age_minutes,
            "target_rpo_minutes": target_rpo_minutes,
            "severity": "OK" if compliant else "WARNING"
        }
    
    def check_rto_compliance(self, target_rto_hours: float) -> Dict:
        """
        Check if RTO target is achievable
        Based on recent test restore times
        """
        test_duration = self.get_latest_test_restore_duration()
        
        if not test_duration:
            return {
                "compliant": False,
                "reason": "No test restore data available",
                "severity": "WARNING"
            }
        
        test_duration_hours = test_duration / 3600
        
        # Add 20% buffer for production restore
        estimated_rto = test_duration_hours * 1.2
        
        compliant = estimated_rto <= target_rto_hours
        
        return {
            "compliant": compliant,
            "test_restore_hours": test_duration_hours,
            "estimated_rto_hours": estimated_rto,
            "target_rto_hours": target_rto_hours,
            "buffer_percentage": 20,
            "severity": "OK" if compliant else "CRITICAL"
        }
    
    def get_last_backup_time(self) -> datetime:
        """Get timestamp of last successful backup"""
        import os
        import glob
        
        backup_dir = "/var/backups/postgres"
        backups = glob.glob(f"{backup_dir}/*.sql.gz")
        
        if not backups:
            return None
        
        latest = max(backups, key=os.path.getctime)
        return datetime.fromtimestamp(os.path.getctime(latest))
    
    def get_latest_test_restore_duration(self) -> float:
        """Get duration of latest test restore in seconds"""
        # Read from test log
        try:
            with open("/var/log/postgres/backup_test_report.txt") as f:
                for line in f:
                    if "Restore Duration:" in line:
                        # Parse "Restore Duration: 125s"
                        duration_str = line.split(":")[1].strip().rstrip("s")
                        return float(duration_str)
        except:
            return None
        
        return None
    
    def generate_compliance_report(
        self,
        target_rpo_minutes: int,
        target_rto_hours: float
    ) -> Dict:
        """Generate full compliance report"""
        
        rpo_status = self.check_rpo_compliance(target_rpo_minutes)
        rto_status = self.check_rto_compliance(target_rto_hours)
        
        # Overall compliance
        overall_compliant = (
            rpo_status["compliant"] and 
            rto_status["compliant"]
        )
        
        report = {
            "timestamp": datetime.now().isoformat(),
            "overall_compliant": overall_compliant,
            "rpo": rpo_status,
            "rto": rto_status,
            "recommendations": []
        }
        
        # Add recommendations
        if not rpo_status["compliant"]:
            report["recommendations"].append(
                "Increase backup frequency to meet RPO target"
            )
        
        if not rto_status["compliant"]:
            report["recommendations"].append(
                "Consider faster restore method or improve hardware"
            )
        
        return report


# Usage
if __name__ == "__main__":
    config = {}
    monitor = RTORPOMonitor(config)
    
    # For a Tier 2 system (1h RTO, 5min RPO)
    report = monitor.generate_compliance_report(
        target_rpo_minutes=5,
        target_rto_hours=1.0
    )
    
    print("RTO/RPO COMPLIANCE REPORT")
    print("=" * 60)
    print(f"Timestamp: {report['timestamp']}")
    print(f"Overall Compliant: {'✅ YES' if report['overall_compliant'] else '❌ NO'}")
    print()
    print("RPO Status:")
    print(f"  Target: {report['rpo']['target_rpo_minutes']} minutes")
    print(f"  Last Backup Age: {report['rpo'].get('last_backup_age_minutes', 'N/A')} minutes")
    print(f"  Compliant: {'✅ YES' if report['rpo']['compliant'] else '❌ NO'}")
    print()
    print("RTO Status:")
    print(f"  Target: {report['rto']['target_rto_hours']} hours")
    print(f"  Estimated: {report['rto'].get('estimated_rto_hours', 'N/A')} hours")
    print(f"  Compliant: {'✅ YES' if report['rto']['compliant'] else '❌ NO'}")
    
    if report['recommendations']:
        print()
        print("Recommendations:")
        for rec in report['recommendations']:
            print(f"  - {rec}")



BACKUP & DISASTER RECOVERY GUIDE - TEIL 3
Restoration Procedures, Monitoring & Best Practices

📋 TABLE OF CONTENTS (TEIL 3)

Restoration Procedures
Monitoring & Alerting
Best Practices Summary
Checklists & Quick Reference


9. 🔄 RESTORATION PROCEDURES
9.1 Full Database Restore
bash#!/bin/bash
# scripts/full_restore.sh

# ============================================
# FULL DATABASE RESTORE SCRIPT
# ============================================
#
# This script performs a complete database restore
# from a backup file.
#
# Usage:
#   ./full_restore.sh /path/to/backup.sql.gz
#   ./full_restore.sh --latest
#   ./full_restore.sh --date 2024-01-15
#
# WARNING: This will REPLACE the entire database!
# ============================================

set -euo pipefail

# ============================================
# CONFIGURATION
# ============================================

DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
DB_NAME="${DB_NAME:-myapp}"
DB_USER="${DB_USER:-postgres}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/postgres}"
LOG_FILE="/var/log/postgres/restore.log"

# ============================================
# LOGGING
# ============================================

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

log_error() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: $*" | tee -a "$LOG_FILE" >&2
}

# ============================================
# PARSE ARGUMENTS
# ============================================

BACKUP_FILE=""

case "${1:-}" in
    --latest)
        log "Finding latest backup..."
        BACKUP_FILE=$(ls -1t "$BACKUP_DIR"/*.sql.gz 2>/dev/null | head -n1)
        if [ -z "$BACKUP_FILE" ]; then
            log_error "No backup files found in $BACKUP_DIR"
            exit 1
        fi
        ;;
    --date)
        if [ -z "${2:-}" ]; then
            log_error "Date required. Usage: --date 2024-01-15"
            exit 1
        fi
        DATE=$2
        BACKUP_FILE=$(ls -1 "$BACKUP_DIR"/*${DATE}*.sql.gz 2>/dev/null | head -n1)
        if [ -z "$BACKUP_FILE" ]; then
            log_error "No backup found for date: $DATE"
            exit 1
        fi
        ;;
    *)
        if [ -z "${1:-}" ]; then
            log_error "Usage: $0 <backup_file> | --latest | --date YYYY-MM-DD"
            exit 1
        fi
        BACKUP_FILE=$1
        if [ ! -f "$BACKUP_FILE" ]; then
            log_error "Backup file not found: $BACKUP_FILE"
            exit 1
        fi
        ;;
esac

log "Using backup file: $BACKUP_FILE"

# ============================================
# SAFETY CHECKS
# ============================================

# Confirm action
read -p "⚠️  WARNING: This will REPLACE database '$DB_NAME'. Continue? (yes/no): " CONFIRM
if [ "$CONFIRM" != "yes" ]; then
    log "Restore cancelled by user"
    exit 0
fi

# Check if database is in use
ACTIVE_CONNECTIONS=$(psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d postgres -t -c \
    "SELECT COUNT(*) FROM pg_stat_activity WHERE datname = '$DB_NAME' AND pid <> pg_backend_pid();")

if [ "$ACTIVE_CONNECTIONS" -gt 0 ]; then
    log_error "Database has $ACTIVE_CONNECTIONS active connections!"
    log "Please close all connections before restoring."
    exit 1
fi

# ============================================
# CREATE BACKUP OF CURRENT STATE (OPTIONAL)
# ============================================

log "Creating safety backup of current database..."
SAFETY_BACKUP="$BACKUP_DIR/pre_restore_$(date +%Y%m%d_%H%M%S).sql.gz"

pg_dump \
    -h $DB_HOST \
    -p $DB_PORT \
    -U $DB_USER \
    -d $DB_NAME \
    --format=plain \
    --no-owner \
    --no-acl \
    | gzip > "$SAFETY_BACKUP"

if [ $? -eq 0 ]; then
    log "Safety backup created: $SAFETY_BACKUP"
else
    log_error "Failed to create safety backup!"
    exit 1
fi

# ============================================
# DROP AND RECREATE DATABASE
# ============================================

log "Dropping database: $DB_NAME"
psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d postgres -c \
    "DROP DATABASE IF EXISTS $DB_NAME;"

log "Creating fresh database: $DB_NAME"
psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d postgres -c \
    "CREATE DATABASE $DB_NAME OWNER $DB_USER;"

# ============================================
# RESTORE FROM BACKUP
# ============================================

log "Starting restore from: $BACKUP_FILE"
START_TIME=$(date +%s)

gunzip -c "$BACKUP_FILE" | psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME \
    2>&1 | tee -a "$LOG_FILE"

if [ ${PIPESTATUS[1]} -eq 0 ]; then
    END_TIME=$(date +%s)
    DURATION=$((END_TIME - START_TIME))
    log "✅ Restore completed successfully in ${DURATION}s"
    
    # Run ANALYZE
    log "Running ANALYZE..."
    psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -c "ANALYZE;"
    
    log "Restore finished!"
else
    log_error "Restore failed! Check log file: $LOG_FILE"
    log "You can restore from safety backup: $SAFETY_BACKUP"
    exit 1
fi

9.2 Point-in-Time Recovery (PITR) Restore
bash#!/bin/bash
# scripts/pitr_restore.sh

# ============================================
# POINT-IN-TIME RECOVERY SCRIPT
# ============================================
#
# Restore database to a specific point in time
# using base backup + WAL replay.
#
# Usage:
#   ./pitr_restore.sh "2024-01-15 14:30:00"
#   ./pitr_restore.sh --latest-backup
#
# ============================================

set -euo pipefail

# Configuration
BACKUP_DIR="/var/backups/postgres/base"
WAL_ARCHIVE="/var/backups/postgres/wal"
RESTORE_DIR="/var/lib/postgresql/restore"
LOG_FILE="/var/log/postgres/pitr_restore.log"
PGDATA="/var/lib/postgresql/14/main"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

# ============================================
# PARSE TARGET TIME
# ============================================

if [ -z "${1:-}" ]; then
    echo "Usage: $0 'YYYY-MM-DD HH:MM:SS' | --latest-backup"
    exit 1
fi

if [ "$1" == "--latest-backup" ]; then
    TARGET_TIME="latest"
else
    TARGET_TIME="$1"
fi

log "Starting PITR restore to: $TARGET_TIME"

# ============================================
# FIND BASE BACKUP
# ============================================

# Find latest base backup before target time
if [ "$TARGET_TIME" == "latest" ]; then
    BASE_BACKUP=$(ls -1t "$BACKUP_DIR"/*.tar.gz 2>/dev/null | head -n1)
else
    # Find backup taken before target time
    TARGET_EPOCH=$(date -d "$TARGET_TIME" +%s)
    
    for backup in $(ls -1t "$BACKUP_DIR"/*.tar.gz 2>/dev/null); do
        # Extract timestamp from filename
        BACKUP_TIME=$(echo $backup | grep -oP '\d{8}_\d{6}')
        BACKUP_EPOCH=$(date -d "${BACKUP_TIME:0:8} ${BACKUP_TIME:9:2}:${BACKUP_TIME:11:2}:${BACKUP_TIME:13:2}" +%s 2>/dev/null || echo 0)
        
        if [ $BACKUP_EPOCH -le $TARGET_EPOCH ]; then
            BASE_BACKUP=$backup
            break
        fi
    done
fi

if [ -z "$BASE_BACKUP" ] || [ ! -f "$BASE_BACKUP" ]; then
    log "ERROR: No suitable base backup found!"
    exit 1
fi

log "Using base backup: $BASE_BACKUP"

# ============================================
# PREPARE RESTORE DIRECTORY
# ============================================

log "Preparing restore directory..."

# Stop PostgreSQL
sudo systemctl stop postgresql

# Clean restore directory
rm -rf "$RESTORE_DIR"
mkdir -p "$RESTORE_DIR"

# Extract base backup
log "Extracting base backup..."
tar -xzf "$BASE_BACKUP" -C "$RESTORE_DIR"

# ============================================
# CREATE RECOVERY CONFIGURATION
# ============================================

log "Creating recovery configuration..."

cat > "$RESTORE_DIR/recovery.signal" << EOF
# Recovery signal file - indicates recovery mode
EOF

if [ "$TARGET_TIME" == "latest" ]; then
    RECOVERY_TARGET="'latest'"
else
    RECOVERY_TARGET="'$TARGET_TIME'"
fi

cat > "$RESTORE_DIR/postgresql.auto.conf" << EOF
# Auto-generated recovery configuration

# Restore from WAL archive
restore_command = 'cp $WAL_ARCHIVE/%f %p'

# Recovery target time
recovery_target_time = $RECOVERY_TARGET

# Action after recovery
recovery_target_action = 'promote'

# Recovery options
recovery_target_inclusive = true
EOF

# ============================================
# SET PERMISSIONS
# ============================================

log "Setting permissions..."
chown -R postgres:postgres "$RESTORE_DIR"
chmod 700 "$RESTORE_DIR"

# ============================================
# REPLACE DATA DIRECTORY
# ============================================

log "Replacing data directory..."

# Backup current data directory
CURRENT_DATA_BACKUP="${PGDATA}_backup_$(date +%Y%m%d_%H%M%S)"
if [ -d "$PGDATA" ]; then
    mv "$PGDATA" "$CURRENT_DATA_BACKUP"
    log "Current data backed up to: $CURRENT_DATA_BACKUP"
fi

# Move restored data to production location
mv "$RESTORE_DIR" "$PGDATA"

# ============================================
# START RECOVERY
# ============================================

log "Starting PostgreSQL for recovery..."
sudo systemctl start postgresql

# Wait for recovery to complete
log "Waiting for recovery to complete..."
sleep 5

# Monitor recovery progress
while true; do
    # Check if recovery is complete (recovery.signal removed)
    if [ ! -f "$PGDATA/recovery.signal" ]; then
        log "✅ Recovery completed!"
        break
    fi
    
    # Check recovery progress
    PROGRESS=$(psql -U postgres -t -c "SELECT pg_last_wal_replay_lsn();" 2>/dev/null || echo "recovering")
    log "Recovery in progress... LSN: $PROGRESS"
    sleep 10
done

# ============================================
# VALIDATION
# ============================================

log "Running validation checks..."

# Test database connection
if psql -U postgres -c "SELECT 1;" > /dev/null 2>&1; then
    log "✅ Database connection OK"
else
    log "❌ ERROR: Cannot connect to database!"
    exit 1
fi

# Count rows in critical tables
log "Checking data integrity..."
psql -U postgres -d myapp << EOF
SELECT 
    schemaname,
    tablename,
    n_live_tup as row_count
FROM pg_stat_user_tables
ORDER BY n_live_tup DESC
LIMIT 10;
EOF

log "========================================="
log "PITR RESTORE COMPLETED SUCCESSFULLY!"
log "========================================="
log "Restored to: $TARGET_TIME"
log "Base backup: $BASE_BACKUP"
log "Original data preserved at: $CURRENT_DATA_BACKUP"

9.3 Selective Table Restore
bash#!/bin/bash
# scripts/selective_restore.sh

# ============================================
# SELECTIVE TABLE RESTORE
# ============================================
#
# Restore specific tables from backup without
# affecting the rest of the database.
#
# Usage:
#   ./selective_restore.sh users orders
#   ./selective_restore.sh --backup backup.sql.gz users
#
# ============================================

set -euo pipefail

# Configuration
BACKUP_DIR="/var/backups/postgres"
TEMP_DB="temp_restore_$(date +%s)"
DB_NAME="myapp"
LOG_FILE="/var/log/postgres/selective_restore.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

# ============================================
# PARSE ARGUMENTS
# ============================================

BACKUP_FILE=""
TABLES=()

# Check for --backup flag
if [ "${1:-}" == "--backup" ]; then
    BACKUP_FILE=$2
    shift 2
else
    # Use latest backup
    BACKUP_FILE=$(ls -1t "$BACKUP_DIR"/*.sql.gz 2>/dev/null | head -n1)
fi

# Remaining args are table names
TABLES=("$@")

if [ ${#TABLES[@]} -eq 0 ]; then
    echo "Usage: $0 [--backup file.sql.gz] table1 [table2 ...]"
    exit 1
fi

log "Backup file: $BACKUP_FILE"
log "Tables to restore: ${TABLES[*]}"

# ============================================
# CREATE TEMPORARY DATABASE
# ============================================

log "Creating temporary database: $TEMP_DB"
createdb "$TEMP_DB"

# ============================================
# RESTORE TO TEMPORARY DATABASE
# ============================================

log "Restoring backup to temporary database..."
gunzip -c "$BACKUP_FILE" | psql -d "$TEMP_DB" > /dev/null 2>&1

if [ $? -ne 0 ]; then
    log "ERROR: Failed to restore to temporary database"
    dropdb "$TEMP_DB"
    exit 1
fi

# ============================================
# BACKUP CURRENT TABLES
# ============================================

log "Backing up current tables..."
for table in "${TABLES[@]}"; do
    BACKUP_TABLE="${table}_backup_$(date +%Y%m%d_%H%M%S)"
    
    psql -d "$DB_NAME" -c \
        "CREATE TABLE $BACKUP_TABLE AS SELECT * FROM $table;" \
        2>&1 | tee -a "$LOG_FILE"
    
    log "✅ Backed up $table to $BACKUP_TABLE"
done

# ============================================
# RESTORE TABLES
# ============================================

log "Restoring tables from backup..."

for table in "${TABLES[@]}"; do
    log "Restoring table: $table"
    
    # Truncate target table
    psql -d "$DB_NAME" -c "TRUNCATE TABLE $table CASCADE;" 2>&1 | tee -a "$LOG_FILE"
    
    # Copy data from temp DB
    pg_dump -d "$TEMP_DB" -t "$table" --data-only | psql -d "$DB_NAME" 2>&1 | tee -a "$LOG_FILE"
    
    if [ $? -eq 0 ]; then
        log "✅ Restored $table successfully"
        
        # Get row count
        ROW_COUNT=$(psql -d "$DB_NAME" -t -c "SELECT COUNT(*) FROM $table;")
        log "   Rows restored: $ROW_COUNT"
    else
        log "❌ ERROR: Failed to restore $table"
        log "   Rolling back from backup..."
        
        # Restore from backup table
        BACKUP_TABLE="${table}_backup_$(date +%Y%m%d_%H%M%S)"
        psql -d "$DB_NAME" -c "TRUNCATE TABLE $table;" 2>&1 | tee -a "$LOG_FILE"
        psql -d "$DB_NAME" -c "INSERT INTO $table SELECT * FROM $BACKUP_TABLE;" 2>&1 | tee -a "$LOG_FILE"
    fi
done

# ============================================
# CLEANUP
# ============================================

log "Cleaning up temporary database..."
dropdb "$TEMP_DB"

log "========================================="
log "SELECTIVE RESTORE COMPLETED!"
log "========================================="
log "Tables restored: ${TABLES[*]}"
log "Backup tables created (keep for safety):"
for table in "${TABLES[@]}"; do
    log "  - ${table}_backup_*"
done

9.4 File Storage Restore (Restic)
bash#!/bin/bash
# scripts/restore_files_restic.sh

# ============================================
# RESTORE FILES USING RESTIC
# ============================================
#
# Restore files from Restic backup
#
# Usage:
#   ./restore_files_restic.sh                    # Latest
#   ./restore_files_restic.sh --snapshot abc123  # Specific
#   ./restore_files_restic.sh --date 2024-01-15  # By date
#   ./restore_files_restic.sh --path /uploads/important.pdf
#
# ============================================

set -euo pipefail

# Configuration
RESTIC_REPOSITORY="${RESTIC_REPOSITORY:-s3:s3.amazonaws.com/my-backups/restic}"
RESTIC_PASSWORD_FILE="${RESTIC_PASSWORD_FILE:-/etc/restic/password}"
RESTORE_DIR="/var/restore/files"
LOG_FILE="/var/log/app/restic_restore.log"

export RESTIC_REPOSITORY
export RESTIC_PASSWORD_FILE

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

# ============================================
# PARSE ARGUMENTS
# ============================================

SNAPSHOT_ID="latest"
SPECIFIC_PATH=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --snapshot)
            SNAPSHOT_ID=$2
            shift 2
            ;;
        --date)
            # Find snapshot by date
            DATE=$2
            SNAPSHOT_ID=$(restic snapshots --json | jq -r ".[] | select(.time | startswith(\"$DATE\")) | .short_id" | head -n1)
            shift 2
            ;;
        --path)
            SPECIFIC_PATH=$2
            shift 2
            ;;
        *)
            log "Unknown option: $1"
            exit 1
            ;;
    esac
done

log "========================================="
log "RESTIC FILE RESTORE"
log "========================================="
log "Snapshot: $SNAPSHOT_ID"
log "Restore to: $RESTORE_DIR"

# ============================================
# LIST SNAPSHOTS
# ============================================

log "Available snapshots:"
restic snapshots | tee -a "$LOG_FILE"

# ============================================
# PREPARE RESTORE DIRECTORY
# ============================================

mkdir -p "$RESTORE_DIR"

# ============================================
# RESTORE FILES
# ============================================

log "Starting restore..."

if [ -n "$SPECIFIC_PATH" ]; then
    # Restore specific path
    log "Restoring specific path: $SPECIFIC_PATH"
    restic restore $SNAPSHOT_ID \
        --target "$RESTORE_DIR" \
        --path "$SPECIFIC_PATH" \
        2>&1 | tee -a "$LOG_FILE"
else
    # Restore everything
    log "Restoring entire snapshot..."
    restic restore $SNAPSHOT_ID \
        --target "$RESTORE_DIR" \
        2>&1 | tee -a "$LOG_FILE"
fi

if [ ${PIPESTATUS[0]} -eq 0 ]; then
    log "✅ Restore completed successfully!"
    
    # Show restored files
    log "Restored files:"
    du -sh "$RESTORE_DIR"/* | tee -a "$LOG_FILE"
else
    log "❌ ERROR: Restore failed!"
    exit 1
fi

log "========================================="
log "Files restored to: $RESTORE_DIR"
log "Review files before moving to production!"

10. 📊 MONITORING & ALERTING
10.1 Prometheus Metrics
python# monitoring/backup_metrics.py

"""
Prometheus metrics exporter for backup monitoring
"""

from prometheus_client import Gauge, Counter, Histogram, start_http_server
import time
import os
import glob
from datetime import datetime

# ============================================
# DEFINE METRICS
# ============================================

# Backup age
backup_age_seconds = Gauge(
    'backup_age_seconds',
    'Time since last successful backup',
    ['backup_type']
)

# Backup size
backup_size_bytes = Gauge(
    'backup_size_bytes',
    'Size of latest backup',
    ['backup_type']
)

# Backup duration
backup_duration_seconds = Histogram(
    'backup_duration_seconds',
    'Time taken to create backup',
    ['backup_type']
)

# Backup success/failure
backup_success_total = Counter(
    'backup_success_total',
    'Total number of successful backups',
    ['backup_type']
)

backup_failure_total = Counter(
    'backup_failure_total',
    'Total number of failed backups',
    ['backup_type']
)

# Restore test results
restore_test_duration_seconds = Gauge(
    'restore_test_duration_seconds',
    'Time taken for last restore test'
)

restore_test_success = Gauge(
    'restore_test_success',
    'Last restore test success (1=success, 0=failure)'
)

# WAL archiving
wal_archive_lag_seconds = Gauge(
    'wal_archive_lag_seconds',
    'Age of oldest unarchived WAL file'
)

# Storage usage
backup_storage_used_bytes = Gauge(
    'backup_storage_used_bytes',
    'Total backup storage used'
)

backup_storage_available_bytes = Gauge(
    'backup_storage_available_bytes',
    'Available backup storage'
)

# ============================================
# METRIC COLLECTORS
# ============================================

class BackupMetricsCollector:
    """Collect and expose backup metrics"""
    
    def __init__(self, backup_dir: str):
        self.backup_dir = backup_dir
    
    def collect_backup_age(self):
        """Calculate time since last backup"""
        try:
            # Find latest backup
            backups = glob.glob(f"{self.backup_dir}/*.sql.gz")
            if not backups:
                backup_age_seconds.labels(backup_type='full').set(float('inf'))
                return
            
            latest = max(backups, key=os.path.getctime)
            age = time.time() - os.path.getctime(latest)
            
            backup_age_seconds.labels(backup_type='full').set(age)
        except Exception as e:
            print(f"Error collecting backup age: {e}")
    
    def collect_backup_size(self):
        """Get size of latest backup"""
        try:
            backups = glob.glob(f"{self.backup_dir}/*.sql.gz")
            if not backups:
                return
            
            latest = max(backups, key=os.path.getctime)
            size = os.path.getsize(latest)
            
            backup_size_bytes.labels(backup_type='full').set(size)
        except Exception as e:
            print(f"Error collecting backup size: {e}")
    
    def collect_storage_usage(self):
        """Get backup storage usage"""
        try:
            import shutil
            
            total, used, free = shutil.disk_usage(self.backup_dir)
            
            backup_storage_used_bytes.set(used)
            backup_storage_available_bytes.set(free)
        except Exception as e:
            print(f"Error collecting storage usage: {e}")
    
    def collect_restore_test_metrics(self):
        """Parse restore test results"""
        try:
            report_file = "/var/log/postgres/backup_test_report.txt"
            
            if not os.path.exists(report_file):
                return
            
            with open(report_file) as f:
                content = f.read()
            
            # Parse duration
            if "Restore Duration:" in content:
                for line in content.split('\n'):
                    if "Restore Duration:" in line:
                        duration_str = line.split(":")[1].strip().rstrip("s")
                        restore_test_duration_seconds.set(float(duration_str))
            
            # Parse success
            if "OVERALL STATUS:" in content:
                success = "PASSED" in content
                restore_test_success.set(1 if success else 0)
                
        except Exception as e:
            print(f"Error collecting restore test metrics: {e}")
    
    def collect_all_metrics(self):
        """Collect all metrics"""
        self.collect_backup_age()
        self.collect_backup_size()
        self.collect_storage_usage()
        self.collect_restore_test_metrics()


# ============================================
# RUN METRICS SERVER
# ============================================

def main():
    """Start Prometheus metrics server"""
    
    # Start HTTP server for Prometheus to scrape
    start_http_server(8000)
    print("Prometheus metrics server started on :8000")
    
    collector = BackupMetricsCollector("/var/backups/postgres")
    
    # Collect metrics every 30 seconds
    while True:
        collector.collect_all_metrics()
        time.sleep(30)


if __name__ == "__main__":
    main()
10.2 Prometheus Alerting Rules
yaml# prometheus/backup_alerts.yml

groups:
  - name: backup_alerts
    interval: 1m
    rules:
      
      # ============================================
      # BACKUP AGE ALERTS
      # ============================================
      
      - alert: BackupTooOld
        expr: backup_age_seconds{backup_type="full"} > 86400
        for: 5m
        labels:
          severity: critical
          component: backup
        annotations:
          summary: "Backup is older than 24 hours"
          description: "Last backup was {{ humanizeDuration $value }} ago. RPO at risk!"
      
      - alert: BackupAgeWarning
        expr: backup_age_seconds{backup_type="full"} > 43200
        for: 5m
        labels:
          severity: warning
          component: backup
        annotations:
          summary: "Backup is older than 12 hours"
          description: "Last backup was {{ humanizeDuration $value }} ago."
      
      # ============================================
      # BACKUP FAILURE ALERTS
      # ============================================
      
      - alert: BackupFailed
        expr: increase(backup_failure_total[1h]) > 0
        for: 1m
        labels:
          severity: critical
          component: backup
        annotations:
          summary: "Backup has failed"
          description: "{{ $value }} backup failures in the last hour."
      
      # ============================================
      # RESTORE TEST ALERTS
      # ============================================
      
      - alert: RestoreTestFailed
        expr: restore_test_success == 0
        for: 5m
        labels:
          severity: critical
          component: backup
        annotations:
          summary: "Backup restore test failed"
          description: "Latest restore test failed. Backups may not be viable!"
      
      - alert: RestoreTestNotRun
        expr: time() - restore_test_duration_seconds > 604800  # 7 days
        for: 1h
        labels:
          severity: warning
          component: backup
        annotations:
          summary: "Restore test has not been run recently"
          description: "Last restore test was more than 7 days ago."
      
      - alert: RestoreTestTooSlow
        expr: restore_test_duration_seconds > 7200  # 2 hours
        for: 5m
        labels:
          severity: warning
          component: backup
        annotations:
          summary: "Restore test taking too long"
          description: "Last restore took {{ humanizeDuration $value }}. RTO may be at risk."
      
      # ============================================
      # STORAGE ALERTS
      # ============================================
      
      - alert: BackupStorageLow
        expr: backup_storage_available_bytes < 10737418240  # 10GB
        for: 10m
        labels:
          severity: warning
          component: backup
        annotations:
          summary: "Backup storage running low"
          description: "Only {{ humanize $value }} of backup storage remaining."
      
      - alert: BackupStorageCritical
        expr: backup_storage_available_bytes < 5368709120  # 5GB
        for: 5m
        labels:
          severity: critical
          component: backup
        annotations:
          summary: "Backup storage critically low!"
          description: "Only {{ humanize $value }} of backup storage remaining. Backups may fail!"
      
      # ============================================
      # WAL ARCHIVING ALERTS
      # ============================================
      
      - alert: WALArchivingLagging
        expr: wal_archive_lag_seconds > 1800  # 30 minutes
        for: 5m
        labels:
          severity: warning
          component: backup
        annotations:
          summary: "WAL archiving is lagging"
          description: "WAL files are {{ humanizeDuration $value }} behind. RPO at risk!"
      
      # ============================================
      # BACKUP SIZE ALERTS
      # ============================================
      
      - alert: BackupSizeAnomaly
        expr: |
          abs(
            backup_size_bytes{backup_type="full"} -
            avg_over_time(backup_size_bytes{backup_type="full"}[7d])
          ) / avg_over_time(backup_size_bytes{backup_type="full"}[7d]) > 0.5
        for: 1h
        labels:
          severity: warning
          component: backup
        annotations:
          summary: "Backup size anomaly detected"
          description: "Backup size changed by more than 50% compared to 7-day average."
10.3 Grafana Dashboard
json{
  "dashboard": {
    "title": "Backup & Recovery Monitoring",
    "panels": [
      {
        "title": "Backup Age",
        "targets": [
          {
            "expr": "backup_age_seconds{backup_type='full'} / 3600",
            "legendFormat": "Hours since last backup"
          }
        ],
        "type": "graph",
        "yaxes": [
          {
            "label": "Hours",
            "format": "short"
          }
        ],
        "alert": {
          "conditions": [
            {
              "evaluator": {
                "params": [24],
                "type": "gt"
              },
              "query": {
                "params": ["A", "5m", "now"]
              }
            }
          ],
          "executionErrorState": "alerting",
          "frequency": "1m",
          "name": "Backup Too Old"
        }
      },
      {
        "title": "Backup Size Trend",
        "targets": [
          {
            "expr": "backup_size_bytes{backup_type='full'} / 1024 / 1024 / 1024",
            "legendFormat": "Backup Size (GB)"
          }
        ],
        "type": "graph"
      },
      {
        "title": "Restore Test Duration",
        "targets": [
          {
            "expr": "restore_test_duration_seconds / 60",
            "legendFormat": "Restore Time (minutes)"
          }
        ],
        "type": "stat",
        "fieldConfig": {
          "defaults": {
            "thresholds": {
              "steps": [
                {"value": 0, "color": "green"},
                {"value": 60, "color": "yellow"},
                {"value": 120, "color": "red"}
              ]
            }
          }
        }
      },
      {
        "title": "Backup Success Rate",
        "targets": [
          {
            "expr": "rate(backup_success_total[24h]) / (rate(backup_success_total[24h]) + rate(backup_failure_total[24h]))",
            "legendFormat": "Success Rate"
          }
        ],
        "type": "gauge",
        "fieldConfig": {
          "defaults": {
            "unit": "percentunit",
            "thresholds": {
              "steps": [
                {"value": 0, "color": "red"},
                {"value": 0.95, "color": "yellow"},
                {"value": 0.99, "color": "green"}
              ]
            }
          }
        }
      },
      {
        "title": "Storage Usage",
        "targets": [
          {
            "expr": "backup_storage_used_bytes / 1024 / 1024 / 1024",
            "legendFormat": "Used (GB)"
          },
          {
            "expr": "backup_storage_available_bytes / 1024 / 1024 / 1024",
            "legendFormat": "Available (GB)"
          }
        ],
        "type": "graph"
      },
      {
        "title": "RTO/RPO Compliance",
        "type": "table",
        "targets": [
          {
            "expr": "backup_age_seconds{backup_type='full'} / 60",
            "format": "table",
            "legendFormat": "RPO (minutes)"
          },
          {
            "expr": "restore_test_duration_seconds / 3600",
            "format": "table",
            "legendFormat": "RTO (hours)"
          }
        ]
      }
    ],
    "refresh": "1m",
    "time": {
      "from": "now-24h",
      "to": "now"
    }
  }
}
10.4 Notification Channels
python# monitoring/notifications.py

"""
Send notifications for backup events
"""

import requests
import json
from typing import Dict
from datetime import datetime

class NotificationManager:
    """Manage notifications for backup events"""
    
    def __init__(self, config: Dict):
        self.config = config
    
    def send_slack_notification(self, message: str, severity: str = "info"):
        """Send Slack notification"""
        
        webhook_url = self.config.get('slack_webhook_url')
        if not webhook_url:
            return
        
        # Color based on severity
        colors = {
            "info": "#36a64f",
            "warning": "#ff9900",
            "error": "#ff0000",
            "critical": "#cc0000"
        }
        
        payload = {
            "attachments": [{
                "color": colors.get(severity, "#808080"),
                "title": f"Backup System - {severity.upper()}",
                "text": message,
                "footer": "Backup Monitoring",
                "ts": int(datetime.now().timestamp())
            }]
        }
        
        try:
            response = requests.post(
                webhook_url,
                data=json.dumps(payload),
                headers={'Content-Type': 'application/json'}
            )
            response.raise_for_status()
        except Exception as e:
            print(f"Failed to send Slack notification: {e}")
    
    def send_email_notification(self, subject: str, body: str):
        """Send email notification"""
        
        import smtplib
        from email.mime.text import MIMEText
        
        smtp_config = self.config.get('smtp', {})
        
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = smtp_config.get('from')
        msg['To'] = smtp_config.get('to')
        
        try:
            with smtplib.SMTP(smtp_config.get('server'), smtp_config.get('port')) as server:
                if smtp_config.get('use_tls'):
                    server.starttls()
                if smtp_config.get('username'):
                    server.login(
                        smtp_config.get('username'),
                        smtp_config.get('password')
                    )
                server.send_message(msg)
        except Exception as e:
            print(f"Failed to send email: {e}")
    
    def send_pagerduty_alert(self, description: str, severity: str = "error"):
        """Send PagerDuty alert"""
        
        api_key = self.config.get('pagerduty_api_key')
        if not api_key:
            return
        
        payload = {
            "routing_key": api_key,
            "event_action": "trigger",
            "payload": {
                "summary": description,
                "severity": severity,
                "source": "backup_system",
                "timestamp": datetime.now().isoformat()
            }
        }
        
        try:
            response = requests.post(
                "https://events.pagerduty.com/v2/enqueue",
                data=json.dumps(payload),
                headers={'Content-Type': 'application/json'}
            )
            response.raise_for_status()
        except Exception as e:
            print(f"Failed to send PagerDuty alert: {e}")
    
    def notify_backup_success(self, duration: float, size_mb: float):
        """Notify successful backup"""
        message = f"✅ Backup completed successfully\nDuration: {duration:.1f}s\nSize: {size_mb:.1f} MB"
        self.send_slack_notification(message, "info")
    
    def notify_backup_failure(self, error: str):
        """Notify backup failure"""
        message = f"❌ Backup FAILED\nError: {error}"
        self.send_slack_notification(message, "critical")
        self.send_pagerduty_alert(f"Backup failed: {error}", "critical")
    
    def notify_restore_test_failed(self):
        """Notify restore test failure"""
        message = "❌ Restore test FAILED - Backups may not be viable!"
        self.send_slack_notification(message, "critical")
        self.send_email_notification(
            "CRITICAL: Restore Test Failed",
            "The latest backup restore test has failed. Please investigate immediately."
        )
    
    def notify_storage_low(self, available_gb: float):
        """Notify low storage"""
        message = f"⚠️ Backup storage running low\nAvailable: {available_gb:.1f} GB"
        self.send_slack_notification(message, "warning")


# Usage example
if __name__ == "__main__":
    config = {
        'slack_webhook_url': 'https://hooks.slack.com/services/YOUR/WEBHOOK/URL',
        'smtp': {
            'server': 'smtp.gmail.com',
            'port': 587,
            'use_tls': True,
            'username': 'alerts@example.com',
            'password': 'your-password',
            'from': 'alerts@example.com',
            'to': 'admin@example.com'
        },
        'pagerduty_api_key': 'your-pagerduty-key'
    }
    
    notifier = NotificationManager(config)
    notifier.notify_backup_success(duration=125.5, size_mb=2048.7)
```

---

## 11. 📝 BEST PRACTICES SUMMARY

### 11.1 The 3-2-1 Rule
```
┌─────────────────────────────────────────────────────────┐
│                    3-2-1 BACKUP RULE                     │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  3️⃣  Keep THREE copies of your data                     │
│     ├─ 1 Primary (production)                          │
│     ├─ 1 Local backup                                  │
│     └─ 1 Remote backup                                 │
│                                                         │
│  2️⃣  Store backups on TWO different media types         │
│     ├─ Local disk/NAS                                  │
│     └─ Cloud storage (S3, etc.)                        │
│                                                         │
│  1️⃣  Keep ONE copy OFFSITE                              │
│     └─ Different location (cloud, datacenter)          │
│                                                         │
└─────────────────────────────────────────────────────────┘
11.2 Critical Success Factors
markdown# Backup & Recovery Success Checklist

## ✅ Planning
- [ ] RTO/RPO defined for each system
- [ ] Backup strategy documented
- [ ] Recovery procedures documented
- [ ] Team trained on procedures
- [ ] Budget allocated

## ✅ Implementation
- [ ] Automated backup scripts
- [ ] Multiple backup types (full, incremental, WAL)
- [ ] Encryption enabled
- [ ] Compression enabled
- [ ] Backup verification

## ✅ Testing
- [ ] Regular restore tests (at least monthly)
- [ ] DR drills scheduled (quarterly)
- [ ] Automated testing scripts
- [ ] Test results documented
- [ ] Team familiar with restore procedures

## ✅ Monitoring
- [ ] Prometheus metrics collecting
- [ ] Grafana dashboards configured
- [ ] Alerting rules defined
- [ ] Notifications working
- [ ] On-call rotation established

## ✅ Storage
- [ ] Sufficient storage capacity
- [ ] Retention policy defined
- [ ] Automated cleanup configured
- [ ] Offsite backups enabled
- [ ] Storage monitored

## ✅ Security
- [ ] Backups encrypted
- [ ] Access controls in place
- [ ] Audit logs enabled
- [ ] Compliance verified
- [ ] Keys securely stored

## ✅ Documentation
- [ ] Runbooks created
- [ ] Procedures documented
- [ ] Contact list maintained
- [ ] Escalation paths defined
- [ ] Lessons learned captured
11.3 Common Pitfalls to Avoid
python# Common backup mistakes and how to avoid them

COMMON_PITFALLS = {
    "untested_backups": {
        "problem": "Backups exist but restore has never been tested",
        "risk": "CRITICAL - May discover backup is broken during disaster",
        "solution": "Schedule monthly automated restore tests",
        "prevention": "Make testing part of backup procedure"
    },
    
    "single_backup_location": {
        "problem": "All backups in one location",
        "risk": "HIGH - Single point of failure",
        "solution": "Implement 3-2-1 rule (local + offsite)",
        "prevention": "Use multiple storage backends"
    },
    
    "no_encryption": {
        "problem": "Backups stored unencrypted",
        "risk": "HIGH - Data breach, compliance violation",
        "solution": "Enable encryption for all backups",
        "prevention": "Make encryption mandatory in scripts"
    },
    
    "forgotten_passwords": {
        "problem": "Lost backup encryption keys/passwords",
        "risk": "CRITICAL - Cannot restore even if backup exists",
        "solution": "Store keys in secure key management system",
        "prevention": "Document key storage procedures"
    },
    
    "insufficient_storage": {
        "problem": "Backups fail due to full disk",
        "risk": "MEDIUM - No recent backups available",
        "solution": "Implement automated cleanup and monitoring",
        "prevention": "Set up storage alerts"
    },
    
    "no_monitoring": {
        "problem": "Backup failures go unnoticed",
        "risk": "HIGH - No backups for extended period",
        "solution": "Set up monitoring and alerting",
        "prevention": "Make alerts mandatory"
    },
    
    "inadequate_retention": {
        "problem": "Only keeping very recent backups",
        "risk": "MEDIUM - Cannot restore to earlier point",
        "solution": "Implement proper retention policy (daily/weekly/monthly)",
        "prevention": "Define retention requirements upfront"
    },
    
    "manual_procedures": {
        "problem": "Backups require manual intervention",
        "risk": "MEDIUM - Backups missed when person unavailable",
        "solution": "Fully automate backup and testing",
        "prevention": "Design for automation from start"
    },
    
    "no_documentation": {
        "problem": "Procedures exist only in someone's head",
        "risk": "HIGH - Cannot recover if key person unavailable",
        "solution": "Document all procedures in runbooks",
        "prevention": "Make documentation part of process"
    },
    
    "slow_restores": {
        "problem": "Restore takes longer than RTO",
        "risk": "HIGH - Cannot meet business requirements",
        "solution": "Optimize restore process, consider standby systems",
        "prevention": "Test and measure restore times regularly"
    }
}

12. 📋 CHECKLISTS & QUICK REFERENCE
12.1 Daily Operations Checklist
bash#!/bin/bash
# scripts/daily_backup_checklist.sh

# ============================================
# DAILY BACKUP OPERATIONS CHECKLIST
# ============================================

echo "═══════════════════════════════════════════"
echo "DAILY BACKUP OPERATIONS CHECKLIST"
echo "Date: $(date '+%Y-%m-%d')"
echo "═══════════════════════════════════════════"
echo ""

check_item() {
    if [ $1 -eq 0 ]; then
        echo "✅ $2"
        return 0
    else
        echo "❌ $2"
        return 1
    fi
}

FAILED=0

# Check last backup
echo "1. Checking last backup..."
LAST_BACKUP=$(find /var/backups/postgres -name "*.sql.gz" -mtime -1 | wc -l)
check_item $([ $LAST_BACKUP -gt 0 ]; echo $?) "Backup created in last 24 hours"
[ $? -ne 0 ] && FAILED=$((FAILED+1))

# Check backup size
echo "2. Checking backup size..."
LATEST=$(ls -1t /var/backups/postgres/*.sql.gz 2>/dev/null | head -n1)
if [ -n "$LATEST" ]; then
    SIZE=$(stat -f%z "$LATEST" 2>/dev/null || stat -c%s "$LATEST")
    check_item $([ $SIZE -gt 1000000 ]; echo $?) "Backup size > 1MB ($SIZE bytes)"
    [ $? -ne 0 ] && FAILED=$((FAILED+1))
fi

# Check storage space
echo "3. Checking storage space..."
AVAIL=$(df /var/backups | tail -1 | awk '{print $4}')
check_item $([ $AVAIL -gt 10485760 ]; echo $?) "Storage available > 10GB"
[ $? -ne 0 ] && FAILED=$((FAILED+1))

# Check WAL archiving
echo "4. Checking WAL archiving..."
WAL_COUNT=$(find /var/backups/postgres/wal -name "*.gz" -mmin -60 | wc -l)
check_item $([ $WAL_COUNT -gt 0 ]; echo $?) "WAL files archived in last hour"
[ $? -ne 0 ] && FAILED=$((FAILED+1))

# Check monitoring
echo "5. Checking monitoring..."
curl -s http://localhost:8000/metrics | grep -q backup_age_seconds
check_item $? "Metrics endpoint responding"
[ $? -ne 0 ] && FAILED=$((FAILED+1))

# Check alerts
echo "6. Checking alerts..."
# (Add your alert check here)
check_item 0 "No active backup alerts"

echo ""
echo "═══════════════════════════════════════════"
if [ $FAILED -eq 0 ]; then
    echo "✅ All checks passed!"
    exit 0
else
    echo "❌ $FAILED check(s) failed!"
    exit 1
fi
12.2 Quick Reference Guide
markdown# BACKUP & RECOVERY QUICK REFERENCE

## Emergency Contacts
- On-Call DBA: +49-xxx-xxx-xxxx
- Incident Commander: +49-xxx-xxx-xxxx  
- PagerDuty: https://company.pagerduty.com
- Slack: #incident-response

## Critical Locations
- Backups: `/var/backups/postgres`
- WAL Archive: `/var/backups/postgres/wal`
- Scripts: `/opt/scripts`
- Logs: `/var/log/postgres`
- Docs: `/docs/runbooks`

## Quick Commands

### List Backups
```bash
ls -lht /var/backups/postgres/*.sql.gz | head -10
```

### Latest Backup Age
```bash
stat -c %y $(ls -1t /var/backups/postgres/*.sql.gz | head -n1)
```

### Disk Space
```bash
df -h /var/backups
```

### Check Database Size
```bash
psql -c "SELECT pg_size_pretty(pg_database_size('myapp'));"
```

### Emergency Restore (Latest)
```bash
sudo /opt/scripts/full_restore.sh --latest
```

### PITR to Specific Time
```bash
sudo /opt/scripts/pitr_restore.sh "2024-01-15 14:30:00"
```

### Test Latest Backup
```bash
sudo /opt/scripts/test_backup.sh
```

### View Metrics
```bash
curl http://localhost:8000/metrics | grep backup
```

### Check Active Connections
```bash
psql -c "SELECT COUNT(*) FROM pg_stat_activity WHERE datname = 'myapp';"
```

### Force Backup Now
```bash
sudo /opt/scripts/backup_full.sh
```

## RTO/RPO Targets

| System Tier | RTO | RPO | Strategy |
|-------------|-----|-----|----------|
| Critical | 15m | <1m | Hot standby |
| Important | 1h | 5m | WAL archiving |
| Standard | 4h | 15m | Daily backup |
| Low Priority | 24h | 24h | Daily backup |

## Retention Policy
- Daily backups: Keep 7 days
- Weekly backups: Keep 4 weeks
- Monthly backups: Keep 12 months
- Yearly backups: Keep 3 years

## When to Escalate
1. **Backup Age > 24h** → Page on-call DBA immediately
2. **Restore Test Fails** → Create incident, notify team
3. **Storage < 5GB** → Urgent cleanup needed
4. **WAL Archive Lag > 1h** → Investigate immediately

## Disaster Response Steps
1. **Assess** - What happened? What's affected?
2. **Notify** - Alert team via PagerDuty
3. **Stabilize** - Stop further damage
4. **Recover** - Execute recovery procedure
5. **Validate** - Test system thoroughly
6. **Document** - Write incident report

## Important Links
- [Full Runbook](http://wiki.company.com/runbooks/backup)
- [Grafana Dashboard](http://grafana.company.com/d/backup)
- [Prometheus](http://prometheus.company.com)
- [Status Page](http://status.company.com)
12.3 Disaster Scenario Quick Cards
markdown# DISASTER SCENARIO QUICK CARDS

## 🔥 DATABASE CORRUPTION

**Detection**
- Database won't start
- Corruption errors in logs
- Data inconsistency

**Immediate Actions**
1. Stop application
2. Check backup integrity: `ls -lh /var/backups/postgres/*.sql.gz`
3. Alert team via PagerDuty

**Recovery**
```bash
sudo /opt/scripts/full_restore.sh --latest
```

**RTO Target:** 2 hours  
**RPO Target:** 15 minutes

---

## 💾 HARDWARE FAILURE

**Detection**
- Server unresponsive
- Disk failure alerts
- SMART errors

**Immediate Actions**
1. Confirm hardware failure
2. Provision replacement
3. Prepare for full restore

**Recovery**
```bash
# On new hardware:
sudo apt install postgresql-14
sudo /opt/scripts/full_restore.sh --latest
```

**RTO Target:** 4 hours  
**RPO Target:** 30 minutes

---

## 🗑️ ACCIDENTAL DELETION

**Detection**
- User reports missing data
- Unexpected row count drop

**Immediate Actions**
1. Identify what was deleted
2. Check transaction logs
3. Determine recovery point

**Recovery**
```bash
sudo /opt/scripts/pitr_restore.sh "2024-01-15 14:30:00"
```

**RTO Target:** 30 minutes  
**RPO Target:** 5 minutes

---

## 🦠 RANSOMWARE ATTACK

**Detection**
- Files encrypted
- Ransom note found
- Unusual activity

**Immediate Actions**
1. **DISCONNECT FROM NETWORK**
2. **DO NOT PAY RANSOM**
3. Contact security team
4. Preserve evidence
5. Notify authorities

**Recovery**
```bash
# Use backup from BEFORE infection
sudo /opt/scripts/full_restore.sh --date 2024-01-10
```

**RTO Target:** 8 hours  
**RPO Target:** 24 hours (use old backup)

---

## 🌩️ DATA CENTER OUTAGE

**Detection**
- Complete site unavailable
- Network unreachable

**Immediate Actions**
1. Activate DR site
2. Verify backup availability
3. Update DNS

**Recovery**
```bash
# At DR site:
sudo /opt/scripts/full_restore.sh --latest
# Update connection strings
# Redirect traffic
```

**RTO Target:** 1 hour  
**RPO Target:** 5 minutes




