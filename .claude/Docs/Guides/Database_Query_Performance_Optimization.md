⚡ QUERY PERFORMANCE OPTIMIZATION GUIDE
SQLAlchemy + PostgreSQL Performance Best Practices

📋 TABLE OF CONTENTS

Introduction
Understanding Query Performance
The N+1 Query Problem
Eager Loading Strategies
Indexing Strategies
Query Profiling & Analysis
Pagination Best Practices
Connection Pooling
Caching Strategies
Bulk Operations
Raw SQL vs ORM
PostgreSQL-Specific Optimizations
Common Anti-Patterns
Monitoring & Debugging
Performance Checklist


🎯 INTRODUCTION
Why Query Performance Matters
Slow Query:  SELECT * FROM documents WHERE user_id = ?
→ 2000ms response time
→ Poor user experience
→ High server load
→ Wasted resources

Optimized:   SELECT id, title, status FROM documents 
             WHERE user_id = ? 
             AND status = 'active'
             ORDER BY created_at DESC 
             LIMIT 20
→ 15ms response time
→ Great user experience
→ Low server load
→ Efficient resource usage
Performance Hierarchy
1. Don't do the query at all          → Caching, memoization
2. Do less queries                     → Eager loading, joins
3. Query less data                     → SELECT specific columns
4. Make queries faster                 → Indexes, query optimization
5. Run queries in parallel             → Async, batch processing

📊 UNDERSTANDING QUERY PERFORMANCE
1. Query Execution Phases
Query Lifecycle:
┌─────────────────┐
│ 1. Parsing      │  Parse SQL syntax
├─────────────────┤
│ 2. Planning     │  Query planner finds optimal execution plan
├─────────────────┤
│ 3. Execution    │  Execute plan, fetch data
├─────────────────┤
│ 4. Transfer     │  Send results to application
└─────────────────┘
2. Measuring Query Performance
python# backend/utils/query_profiler.py

import time
from functools import wraps
from sqlalchemy import event
from sqlalchemy.engine import Engine

class QueryProfiler:
    """Profile database queries for performance analysis"""
    
    def __init__(self):
        self.queries = []
        self.enabled = False
    
    def enable(self):
        """Enable query profiling"""
        self.enabled = True
        self.queries = []
        
        @event.listens_for(Engine, "before_cursor_execute")
        def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
            conn.info.setdefault('query_start_time', []).append(time.time())
        
        @event.listens_for(Engine, "after_cursor_execute")
        def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
            total = time.time() - conn.info['query_start_time'].pop(-1)
            self.queries.append({
                'statement': statement,
                'parameters': parameters,
                'duration_ms': round(total * 1000, 2)
            })
    
    def disable(self):
        """Disable query profiling"""
        self.enabled = False
    
    def get_summary(self):
        """Get query performance summary"""
        if not self.queries:
            return "No queries recorded"
        
        total_time = sum(q['duration_ms'] for q in self.queries)
        slowest = max(self.queries, key=lambda q: q['duration_ms'])
        
        return {
            'total_queries': len(self.queries),
            'total_time_ms': round(total_time, 2),
            'avg_time_ms': round(total_time / len(self.queries), 2),
            'slowest_query': {
                'statement': slowest['statement'][:100],
                'duration_ms': slowest['duration_ms']
            }
        }
    
    def print_summary(self):
        """Print formatted summary"""
        summary = self.get_summary()
        
        print("\n" + "=" * 70)
        print("QUERY PERFORMANCE SUMMARY")
        print("=" * 70)
        print(f"Total Queries: {summary['total_queries']}")
        print(f"Total Time: {summary['total_time_ms']}ms")
        print(f"Average Time: {summary['avg_time_ms']}ms")
        print(f"\nSlowest Query ({summary['slowest_query']['duration_ms']}ms):")
        print(f"  {summary['slowest_query']['statement']}")
        print("=" * 70 + "\n")

# Usage
profiler = QueryProfiler()
profiler.enable()

# Run your queries
documents = db.query(Document).all()

# Check performance
profiler.print_summary()
profiler.disable()
3. EXPLAIN ANALYZE
python# Analyze query execution plan

from sqlalchemy import text

def analyze_query(db, query):
    """Get PostgreSQL EXPLAIN ANALYZE for a query"""
    
    # Get the compiled SQL
    compiled = query.statement.compile(compile_kwargs={"literal_binds": True})
    sql = str(compiled)
    
    # Run EXPLAIN ANALYZE
    result = db.execute(text(f"EXPLAIN ANALYZE {sql}"))
    
    print("\n" + "=" * 70)
    print("QUERY EXECUTION PLAN")
    print("=" * 70)
    for row in result:
        print(row[0])
    print("=" * 70 + "\n")

# Usage
query = db.query(Document).filter(Document.user_id == user_id)
analyze_query(db, query)
```

**Example Output:**
```
Seq Scan on documents  (cost=0.00..1234.56 rows=100 width=512) (actual time=0.123..45.678 rows=95 loops=1)
  Filter: (user_id = '550e8400-e29b-41d4-a716-446655440000')
  Rows Removed by Filter: 9905
Planning Time: 0.234 ms
Execution Time: 45.890 ms

⚠️ Problem: Sequential scan (no index)
✅ Solution: Add index on user_id

🔥 THE N+1 QUERY PROBLEM
1. What is the N+1 Problem?
python# ❌ BAD: N+1 Query Problem

# Query 1: Get all documents
documents = db.query(Document).limit(10).all()

# Query 2-11: Get user for each document (10 more queries!)
for doc in documents:
    print(f"{doc.title} by {doc.user.name}")  # Triggers lazy load!

# Total: 1 + 10 = 11 queries
sql-- What actually happens:
SELECT * FROM documents LIMIT 10;                    -- Query 1
SELECT * FROM users WHERE id = 'user_1';             -- Query 2
SELECT * FROM users WHERE id = 'user_2';             -- Query 3
SELECT * FROM users WHERE id = 'user_3';             -- Query 4
-- ... 7 more queries
2. Detecting N+1 Problems
python# backend/middleware/query_counter.py

from sqlalchemy import event
from sqlalchemy.engine import Engine
import warnings

class QueryCounter:
    """Detect and warn about N+1 query problems"""
    
    def __init__(self, threshold=10):
        self.threshold = threshold
        self.query_count = 0
    
    def __enter__(self):
        self.query_count = 0
        
        @event.listens_for(Engine, "before_cursor_execute")
        def receive_before_cursor_execute(conn, cursor, statement, params, context, executemany):
            self.query_count += 1
            
            if self.query_count > self.threshold:
                warnings.warn(
                    f"⚠️ Potential N+1 problem: {self.query_count} queries executed! "
                    f"Last query: {statement[:100]}",
                    stacklevel=4
                )
        
        return self
    
    def __exit__(self, *args):
        event.remove(Engine, "before_cursor_execute", receive_before_cursor_execute)
        print(f"Total queries executed: {self.query_count}")

# Usage
with QueryCounter(threshold=5):
    documents = db.query(Document).limit(10).all()
    for doc in documents:
        print(doc.user.name)  # Will trigger warning!
3. Solving N+1 with Joins
python# ✅ GOOD: Single query with JOIN

from sqlalchemy.orm import joinedload

# Single query with LEFT OUTER JOIN
documents = db.query(Document)\
    .options(joinedload(Document.user))\
    .limit(10)\
    .all()

# Now accessing user doesn't trigger additional queries
for doc in documents:
    print(f"{doc.title} by {doc.user.name}")  # No extra query!

# Total: 1 query
sql-- What actually happens:
SELECT documents.*, users.*
FROM documents
LEFT OUTER JOIN users ON documents.user_id = users.id
LIMIT 10;

🚀 EAGER LOADING STRATEGIES
1. joinedload (Single Query, JOIN)
Use when: Loading related data that's frequently accessed together
pythonfrom sqlalchemy.orm import joinedload

# ✅ One-to-One / Many-to-One
documents = db.query(Document)\
    .options(joinedload(Document.user))\
    .all()

# ✅ Nested relationships
documents = db.query(Document)\
    .options(
        joinedload(Document.user).joinedload(User.organization)
    )\
    .all()

# ✅ Multiple relationships
documents = db.query(Document)\
    .options(
        joinedload(Document.user),
        joinedload(Document.category),
        joinedload(Document.supplier)
    )\
    .all()
Pros:

Single query
Efficient for one-to-one/many-to-one

Cons:

Can create huge result sets with one-to-many
Cartesian product with multiple collections

2. selectinload (Multiple Queries, IN)
Use when: Loading collections (one-to-many)
pythonfrom sqlalchemy.orm import selectinload

# ✅ One-to-Many relationships
users = db.query(User)\
    .options(selectinload(User.documents))\
    .all()

# Total: 2 queries
# Query 1: SELECT * FROM users
# Query 2: SELECT * FROM documents WHERE user_id IN (...)
python# ✅ BEST for collections
documents = db.query(Document)\
    .options(
        joinedload(Document.user),           # Many-to-one: use joinedload
        selectinload(Document.pages),        # One-to-many: use selectinload
        selectinload(Document.versions)      # One-to-many: use selectinload
    )\
    .all()

# Total: 3 queries (much better than N+1)
Pros:

Efficient for one-to-many
Predictable number of queries
No cartesian product

Cons:

Multiple queries (but controlled)

3. subqueryload (Subquery Strategy)
Use when: selectinload isn't available (older SQLAlchemy)
pythonfrom sqlalchemy.orm import subqueryload

documents = db.query(Document)\
    .options(subqueryload(Document.pages))\
    .all()

# Uses subquery instead of IN clause
Usually prefer selectinload over subqueryload in modern SQLAlchemy.
4. contains_eager (Manual Join)
Use when: Already joining for filtering
pythonfrom sqlalchemy.orm import contains_eager

# When you're already joining
documents = db.query(Document)\
    .join(Document.user)\
    .filter(User.is_active == True)\
    .options(contains_eager(Document.user))\
    .all()

# Tells SQLAlchemy: "I already joined, use that data"
5. Comparison Table
StrategyQueriesBest ForAvoid Forjoinedload1Many-to-one, one-to-oneMultiple one-to-manyselectinload2+One-to-many collectionsN/A (generally best)subqueryload2+Older SQLAlchemyModern codecontains_eager1Already joinedSimple loadsNone (lazy)N+1❌ NeverAlways avoid
6. Real-World Example
python# backend/api/documents.py

from sqlalchemy.orm import joinedload, selectinload

def get_documents_optimized(db: Session, user_id: UUID):
    """
    Optimized document loading with all relationships.
    
    ❌ Naive approach: 100+ queries
    ✅ Optimized: 4 queries
    """
    
    documents = db.query(Document)\
        .filter(Document.user_id == user_id)\
        .options(
            # Many-to-one: use joinedload (1 query total)
            joinedload(Document.user),
            joinedload(Document.category),
            joinedload(Document.detected_supplier),
            
            # One-to-many: use selectinload (1 query per collection)
            selectinload(Document.pages),
            selectinload(Document.versions),
            selectinload(Document.processing_jobs)
                .joinedload(ProcessingJob.backend_config),
            
            # Nested relationships
            selectinload(Document.workflow_executions)
                .joinedload(WorkflowExecution.workflow),
        )\
        .order_by(Document.created_at.desc())\
        .limit(50)\
        .all()
    
    # Total: ~4 queries instead of 200+
    return documents

📇 INDEXING STRATEGIES
1. When to Add Indexes
python# ✅ ADD indexes for:
# - Foreign keys
# - WHERE clause columns
# - ORDER BY columns
# - JOIN conditions
# - UNIQUE constraints

# ❌ DON'T index:
# - Small tables (<1000 rows)
# - Columns rarely queried
# - High-cardinality updates (slows writes)
2. Single Column Indexes
python# models/documents.py

class Document(BaseModel):
    __tablename__ = 'documents'
    
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), index=True)  # ✅
    status = Column(String, index=True)  # ✅ Frequently filtered
    created_at = Column(DateTime(timezone=True), index=True)  # ✅ ORDER BY
sql-- Generated SQL:
CREATE INDEX ix_documents_user_id ON documents (user_id);
CREATE INDEX ix_documents_status ON documents (status);
CREATE INDEX ix_documents_created_at ON documents (created_at);
3. Composite Indexes
pythonfrom sqlalchemy import Index

class Document(BaseModel):
    __tablename__ = 'documents'
    
    # ... columns ...
    
    __table_args__ = (
        # Composite index for common query pattern
        Index('ix_documents_user_status', 'user_id', 'status'),
        
        # Composite index for pagination
        Index('ix_documents_user_created', 'user_id', 'created_at'),
    )
Rule: Column order matters!
python# Index: (user_id, status)

# ✅ Uses index
WHERE user_id = ? AND status = ?
WHERE user_id = ?

# ❌ Doesn't use index
WHERE status = ?
4. Partial Indexes
python# PostgreSQL-specific: Index only subset of data

class Document(BaseModel):
    __tablename__ = 'documents'
    
    __table_args__ = (
        # Only index active documents
        Index(
            'ix_documents_active',
            'user_id', 'created_at',
            postgresql_where=text("status = 'active'")
        ),
        
        # Only index unprocessed documents
        Index(
            'ix_documents_pending',
            'created_at',
            postgresql_where=text("status = 'pending'")
        ),
    )
Benefits:

Smaller index size
Faster queries on filtered data
Less disk I/O

5. GIN Indexes (PostgreSQL)
python# For JSONB and array columns

class Document(BaseModel):
    __tablename__ = 'documents'
    
    metadata = Column(JSONB)
    tags = Column(ARRAY(String))
    
    __table_args__ = (
        # GIN index for JSONB queries
        Index(
            'ix_documents_metadata',
            'metadata',
            postgresql_using='gin'
        ),
        
        # GIN index for array queries
        Index(
            'ix_documents_tags',
            'tags',
            postgresql_using='gin'
        ),
    )

# Fast JSONB queries
documents = db.query(Document)\
    .filter(Document.metadata['key'].astext == 'value')\
    .all()

# Fast array queries
documents = db.query(Document)\
    .filter(Document.tags.contains(['invoice']))\
    .all()
6. Full-Text Search Indexes
pythonfrom sqlalchemy import Index, func

class Document(BaseModel):
    __tablename__ = 'documents'
    
    # Add tsvector column for full-text search
    search_vector = Column(
        TSVECTOR,
        Computed(
            "to_tsvector('english', coalesce(title, '') || ' ' || coalesce(description, ''))",
            persisted=True
        )
    )
    
    __table_args__ = (
        # GIN index for full-text search
        Index(
            'ix_documents_search',
            'search_vector',
            postgresql_using='gin'
        ),
    )

# Fast full-text search
from sqlalchemy import func

documents = db.query(Document)\
    .filter(
        Document.search_vector.match('invoice payment')
    )\
    .all()
7. Covering Indexes
python# Include frequently accessed columns in index

class Document(BaseModel):
    __tablename__ = 'documents'
    
    __table_args__ = (
        # Covering index: includes status in index
        Index(
            'ix_documents_user_covering',
            'user_id', 'created_at',
            postgresql_include=['status', 'title']  # Extra columns
        ),
    )

# This query can be satisfied entirely from index (index-only scan)
documents = db.query(Document.id, Document.status, Document.title)\
    .filter(Document.user_id == user_id)\
    .order_by(Document.created_at.desc())\
    .all()
8. Index Monitoring
python# Check index usage

def check_index_usage(db):
    """Show index usage statistics"""
    
    query = text("""
        SELECT 
            schemaname,
            tablename,
            indexname,
            idx_scan as scans,
            idx_tup_read as tuples_read,
            idx_tup_fetch as tuples_fetched,
            pg_size_pretty(pg_relation_size(indexrelid)) as size
        FROM pg_stat_user_indexes
        WHERE schemaname = 'public'
        ORDER BY idx_scan ASC
    """)
    
    result = db.execute(query)
    
    print("\n" + "=" * 70)
    print("INDEX USAGE STATISTICS")
    print("=" * 70)
    print(f"{'Index':<40} {'Scans':<10} {'Size':<10}")
    print("-" * 70)
    
    for row in result:
        print(f"{row.indexname:<40} {row.scans:<10} {row.size:<10}")
        if row.scans == 0:
            print(f"  ⚠️ Unused index - consider dropping")
    
    print("=" * 70 + "\n")

📈 QUERY PROFILING & ANALYSIS
1. Enable Query Logging
python# database.py

import logging

# Enable SQLAlchemy query logging
logging.basicConfig()
logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)

# Now all queries are logged:
# INFO:sqlalchemy.engine:SELECT documents.id, documents.title FROM documents WHERE documents.user_id = ?
2. Query Execution Time Decorator
python# utils/performance.py

import time
from functools import wraps

def measure_query_time(func):
    """Decorator to measure query execution time"""
    
    @wraps(func)
    def wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        duration = (time.time() - start) * 1000
        
        print(f"⏱️ {func.__name__} took {duration:.2f}ms")
        
        if duration > 100:
            print(f"  ⚠️ Slow query! Consider optimization")
        
        return result
    
    return wrapper

# Usage
@measure_query_time
def get_user_documents(db, user_id):
    return db.query(Document)\
        .filter(Document.user_id == user_id)\
        .all()
3. Query Plan Visualization
pythondef explain_query(db, query, analyze=True):
    """
    Get and format EXPLAIN output for a query.
    
    Args:
        db: Database session
        query: SQLAlchemy query object
        analyze: If True, actually execute query (EXPLAIN ANALYZE)
    """
    from sqlalchemy import text
    
    # Get compiled SQL with bound parameters
    compiled = query.statement.compile(
        compile_kwargs={"literal_binds": True}
    )
    sql = str(compiled)
    
    # Run EXPLAIN
    explain_sql = f"EXPLAIN {'ANALYZE ' if analyze else ''}{sql}"
    result = db.execute(text(explain_sql))
    
    print("\n" + "=" * 70)
    print(f"EXPLAIN {'ANALYZE ' if analyze else ''}OUTPUT")
    print("=" * 70)
    
    for row in result:
        line = row[0]
        
        # Highlight important parts
        if 'Seq Scan' in line:
            print(f"🔴 {line}")  # Sequential scan - bad
        elif 'Index Scan' in line or 'Index Only Scan' in line:
            print(f"🟢 {line}")  # Index scan - good
        elif 'cost=' in line:
            print(f"💰 {line}")  # Cost info
        else:
            print(f"   {line}")
    
    print("=" * 70 + "\n")

# Usage
query = db.query(Document).filter(Document.user_id == user_id)
explain_query(db, query, analyze=True)
4. Slow Query Logger
python# middleware/slow_query_logger.py

from sqlalchemy import event
from sqlalchemy.engine import Engine
import time
import logging

logger = logging.getLogger(__name__)

class SlowQueryLogger:
    """Log queries that exceed threshold"""
    
    def __init__(self, threshold_ms=100):
        self.threshold_ms = threshold_ms
    
    def setup(self):
        @event.listens_for(Engine, "before_cursor_execute")
        def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
            conn.info.setdefault('query_start_time', []).append(time.time())
        
        @event.listens_for(Engine, "after_cursor_execute")
        def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
            total = time.time() - conn.info['query_start_time'].pop(-1)
            duration_ms = total * 1000
            
            if duration_ms > self.threshold_ms:
                logger.warning(
                    f"Slow query detected ({duration_ms:.2f}ms):\n"
                    f"SQL: {statement}\n"
                    f"Params: {parameters}"
                )

# Setup in app initialization
slow_logger = SlowQueryLogger(threshold_ms=50)
slow_logger.setup()

📄 PAGINATION BEST PRACTICES
1. Offset Pagination (Simple but Slow)
python# ❌ SLOW for large offsets

def get_documents_offset(db, page=1, per_page=20):
    """Offset pagination - slow for large pages"""
    
    offset = (page - 1) * per_page
    
    documents = db.query(Document)\
        .order_by(Document.created_at.desc())\
        .offset(offset)\
        .limit(per_page)\
        .all()
    
    # Page 1: OFFSET 0     ✅ Fast
    # Page 100: OFFSET 1980  ⚠️ Slow (scans 1980 rows)
    # Page 1000: OFFSET 19980  🔴 Very slow (scans 19980 rows)
    
    return documents
Problems:

Slow for large offsets
Inconsistent results if data changes
Database must scan all skipped rows

2. Cursor Pagination (Fast and Consistent)
python# ✅ FAST for any page

def get_documents_cursor(db, cursor=None, per_page=20):
    """
    Cursor-based pagination using created_at.
    
    Args:
        cursor: Last item's created_at timestamp
        per_page: Items per page
    """
    
    query = db.query(Document)\
        .order_by(Document.created_at.desc())
    
    # Filter by cursor
    if cursor:
        query = query.filter(Document.created_at < cursor)
    
    documents = query.limit(per_page).all()
    
    # Next cursor
    next_cursor = documents[-1].created_at if documents else None
    
    return {
        'documents': documents,
        'next_cursor': next_cursor.isoformat() if next_cursor else None,
        'has_more': len(documents) == per_page
    }

# Usage
# Page 1
result = get_documents_cursor(db, cursor=None, per_page=20)

# Page 2
result = get_documents_cursor(db, cursor=result['next_cursor'], per_page=20)

# Always fast, even for page 1000!
3. Keyset Pagination (Most Efficient)
python# ✅ BEST for ordered lists with unique keys

def get_documents_keyset(db, last_id=None, last_created_at=None, per_page=20):
    """
    Keyset pagination using (created_at, id) composite cursor.
    
    More reliable than single-column cursor.
    """
    
    query = db.query(Document)\
        .order_by(Document.created_at.desc(), Document.id.desc())
    
    if last_created_at and last_id:
        # Use composite condition
        query = query.filter(
            or_(
                Document.created_at < last_created_at,
                and_(
                    Document.created_at == last_created_at,
                    Document.id < last_id
                )
            )
        )
    
    documents = query.limit(per_page).all()
    
    return {
        'documents': documents,
        'next_cursor': {
            'last_id': str(documents[-1].id),
            'last_created_at': documents[-1].created_at.isoformat()
        } if documents else None
    }
4. Count Optimization
python# ❌ SLOW: Counting large tables

def get_paginated_slow(db, page=1, per_page=20):
    query = db.query(Document)
    
    # This is SLOW on large tables
    total = query.count()  # Full table scan!
    
    documents = query.offset((page - 1) * per_page).limit(per_page).all()
    
    return {
        'documents': documents,
        'total': total,
        'pages': (total + per_page - 1) // per_page
    }

# ✅ FAST: Estimate or skip count

def get_paginated_fast(db, page=1, per_page=20):
    query = db.query(Document)
    
    documents = query.offset((page - 1) * per_page).limit(per_page + 1).all()
    
    has_more = len(documents) > per_page
    documents = documents[:per_page]
    
    return {
        'documents': documents,
        'has_more': has_more,
        # No total count - much faster!
    }
5. Pagination Comparison
MethodSpeedConsistencyUse CaseOffset🔴 Slow for large offsets⚠️ InconsistentSmall datasets, page numbers requiredCursor🟢 Always fast✅ ConsistentInfinite scroll, feedsKeyset🟢 Always fast✅ Very consistentOrdered lists, APIs

🔌 CONNECTION POOLING
1. Configure Pool Size
python# database.py

from sqlalchemy import create_engine
from sqlalchemy.pool import QueuePool

DATABASE_URL = "postgresql://user:pass@localhost/db"

engine = create_engine(
    DATABASE_URL,
    
    # Pool configuration
    poolclass=QueuePool,
    pool_size=20,              # Normal connections
    max_overflow=10,           # Extra connections under load
    pool_timeout=30,           # Wait 30s for connection
    pool_recycle=3600,         # Recycle connections every hour
    pool_pre_ping=True,        # Test connections before use
    
    # Connection arguments
    connect_args={
        "application_name": "ocr-backend",
        "options": "-c statement_timeout=30000"  # 30s query timeout
    },
    
    # Echo SQL (disable in production)
    echo=False
)
```

### 2. Pool Size Calculation
```
Recommended pool_size = (2 × CPU cores) + effective_spindle_count

Examples:
- 4 CPU cores, SSD → pool_size = 10
- 8 CPU cores, SSD → pool_size = 20
- 16 CPU cores, RAID → pool_size = 40

Conservative: 20-50 connections
Aggressive: 100+ connections (if DB can handle it)
3. Monitor Pool Usage
python# utils/pool_monitor.py

def check_pool_status(engine):
    """Check connection pool status"""
    
    pool = engine.pool
    
    print("\n" + "=" * 70)
    print("CONNECTION POOL STATUS")
    print("=" * 70)
    print(f"Pool size: {pool.size()}")
    print(f"Checked out: {pool.checkedout()}")
    print(f"Overflow: {pool.overflow()}")
    print(f"Checked in: {pool.checkedin()}")
    print("=" * 70 + "\n")
    
    # Warnings
    if pool.checkedout() / pool.size() > 0.8:
        print("⚠️ Pool is >80% utilized - consider increasing pool_size")
    
    if pool.overflow() > 0:
        print(f"⚠️ Using overflow connections ({pool.overflow()}) - high load")

# Usage
from database import engine
check_pool_status(engine)
4. Context Manager Pattern
python# ✅ ALWAYS use context managers or try/finally

from database import SessionLocal

# Option 1: Context manager (preferred)
def get_documents():
    with SessionLocal() as db:
        documents = db.query(Document).all()
        return documents
    # Session automatically closed

# Option 2: Try/finally
def get_documents_manual():
    db = SessionLocal()
    try:
        documents = db.query(Document).all()
        return documents
    finally:
        db.close()  # Always close!

# ❌ NEVER do this (connection leak!)
def get_documents_bad():
    db = SessionLocal()
    documents = db.query(Document).all()
    # Session never closed - connection leak!
    return documents

💾 CACHING STRATEGIES
1. Application-Level Caching
python# utils/cache.py

from functools import lru_cache
from datetime import datetime, timedelta
import hashlib
import json

class QueryCache:
    """Simple query result cache"""
    
    def __init__(self, ttl_seconds=300):
        self.cache = {}
        self.ttl = ttl_seconds
    
    def _make_key(self, *args, **kwargs):
        """Generate cache key from arguments"""
        key_data = json.dumps({'args': args, 'kwargs': kwargs}, sort_keys=True)
        return hashlib.md5(key_data.encode()).hexdigest()
    
    def get(self, key):
        """Get from cache if not expired"""
        if key in self.cache:
            value, expires_at = self.cache[key]
            if datetime.now() < expires_at:
                return value
            else:
                del self.cache[key]
        return None
    
    def set(self, key, value):
        """Store in cache with TTL"""
        expires_at = datetime.now() + timedelta(seconds=self.ttl)
        self.cache[key] = (value, expires_at)
    
    def clear(self):
        """Clear all cache"""
        self.cache = {}

# Global cache instance
query_cache = QueryCache(ttl_seconds=300)  # 5 minutes

# Usage
def get_user_stats(db, user_id):
    cache_key = f"user_stats:{user_id}"
    
    # Check cache
    cached = query_cache.get(cache_key)
    if cached:
        return cached
    
    # Query database
    stats = db.query(func.count(Document.id))\
        .filter(Document.user_id == user_id)\
        .scalar()
    
    # Store in cache
    query_cache.set(cache_key, stats)
    
    return stats
2. Redis Caching
python# utils/redis_cache.py

import redis
import json
from typing import Any, Optional
import pickle

class RedisCache:
    """Redis-backed cache for query results"""
    
    def __init__(self, host='localhost', port=6379, db=0):
        self.redis = redis.Redis(host=host, port=port, db=db)
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from Redis"""
        value = self.redis.get(key)
        if value:
            return pickle.loads(value)
        return None
    
    def set(self, key: str, value: Any, ttl: int = 300):
        """Set value in Redis with TTL"""
        self.redis.setex(
            key,
            ttl,
            pickle.dumps(value)
        )
    
    def delete(self, key: str):
        """Delete from cache"""
        self.redis.delete(key)
    
    def clear_pattern(self, pattern: str):
        """Clear all keys matching pattern"""
        for key in self.redis.scan_iter(pattern):
            self.redis.delete(key)

# Usage
cache = RedisCache()

def get_popular_documents(db):
    cache_key = "popular_documents"
    
    # Try cache
    cached = cache.get(cache_key)
    if cached:
        return cached
    
    # Query database
    documents = db.query(Document)\
        .order_by(Document.view_count.desc())\
        .limit(10)\
        .all()
    
    # Cache for 1 hour
    cache.set(cache_key, documents, ttl=3600)
    
    return documents

# Invalidate cache when document updated
def update_document(db, document_id, **kwargs):
    document = db.query(Document).get(document_id)
    for key, value in kwargs.items():
        setattr(document, key, value)
    db.commit()
    
    # Clear related caches
    cache.delete("popular_documents")
    cache.delete(f"document:{document_id}")
3. Decorator-Based Caching
python# utils/cache_decorator.py

from functools import wraps
import hashlib
import json

def cached(ttl=300, key_prefix=""):
    """
    Decorator for caching function results.
    
    Args:
        ttl: Time to live in seconds
        key_prefix: Prefix for cache key
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Generate cache key
            key_data = {
                'func': func.__name__,
                'args': str(args),
                'kwargs': str(kwargs)
            }
            cache_key = f"{key_prefix}:{hashlib.md5(json.dumps(key_data).encode()).hexdigest()}"
            
            # Try cache
            cached_result = query_cache.get(cache_key)
            if cached_result:
                return cached_result
            
            # Execute function
            result = func(*args, **kwargs)
            
            # Cache result
            query_cache.set(cache_key, result)
            
            return result
        
        return wrapper
    return decorator

# Usage
@cached(ttl=600, key_prefix="user_docs")
def get_user_document_count(db, user_id):
    return db.query(func.count(Document.id))\
        .filter(Document.user_id == user_id)\
        .scalar()
4. Query Result Caching (Dogpile)
python# Using dogpile.cache for sophisticated caching

from dogpile.cache import make_region

# Configure cache region
cache_region = make_region().configure(
    'dogpile.cache.redis',
    expiration_time=3600,
    arguments={
        'host': 'localhost',
        'port': 6379,
        'db': 0,
        'redis_expiration_time': 3600,
        'distributed_lock': True
    }
)

# Use with queries
@cache_region.cache_on_arguments()
def get_active_users(db):
    return db.query(User).filter(User.is_active == True).all()

# Invalidate cache
cache_region.delete('get_active_users')

📦 BULK OPERATIONS
1. Bulk Insert
python# ❌ SLOW: Insert one by one

documents = []
for i in range(1000):
    doc = Document(title=f"Document {i}", user_id=user_id)
    db.add(doc)
    db.flush()  # 1000 round trips!

# ✅ FAST: Bulk insert

documents = [
    Document(title=f"Document {i}", user_id=user_id)
    for i in range(1000)
]
db.bulk_save_objects(documents)
db.commit()  # Single transaction

# ✅ FASTER: Bulk insert with COPY (PostgreSQL)

from io import StringIO
import csv

# Prepare CSV data
csv_data = StringIO()
writer = csv.writer(csv_data)
for i in range(1000):
    writer.writerow([str(uuid.uuid4()), f"Document {i}", user_id])

csv_data.seek(0)

# Use COPY
raw_connection = db.connection().connection
cursor = raw_connection.cursor()
cursor.copy_expert(
    "COPY documents (id, title, user_id) FROM STDIN WITH CSV",
    csv_data
)
db.commit()

# 10-100x faster for large datasets!
2. Bulk Update
python# ❌ SLOW: Update one by one

documents = db.query(Document).filter(Document.user_id == user_id).all()
for doc in documents:
    doc.status = 'archived'
    db.flush()

# ✅ FAST: Bulk update

db.query(Document)\
    .filter(Document.user_id == user_id)\
    .update({'status': 'archived'})
db.commit()

# ✅ CONDITIONAL bulk update

db.query(Document)\
    .filter(
        Document.user_id == user_id,
        Document.created_at < datetime.now() - timedelta(days=90)
    )\
    .update({
        'status': 'archived',
        'archived_at': datetime.now()
    })
db.commit()
3. Bulk Delete
python# ❌ SLOW: Delete one by one

documents = db.query(Document).filter(Document.status == 'temporary').all()
for doc in documents:
    db.delete(doc)

# ✅ FAST: Bulk delete

db.query(Document)\
    .filter(Document.status == 'temporary')\
    .delete()
db.commit()

# ⚠️ Note: Bulk delete bypasses ORM events (before_delete, etc.)
4. Batch Processing
pythondef process_documents_in_batches(db, batch_size=100):
    """Process large dataset in batches to avoid memory issues"""
    
    offset = 0
    
    while True:
        # Fetch batch
        documents = db.query(Document)\
            .filter(Document.status == 'pending')\
            .order_by(Document.id)\
            .offset(offset)\
            .limit(batch_size)\
            .all()
        
        if not documents:
            break
        
        # Process batch
        for doc in documents:
            # Process document
            doc.status = 'processed'
        
        db.commit()
        
        # Free memory
        db.expunge_all()
        
        offset += batch_size
        
        print(f"Processed {offset} documents...")

⚙️ RAW SQL vs ORM
When to Use Raw SQL
python# ✅ Use RAW SQL for:
# - Complex aggregations
# - Database-specific features
# - Performance-critical queries
# - Bulk operations

# ❌ Use ORM for:
# - Simple CRUD
# - Type safety
# - Relationship loading
# - Portability
1. Raw SQL with SQLAlchemy
pythonfrom sqlalchemy import text

# Simple raw query
result = db.execute(
    text("SELECT * FROM documents WHERE user_id = :user_id"),
    {"user_id": str(user_id)}
)
documents = result.fetchall()

# Complex aggregation
stats = db.execute(text("""
    SELECT 
        DATE_TRUNC('day', created_at) as date,
        COUNT(*) as count,
        AVG(file_size) as avg_size
    FROM documents
    WHERE user_id = :user_id
    GROUP BY DATE_TRUNC('day', created_at)
    ORDER BY date DESC
    LIMIT 30
"""), {"user_id": str(user_id)}).fetchall()
2. Hybrid Approach
python# Use ORM for structure, raw SQL for performance

def get_user_statistics(db, user_id):
    """Hybrid: ORM + raw SQL"""
    
    # Use ORM for simple query
    user = db.query(User).get(user_id)
    
    # Use raw SQL for complex aggregation
    stats = db.execute(text("""
        SELECT 
            COUNT(DISTINCT d.id) as total_documents,
            COUNT(DISTINCT CASE WHEN d.status = 'completed' THEN d.id END) as completed,
            SUM(d.file_size) as total_size,
            AVG(pj.processing_time_ms) as avg_processing_time
        FROM documents d
        LEFT JOIN processing_jobs pj ON pj.document_id = d.id
        WHERE d.user_id = :user_id
    """), {"user_id": str(user_id)}).fetchone()
    
    return {
        'user': user,
        'stats': dict(stats)
    }

🐘 POSTGRESQL-SPECIFIC OPTIMIZATIONS
1. Analyze and Vacuum
pythondef maintain_database(db):
    """Run maintenance tasks"""
    
    # Update statistics
    db.execute(text("ANALYZE"))
    
    # Reclaim space
    db.execute(text("VACUUM"))
    
    # Full vacuum (locks table!)
    # db.execute(text("VACUUM FULL"))
2. Parallel Queries
python# Enable parallel queries (PostgreSQL 9.6+)

from sqlalchemy import text

# Set for session
db.execute(text("SET max_parallel_workers_per_gather = 4"))

# Or in postgresql.conf:
# max_parallel_workers_per_gather = 4
# max_parallel_workers = 8
3. Materialized Views
python# Create materialized view for expensive aggregations

def create_user_stats_view(db):
    db.execute(text("""
        CREATE MATERIALIZED VIEW user_document_stats AS
        SELECT 
            user_id,
            COUNT(*) as document_count,
            SUM(file_size) as total_size,
            MAX(created_at) as last_upload
        FROM documents
        GROUP BY user_id
    """))
    
    # Create index
    db.execute(text("""
        CREATE INDEX idx_user_stats_user_id 
        ON user_document_stats (user_id)
    """))

# Refresh view
def refresh_user_stats(db):
    db.execute(text("REFRESH MATERIALIZED VIEW user_document_stats"))

# Query view (very fast!)
stats = db.execute(text("""
    SELECT * FROM user_document_stats WHERE user_id = :user_id
"""), {"user_id": str(user_id)}).fetchone()
4. Table Partitioning
python# Partition large tables by date

def create_partitioned_documents_table(db):
    """Create partitioned documents table"""
    
    # Parent table
    db.execute(text("""
        CREATE TABLE documents (
            id UUID PRIMARY KEY,
            user_id UUID NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL,
            ...
        ) PARTITION BY RANGE (created_at)
    """))
    
    # Create partitions for each month
    db.execute(text("""
        CREATE TABLE documents_2025_01 
        PARTITION OF documents
        FOR VALUES FROM ('2025-01-01') TO ('2025-02-01')
    """))
    
    db.execute(text("""
        CREATE TABLE documents_2025_02 
        PARTITION OF documents
        FOR VALUES FROM ('2025-02-01') TO ('2025-03-01')
    """))
    
    # Queries automatically use correct partition
    # SELECT * FROM documents WHERE created_at >= '2025-01-15'
    # → Only scans documents_2025_01 partition

⚠️ COMMON ANTI-PATTERNS
1. SELECT * Anti-Pattern
python# ❌ BAD: Select all columns
documents = db.query(Document).all()

# ✅ GOOD: Select only needed columns
documents = db.query(
    Document.id,
    Document.title,
    Document.status
).all()

# Even better: Use load_only
from sqlalchemy.orm import load_only

documents = db.query(Document)\
    .options(load_only(Document.id, Document.title, Document.status))\
    .all()
2. Loading in Loops Anti-Pattern
python# ❌ BAD: Query in loop
user_ids = [uuid1, uuid2, uuid3]
users = []
for user_id in user_ids:
    user = db.query(User).get(user_id)  # N queries!
    users.append(user)

# ✅ GOOD: Single query with IN
users = db.query(User)\
    .filter(User.id.in_(user_ids))\
    .all()
3. Unnecessary COUNT Anti-Pattern
python# ❌ BAD: Count to check existence
count = db.query(Document).filter(Document.id == doc_id).count()
if count > 0:
    print("Document exists")

# ✅ GOOD: Use EXISTS
from sqlalchemy import exists

exists_query = db.query(
    exists().where(Document.id == doc_id)
).scalar()

if exists_query:
    print("Document exists")

# Even simpler
document = db.query(Document).filter(Document.id == doc_id).first()
if document:
    print("Document exists")
4. Large Offset Anti-Pattern
python# ❌ BAD: Large offset
documents = db.query(Document)\
    .order_by(Document.created_at.desc())\
    .offset(10000)\
    .limit(20)\
    .all()

# ✅ GOOD: Cursor-based pagination
last_created_at = ...  # From previous page
documents = db.query(Document)\
    .filter(Document.created_at < last_created_at)\
    .order_by(Document.created_at.desc())\
    .limit(20)\
    .all()
5. Implicit Cartesian Product
python# ❌ BAD: Multiple joinedload on collections
documents = db.query(Document)\
    .options(
        joinedload(Document.pages),      # Collection 1
        joinedload(Document.versions)    # Collection 2
    )\
    .all()
# Result: Cartesian product! (pages × versions rows returned)

# ✅ GOOD: Use selectinload for collections
documents = db.query(Document)\
    .options(
        selectinload(Document.pages),
        selectinload(Document.versions)
    )\
    .all()

🔍 MONITORING & DEBUGGING
1. Query Statistics
pythondef get_query_statistics(db):
    """Get database query statistics"""
    
    stats = db.execute(text("""
        SELECT 
            query,
            calls,
            total_time,
            mean_time,
            max_time
        FROM pg_stat_statements
        ORDER BY total_time DESC
        LIMIT 20
    """)).fetchall()
    
    print("\n" + "=" * 70)
    print("TOP 20 QUERIES BY TOTAL TIME")
    print("=" * 70)
    
    for stat in stats:
        print(f"Calls: {stat.calls}")
        print(f"Total: {stat.total_time:.2f}ms")
        print(f"Mean: {stat.mean_time:.2f}ms")
        print(f"Max: {stat.max_time:.2f}ms")
        print(f"Query: {stat.query[:100]}...")
        print("-" * 70)
2. Connection Monitoring
pythondef monitor_connections(db):
    """Monitor active database connections"""
    
    connections = db.execute(text("""
        SELECT 
            pid,
            usename,
            application_name,
            state,
            query,
            state_change
        FROM pg_stat_activity
        WHERE datname = current_database()
        ORDER BY state_change DESC
    """)).fetchall()
    
    print(f"\nActive connections: {len(connections)}")
    
    for conn in connections:
        print(f"PID: {conn.pid}")
        print(f"User: {conn.usename}")
        print(f"App: {conn.application_name}")
        print(f"State: {conn.state}")
        print(f"Query: {conn.query[:50]}...")
        print("-" * 70)
3. Slow Query Detection
python# Enable log_min_duration_statement in postgresql.conf
# log_min_duration_statement = 100  # Log queries slower than 100ms

# Or set per session
db.execute(text("SET log_min_duration_statement = 100"))

✅ PERFORMANCE CHECKLIST
Query Optimization

 Use indexes on frequently queried columns
 Avoid N+1 queries (use eager loading)
 Select only needed columns
 Use cursor/keyset pagination for large datasets
 Use bulk operations for multiple inserts/updates
 Add composite indexes for multi-column filters
 Use covering indexes when possible
 Avoid SELECT * in production code

Database Configuration

 Configure appropriate connection pool size
 Enable query logging for slow queries
 Set up regular VACUUM and ANALYZE
 Monitor index usage and remove unused indexes
 Use materialized views for expensive aggregations
 Enable parallel query execution
 Set appropriate query timeout

Application Level

 Implement caching for frequently accessed data
 Use database connection pooling
 Close database sessions properly
 Batch API requests when possible
 Implement rate limiting
 Monitor query performance in production
 Set up alerts for slow queries

Code Review

 Check for N+1 problems in relationships
 Verify indexes exist for WHERE/ORDER BY clauses
 Ensure proper pagination implementation
 Review bulk operation efficiency
 Check for unnecessary COUNT queries
 Verify proper use of eager loading
 Test query performance with production-sized data


🎓 SUMMARY
Golden Rules:

Measure First - Profile before optimizing
Index Strategically - Index what you query, not everything
Eager Load - Avoid N+1 problems with proper loading strategies
Paginate Smart - Use cursor/keyset pagination for large datasets
Cache Wisely - Cache expensive queries, invalidate properly
Bulk When Possible - Use bulk operations for multiple records
Monitor Always - Track query performance in production

Quick Wins:
python# ✅ Add these to every query-heavy endpoint:

1. Use selectinload/joinedload for relationships
2. Add .options(load_only(...)) to select specific columns
3. Implement cursor-based pagination
4. Add appropriate indexes
5. Use connection pooling
6. Enable query logging
7. Cache frequently accessed data
Performance Metrics:

Fast: < 50ms query time
Acceptable: 50-200ms query time
Slow: 200-1000ms query time
Critical: > 1000ms query time (needs immediate optimization)