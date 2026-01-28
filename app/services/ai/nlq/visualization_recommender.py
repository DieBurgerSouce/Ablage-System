"""Visualization Recommender - Empfiehlt Chart-Typ basierend auf Query und Daten."""

from typing import List

import structlog

logger = structlog.get_logger(__name__)


class VisualizationRecommender:
    """Recommends optimal visualization type based on query and data.

    Visualization Types:
        - kpi: Single key metric
        - bar: Category comparisons
        - line: Time series trends
        - pie: Proportions/percentages
        - table: Detailed data view
    """

    def recommend(
        self, query: str, columns: List[str], row_count: int
    ) -> str:
        """Recommend visualization type.

        Args:
            query: Natural language query
            columns: Result column names
            row_count: Number of result rows

        Returns:
            Visualization type (kpi, bar, line, pie, table)

        Heuristics:
            - Single value -> kpi
            - Time series -> line
            - Categories -> bar
            - Percentages/shares -> pie
            - Many rows/columns -> table
        """
        query_lower = query.lower()
        col_count = len(columns)

        # KPI: Single value
        if row_count == 1 and col_count == 1:
            logger.info("viz_recommendation", type="kpi", reason="single_value")
            return "kpi"

        # KPI: Aggregation query
        if row_count == 1 and any(
            kw in query_lower
            for kw in [
                "gesamt",
                "total",
                "summe",
                "sum",
                "durchschnitt",
                "average",
                "anzahl",
                "count",
            ]
        ):
            logger.info(
                "viz_recommendation", type="kpi", reason="aggregation"
            )
            return "kpi"

        # Line: Time series
        if self._is_time_series(columns, query_lower):
            logger.info(
                "viz_recommendation", type="line", reason="time_series"
            )
            return "line"

        # Pie: Percentage/share queries
        if self._is_proportion_query(query_lower, columns):
            logger.info(
                "viz_recommendation", type="pie", reason="proportions"
            )
            return "pie"

        # Bar: Category comparisons
        if self._is_category_comparison(columns, row_count):
            logger.info(
                "viz_recommendation",
                type="bar",
                reason="category_comparison",
            )
            return "bar"

        # Table: Large datasets or many columns
        if row_count > 50 or col_count > 5:
            logger.info(
                "viz_recommendation",
                type="table",
                reason="large_dataset",
                rows=row_count,
                cols=col_count,
            )
            return "table"

        # Default: Bar for small categorical data
        logger.info("viz_recommendation", type="bar", reason="default")
        return "bar"

    def _is_time_series(self, columns: List[str], query: str) -> bool:
        """Check if data is time series.

        Args:
            columns: Column names
            query: Query text

        Returns:
            True if time series detected
        """
        # Check for time/date keywords in query
        time_keywords = [
            "trend",
            "verlauf",
            "entwicklung",
            "monat",
            "month",
            "jahr",
            "year",
            "tag",
            "day",
            "woche",
            "week",
            "quartal",
            "quarter",
            "zeitraum",
            "period",
        ]
        if any(kw in query for kw in time_keywords):
            return True

        # Check for date/time columns
        date_column_keywords = [
            "date",
            "datum",
            "time",
            "zeit",
            "month",
            "monat",
            "year",
            "jahr",
            "created_at",
            "updated_at",
        ]
        for col in columns:
            col_lower = col.lower()
            if any(kw in col_lower for kw in date_column_keywords):
                return True

        return False

    def _is_proportion_query(
        self, query: str, columns: List[str]
    ) -> bool:
        """Check if query is about proportions/percentages.

        Args:
            query: Query text
            columns: Column names

        Returns:
            True if proportion query detected
        """
        # Keywords indicating proportions
        proportion_keywords = [
            "anteil",
            "share",
            "prozent",
            "percent",
            "verteilung",
            "distribution",
            "aufteilung",
            "breakdown",
        ]
        if any(kw in query for kw in proportion_keywords):
            return True

        # Check column names
        for col in columns:
            col_lower = col.lower()
            if "percent" in col_lower or "prozent" in col_lower:
                return True

        return False

    def _is_category_comparison(
        self, columns: List[str], row_count: int
    ) -> bool:
        """Check if data represents category comparison.

        Args:
            columns: Column names
            row_count: Number of rows

        Returns:
            True if category comparison detected
        """
        # Typical pattern: category column + value column(s)
        if len(columns) >= 2 and 2 <= row_count <= 20:
            # Check if first column looks like category
            first_col = columns[0].lower()
            category_indicators = [
                "name",
                "type",
                "typ",
                "category",
                "kategorie",
                "status",
                "group",
                "gruppe",
            ]
            if any(ind in first_col for ind in category_indicators):
                return True

            # Check if other columns are numeric (counts, sums)
            numeric_indicators = [
                "count",
                "anzahl",
                "sum",
                "summe",
                "total",
                "gesamt",
                "amount",
                "betrag",
            ]
            for col in columns[1:]:
                col_lower = col.lower()
                if any(ind in col_lower for ind in numeric_indicators):
                    return True

        return False
