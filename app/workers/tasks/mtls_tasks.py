# -*- coding: utf-8 -*-
"""
Celery Tasks fuer mTLS Certificate Management.

Geplante Tasks:
- rotate_expiring_certificates_task: Taeglich 03:00 - Zertifikate rotieren
- verify_all_certificates_task: Woechentlich Sonntag 04:00 - Zertifikat-Validierung
- cleanup_revoked_certificates_task: Monatlich am 1. um 02:00 - Aufraumen
- sync_certificate_registry_task: Alle 5 Minuten - Registry-Sync
- generate_mtls_audit_report_task: Woechentlich Montag 06:00 - Audit-Bericht

Feinpoliert und durchdacht - Automatische Zertifikatsverwaltung.
"""

import asyncio
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog

from app.workers.celery_app import celery_app, CPUTask

logger = structlog.get_logger(__name__)


def run_async(coro):
    """Hilfsfunktion um async Code in sync Celery Tasks auszufuehren.

    MEMORY FIX: Verwendet asyncio.run() statt new_event_loop() um Memory Leaks
    zu verhindern. asyncio.run() erstellt einen neuen Event-Loop, fuehrt die
    Coroutine aus und schließt den Loop korrekt inkl. aller pending Tasks.
    """
    return asyncio.run(coro)


# =============================================================================
# Certificate Rotation Task
# =============================================================================

@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.mtls_tasks.rotate_expiring_certificates_task",
    max_retries=3,
    default_retry_delay=600,  # 10 Minuten
)
def rotate_expiring_certificates_task(
    self,
    threshold_days: int = 7,
) -> Dict[str, Any]:
    """
    Celery Task fuer automatische Zertifikat-Rotation.

    Prueft alle registrierten Service-Zertifikate und rotiert jene,
    die innerhalb des Schwellenwerts ablaufen.

    Args:
        threshold_days: Tage vor Ablauf fuer Rotation (Standard: 7)

    Returns:
        Dict mit Rotationsergebnis
    """
    logger.info(
        "rotate_expiring_certificates_task_gestartet",
        task_id=self.request.id,
        threshold_days=threshold_days,
    )

    try:
        from app.core.security.mtls_service import get_mtls_service

        mtls_service = get_mtls_service()

        # Finde Zertifikate die Rotation brauchen
        needs_rotation = mtls_service.get_certificates_needing_rotation(threshold_days)

        rotated = []
        failed = []

        for service_name, service_type, cert_info in needs_rotation:
            try:
                # Rotiere Zertifikat
                new_cert = mtls_service.rotate_service_certificate(
                    service_name=service_name,
                    service_type=service_type,
                    revoke_old=True,
                )

                rotated.append({
                    "service_name": service_name,
                    "service_type": service_type,
                    "old_serial": cert_info.serial_number,
                    "new_serial": new_cert.cert_info.serial_number,
                    "new_not_after": new_cert.cert_info.not_after.isoformat(),
                })

                logger.info(
                    "certificate_rotated_successfully",
                    service_name=service_name,
                    service_type=service_type,
                    old_serial=cert_info.serial_number,
                    new_serial=new_cert.cert_info.serial_number,
                )

            except Exception as e:
                failed.append({
                    "service_name": service_name,
                    "service_type": service_type,
                    "error": str(e),
                })

                logger.error(
                    "certificate_rotation_failed",
                    service_name=service_name,
                    service_type=service_type,
                    error=str(e),
                )

        response = {
            "erfolg": len(failed) == 0,
            "geprueft": len(needs_rotation),
            "rotiert": len(rotated),
            "fehlgeschlagen": len(failed),
            "rotierte_zertifikate": rotated,
            "fehler": failed,
            "threshold_days": threshold_days,
        }

        logger.info(
            "rotate_expiring_certificates_task_abgeschlossen",
            task_id=self.request.id,
            geprueft=len(needs_rotation),
            rotiert=len(rotated),
            fehlgeschlagen=len(failed),
        )

        return response

    except Exception as e:
        logger.exception(
            "rotate_expiring_certificates_task_fehler",
            task_id=self.request.id,
        )
        raise self.retry(exc=e)


# =============================================================================
# Certificate Verification Task
# =============================================================================

@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.mtls_tasks.verify_all_certificates_task",
)
def verify_all_certificates_task(self) -> Dict[str, Any]:
    """
    Celery Task fuer woechentliche Zertifikat-Validierung.

    Prueft alle registrierten Zertifikate auf:
    - Gueltigkeit
    - Korrekte CA-Signatur
    - Widerrufsstatus

    Returns:
        Dict mit Validierungsergebnis
    """
    logger.info(
        "verify_all_certificates_task_gestartet",
        task_id=self.request.id,
    )

    try:
        from app.core.security.mtls_service import get_mtls_service
        from app.core.security.certificate_authority import get_certificate_authority

        mtls_service = get_mtls_service()
        ca = get_certificate_authority()

        stats = mtls_service.get_service_statistics()
        results = {
            "valid": [],
            "invalid": [],
            "expiring_soon": [],
            "expired": [],
        }

        for service_info in stats.get("services", []):
            service_name = service_info["name"]
            service_type = service_info["type"]

            # Lade Zertifikat
            service_cert = mtls_service.get_service_certificate(
                service_name, service_type
            )

            if service_cert is None:
                results["invalid"].append({
                    "service_name": service_name,
                    "service_type": service_type,
                    "error": "Zertifikat nicht gefunden",
                })
                continue

            # Verifiziere Zertifikat
            is_valid, error_msg = ca.verify_certificate(service_cert.cert_pem)

            if not is_valid:
                if "abgelaufen" in (error_msg or "").lower():
                    results["expired"].append({
                        "service_name": service_name,
                        "service_type": service_type,
                        "error": error_msg,
                        "not_after": service_cert.cert_info.not_after.isoformat(),
                    })
                else:
                    results["invalid"].append({
                        "service_name": service_name,
                        "service_type": service_type,
                        "error": error_msg,
                    })
            else:
                # Pruefe auf baldigen Ablauf
                days_until_expiry = service_info["days_until_expiry"]

                if days_until_expiry <= 7:
                    results["expiring_soon"].append({
                        "service_name": service_name,
                        "service_type": service_type,
                        "days_until_expiry": days_until_expiry,
                        "not_after": service_cert.cert_info.not_after.isoformat(),
                    })
                else:
                    results["valid"].append({
                        "service_name": service_name,
                        "service_type": service_type,
                        "days_until_expiry": days_until_expiry,
                    })

        response = {
            "erfolg": len(results["invalid"]) == 0 and len(results["expired"]) == 0,
            "gesamt": len(stats.get("services", [])),
            "gueltig": len(results["valid"]),
            "ungueltig": len(results["invalid"]),
            "ablaufend": len(results["expiring_soon"]),
            "abgelaufen": len(results["expired"]),
            "details": results,
        }

        # Warnung bei Problemen
        if len(results["invalid"]) > 0 or len(results["expired"]) > 0:
            logger.warning(
                "certificate_verification_issues",
                task_id=self.request.id,
                ungueltig=len(results["invalid"]),
                abgelaufen=len(results["expired"]),
            )

        logger.info(
            "verify_all_certificates_task_abgeschlossen",
            task_id=self.request.id,
            gueltig=len(results["valid"]),
            ungueltig=len(results["invalid"]),
            ablaufend=len(results["expiring_soon"]),
        )

        return response

    except Exception as e:
        logger.exception(
            "verify_all_certificates_task_fehler",
            task_id=self.request.id,
        )
        raise


# =============================================================================
# Certificate Cleanup Task
# =============================================================================

@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.mtls_tasks.cleanup_revoked_certificates_task",
)
def cleanup_revoked_certificates_task(
    self,
    max_age_days: int = 90,
) -> Dict[str, Any]:
    """
    Celery Task fuer Aufraumen widerrufener Zertifikate.

    Loescht Zertifikat-Dateien von widerrufenen Zertifikaten die
    aelter als max_age_days sind.

    Args:
        max_age_days: Maximales Alter in Tagen (Standard: 90)

    Returns:
        Dict mit Aufraeum-Ergebnis
    """
    logger.info(
        "cleanup_revoked_certificates_task_gestartet",
        task_id=self.request.id,
        max_age_days=max_age_days,
    )

    try:
        from app.core.security.mtls_service import get_mtls_service

        mtls_service = get_mtls_service()
        certs_dir = mtls_service.certs_dir
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=max_age_days)

        cleaned_up = []
        errors = []

        # Durchsuche alle Service-Verzeichnisse
        for service_type_dir in certs_dir.iterdir():
            if not service_type_dir.is_dir():
                continue

            for service_dir in service_type_dir.iterdir():
                if not service_dir.is_dir():
                    continue

                # Pruefe auf alte Backup-Dateien von Rotation
                for old_file in service_dir.glob("*.old"):
                    try:
                        stat = old_file.stat()
                        file_mtime = datetime.fromtimestamp(
                            stat.st_mtime, tz=timezone.utc
                        )

                        if file_mtime < cutoff_date:
                            old_file.unlink()
                            cleaned_up.append(str(old_file))

                            logger.debug(
                                "old_certificate_file_removed",
                                path=str(old_file),
                                age_days=(datetime.now(timezone.utc) - file_mtime).days,
                            )

                    except Exception as e:
                        errors.append({
                            "path": str(old_file),
                            "error": str(e),
                        })

        response = {
            "erfolg": len(errors) == 0,
            "aufgeraeumt": len(cleaned_up),
            "fehler": len(errors),
            "dateien": cleaned_up[:20],  # Erste 20 anzeigen
            "fehler_details": errors[:5],  # Erste 5 Fehler
            "max_age_days": max_age_days,
        }

        logger.info(
            "cleanup_revoked_certificates_task_abgeschlossen",
            task_id=self.request.id,
            aufgeraeumt=len(cleaned_up),
            fehler=len(errors),
        )

        return response

    except Exception as e:
        logger.exception(
            "cleanup_revoked_certificates_task_fehler",
            task_id=self.request.id,
        )
        raise


# =============================================================================
# Registry Sync Task
# =============================================================================

@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.mtls_tasks.sync_certificate_registry_task",
)
def sync_certificate_registry_task(self) -> Dict[str, Any]:
    """
    Celery Task fuer Zertifikat-Registry-Synchronisation.

    Laedt alle Zertifikate von Disk in das In-Memory-Registry.
    Wird alle 5 Minuten ausgefuehrt um neue Zertifikate zu erkennen.

    Returns:
        Dict mit Sync-Ergebnis
    """
    logger.info(
        "sync_certificate_registry_task_gestartet",
        task_id=self.request.id,
    )

    try:
        from app.core.security.mtls_service import get_mtls_service
        from app.core.security.certificate_authority import ALLOWED_SERVICE_TYPES

        mtls_service = get_mtls_service()
        certs_dir = mtls_service.certs_dir

        loaded = []
        errors = []

        # Durchsuche alle Service-Verzeichnisse
        for service_type in ALLOWED_SERVICE_TYPES:
            service_type_dir = certs_dir / service_type

            if not service_type_dir.exists():
                continue

            for service_dir in service_type_dir.iterdir():
                if not service_dir.is_dir():
                    continue

                cert_path = service_dir / "cert.pem"
                key_path = service_dir / "key.pem"

                if not cert_path.exists() or not key_path.exists():
                    continue

                service_name = service_dir.name

                try:
                    service_cert = mtls_service.load_service_certificate(
                        service_name=service_name,
                        service_type=service_type,
                    )

                    if service_cert:
                        loaded.append({
                            "service_name": service_name,
                            "service_type": service_type,
                            "fingerprint": service_cert.cert_info.fingerprint_sha256[:16] + "...",
                        })

                except Exception as e:
                    errors.append({
                        "service_name": service_name,
                        "service_type": service_type,
                        "error": str(e),
                    })

        stats = mtls_service.get_service_statistics()

        response = {
            "erfolg": True,
            "geladen": len(loaded),
            "fehler": len(errors),
            "gesamt_registriert": stats["total_services"],
            "ablaufend": stats["expiring_soon"],
            "abgelaufen": stats["expired"],
            "neu_geladen": loaded,
            "fehler_details": errors[:5],
        }

        logger.info(
            "sync_certificate_registry_task_abgeschlossen",
            task_id=self.request.id,
            geladen=len(loaded),
            gesamt=stats["total_services"],
        )

        return response

    except Exception as e:
        logger.exception(
            "sync_certificate_registry_task_fehler",
            task_id=self.request.id,
        )
        raise


# =============================================================================
# Audit Report Task
# =============================================================================

@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.mtls_tasks.generate_mtls_audit_report_task",
)
def generate_mtls_audit_report_task(
    self,
    days: int = 7,
) -> Dict[str, Any]:
    """
    Celery Task fuer woechentlichen mTLS Audit-Bericht.

    Erstellt einen Bericht ueber alle mTLS-Aktivitaeten der letzten Woche:
    - Authentifizierungsversuche
    - Zertifikat-Ausstellungen
    - Rotationen
    - Widerrufe

    Args:
        days: Zeitraum in Tagen (Standard: 7)

    Returns:
        Dict mit Audit-Bericht
    """
    logger.info(
        "generate_mtls_audit_report_task_gestartet",
        task_id=self.request.id,
        days=days,
    )

    try:
        from app.core.security.mtls_service import get_mtls_service

        mtls_service = get_mtls_service()

        # Hole Audit-Log
        audit_entries = mtls_service.get_audit_log(limit=10000)

        # Filtere nach Zeitraum
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        filtered_entries = [
            e for e in audit_entries
            if datetime.fromisoformat(e["timestamp"]) >= cutoff
        ]

        # Aggregiere nach Event-Typ
        event_counts: Dict[str, int] = {}
        success_counts: Dict[str, int] = {}
        failure_counts: Dict[str, int] = {}
        service_activity: Dict[str, int] = {}

        for entry in filtered_entries:
            event_type = entry["event_type"]
            result = entry["result"]
            service_name = entry.get("service_name", "unknown")

            # Event-Typ zaehlen
            event_counts[event_type] = event_counts.get(event_type, 0) + 1

            # Erfolg/Fehler zaehlen
            if result == "success":
                success_counts[event_type] = success_counts.get(event_type, 0) + 1
            else:
                failure_counts[event_type] = failure_counts.get(event_type, 0) + 1

            # Service-Aktivitaet zaehlen
            if service_name:
                service_activity[service_name] = service_activity.get(service_name, 0) + 1

        # Service-Statistiken
        stats = mtls_service.get_service_statistics()

        # Top 5 aktivste Services
        top_services = sorted(
            service_activity.items(),
            key=lambda x: x[1],
            reverse=True,
        )[:5]

        response = {
            "erfolg": True,
            "zeitraum_tage": days,
            "zeitraum_von": cutoff.isoformat(),
            "zeitraum_bis": datetime.now(timezone.utc).isoformat(),
            "gesamt_ereignisse": len(filtered_entries),
            "ereignisse_nach_typ": event_counts,
            "erfolgreiche_ereignisse": success_counts,
            "fehlgeschlagene_ereignisse": failure_counts,
            "service_statistiken": {
                "gesamt": stats["total_services"],
                "ablaufend": stats["expiring_soon"],
                "abgelaufen": stats["expired"],
            },
            "top_aktive_services": [
                {"service": name, "ereignisse": count}
                for name, count in top_services
            ],
            "letzte_fehler": [
                e for e in filtered_entries[-10:]
                if e["result"] != "success"
            ],
        }

        logger.info(
            "generate_mtls_audit_report_task_abgeschlossen",
            task_id=self.request.id,
            ereignisse=len(filtered_entries),
        )

        return response

    except Exception as e:
        logger.exception(
            "generate_mtls_audit_report_task_fehler",
            task_id=self.request.id,
        )
        raise


# =============================================================================
# Initialize Service Certificates Task
# =============================================================================

@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.mtls_tasks.initialize_service_certificates_task",
    max_retries=3,
    default_retry_delay=60,
)
def initialize_service_certificates_task(
    self,
    services: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    """
    Celery Task fuer initiale Zertifikat-Erstellung.

    Erstellt Zertifikate fuer alle Core-Services wenn nicht vorhanden.
    Wird beim System-Start ausgefuehrt.

    Args:
        services: Liste von Services [{name, type}] oder None fuer Defaults

    Returns:
        Dict mit Erstellungsergebnis
    """
    logger.info(
        "initialize_service_certificates_task_gestartet",
        task_id=self.request.id,
    )

    # Default-Services wenn nicht angegeben
    if services is None:
        services = [
            {"name": "api", "type": "backend"},
            {"name": "celery-worker", "type": "worker"},
            {"name": "celery-beat", "type": "celery-beat"},
            {"name": "redis-client", "type": "backend"},
            {"name": "postgres-client", "type": "backend"},
            {"name": "minio-client", "type": "backend"},
            {"name": "monitoring", "type": "monitoring"},
        ]

    try:
        from app.core.security.mtls_service import get_mtls_service

        mtls_service = get_mtls_service()

        created = []
        existing = []
        failed = []

        for service in services:
            service_name = service.get("name")
            service_type = service.get("type")

            if not service_name or not service_type:
                continue

            try:
                # Pruefe ob Zertifikat existiert
                cert = mtls_service.load_service_certificate(
                    service_name=service_name,
                    service_type=service_type,
                )

                if cert is not None:
                    existing.append({
                        "service_name": service_name,
                        "service_type": service_type,
                        "fingerprint": cert.cert_info.fingerprint_sha256[:16] + "...",
                    })
                    continue

                # Erstelle neues Zertifikat
                new_cert = mtls_service.issue_service_certificate(
                    service_name=service_name,
                    service_type=service_type,
                )

                created.append({
                    "service_name": service_name,
                    "service_type": service_type,
                    "fingerprint": new_cert.cert_info.fingerprint_sha256[:16] + "...",
                    "not_after": new_cert.cert_info.not_after.isoformat(),
                })

                logger.info(
                    "service_certificate_created",
                    service_name=service_name,
                    service_type=service_type,
                )

            except Exception as e:
                failed.append({
                    "service_name": service_name,
                    "service_type": service_type,
                    "error": str(e),
                })

                logger.error(
                    "service_certificate_creation_failed",
                    service_name=service_name,
                    service_type=service_type,
                    error=str(e),
                )

        response = {
            "erfolg": len(failed) == 0,
            "erstellt": len(created),
            "existierend": len(existing),
            "fehlgeschlagen": len(failed),
            "erstellte_zertifikate": created,
            "existierende_zertifikate": existing,
            "fehler": failed,
        }

        logger.info(
            "initialize_service_certificates_task_abgeschlossen",
            task_id=self.request.id,
            erstellt=len(created),
            existierend=len(existing),
            fehlgeschlagen=len(failed),
        )

        return response

    except Exception as e:
        logger.exception(
            "initialize_service_certificates_task_fehler",
            task_id=self.request.id,
        )
        raise self.retry(exc=e)


# =============================================================================
# Revoke Certificate Task
# =============================================================================

@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.mtls_tasks.revoke_certificate_task",
)
def revoke_certificate_task(
    self,
    serial_number: int,
    reason: str = "unspecified",
) -> Dict[str, Any]:
    """
    Celery Task fuer Zertifikat-Widerruf.

    Widerruft ein Zertifikat anhand der Seriennummer.

    Args:
        serial_number: Seriennummer des Zertifikats
        reason: Grund fuer Widerruf

    Returns:
        Dict mit Widerruf-Ergebnis
    """
    logger.info(
        "revoke_certificate_task_gestartet",
        task_id=self.request.id,
        serial_number=serial_number,
        reason=reason,
    )

    try:
        from app.core.security.certificate_authority import get_certificate_authority

        ca = get_certificate_authority()
        ca.revoke_certificate(serial_number, reason)

        response = {
            "erfolg": True,
            "serial_number": serial_number,
            "reason": reason,
            "revoked_at": datetime.now(timezone.utc).isoformat(),
        }

        logger.info(
            "revoke_certificate_task_abgeschlossen",
            task_id=self.request.id,
            serial_number=serial_number,
        )

        return response

    except Exception as e:
        logger.exception(
            "revoke_certificate_task_fehler",
            task_id=self.request.id,
        )
        return {
            "erfolg": False,
            "serial_number": serial_number,
            "error": str(e),
        }


# =============================================================================
# CA Status Task
# =============================================================================

@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.mtls_tasks.get_ca_status_task",
)
def get_ca_status_task(self) -> Dict[str, Any]:
    """
    Celery Task fuer CA-Status-Abfrage.

    Gibt Informationen ueber die Certificate Authority zurueck.

    Returns:
        Dict mit CA-Status
    """
    logger.info(
        "get_ca_status_task_gestartet",
        task_id=self.request.id,
    )

    try:
        from app.core.security.certificate_authority import get_certificate_authority
        from app.core.security.mtls_service import get_mtls_service

        ca = get_certificate_authority()
        mtls_service = get_mtls_service()

        if not ca.is_initialized():
            return {
                "erfolg": False,
                "initialisiert": False,
                "nachricht": "CA ist nicht initialisiert",
            }

        ca_info = ca.get_ca_info()
        service_stats = mtls_service.get_service_statistics()
        now = datetime.now(timezone.utc)

        response = {
            "erfolg": True,
            "initialisiert": True,
            "ca_info": {
                "subject": ca_info.subject,
                "fingerprint": ca_info.fingerprint_sha256[:32] + "...",
                "not_before": ca_info.not_before.isoformat(),
                "not_after": ca_info.not_after.isoformat(),
                "days_until_expiry": (ca_info.not_after - now).days,
            },
            "service_statistiken": service_stats,
        }

        logger.info(
            "get_ca_status_task_abgeschlossen",
            task_id=self.request.id,
        )

        return response

    except Exception as e:
        logger.exception(
            "get_ca_status_task_fehler",
            task_id=self.request.id,
        )
        return {
            "erfolg": False,
            "error": str(e),
        }
