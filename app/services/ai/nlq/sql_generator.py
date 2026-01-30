"""SQL Generator - LLM-basierte SQL-Generierung mit Ollama."""

import time
from dataclasses import dataclass
from typing import Any, Dict

import httpx
import structlog

from app.core.safe_errors import safe_error_log, safe_error_detail

logger = structlog.get_logger(__name__)


@dataclass
class SQLGenerationResult:
    """Ergebnis der SQL-Generierung."""

    sql: str
    confidence: float
    explanation: str  # German
    model_used: str
    generation_time_ms: int


class SQLGenerator:
    """Generates SQL from natural language using Ollama LLM.

    On-Premises Only:
        - Uses local Ollama instance (localhost:11434)
        - No cloud API dependencies
        - Model: qwen3:8b (optimal for SQL generation)
    """

    OLLAMA_BASE_URL: str = "http://localhost:11434"
    DEFAULT_MODEL: str = "qwen3:8b"
    TIMEOUT_SECONDS: int = 30

    def __init__(self, model: str = DEFAULT_MODEL):
        """Initialize SQL generator.

        Args:
            model: Ollama model name (default: qwen3:8b)
        """
        self.model = model

    async def generate_sql(
        self, query: str, schema_context: str
    ) -> SQLGenerationResult:
        """Generate SQL from natural language query.

        Args:
            query: Natural language query in German
            schema_context: Database schema description

        Returns:
            SQLGenerationResult with generated SQL and metadata

        Raises:
            RuntimeError: If Ollama is not available or generation fails
        """
        start_time = time.time()

        try:
            # Build prompt
            prompt = self._build_prompt(query, schema_context)

            # Call Ollama API
            async with httpx.AsyncClient(
                timeout=self.TIMEOUT_SECONDS
            ) as client:
                response = await client.post(
                    f"{self.OLLAMA_BASE_URL}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {
                            "temperature": 0.1,  # Low temp for deterministic SQL
                            "top_p": 0.9,
                            "num_predict": 500,  # Max tokens for SQL
                        },
                    },
                )
                response.raise_for_status()

            result_json: Dict[str, Any] = response.json()
            raw_response = result_json.get("response", "")

            # Extract SQL and explanation
            sql, explanation = self._parse_response(raw_response)

            # Calculate confidence based on SQL quality
            confidence = self._estimate_confidence(sql, query)

            generation_time_ms = int((time.time() - start_time) * 1000)

            logger.info(
                "sql_generation_success",
                model=self.model,
                generation_time_ms=generation_time_ms,
                confidence=confidence,
                sql_length=len(sql),
            )

            return SQLGenerationResult(
                sql=sql,
                confidence=confidence,
                explanation=explanation,
                model_used=self.model,
                generation_time_ms=generation_time_ms,
            )

        except httpx.HTTPError as e:
            logger.error(
                "ollama_connection_failed",
                **safe_error_log(e),
                url=self.OLLAMA_BASE_URL,
            )
            raise RuntimeError(
                "Ollama ist nicht verfügbar. Bitte starten Sie den Ollama-Server."
            ) from e

        except Exception as e:
            logger.error("sql_generation_failed", **safe_error_log(e))
            raise RuntimeError(
                safe_error_detail(e, "SQL-Generierung")
            ) from e

    def _build_prompt(self, query: str, schema_context: str) -> str:
        """Build LLM prompt for SQL generation.

        Args:
            query: Natural language query
            schema_context: Database schema description

        Returns:
            Formatted prompt string
        """
        return f"""Du bist ein SQL-Experte für PostgreSQL. Generiere eine SQL-Abfrage basierend auf der natürlichen Sprache-Anfrage.

{schema_context}

## Anforderungen:
- Nur SELECT-Abfragen
- PostgreSQL-Syntax verwenden
- Deutsche Spaltennamen und Werte beachten
- Effiziente JOINs verwenden
- Aggregationen mit GROUP BY
- Sortierung mit ORDER BY wenn sinnvoll
- KEINE LIMIT-Klausel (wird automatisch hinzugefügt)
- KEINE WHERE-Klausel für company_id (wird automatisch injiziert)

## Natürliche Sprache-Anfrage:
{query}

## Antwort-Format:
Generiere die SQL-Abfrage und erkläre kurz auf Deutsch was sie macht.

SQL:
```sql
-- Deine SQL-Abfrage hier
```

Erklärung:
-- Deine Erklärung auf Deutsch hier
"""

    def _parse_response(self, raw_response: str) -> tuple[str, str]:
        """Parse LLM response to extract SQL and explanation.

        Args:
            raw_response: Raw LLM output

        Returns:
            Tuple of (sql, explanation)
        """
        sql = ""
        explanation = ""

        # Extract SQL from code block
        import re


        sql_match = re.search(
            r"```sql\s*\n(.*?)\n```", raw_response, re.DOTALL | re.IGNORECASE
        )
        if sql_match:
            sql = sql_match.group(1).strip()
        else:
            # Try to extract SELECT statement directly
            select_match = re.search(
                r"(SELECT\s+.*?)(?:\n\n|$)",
                raw_response,
                re.DOTALL | re.IGNORECASE,
            )
            if select_match:
                sql = select_match.group(1).strip()

        # Extract explanation
        explanation_match = re.search(
            r"Erklärung:\s*\n(.*?)(?:\n\n|$)",
            raw_response,
            re.DOTALL | re.IGNORECASE,
        )
        if explanation_match:
            explanation = explanation_match.group(1).strip()
        else:
            # Use everything after SQL as explanation
            if sql:
                parts = raw_response.split(sql)
                if len(parts) > 1:
                    explanation = parts[1].strip()

        # Fallback
        if not explanation:
            explanation = "SQL-Abfrage wurde generiert."

        # Clean up SQL comments
        sql = re.sub(r"--.*?$", "", sql, flags=re.MULTILINE).strip()

        return sql, explanation

    def _estimate_confidence(self, sql: str, query: str) -> float:
        """Estimate confidence based on SQL quality.

        Args:
            sql: Generated SQL
            query: Original natural language query

        Returns:
            Confidence score (0.0 - 1.0)
        """
        confidence = 0.5  # Base confidence

        # Check SQL validity indicators
        if re.search(r"\bSELECT\b", sql, re.IGNORECASE):
            confidence += 0.2

        if re.search(r"\bFROM\b", sql, re.IGNORECASE):
            confidence += 0.1

        # Bonus for complex queries
        if re.search(r"\bJOIN\b", sql, re.IGNORECASE):
            confidence += 0.05

        if re.search(r"\bGROUP BY\b", sql, re.IGNORECASE):
            confidence += 0.05

        if re.search(r"\bORDER BY\b", sql, re.IGNORECASE):
            confidence += 0.05

        # Penalty for empty or very short SQL
        if len(sql) < 20:
            confidence -= 0.3

        # Cap at 0.95 (never 100% confident with LLM)
        return min(max(confidence, 0.0), 0.95)

    async def check_ollama_health(self) -> bool:
        """Check if Ollama is running and responsive.

        Returns:
            True if Ollama is healthy
        """
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.OLLAMA_BASE_URL}/api/tags")
                response.raise_for_status()

                # Check if our model is available
                tags = response.json().get("models", [])
                model_available = any(
                    tag.get("name") == self.model for tag in tags
                )

                if not model_available:
                    logger.warning(
                        "ollama_model_not_found",
                        model=self.model,
                        available_models=[t.get("name") for t in tags],
                    )

                return model_available

        except Exception as e:
            logger.error("ollama_health_check_failed", **safe_error_log(e))
            return False
