# -*- coding: utf-8 -*-
"""
Backup Report Service - Ablage-System

Generates comprehensive backup reports for monitoring and compliance.

Features:
- Daily/weekly/monthly backup status reports
- Validation summary reports
- Storage usage reports
- Retention compliance reports
- Email notification integration

Related:
- Backup Metrics Service: ./backup_metrics_service.py
- Backup Validator: ../../Execution_Layer/Validators/backup_validator.py
- German Messages: ../core/german_messages.py
"""

import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog
from pydantic import BaseModel

try:
    from app.core.german_messages import BackupMessages
except ImportError:
    class BackupMessages:
        DAILY_REPORT = "Taeglicher Sicherungsbericht"
        WEEKLY_REPORT = "Woechentlicher Sicherungsbericht"
        MONTHLY_REPORT = "Monatlicher Sicherungsbericht"
        REPORT_GENERATED = "Sicherungsbericht erstellt: {filename}"

try:
    from app.services.backup_metrics_service import get_backup_metrics
    METRICS_AVAILABLE = True
except ImportError:
    METRICS_AVAILABLE = False
    get_backup_metrics = None

logger = structlog.get_logger(__name__)


class BackupReportData(BaseModel):
    """Data model for backup report."""

    report_type: str  # daily, weekly, monthly
    generated_at: datetime
    period_start: datetime
    period_end: datetime

    # Backup statistics
    total_backups: int = 0
    successful_backups: int = 0
    failed_backups: int = 0
    success_rate: float = 0.0

    # Validation statistics
    total_validations: int = 0
    passed_validations: int = 0
    failed_validations: int = 0
    validation_rate: float = 0.0

    # Restore test statistics
    restore_tests_run: int = 0
    restore_tests_passed: int = 0
    restore_tests_failed: int = 0

    # Storage statistics
    total_backup_size_gb: float = 0.0
    disk_usage_percent: float = 0.0
    disk_free_gb: float = 0.0
    oldest_backup_days: float = 0.0
    newest_backup_hours: float = 0.0

    # Remote sync statistics
    remote_syncs_attempted: int = 0
    remote_syncs_successful: int = 0
    remote_syncs_failed: int = 0

    # Encryption status
    encryption_enabled: bool = False

    # Issues and warnings
    issues: List[str] = []
    warnings: List[str] = []
    recommendations: List[str] = []


class BackupReportService:
    """Service for generating backup reports."""

    def __init__(
        self,
        backup_dir: Optional[Path] = None,
        report_dir: Optional[Path] = None,
    ):
        """
        Initialize backup report service.

        Args:
            backup_dir: Directory containing backups
            report_dir: Directory to save reports (defaults to backup_dir/reports)
        """
        self.backup_dir = Path(backup_dir or os.getenv("BACKUP_DIR", "/var/backups/ablage"))
        self.report_dir = Path(report_dir) if report_dir else self.backup_dir / "reports"
        self.report_dir.mkdir(parents=True, exist_ok=True)

        if METRICS_AVAILABLE and get_backup_metrics:
            self.metrics = get_backup_metrics()
        else:
            self.metrics = None

    def generate_daily_report(self) -> BackupReportData:
        """
        Generate daily backup report.

        Returns:
            BackupReportData with daily statistics
        """
        now = datetime.utcnow()
        period_start = now - timedelta(days=1)

        report = self._collect_report_data("daily", period_start, now)
        self._analyze_issues(report)

        # Save report
        filename = f"daily_report_{now.strftime('%Y%m%d')}.md"
        self._save_report(report, filename)

        logger.info(
            "daily_report_generated",
            filename=filename,
            success_rate=report.success_rate,
        )

        return report

    def generate_weekly_report(self) -> BackupReportData:
        """
        Generate weekly backup report.

        Returns:
            BackupReportData with weekly statistics
        """
        now = datetime.utcnow()
        period_start = now - timedelta(days=7)

        report = self._collect_report_data("weekly", period_start, now)
        self._analyze_issues(report)

        # Save report
        filename = f"weekly_report_{now.strftime('%Y%m%d')}.md"
        self._save_report(report, filename)

        logger.info(
            "weekly_report_generated",
            filename=filename,
            success_rate=report.success_rate,
        )

        return report

    def generate_monthly_report(self) -> BackupReportData:
        """
        Generate monthly backup report.

        Returns:
            BackupReportData with monthly statistics
        """
        now = datetime.utcnow()
        period_start = now - timedelta(days=30)

        report = self._collect_report_data("monthly", period_start, now)
        self._analyze_issues(report)

        # Save report
        filename = f"monthly_report_{now.strftime('%Y%m')}.md"
        self._save_report(report, filename)

        logger.info(
            "monthly_report_generated",
            filename=filename,
            success_rate=report.success_rate,
        )

        return report

    def _collect_report_data(
        self,
        report_type: str,
        period_start: datetime,
        period_end: datetime,
    ) -> BackupReportData:
        """
        Collect data for backup report.

        Args:
            report_type: Type of report (daily, weekly, monthly)
            period_start: Start of reporting period
            period_end: End of reporting period

        Returns:
            BackupReportData with collected statistics
        """
        report = BackupReportData(
            report_type=report_type,
            generated_at=datetime.utcnow(),
            period_start=period_start,
            period_end=period_end,
        )

        # Collect from metrics if available
        if self.metrics:
            try:
                metrics_data = self.metrics.get_summary()

                report.total_backups = (
                    metrics_data.get("success_count", 0) +
                    metrics_data.get("failure_count", 0)
                )
                report.successful_backups = metrics_data.get("success_count", 0)
                report.failed_backups = metrics_data.get("failure_count", 0)

                if report.total_backups > 0:
                    report.success_rate = round(
                        report.successful_backups / report.total_backups * 100, 1
                    )

                report.total_validations = (
                    metrics_data.get("validation_success_count", 0) +
                    metrics_data.get("validation_failure_count", 0)
                )
                report.passed_validations = metrics_data.get("validation_success_count", 0)
                report.failed_validations = metrics_data.get("validation_failure_count", 0)

                if report.total_validations > 0:
                    report.validation_rate = round(
                        report.passed_validations / report.total_validations * 100, 1
                    )

                report.encryption_enabled = metrics_data.get("encryption_enabled", False)

            except Exception as e:
                logger.warning("metrics_collection_error", error=str(e))

        # Collect from file system
        self._collect_storage_stats(report)
        self._collect_backup_file_stats(report, period_start, period_end)

        return report

    def _collect_storage_stats(self, report: BackupReportData) -> None:
        """Collect storage statistics from backup directory."""
        try:
            import shutil

            total, used, free = shutil.disk_usage(self.backup_dir)

            report.disk_free_gb = round(free / (1024**3), 2)
            report.disk_usage_percent = round((used / total) * 100, 1)

            # Calculate total backup size
            total_size = 0
            for subdir in ["postgres", "redis", "minio", "config"]:
                dir_path = self.backup_dir / subdir
                if dir_path.exists():
                    for f in dir_path.rglob("*"):
                        if f.is_file():
                            total_size += f.stat().st_size

            report.total_backup_size_gb = round(total_size / (1024**3), 2)

        except Exception as e:
            logger.warning("storage_stats_error", error=str(e))

    def _collect_backup_file_stats(
        self,
        report: BackupReportData,
        period_start: datetime,
        period_end: datetime,
    ) -> None:
        """Collect statistics from backup files."""
        try:
            backup_files: List[Path] = []

            for subdir in ["postgres", "redis", "minio", "config"]:
                dir_path = self.backup_dir / subdir
                if dir_path.exists():
                    for f in dir_path.glob("*"):
                        if f.is_file() and f.suffix in [".gz", ".gpg", ".rdb", ".tar"]:
                            backup_files.append(f)

            if not backup_files:
                return

            # Find oldest and newest
            now = datetime.now()
            oldest_mtime = min(f.stat().st_mtime for f in backup_files)
            newest_mtime = max(f.stat().st_mtime for f in backup_files)

            report.oldest_backup_days = round(
                (now - datetime.fromtimestamp(oldest_mtime)).days, 1
            )
            report.newest_backup_hours = round(
                (now - datetime.fromtimestamp(newest_mtime)).total_seconds() / 3600, 1
            )

        except Exception as e:
            logger.warning("backup_file_stats_error", error=str(e))

    def _analyze_issues(self, report: BackupReportData) -> None:
        """Analyze report data and identify issues/recommendations."""
        # Check success rate
        if report.success_rate < 100:
            report.issues.append(
                f"Backup-Erfolgsrate unter 100% ({report.success_rate}%)"
            )

        if report.success_rate < 90:
            report.recommendations.append(
                "Dringend: Backup-Fehler untersuchen und beheben"
            )

        # Check validation rate
        if report.validation_rate < 100 and report.total_validations > 0:
            report.issues.append(
                f"Validierungs-Erfolgsrate unter 100% ({report.validation_rate}%)"
            )

        # Check backup age
        if report.newest_backup_hours > 26:
            report.issues.append(
                f"Letzte Sicherung ist {report.newest_backup_hours:.1f} Stunden alt"
            )
            report.recommendations.append(
                "Backup-Zeitplan ueberpruefen"
            )

        # Check disk space
        if report.disk_usage_percent > 90:
            report.issues.append(
                f"Speicherplatz kritisch: {report.disk_usage_percent}% belegt"
            )
            report.recommendations.append(
                "Dringend: Speicherplatz erweitern oder alte Backups loeschen"
            )
        elif report.disk_usage_percent > 80:
            report.warnings.append(
                f"Speicherplatz wird knapp: {report.disk_usage_percent}% belegt"
            )

        # Check encryption
        if not report.encryption_enabled:
            report.warnings.append(
                "Backup-Verschluesselung ist nicht aktiviert"
            )
            report.recommendations.append(
                "GPG-Verschluesselung fuer Backups aktivieren"
            )

        # Check for no backups
        if report.total_backups == 0:
            report.issues.append(
                "Keine Backups im Berichtszeitraum"
            )
            report.recommendations.append(
                "Backup-Service und Zeitplan ueberpruefen"
            )

    def _save_report(self, report: BackupReportData, filename: str) -> Path:
        """
        Save report to file.

        Args:
            report: Report data to save
            filename: Name of the report file

        Returns:
            Path to saved report file
        """
        report_path = self.report_dir / filename

        content = self._format_report_markdown(report)
        report_path.write_text(content, encoding="utf-8")

        logger.info(
            "report_saved",
            path=str(report_path),
            report_type=report.report_type,
        )

        return report_path

    def _format_report_markdown(self, report: BackupReportData) -> str:
        """Format report data as markdown."""
        title_map = {
            "daily": BackupMessages.DAILY_REPORT,
            "weekly": BackupMessages.WEEKLY_REPORT,
            "monthly": BackupMessages.MONTHLY_REPORT,
        }
        title = title_map.get(report.report_type, "Sicherungsbericht")

        lines = [
            f"# {title}",
            "",
            f"**Erstellt:** {report.generated_at.strftime('%d.%m.%Y %H:%M:%S')} UTC",
            f"**Zeitraum:** {report.period_start.strftime('%d.%m.%Y')} - {report.period_end.strftime('%d.%m.%Y')}",
            "",
            "---",
            "",
            "## Zusammenfassung",
            "",
        ]

        # Status indicator
        if report.issues:
            lines.append("**Status:** [!] PROBLEME ERKANNT")
        elif report.warnings:
            lines.append("**Status:** [~] WARNUNGEN")
        else:
            lines.append("**Status:** [OK] ALLES IN ORDNUNG")

        lines.extend([
            "",
            "---",
            "",
            "## Backup-Statistiken",
            "",
            f"| Metrik | Wert |",
            f"|--------|------|",
            f"| Gesamt Backups | {report.total_backups} |",
            f"| Erfolgreiche Backups | {report.successful_backups} |",
            f"| Fehlgeschlagene Backups | {report.failed_backups} |",
            f"| Erfolgsrate | {report.success_rate}% |",
            "",
            "## Validierungs-Statistiken",
            "",
            f"| Metrik | Wert |",
            f"|--------|------|",
            f"| Gesamt Validierungen | {report.total_validations} |",
            f"| Erfolgreich | {report.passed_validations} |",
            f"| Fehlgeschlagen | {report.failed_validations} |",
            f"| Erfolgsrate | {report.validation_rate}% |",
            "",
            "## Speicher-Statistiken",
            "",
            f"| Metrik | Wert |",
            f"|--------|------|",
            f"| Gesamt Backup-Groesse | {report.total_backup_size_gb} GB |",
            f"| Speicher belegt | {report.disk_usage_percent}% |",
            f"| Speicher frei | {report.disk_free_gb} GB |",
            f"| Aeltestes Backup | {report.oldest_backup_days} Tage |",
            f"| Neuestes Backup | {report.newest_backup_hours} Stunden |",
            "",
            "## Konfiguration",
            "",
            f"| Einstellung | Status |",
            f"|-------------|--------|",
            f"| Verschluesselung | {'Aktiviert' if report.encryption_enabled else 'Deaktiviert'} |",
            "",
        ])

        # Issues section
        if report.issues:
            lines.extend([
                "## [!] Probleme",
                "",
            ])
            for issue in report.issues:
                lines.append(f"- {issue}")
            lines.append("")

        # Warnings section
        if report.warnings:
            lines.extend([
                "## [~] Warnungen",
                "",
            ])
            for warning in report.warnings:
                lines.append(f"- {warning}")
            lines.append("")

        # Recommendations section
        if report.recommendations:
            lines.extend([
                "## Empfehlungen",
                "",
            ])
            for rec in report.recommendations:
                lines.append(f"- {rec}")
            lines.append("")

        lines.extend([
            "---",
            "",
            f"*Bericht generiert von Ablage-System Backup Report Service*",
        ])

        return "\n".join(lines)

    def get_latest_report(self, report_type: str = "daily") -> Optional[BackupReportData]:
        """
        Get the most recent report of specified type.

        Args:
            report_type: Type of report (daily, weekly, monthly)

        Returns:
            BackupReportData or None if no report found
        """
        pattern = f"{report_type}_report_*.md"
        reports = sorted(self.report_dir.glob(pattern), reverse=True)

        if not reports:
            return None

        # Parse the most recent report
        # Note: This is a simplified implementation - in production,
        # you might want to store reports as JSON for easier parsing
        return None  # Would need to parse markdown back to data


# Singleton instance
_report_service: Optional[BackupReportService] = None


def get_backup_report_service() -> BackupReportService:
    """Get singleton backup report service instance."""
    global _report_service
    if _report_service is None:
        _report_service = BackupReportService()
    return _report_service


async def main():
    """Main entry point for generating reports."""
    import sys

    report_type = sys.argv[1] if len(sys.argv) > 1 else "daily"

    service = BackupReportService()

    if report_type == "daily":
        report = service.generate_daily_report()
    elif report_type == "weekly":
        report = service.generate_weekly_report()
    elif report_type == "monthly":
        report = service.generate_monthly_report()
    else:
        logger.error("unknown_report_type", report_type=report_type)
        sys.stderr.write(f"Unbekannter Berichtstyp: {report_type}\n")
        sys.stderr.write("Verwendung: python backup_report_service.py [daily|weekly|monthly]\n")
        sys.exit(1)

    logger.info(
        "backup_report_generated",
        report_type=report.report_type,
        period_start=report.period_start.isoformat(),
        period_end=report.period_end.isoformat(),
        success_rate=report.success_rate,
        issues_count=len(report.issues),
        warnings_count=len(report.warnings)
    )
    # CLI-Ausgabe fuer interaktive Nutzung
    sys.stdout.write(f"\nBericht generiert:\n")
    sys.stdout.write(f"  Typ: {report.report_type}\n")
    sys.stdout.write(f"  Zeitraum: {report.period_start.date()} - {report.period_end.date()}\n")
    sys.stdout.write(f"  Erfolgsrate: {report.success_rate}%\n")
    sys.stdout.write(f"  Probleme: {len(report.issues)}\n")
    sys.stdout.write(f"  Warnungen: {len(report.warnings)}\n")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
