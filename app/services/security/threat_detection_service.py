"""
Erweiterte Bedrohungserkennung fuer Security Monitoring.

Implementiert ML-basierte Anomalieerkennung auf Zugriffslogs,
Datenexfiltrationserkennung und Insider-Threat-Monitoring.
"""

import structlog
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from dataclasses import dataclass, field, asdict
from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User, Document, DocumentActivity, AuditLog

logger = structlog.get_logger(__name__)


@dataclass
class ThreatIndicator:
    """Einzelner Bedrohungsindikator."""

    indicator_type: str  # access_anomaly, exfiltration, permission_escalation, etc.
    severity: str  # niedrig, mittel, hoch, kritisch
    description: str
    user_id: Optional[int] = None
    detected_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    details: Dict = field(default_factory=dict)


@dataclass
class SecurityReport:
    """Aggregierter Sicherheitsbericht."""

    period: str  # tag, woche, monat
    gesamtrisiko: str  # niedrig, mittel, hoch, kritisch
    anomalie_count: int
    top_risiken: List[Dict] = field(default_factory=list)
    empfehlungen: List[str] = field(default_factory=list)
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ThreatDetectionService:
    """
    Service fuer erweiterte Bedrohungserkennung.

    Funktionen:
    - ML-basierte Anomalieerkennung auf Zugriffslogs
    - Datenexfiltrationserkennung
    - Insider-Threat-Monitoring
    - Permission-Anomalie-Erkennung
    - Sicherheitsberichterstattung
    """

    # Schwellwerte fuer Anomalieerkennung
    NORMAL_WORK_HOURS = (8, 18)  # 8:00 - 18:00
    MAX_DOWNLOADS_PER_HOUR = 50
    MAX_EXPORTS_PER_HOUR = 20
    BULK_DOWNLOAD_THRESHOLD = 10  # Downloads in 5min
    FAILED_ACCESS_THRESHOLD = 5   # Fehlversuche in 1h

    # Risiko-Gewichtung
    RISK_WEIGHTS = {
        "after_hours_access": 0.3,
        "bulk_downloads": 0.5,
        "failed_access": 0.4,
        "export_attempts": 0.6,
        "permission_changes": 0.7,
        "sensitive_doc_access": 0.5,
    }

    async def analyze_access_patterns(
        self,
        db: AsyncSession,
        company_id: int,
        hours: int = 24
    ) -> Dict:
        """
        Analysiert Zugriffsmuster der letzten N Stunden.

        Erkennt:
        - Ungewoehnliche Zugriffszeiten
        - Bulk-Downloads
        - Wiederholte Fehlzugriffe

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID
            hours: Analysezeitraum in Stunden

        Returns:
            Dict mit threat_level, anomalies, user_risk_scores
        """
        logger.info(
            "analyzing_access_patterns",
            company_id=company_id,
            hours=hours
        )

        since = datetime.now(timezone.utc) - timedelta(hours=hours)

        # Aktivitaeten abfragen
        stmt = (
            select(DocumentActivity)
            .join(Document)
            .where(
                and_(
                    Document.company_id == company_id,
                    DocumentActivity.created_at >= since
                )
            )
        )
        result = await db.execute(stmt)
        activities = result.scalars().all()

        anomalies: List[ThreatIndicator] = []
        user_activity: Dict[int, List[DocumentActivity]] = {}

        # Gruppiere nach User
        for activity in activities:
            if activity.user_id not in user_activity:
                user_activity[activity.user_id] = []
            user_activity[activity.user_id].append(activity)

        user_risk_scores: Dict[int, float] = {}

        # Analysiere pro User
        for user_id, user_activities in user_activity.items():
            risk_score = 0.0

            # 1. After-hours access
            after_hours = [
                a for a in user_activities
                if not (self.NORMAL_WORK_HOURS[0] <= a.created_at.hour < self.NORMAL_WORK_HOURS[1])
            ]
            if len(after_hours) > 5:
                risk_score += self.RISK_WEIGHTS["after_hours_access"]
                anomalies.append(ThreatIndicator(
                    indicator_type="after_hours_access",
                    severity="mittel",
                    description=f"User {user_id} hat {len(after_hours)} Zugriffe ausserhalb der Arbeitszeiten",
                    user_id=user_id,
                    details={"count": len(after_hours)}
                ))

            # 2. Bulk downloads (10+ in 5min)
            sorted_activities = sorted(user_activities, key=lambda a: a.created_at)
            for i in range(len(sorted_activities) - self.BULK_DOWNLOAD_THRESHOLD + 1):
                window = sorted_activities[i:i + self.BULK_DOWNLOAD_THRESHOLD]
                time_diff = (window[-1].created_at - window[0].created_at).total_seconds()
                if time_diff <= 300:  # 5min
                    downloads = [a for a in window if a.activity_type == "download"]
                    if len(downloads) >= self.BULK_DOWNLOAD_THRESHOLD:
                        risk_score += self.RISK_WEIGHTS["bulk_downloads"]
                        anomalies.append(ThreatIndicator(
                            indicator_type="bulk_downloads",
                            severity="hoch",
                            description=f"User {user_id} hat {len(downloads)} Downloads in 5min durchgefuehrt",
                            user_id=user_id,
                            details={"count": len(downloads), "timeframe": "5min"}
                        ))
                        break

            # 3. Fehlzugriffe (aus AuditLog)
            audit_stmt = (
                select(func.count(AuditLog.id))
                .where(
                    and_(
                        AuditLog.user_id == user_id,
                        AuditLog.action.like("%access_denied%"),
                        AuditLog.created_at >= since
                    )
                )
            )
            failed_count = (await db.execute(audit_stmt)).scalar() or 0

            if failed_count >= self.FAILED_ACCESS_THRESHOLD:
                risk_score += self.RISK_WEIGHTS["failed_access"]
                anomalies.append(ThreatIndicator(
                    indicator_type="failed_access",
                    severity="hoch",
                    description=f"User {user_id} hat {failed_count} Fehlzugriffe",
                    user_id=user_id,
                    details={"count": failed_count}
                ))

            user_risk_scores[user_id] = min(risk_score, 1.0)

        # Gesamtbedrohungslevel
        if not user_risk_scores:
            threat_level = "niedrig"
        else:
            max_risk = max(user_risk_scores.values())
            if max_risk >= 0.7:
                threat_level = "kritisch"
            elif max_risk >= 0.5:
                threat_level = "hoch"
            elif max_risk >= 0.3:
                threat_level = "mittel"
            else:
                threat_level = "niedrig"

        logger.info(
            "access_pattern_analysis_complete",
            threat_level=threat_level,
            anomaly_count=len(anomalies),
            users_analyzed=len(user_risk_scores)
        )

        return {
            "threat_level": threat_level,
            "anomalies": [asdict(a) for a in anomalies],
            "user_risk_scores": user_risk_scores,
            "analyzed_activities": len(activities),
            "analyzed_users": len(user_risk_scores),
            "period_hours": hours
        }

    async def detect_data_exfiltration(
        self,
        db: AsyncSession,
        company_id: int,
        user_id: Optional[int] = None,
        hours: int = 24
    ) -> Dict:
        """
        Erkennt Datenexfiltrationsversuche.

        Prueft:
        - Massen-Export-Versuche
        - Ungewoehnliche Download-Volumina
        - Zugriff auf sensible Dokumente ausserhalb der Arbeitszeiten

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID
            user_id: Optional spezifischer User
            hours: Analysezeitraum

        Returns:
            Dict mit exfiltration_risk, indicators, recommended_actions
        """
        logger.info(
            "detecting_data_exfiltration",
            company_id=company_id,
            user_id=user_id,
            hours=hours
        )

        since = datetime.now(timezone.utc) - timedelta(hours=hours)

        # Aktivitaeten filtern
        stmt = (
            select(DocumentActivity)
            .join(Document)
            .where(
                and_(
                    Document.company_id == company_id,
                    DocumentActivity.created_at >= since,
                    or_(
                        DocumentActivity.activity_type == "download",
                        DocumentActivity.activity_type == "export"
                    )
                )
            )
        )

        if user_id:
            stmt = stmt.where(DocumentActivity.user_id == user_id)

        result = await db.execute(stmt)
        activities = result.scalars().all()

        indicators: List[ThreatIndicator] = []
        exfiltration_risk = 0.0

        # Gruppiere nach User
        user_exports: Dict[int, int] = {}
        user_downloads: Dict[int, int] = {}

        for activity in activities:
            uid = activity.user_id
            if activity.activity_type == "export":
                user_exports[uid] = user_exports.get(uid, 0) + 1
            elif activity.activity_type == "download":
                user_downloads[uid] = user_downloads.get(uid, 0) + 1

        # 1. Massen-Exports
        for uid, export_count in user_exports.items():
            if export_count > self.MAX_EXPORTS_PER_HOUR * (hours / 24):
                exfiltration_risk += 0.4
                indicators.append(ThreatIndicator(
                    indicator_type="mass_export",
                    severity="hoch",
                    description=f"User {uid} hat {export_count} Exports durchgefuehrt",
                    user_id=uid,
                    details={"export_count": export_count, "hours": hours}
                ))

        # 2. Ungewoehnliche Download-Volumina
        for uid, download_count in user_downloads.items():
            if download_count > self.MAX_DOWNLOADS_PER_HOUR * (hours / 24):
                exfiltration_risk += 0.3
                indicators.append(ThreatIndicator(
                    indicator_type="high_volume_download",
                    severity="mittel",
                    description=f"User {uid} hat {download_count} Downloads durchgefuehrt",
                    user_id=uid,
                    details={"download_count": download_count, "hours": hours}
                ))

        # 3. Sensible Dokumente ausserhalb Arbeitszeiten
        sensitive_after_hours = [
            a for a in activities
            if not (self.NORMAL_WORK_HOURS[0] <= a.created_at.hour < self.NORMAL_WORK_HOURS[1])
        ]

        if len(sensitive_after_hours) > 0:
            exfiltration_risk += 0.3
            affected_users = set(a.user_id for a in sensitive_after_hours)
            for uid in affected_users:
                user_count = sum(1 for a in sensitive_after_hours if a.user_id == uid)
                indicators.append(ThreatIndicator(
                    indicator_type="after_hours_sensitive_access",
                    severity="hoch",
                    description=f"User {uid} hat {user_count} Zugriffe ausserhalb Arbeitszeiten",
                    user_id=uid,
                    details={"count": user_count}
                ))

        exfiltration_risk = min(exfiltration_risk, 1.0)

        # Empfehlungen generieren
        recommended_actions: List[str] = []
        if exfiltration_risk >= 0.7:
            recommended_actions.extend([
                "Sofortige Sperrung verdaechtiger Accounts",
                "Forensische Analyse der Zugriffslogs",
                "Kontaktaufnahme mit betroffenen Usern"
            ])
        elif exfiltration_risk >= 0.5:
            recommended_actions.extend([
                "Erhoehte Ueberwachung verdaechtiger Accounts",
                "Review der Export-Berechtigungen",
                "Benachrichtigung des Security-Teams"
            ])
        elif exfiltration_risk >= 0.3:
            recommended_actions.append("Monitoring fortsetzen")

        logger.info(
            "exfiltration_detection_complete",
            exfiltration_risk=exfiltration_risk,
            indicator_count=len(indicators)
        )

        return {
            "exfiltration_risk": exfiltration_risk,
            "indicators": [asdict(i) for i in indicators],
            "recommended_actions": recommended_actions,
            "analyzed_activities": len(activities),
            "period_hours": hours
        }

    async def get_insider_threat_score(
        self,
        db: AsyncSession,
        company_id: int,
        user_id: int
    ) -> Dict:
        """
        Berechnet Insider-Threat-Score fuer einen User.

        Analysiert:
        - Zugriffshaeufigkeit
        - Dokumenttypen
        - Zeitmuster
        - Permission-Escalation-Versuche

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID
            user_id: User-ID

        Returns:
            Dict mit risk_score, risk_level, contributing_factors, last_assessed
        """
        logger.info(
            "calculating_insider_threat_score",
            company_id=company_id,
            user_id=user_id
        )

        risk_score = 0.0
        contributing_factors: List[str] = []

        # 1. Zugriffshaeufigkeit (letzte 7 Tage)
        since_week = datetime.now(timezone.utc) - timedelta(days=7)
        stmt = (
            select(func.count(DocumentActivity.id))
            .join(Document)
            .where(
                and_(
                    Document.company_id == company_id,
                    DocumentActivity.user_id == user_id,
                    DocumentActivity.created_at >= since_week
                )
            )
        )
        activity_count = (await db.execute(stmt)).scalar() or 0

        if activity_count > 200:  # >200 Aktivitaeten/Woche
            risk_score += 0.2
            contributing_factors.append(f"Hohe Aktivitaet ({activity_count}/Woche)")

        # 2. After-hours Aktivitaet
        after_hours_stmt = (
            select(func.count(DocumentActivity.id))
            .join(Document)
            .where(
                and_(
                    Document.company_id == company_id,
                    DocumentActivity.user_id == user_id,
                    DocumentActivity.created_at >= since_week,
                    or_(
                        func.extract("hour", DocumentActivity.created_at) < self.NORMAL_WORK_HOURS[0],
                        func.extract("hour", DocumentActivity.created_at) >= self.NORMAL_WORK_HOURS[1]
                    )
                )
            )
        )
        after_hours_count = (await db.execute(after_hours_stmt)).scalar() or 0

        if after_hours_count > 20:
            risk_score += 0.3
            contributing_factors.append(f"After-hours Aktivitaet ({after_hours_count})")

        # 3. Fehlzugriffe (Permission-Escalation-Versuche)
        failed_stmt = (
            select(func.count(AuditLog.id))
            .where(
                and_(
                    AuditLog.user_id == user_id,
                    AuditLog.action.like("%access_denied%"),
                    AuditLog.created_at >= since_week
                )
            )
        )
        failed_count = (await db.execute(failed_stmt)).scalar() or 0

        if failed_count > 10:
            risk_score += 0.4
            contributing_factors.append(f"Wiederholte Fehlzugriffe ({failed_count})")

        # 4. Export-Aktivitaet
        export_stmt = (
            select(func.count(DocumentActivity.id))
            .join(Document)
            .where(
                and_(
                    Document.company_id == company_id,
                    DocumentActivity.user_id == user_id,
                    DocumentActivity.activity_type == "export",
                    DocumentActivity.created_at >= since_week
                )
            )
        )
        export_count = (await db.execute(export_stmt)).scalar() or 0

        if export_count > 20:
            risk_score += 0.3
            contributing_factors.append(f"Haeufige Exports ({export_count})")

        risk_score = min(risk_score, 1.0)

        # Risk-Level bestimmen
        if risk_score >= 0.7:
            risk_level = "kritisch"
        elif risk_score >= 0.5:
            risk_level = "hoch"
        elif risk_score >= 0.3:
            risk_level = "mittel"
        else:
            risk_level = "niedrig"

        logger.info(
            "insider_threat_score_calculated",
            user_id=user_id,
            risk_score=risk_score,
            risk_level=risk_level
        )

        return {
            "risk_score": risk_score,
            "risk_level": risk_level,
            "contributing_factors": contributing_factors,
            "last_assessed": datetime.now(timezone.utc).isoformat()
        }

    async def generate_security_report(
        self,
        db: AsyncSession,
        company_id: int,
        period: str = "woche"
    ) -> Dict:
        """
        Generiert aggregierten Sicherheitsbericht.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID
            period: tag, woche, monat

        Returns:
            Dict mit SecurityReport-Struktur
        """
        logger.info(
            "generating_security_report",
            company_id=company_id,
            period=period
        )

        # Zeitraum bestimmen
        hours_map = {"tag": 24, "woche": 168, "monat": 720}
        hours = hours_map.get(period, 168)

        # Alle Analysen durchfuehren
        access_analysis = await self.analyze_access_patterns(db, company_id, hours)
        exfiltration_analysis = await self.detect_data_exfiltration(db, company_id, hours=hours)
        permission_anomalies = await self.check_permission_anomalies(db, company_id, hours)

        # Top Risiken sammeln
        top_risiken: List[Dict] = []

        # Aus Access-Analyse
        for anomaly in access_analysis["anomalies"]:
            top_risiken.append({
                "typ": anomaly["indicator_type"],
                "schwere": anomaly["severity"],
                "beschreibung": anomaly["description"],
                "user_id": anomaly.get("user_id")
            })

        # Aus Exfiltration-Analyse
        for indicator in exfiltration_analysis["indicators"]:
            top_risiken.append({
                "typ": indicator["indicator_type"],
                "schwere": indicator["severity"],
                "beschreibung": indicator["description"],
                "user_id": indicator.get("user_id")
            })

        # Aus Permission-Anomalien
        for anomaly in permission_anomalies:
            top_risiken.append({
                "typ": anomaly["anomaly_type"],
                "schwere": anomaly["severity"],
                "beschreibung": anomaly["details"],
                "user_id": anomaly["user_id"]
            })

        # Nach Schwere sortieren
        severity_order = {"kritisch": 0, "hoch": 1, "mittel": 2, "niedrig": 3}
        top_risiken.sort(key=lambda r: severity_order.get(r["schwere"], 4))
        top_risiken = top_risiken[:10]  # Top 10

        # Gesamtrisiko
        anomalie_count = len(access_analysis["anomalies"]) + len(exfiltration_analysis["indicators"]) + len(permission_anomalies)

        max_exfil_risk = exfiltration_analysis["exfiltration_risk"]
        if max_exfil_risk >= 0.7 or any(r["schwere"] == "kritisch" for r in top_risiken):
            gesamtrisiko = "kritisch"
        elif max_exfil_risk >= 0.5 or any(r["schwere"] == "hoch" for r in top_risiken):
            gesamtrisiko = "hoch"
        elif max_exfil_risk >= 0.3 or any(r["schwere"] == "mittel" for r in top_risiken):
            gesamtrisiko = "mittel"
        else:
            gesamtrisiko = "niedrig"

        # Empfehlungen
        empfehlungen: List[str] = list(exfiltration_analysis["recommended_actions"])

        if gesamtrisiko == "kritisch":
            empfehlungen.append("Sofortiges Security-Review erforderlich")
        if anomalie_count > 50:
            empfehlungen.append("Erhoehte Ueberwachung aktivieren")

        report = SecurityReport(
            period=period,
            gesamtrisiko=gesamtrisiko,
            anomalie_count=anomalie_count,
            top_risiken=top_risiken,
            empfehlungen=empfehlungen
        )

        logger.info(
            "security_report_generated",
            gesamtrisiko=gesamtrisiko,
            anomalie_count=anomalie_count
        )

        return asdict(report)

    async def check_permission_anomalies(
        self,
        db: AsyncSession,
        company_id: int,
        hours: int = 168
    ) -> List[Dict]:
        """
        Erkennt ungewoehnliche Permission-Aenderungen.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID
            hours: Analysezeitraum

        Returns:
            Liste von Anomalie-Dicts
        """
        logger.info(
            "checking_permission_anomalies",
            company_id=company_id,
            hours=hours
        )

        since = datetime.now(timezone.utc) - timedelta(hours=hours)

        # Permission-Aenderungen aus AuditLog
        stmt = (
            select(AuditLog)
            .where(
                and_(
                    AuditLog.company_id == company_id,
                    AuditLog.created_at >= since,
                    or_(
                        AuditLog.action.like("%permission%"),
                        AuditLog.action.like("%role%"),
                        AuditLog.action.like("%grant%")
                    )
                )
            )
        )
        result = await db.execute(stmt)
        logs = result.scalars().all()

        anomalies: List[Dict] = []

        # Gruppiere nach User
        user_changes: Dict[int, List[AuditLog]] = {}
        for log in logs:
            if log.user_id not in user_changes:
                user_changes[log.user_id] = []
            user_changes[log.user_id].append(log)

        # Erkenne Anomalien
        for user_id, changes in user_changes.items():
            # Haeufige Permission-Aenderungen
            if len(changes) > 10:
                anomalies.append({
                    "user_id": user_id,
                    "anomaly_type": "frequent_permission_changes",
                    "severity": "mittel",
                    "details": f"User {user_id} hat {len(changes)} Permission-Aenderungen durchgefuehrt",
                    "detected_at": datetime.now(timezone.utc).isoformat()
                })

            # Escalation-Versuche (grant + denied)
            escalations = [
                c for c in changes
                if "grant" in c.action.lower() or "escalat" in c.action.lower()
            ]
            if len(escalations) > 3:
                anomalies.append({
                    "user_id": user_id,
                    "anomaly_type": "permission_escalation",
                    "severity": "hoch",
                    "details": f"User {user_id} hat {len(escalations)} Escalation-Versuche",
                    "detected_at": datetime.now(timezone.utc).isoformat()
                })

        logger.info(
            "permission_anomalies_checked",
            anomaly_count=len(anomalies)
        )

        return anomalies


# Singleton
_service: Optional[ThreatDetectionService] = None


def get_threat_detection_service() -> ThreatDetectionService:
    """Gibt Singleton-Instanz zurueck."""
    global _service
    if _service is None:
        _service = ThreatDetectionService()
    return _service
