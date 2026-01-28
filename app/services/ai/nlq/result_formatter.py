"""Result Formatter - Formatiert Query-Ergebnisse fuer Display."""

from dataclasses import dataclass, field
from typing import Any, Dict, List

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class FormattedResult:
    """Formatiertes Query-Ergebnis."""

    text_summary: str  # German summary
    data: List[Dict[str, Any]]
    visualization_type: str  # bar, line, pie, table, kpi
    visualization_config: Dict[str, Any] = field(default_factory=dict)
    total_rows: int = 0


class ResultFormatter:
    """Formats query results for user-friendly display.

    Capabilities:
        - Generate German text summaries
        - Convert rows to JSON-serializable format
        - Configure visualization parameters
        - Handle different data types (numbers, dates, text)
    """

    def format_result(
        self,
        query: str,
        columns: List[str],
        rows: List[tuple],
        viz_type: str,
    ) -> FormattedResult:
        """Format query result for display.

        Args:
            query: Original natural language query
            columns: Column names from SQL result
            rows: Result rows as tuples
            viz_type: Recommended visualization type

        Returns:
            FormattedResult with summary and visualization config
        """
        total_rows = len(rows)

        # Convert rows to dicts
        data = [dict(zip(columns, row)) for row in rows]

        # Generate text summary
        text_summary = self._generate_summary(query, columns, rows, viz_type)

        # Generate visualization config
        viz_config = self._generate_viz_config(
            columns, rows, viz_type
        )

        logger.info(
            "result_formatted",
            total_rows=total_rows,
            viz_type=viz_type,
            columns=len(columns),
        )

        return FormattedResult(
            text_summary=text_summary,
            data=data,
            visualization_type=viz_type,
            visualization_config=viz_config,
            total_rows=total_rows,
        )

    def _generate_summary(
        self,
        query: str,
        columns: List[str],
        rows: List[tuple],
        viz_type: str,
    ) -> str:
        """Generate German text summary of results.

        Args:
            query: Original query
            columns: Column names
            rows: Result rows
            viz_type: Visualization type

        Returns:
            German summary text
        """
        if not rows:
            return f"Keine Ergebnisse gefunden für: {query}"

        total_rows = len(rows)

        # KPI-specific summary
        if viz_type == "kpi" and total_rows == 1 and len(columns) == 1:
            value = rows[0][0]
            return f"{columns[0]}: {self._format_value(value)}"

        # Aggregate summary
        if total_rows == 1 and any(
            col.lower() in ["count", "sum", "avg", "max", "min"]
            for col in columns
        ):
            parts = []
            for col, val in zip(columns, rows[0]):
                parts.append(f"{col}: {self._format_value(val)}")
            return " | ".join(parts)

        # General summary
        if total_rows == 1:
            summary = f"1 Ergebnis gefunden"
        elif total_rows < 10:
            summary = f"{total_rows} Ergebnisse gefunden"
        elif total_rows < 100:
            summary = f"{total_rows} Ergebnisse gefunden"
        else:
            summary = f"{total_rows} Ergebnisse (max. 1000 angezeigt)"

        # Add top result info
        if total_rows > 0 and len(columns) >= 2:
            first_col = columns[0]
            first_val = rows[0][0]
            summary += f" | Top: {first_col} = {self._format_value(first_val)}"

        return summary

    def _format_value(self, value: Any) -> str:
        """Format value for display.

        Args:
            value: Value to format

        Returns:
            Formatted string
        """
        if value is None:
            return "—"

        if isinstance(value, (int, float)):
            # Format numbers with thousand separators
            if isinstance(value, float):
                return f"{value:,.2f}"
            return f"{value:,}"

        if isinstance(value, bool):
            return "Ja" if value else "Nein"

        return str(value)

    def _generate_viz_config(
        self, columns: List[str], rows: List[tuple], viz_type: str
    ) -> Dict[str, Any]:
        """Generate visualization configuration.

        Args:
            columns: Column names
            rows: Result rows
            viz_type: Visualization type

        Returns:
            Config dict for visualization component
        """
        config: Dict[str, Any] = {"type": viz_type}

        if viz_type == "kpi":
            config.update(self._kpi_config(columns, rows))
        elif viz_type == "bar":
            config.update(self._bar_config(columns, rows))
        elif viz_type == "line":
            config.update(self._line_config(columns, rows))
        elif viz_type == "pie":
            config.update(self._pie_config(columns, rows))
        elif viz_type == "table":
            config.update(self._table_config(columns))

        return config

    def _kpi_config(
        self, columns: List[str], rows: List[tuple]
    ) -> Dict[str, Any]:
        """Generate KPI visualization config.

        Args:
            columns: Column names
            rows: Result rows

        Returns:
            KPI config
        """
        if not rows or not columns:
            return {}

        value = rows[0][0]
        label = columns[0]

        # Determine formatting
        format_type = "number"
        if isinstance(value, float):
            format_type = "currency" if "betrag" in label.lower() or "amount" in label.lower() else "decimal"
        elif isinstance(value, int) and value > 1000000:
            format_type = "compact"

        return {
            "value": value,
            "label": label,
            "format": format_type,
        }

    def _bar_config(
        self, columns: List[str], rows: List[tuple]
    ) -> Dict[str, Any]:
        """Generate bar chart config.

        Args:
            columns: Column names
            rows: Result rows

        Returns:
            Bar chart config
        """
        if len(columns) < 2:
            return {}

        # Assume first column is category, rest are values
        return {
            "xAxis": columns[0],
            "yAxis": columns[1:],
            "orientation": "vertical" if len(rows) > 10 else "horizontal",
        }

    def _line_config(
        self, columns: List[str], rows: List[tuple]
    ) -> Dict[str, Any]:
        """Generate line chart config.

        Args:
            columns: Column names
            rows: Result rows

        Returns:
            Line chart config
        """
        if len(columns) < 2:
            return {}

        # Detect time/date column
        time_col = None
        for col in columns:
            if any(
                kw in col.lower()
                for kw in ["date", "datum", "time", "zeit", "month", "monat"]
            ):
                time_col = col
                break

        if not time_col:
            time_col = columns[0]

        value_cols = [c for c in columns if c != time_col]

        return {
            "xAxis": time_col,
            "yAxis": value_cols,
            "smooth": True,
        }

    def _pie_config(
        self, columns: List[str], rows: List[tuple]
    ) -> Dict[str, Any]:
        """Generate pie chart config.

        Args:
            columns: Column names
            rows: Result rows

        Returns:
            Pie chart config
        """
        if len(columns) < 2:
            return {}

        return {
            "labelColumn": columns[0],
            "valueColumn": columns[1],
            "showPercentage": True,
        }

    def _table_config(self, columns: List[str]) -> Dict[str, Any]:
        """Generate table config.

        Args:
            columns: Column names

        Returns:
            Table config
        """
        # Determine column types for formatting
        column_config = []
        for col in columns:
            col_type = "text"
            if any(
                kw in col.lower()
                for kw in ["amount", "betrag", "price", "preis", "sum", "summe"]
            ):
                col_type = "currency"
            elif any(kw in col.lower() for kw in ["date", "datum"]):
                col_type = "date"
            elif any(kw in col.lower() for kw in ["count", "anzahl", "total"]):
                col_type = "number"

            column_config.append({"name": col, "type": col_type})

        return {
            "columns": column_config,
            "sortable": True,
            "filterable": True,
        }
