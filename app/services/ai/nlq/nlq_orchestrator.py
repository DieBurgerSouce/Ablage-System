"""NLQ Orchestrator - Hauptorchestrator fuer Natural Language Query 2.0."""

import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from uuid import UUID

import structlog
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.exceptions import BusinessLogicError
from app.db.models import NLQQueryLog
from app.services.ai.nlq.query_cache import CachedResult, QueryCache
from app.services.ai.nlq.result_formatter import (
    FormattedResult,
    ResultFormatter,
)
from app.services.ai.nlq.schema_introspector import SchemaIntrospector
from app.services.ai.nlq.sql_generator import (
    SQLGenerationResult,
    SQLGenerator,
)
from app.services.ai.nlq.sql_sanitizer import (
    SanitizationResult,
    SQLSanitizer,
)
from app.services.ai.nlq.visualization_recommender import (
    VisualizationRecommender,
)

logger = structlog.get_logger(__name__)


@dataclass
class NLQResponse:
    """NLQ Query Response."""

    query_log_id: UUID
    natural_query: str
    generated_sql: str
    result: FormattedResult
    visualization_type: str
    visualization_config: Dict[str, Any]
    execution_time_ms: int
    was_cached: bool
    confidence: float


class NLQOrchestrator:
    """Orchestrates Natural Language Query processing.

    Workflow:
        1. Check cache
        2. Generate SQL via LLM
        3. Sanitize SQL (security critical)
        4. Execute query with timeout
        5. Format results
        6. Recommend visualization
        7. Log query
        8. Cache result
    """

    QUERY_TIMEOUT_SECONDS: int = 10

    def __init__(self, engine: AsyncEngine, redis: Redis):
        """Initialize orchestrator.

        Args:
            engine: SQLAlchemy async engine
            redis: Redis async client
        """
        self.engine = engine
        self.redis = redis

        # Initialize components
        self.cache = QueryCache(redis)
        self.sanitizer = SQLSanitizer()
        self.generator = SQLGenerator()
        self.introspector = SchemaIntrospector(engine)
        self.formatter = ResultFormatter()
        self.viz_recommender = VisualizationRecommender()

    async def query(
        self,
        natural_query: str,
        user_id: UUID,
        company_id: UUID,
        db: AsyncSession,
    ) -> NLQResponse:
        """Process natural language query.

        Args:
            natural_query: Natural language query in German
            user_id: User ID for logging
            company_id: Company ID for multi-tenant isolation
            db: Database session for logging

        Returns:
            NLQResponse with results and metadata

        Raises:
            BusinessLogicError: If query processing fails
        """
        start_time = time.time()
        company_id_str = str(company_id)

        logger.info(
            "nlq_query_started",
            user_id=str(user_id),
            company_id=company_id_str,
            query_length=len(natural_query),
        )

        # 1. Check cache
        cached = await self.cache.get_cached(natural_query, company_id_str)
        if cached:
            execution_time_ms = int((time.time() - start_time) * 1000)
            return await self._handle_cached_result(
                cached, user_id, company_id, db, execution_time_ms
            )

        # 2. Generate SQL via LLM
        try:
            schema_context = await self.introspector.get_schema_context()
            generation_result: SQLGenerationResult = (
                await self.generator.generate_sql(
                    natural_query, schema_context
                )
            )
        except Exception as e:
            logger.error("sql_generation_failed", error=str(e))
            raise BusinessLogicError(
                f"SQL-Generierung fehlgeschlagen: {str(e)}"
            ) from e

        # 3. Sanitize SQL
        sanitization: SanitizationResult = self.sanitizer.sanitize(
            generation_result.sql, company_id
        )
        if not sanitization.safe:
            logger.warning(
                "sql_sanitization_failed",
                violations=sanitization.violations,
            )
            raise BusinessLogicError(
                f"SQL-Sicherheitsprüfung fehlgeschlagen: {', '.join(sanitization.violations)}"
            )

        # 4. Execute query with timeout
        try:
            columns, rows = await self._execute_query(
                sanitization.sanitized_sql
            )
        except Exception as e:
            logger.error(
                "query_execution_failed",
                sql=sanitization.sanitized_sql,
                error=str(e),
            )
            raise BusinessLogicError(
                f"Abfrage-Ausführung fehlgeschlagen: {str(e)}"
            ) from e

        # 5. Recommend visualization
        viz_type = self.viz_recommender.recommend(
            natural_query, columns, len(rows)
        )

        # 6. Format results
        formatted = self.formatter.format_result(
            natural_query, columns, rows, viz_type
        )

        # 7. Log query
        query_log = await self._log_query(
            natural_query=natural_query,
            generated_sql=sanitization.sanitized_sql,
            user_id=user_id,
            company_id=company_id,
            result_count=len(rows),
            confidence=generation_result.confidence,
            db=db,
        )

        # 8. Cache result
        await self.cache.set_cached(
            natural_query=natural_query,
            company_id=company_id_str,
            generated_sql=sanitization.sanitized_sql,
            columns=columns,
            rows=rows,
            visualization_type=viz_type,
            text_summary=formatted.text_summary,
            confidence=generation_result.confidence,
        )

        execution_time_ms = int((time.time() - start_time) * 1000)

        logger.info(
            "nlq_query_completed",
            query_log_id=str(query_log.id),
            execution_time_ms=execution_time_ms,
            result_count=len(rows),
            was_cached=False,
        )

        return NLQResponse(
            query_log_id=query_log.id,
            natural_query=natural_query,
            generated_sql=sanitization.sanitized_sql,
            result=formatted,
            visualization_type=viz_type,
            visualization_config=formatted.visualization_config,
            execution_time_ms=execution_time_ms,
            was_cached=False,
            confidence=generation_result.confidence,
        )

    async def _handle_cached_result(
        self,
        cached: CachedResult,
        user_id: UUID,
        company_id: UUID,
        db: AsyncSession,
        execution_time_ms: int,
    ) -> NLQResponse:
        """Handle cached query result.

        Args:
            cached: Cached result
            user_id: User ID
            company_id: Company ID
            db: Database session
            execution_time_ms: Execution time

        Returns:
            NLQResponse from cache
        """
        # Log cache hit
        query_log = await self._log_query(
            natural_query=cached.natural_query,
            generated_sql=cached.generated_sql,
            user_id=user_id,
            company_id=company_id,
            result_count=cached.total_rows,
            confidence=cached.confidence,
            db=db,
            was_cached=True,
        )

        # Convert cached rows back to tuples
        rows = [tuple(row) for row in cached.rows]

        # Format result
        formatted = self.formatter.format_result(
            cached.natural_query,
            cached.columns,
            rows,
            cached.visualization_type,
        )

        logger.info(
            "nlq_query_from_cache",
            query_log_id=str(query_log.id),
            execution_time_ms=execution_time_ms,
            result_count=cached.total_rows,
        )

        return NLQResponse(
            query_log_id=query_log.id,
            natural_query=cached.natural_query,
            generated_sql=cached.generated_sql,
            result=formatted,
            visualization_type=cached.visualization_type,
            visualization_config=formatted.visualization_config,
            execution_time_ms=execution_time_ms,
            was_cached=True,
            confidence=cached.confidence,
        )

    async def _execute_query(
        self, sql: str
    ) -> tuple[List[str], List[tuple]]:
        """Execute sanitized SQL query.

        Args:
            sql: Sanitized SQL query

        Returns:
            Tuple of (columns, rows)

        Raises:
            Exception: If query execution fails
        """
        async with self.engine.begin() as conn:
            # Set statement timeout
            await conn.execute(
                text(
                    f"SET LOCAL statement_timeout = '{self.QUERY_TIMEOUT_SECONDS}s'"
                )
            )

            # Execute query
            result = await conn.execute(text(sql))
            rows = result.fetchall()
            columns = list(result.keys())

            logger.info(
                "query_executed",
                columns=len(columns),
                rows=len(rows),
            )

            return columns, rows

    async def _log_query(
        self,
        natural_query: str,
        generated_sql: str,
        user_id: UUID,
        company_id: UUID,
        result_count: int,
        confidence: float,
        db: AsyncSession,
        was_cached: bool = False,
    ) -> NLQQueryLog:
        """Log query to database.

        Args:
            natural_query: Natural language query
            generated_sql: Generated SQL
            user_id: User ID
            company_id: Company ID
            result_count: Number of results
            confidence: Query confidence (stored in visualization_config)
            db: Database session
            was_cached: Whether result was from cache

        Returns:
            Created NLQQueryLog
        """
        query_log = NLQQueryLog(
            user_id=user_id,
            company_id=company_id,
            natural_query=natural_query,
            generated_sql=generated_sql,
            sanitized_sql=generated_sql,  # Already sanitized
            result_count=result_count,
            was_cached=was_cached,
            visualization_config={"confidence": confidence},  # Store confidence in config
        )

        db.add(query_log)
        await db.commit()
        await db.refresh(query_log)

        return query_log

    async def get_suggestions(
        self, company_id: UUID, db: AsyncSession, limit: int = 10
    ) -> List[str]:
        """Get query suggestions based on popular queries.

        Args:
            company_id: Company ID
            db: Database session
            limit: Max number of suggestions

        Returns:
            List of suggested natural language queries
        """
        from sqlalchemy import func, select

        # Get most popular queries (successful ones only)
        stmt = (
            select(
                NLQQueryLog.natural_query,
                func.count(NLQQueryLog.id).label("count"),
            )
            .where(NLQQueryLog.company_id == company_id)
            .where(NLQQueryLog.error_message.is_(None))  # Only successful queries
            .where(NLQQueryLog.result_count > 0)  # Only queries with results
            .group_by(NLQQueryLog.natural_query)
            .order_by(func.count(NLQQueryLog.id).desc())
            .limit(limit)
        )

        result = await db.execute(stmt)
        rows = result.all()

        suggestions = [row[0] for row in rows]

        logger.info(
            "suggestions_generated",
            company_id=str(company_id),
            count=len(suggestions),
        )

        return suggestions

    async def submit_feedback(
        self,
        query_log_id: UUID,
        rating: int,
        comment: Optional[str],
        db: AsyncSession,
    ) -> None:
        """Submit feedback for a query.

        Args:
            query_log_id: Query log ID
            rating: Rating (1-5)
            comment: Optional feedback comment
            db: Database session

        Raises:
            BusinessLogicError: If query log not found
        """
        from sqlalchemy import select

        # Get query log
        stmt = select(NLQQueryLog).where(NLQQueryLog.id == query_log_id)
        result = await db.execute(stmt)
        query_log = result.scalar_one_or_none()

        if not query_log:
            raise BusinessLogicError("Abfrage-Log nicht gefunden")

        # Update feedback
        query_log.feedback_rating = rating
        query_log.feedback_comment = comment

        await db.commit()

        logger.info(
            "feedback_submitted",
            query_log_id=str(query_log_id),
            rating=rating,
            has_comment=bool(comment),
        )

    async def health_check(self) -> Dict[str, Any]:
        """Check health of NLQ service.

        Returns:
            Health status dict
        """
        health: Dict[str, Any] = {
            "service": "nlq",
            "status": "healthy",
            "components": {},
        }

        # Check Ollama
        try:
            ollama_healthy = await self.generator.check_ollama_health()
            health["components"]["ollama"] = {
                "status": "healthy" if ollama_healthy else "unhealthy",
                "model": self.generator.model,
            }
        except Exception as e:
            health["components"]["ollama"] = {
                "status": "error",
                "error": str(e),
            }
            health["status"] = "degraded"

        # Check Redis
        try:
            await self.redis.ping()
            health["components"]["redis"] = {"status": "healthy"}
        except Exception as e:
            health["components"]["redis"] = {
                "status": "error",
                "error": str(e),
            }
            health["status"] = "degraded"

        # Check Database
        try:
            async with self.engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            health["components"]["database"] = {"status": "healthy"}
        except Exception as e:
            health["components"]["database"] = {
                "status": "error",
                "error": str(e),
            }
            health["status"] = "degraded"

        return health
