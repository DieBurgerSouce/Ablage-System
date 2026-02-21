# -*- coding: utf-8 -*-
"""
Partition Service fuer Ablage-System.

Verwaltung der Tabellen-Partitionierung:
- Automatische Partition-Erstellung fuer zukuenftige Zeitraeume
- Statistik-Abfragen fuer Monitoring und Dashboards
- Archivierung alter Partitionen (>2 Jahre)
- Row-Count-Aktualisierung fuer Kapazitaetsplanung

Feinpoliert und durchdacht - Enterprise-grade Partition Management.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional
from uuid import UUID

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_partitioning import (
    PARTITIONED_TABLES_CONFIG,
    PartitionInterval,
)

logger = structlog.get_logger(__name__)


class PartitionService:
    """Verwaltung der Tabellen-Partitionierung.

    Stellt sicher, dass Partitionen fuer zukuenftige Zeitraeume existieren,
    sammelt Statistiken und archiviert alte Partitionen.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def ensure_partitions_exist(
        self, months_ahead: int = 3
    ) -> List[str]:
        """Erstellt fehlende Partitionen fuer die naechsten N Monate.

        Prueft fuer jede konfigurierte partitionierte Tabelle, ob
        Partitionen fuer die naechsten months_ahead Monate existieren
        und erstellt fehlende automatisch.

        Args:
            months_ahead: Anzahl Monate im Voraus (Standard: 3)

        Returns:
            Liste der neu erstellten Partitionsnamen
        """
        created_partitions: List[str] = []

        for table_name, config in PARTITIONED_TABLES_CONFIG.items():
            interval = config["interval"]

            try:
                if interval == PartitionInterval.QUARTERLY:
                    result = await self._ensure_quarterly_partitions(
                        table_name, months_ahead
                    )
                elif interval == PartitionInterval.MONTHLY:
                    result = await self._ensure_monthly_partitions(
                        table_name, months_ahead
                    )
                else:
                    logger.warning(
                        "partition_unknown_interval",
                        table=table_name,
                        interval=str(interval),
                    )
                    continue

                created_partitions.extend(result)
            except Exception as exc:
                logger.error(
                    "partition_ensure_failed",
                    table=table_name,
                    error=str(exc),
                )
                # Fehler protokollieren, aber andere Tabellen weiter verarbeiten

        if created_partitions:
            logger.info(
                "partitions_created",
                count=len(created_partitions),
                partitions=created_partitions,
            )

        return created_partitions

    async def _ensure_quarterly_partitions(
        self, table_name: str, months_ahead: int
    ) -> List[str]:
        """Erstellt fehlende Quartals-Partitionen."""
        created: List[str] = []

        result = await self._session.execute(
            text("""
                DO $$
                DECLARE
                    v_start DATE;
                    v_end DATE;
                    v_quarter_start DATE;
                    v_name TEXT;
                BEGIN
                    v_quarter_start := date_trunc('quarter', NOW());

                    WHILE v_quarter_start <=
                          date_trunc('quarter', NOW() + make_interval(months => :months))
                    LOOP
                        v_start := v_quarter_start;
                        v_end := v_quarter_start + INTERVAL '3 months';

                        PERFORM create_time_partition(
                            :table_name, v_start, v_end
                        );

                        v_quarter_start := v_quarter_start + INTERVAL '3 months';
                    END LOOP;
                END $$
            """),
            {"table_name": table_name, "months": months_ahead},
        )

        # Abfrage der neu erstellten Partitionen (letzte Minute)
        rows = await self._session.execute(
            text("""
                SELECT partition_name
                FROM partition_management
                WHERE table_name = :table_name
                  AND created_at >= NOW() - INTERVAL '1 minute'
                ORDER BY range_start
            """),
            {"table_name": table_name},
        )
        for row in rows:
            created.append(row[0])

        return created

    async def _ensure_monthly_partitions(
        self, table_name: str, months_ahead: int
    ) -> List[str]:
        """Erstellt fehlende Monats-Partitionen."""
        created: List[str] = []

        await self._session.execute(
            text("""
                DO $$
                DECLARE
                    v_start DATE;
                    v_end DATE;
                    v_month_start DATE;
                BEGIN
                    v_month_start := date_trunc('month', NOW());

                    WHILE v_month_start <=
                          date_trunc('month', NOW() + make_interval(months => :months))
                    LOOP
                        v_start := v_month_start;
                        v_end := v_month_start + INTERVAL '1 month';

                        PERFORM create_time_partition(
                            :table_name, v_start, v_end
                        );

                        v_month_start := v_month_start + INTERVAL '1 month';
                    END LOOP;
                END $$
            """),
            {"table_name": table_name, "months": months_ahead},
        )

        rows = await self._session.execute(
            text("""
                SELECT partition_name
                FROM partition_management
                WHERE table_name = :table_name
                  AND created_at >= NOW() - INTERVAL '1 minute'
                ORDER BY range_start
            """),
            {"table_name": table_name},
        )
        for row in rows:
            created.append(row[0])

        return created

    async def get_partition_stats(self) -> List[Dict[str, object]]:
        """Gibt Statistiken ueber alle Partitionen zurueck.

        Returns:
            Liste mit Statistiken pro partitionierter Tabelle:
            - table_name: Name der Tabelle
            - total_partitions: Gesamtzahl Partitionen
            - active_partitions: Aktive (nicht-archivierte) Partitionen
            - archived_partitions: Archivierte Partitionen
            - total_rows: Gesamte Zeilenanzahl (geschaetzt)
            - total_size_bytes: Gesamter Speicherverbrauch
            - oldest_partition: Aelteste aktive Partition
            - newest_partition: Neueste Partition
        """
        result = await self._session.execute(
            text("""
                SELECT
                    table_name,
                    COUNT(*) AS total_partitions,
                    COUNT(*) FILTER (WHERE is_archived = FALSE) AS active_partitions,
                    COUNT(*) FILTER (WHERE is_archived = TRUE) AS archived_partitions,
                    COALESCE(SUM(row_count) FILTER (WHERE is_archived = FALSE), 0)
                        AS total_rows,
                    COALESCE(SUM(size_bytes) FILTER (WHERE is_archived = FALSE), 0)
                        AS total_size_bytes,
                    MIN(range_start) FILTER (WHERE is_archived = FALSE)
                        AS oldest_partition,
                    MAX(range_end) FILTER (WHERE is_archived = FALSE)
                        AS newest_partition
                FROM partition_management
                GROUP BY table_name
                ORDER BY table_name
            """)
        )

        stats: List[Dict[str, object]] = []
        for row in result:
            stats.append({
                "table_name": row[0],
                "total_partitions": row[1],
                "active_partitions": row[2],
                "archived_partitions": row[3],
                "total_rows": row[4],
                "total_size_bytes": row[5],
                "oldest_partition": row[6].isoformat() if row[6] else None,
                "newest_partition": row[7].isoformat() if row[7] else None,
            })

        return stats

    async def archive_old_partitions(
        self, older_than_months: int = 24
    ) -> int:
        """Archiviert alte Partitionen (>2 Jahre).

        Detached Partitionen, deren Zeitbereich aelter als
        older_than_months ist. Die Daten bleiben erhalten,
        werden aber aus dem Abfragepfad entfernt.

        Args:
            older_than_months: Alter in Monaten (Standard: 24)

        Returns:
            Anzahl archivierter Partitionen
        """
        total_archived = 0
        interval_str = f"{older_than_months} months"

        for table_name in PARTITIONED_TABLES_CONFIG:
            try:
                result = await self._session.execute(
                    text("""
                        SELECT archive_old_partitions(
                            :table_name,
                            :interval::interval
                        )
                    """),
                    {
                        "table_name": table_name,
                        "interval": interval_str,
                    },
                )
                count = result.scalar()
                if count and count > 0:
                    total_archived += count
                    logger.info(
                        "partitions_archived",
                        table=table_name,
                        count=count,
                        older_than=interval_str,
                    )
            except Exception as exc:
                logger.error(
                    "partition_archive_failed",
                    table=table_name,
                    error=str(exc),
                )

        return total_archived

    async def get_partition_row_counts(
        self, table_name: str
    ) -> List[Dict[str, object]]:
        """Gibt Row-Counts pro Partition fuer eine Tabelle zurueck.

        Args:
            table_name: Name der partitionierten Tabelle

        Returns:
            Liste mit Partition-Details:
            - partition_name: Name der Partition
            - range_start: Start des Zeitbereichs
            - range_end: Ende des Zeitbereichs
            - row_count: Zeilenanzahl
            - size_bytes: Speicherverbrauch in Bytes
            - is_archived: Ob archiviert
        """
        # Validierung: Nur konfigurierte Tabellen erlauben (SQL-Injection-Schutz)
        if table_name not in PARTITIONED_TABLES_CONFIG:
            logger.warning(
                "partition_invalid_table",
                table_name=table_name,
            )
            return []

        result = await self._session.execute(
            text("""
                SELECT
                    partition_name,
                    range_start,
                    range_end,
                    row_count,
                    size_bytes,
                    is_archived
                FROM partition_management
                WHERE table_name = :table_name
                ORDER BY range_start DESC
            """),
            {"table_name": table_name},
        )

        partitions: List[Dict[str, object]] = []
        for row in result:
            partitions.append({
                "partition_name": row[0],
                "range_start": row[1].isoformat() if row[1] else None,
                "range_end": row[2].isoformat() if row[2] else None,
                "row_count": row[3],
                "size_bytes": row[4],
                "is_archived": row[5],
            })

        return partitions

    async def update_row_counts(
        self, table_name: Optional[str] = None
    ) -> int:
        """Aktualisiert Row-Counts fuer alle aktiven Partitionen.

        Ruft die PostgreSQL-Funktion update_partition_row_counts() auf,
        die pro Partition einen COUNT(*) ausfuehrt.

        Args:
            table_name: Optional - nur fuer diese Tabelle aktualisieren

        Returns:
            Anzahl aktualisierter Partitionen
        """
        try:
            result = await self._session.execute(
                text("SELECT update_partition_row_counts(:table_name)"),
                {"table_name": table_name},
            )
            updated = result.scalar()
            count = updated if updated else 0

            logger.info(
                "partition_row_counts_updated",
                count=count,
                table=table_name or "alle",
            )

            return count
        except Exception as exc:
            logger.error(
                "partition_row_count_update_failed",
                table=table_name or "alle",
                error=str(exc),
            )
            return 0

    async def get_health_status(self) -> Dict[str, object]:
        """Prueft den Gesundheitszustand der Partitionierung.

        Returns:
            Dict mit Gesundheitsinformationen:
            - status: "healthy" | "warning" | "critical"
            - message: Beschreibung des Status (Deutsch)
            - tables: Tabellen-spezifische Details
            - missing_future_partitions: Tabellen ohne zukuenftige Partitionen
        """
        issues: List[str] = []
        table_details: Dict[str, Dict[str, object]] = {}

        for table_name in PARTITIONED_TABLES_CONFIG:
            result = await self._session.execute(
                text("""
                    SELECT
                        COUNT(*) FILTER (WHERE is_archived = FALSE) AS active,
                        MAX(range_end) FILTER (WHERE is_archived = FALSE) AS max_end,
                        COUNT(*) FILTER (
                            WHERE is_archived = FALSE
                            AND range_end > NOW()
                        ) AS future_count
                    FROM partition_management
                    WHERE table_name = :table_name
                """),
                {"table_name": table_name},
            )
            row = result.one_or_none()

            if row is None or row[0] == 0:
                issues.append(
                    f"Keine aktiven Partitionen fuer {table_name}"
                )
                table_details[table_name] = {
                    "active_partitions": 0,
                    "future_partitions": 0,
                    "status": "critical",
                }
            else:
                future_count = row[2] or 0
                detail: Dict[str, object] = {
                    "active_partitions": row[0],
                    "max_range_end": row[1].isoformat() if row[1] else None,
                    "future_partitions": future_count,
                    "status": "healthy",
                }

                if future_count == 0:
                    issues.append(
                        f"Keine zukuenftigen Partitionen fuer {table_name}"
                    )
                    detail["status"] = "critical"
                elif future_count <= 1:
                    issues.append(
                        f"Nur {future_count} zukuenftige Partition fuer {table_name}"
                    )
                    detail["status"] = "warning"

                table_details[table_name] = detail

        if not issues:
            status = "healthy"
            message = "Alle Partitionen sind aktuell und ausreichend vorhanden"
        elif any("Keine" in issue for issue in issues):
            status = "critical"
            message = (
                "Kritisch: Fehlende Partitionen gefunden. "
                "Bitte partition.ensure_partitions Task ausfuehren."
            )
        else:
            status = "warning"
            message = (
                "Warnung: Wenige zukuenftige Partitionen vorhanden. "
                "Naechster Maintenance-Lauf sollte diese erstellen."
            )

        return {
            "status": status,
            "message": message,
            "tables": table_details,
            "issues": issues,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
