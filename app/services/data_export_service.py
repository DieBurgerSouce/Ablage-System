"""
Data Export Service - GDPR Art. 20 Datenportabilität.

Implementiert das Recht auf Datenübertragbarkeit gemäß DSGVO Art. 20.

Features:
- Export aller Benutzerdaten in maschinenlesbarem Format (JSON/CSV)
- Asynchrone Verarbeitung via Celery
- ZIP-Archiv mit strukturierten Daten
- 7 Tage Gültigkeit, danach automatische Löschung
- Download-Tracking für Audit-Zwecke

Feinpoliert und durchdacht - DSGVO-konform.
"""

import json
import zipfile
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any
from uuid import UUID
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.models import User, Document, DataExport, ExportStatus, ExportFormat, AuditLog
from app.core.exceptions import ExportError, UserNotFoundError
from app.core.safe_errors import safe_error_log, safe_error_detail

logger = structlog.get_logger(__name__)

# Configuration
EXPORT_EXPIRY_DAYS = 7
EXPORT_MAX_DOCUMENTS = 10000  # Max documents per export


class DataExportService:
    """Service für DSGVO-konforme Datenexporte."""

    async def create_export_request(
        self,
        db: AsyncSession,
        user_id: UUID,
        export_format: str = "json"
    ) -> DataExport:
        """
        Erstellt einen neuen Export-Request.

        Args:
            db: Database session
            user_id: User UUID
            export_format: "json" oder "csv"

        Returns:
            Erstellter DataExport

        Raises:
            ExportError: Wenn bereits ein Export läuft
        """
        # Prüfe ob bereits ein aktiver Export läuft
        existing_result = await db.execute(
            select(DataExport).where(
                DataExport.user_id == user_id,
                DataExport.status.in_([ExportStatus.PENDING, ExportStatus.PROCESSING])
            )
        )
        if existing_result.scalar_one_or_none():
            raise ExportError("Es läuft bereits ein Export für diesen Benutzer")

        # Validiere Format
        if export_format not in [ExportFormat.JSON, ExportFormat.CSV, "json", "csv"]:
            raise ExportError(f"Ungültiges Format: {export_format}. Erlaubt: json, csv")

        export = DataExport(
            user_id=user_id,
            format=export_format,
            status=ExportStatus.PENDING,
            expires_at=datetime.now(timezone.utc) + timedelta(days=EXPORT_EXPIRY_DAYS)
        )
        db.add(export)
        await db.commit()
        await db.refresh(export)

        logger.info(
            "data_export_requested",
            user_id=str(user_id)[:8] + "...",
            export_id=str(export.id),
            format=export_format
        )

        return export

    async def generate_export(
        self,
        db: AsyncSession,
        export_id: UUID
    ) -> DataExport:
        """
        Generiert den eigentlichen Export (als Celery Task aufrufen).

        Args:
            db: Database session
            export_id: Export UUID

        Returns:
            Aktualisierter DataExport

        Raises:
            ExportError: Bei Fehlern während der Generierung
        """
        export = await db.get(DataExport, export_id)
        if not export:
            raise ExportError(f"Export {export_id} nicht gefunden")

        export.status = ExportStatus.PROCESSING
        await db.commit()

        try:
            user = await db.get(User, export.user_id)
            if not user:
                raise UserNotFoundError(str(export.user_id))

            # Sammle alle Benutzerdaten
            export_data = await self._collect_user_data(db, user)

            # Erstelle ZIP-Archiv
            with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as tmp:
                zip_path = Path(tmp.name)

            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                # Benutzerprofil
                zipf.writestr(
                    'profil.json',
                    json.dumps(export_data['profile'], indent=2, ensure_ascii=False)
                )

                # Dokumente
                if export.format == ExportFormat.JSON or export.format == 'json':
                    zipf.writestr(
                        'dokumente.json',
                        json.dumps(export_data['documents'], indent=2, ensure_ascii=False)
                    )
                else:
                    zipf.writestr(
                        'dokumente.csv',
                        self._to_csv(export_data['documents'])
                    )

                # Aktivitätslog
                zipf.writestr(
                    'aktivitaet.json',
                    json.dumps(export_data['activity_log'], indent=2, ensure_ascii=False)
                )

                # README
                zipf.writestr(
                    'LIESMICH.txt',
                    self._generate_readme(user, export)
                )

            # Speichere ZIP-Datei (lokal, da MinIO optional ist)
            export_dir = Path("data/exports") / str(export.user_id)
            export_dir.mkdir(parents=True, exist_ok=True)

            final_path = export_dir / f"{export.id}_datenexport.zip"
            zip_path.rename(final_path)

            export.file_path = str(final_path)
            export.file_size_bytes = final_path.stat().st_size
            export.status = ExportStatus.COMPLETED
            export.completed_at = datetime.now(timezone.utc)

            await db.commit()

            logger.info(
                "data_export_completed",
                export_id=str(export_id),
                size_bytes=export.file_size_bytes
            )

        except UserNotFoundError:
            # UserNotFoundError direkt durchreichen
            export.status = ExportStatus.FAILED
            export.error_message = "User nicht gefunden"
            await db.commit()
            raise
        except Exception as e:
            export.status = ExportStatus.FAILED
            export.error_message = safe_error_detail(e, "Export")
            await db.commit()
            logger.error(
                "data_export_failed",
                export_id=str(export_id),
                **safe_error_log(e)
            )
            raise ExportError(f"Export fehlgeschlagen: {str(e)}")

        return export

    async def _collect_user_data(
        self,
        db: AsyncSession,
        user: User
    ) -> Dict[str, Any]:
        """Sammelt alle Benutzerdaten für den Export."""
        # Profildaten (sensible Daten wie Passwort-Hash werden ausgelassen)
        profile = {
            "benutzer_id": str(user.id),
            "email": user.email,
            "benutzername": user.username,
            "vollstaendiger_name": user.full_name,
            "erstellt_am": user.created_at.isoformat() if user.created_at else None,
            "letzter_login": user.last_login.isoformat() if user.last_login else None,
            "zwei_faktor_aktiviert": user.totp_enabled,
            "ist_aktiv": user.is_active,
        }

        # Dokumente (ohne gelöschte)
        docs_result = await db.execute(
            select(Document)
            .where(
                Document.owner_id == user.id,
                Document.deleted_at.is_(None)
            )
            .limit(EXPORT_MAX_DOCUMENTS)
        )

        documents: List[Dict[str, Any]] = []
        for doc in docs_result.scalars().all():
            documents.append({
                "dokument_id": str(doc.id),
                "dateiname": doc.original_filename,
                "dateityp": doc.document_type,
                "status": doc.status,
                "extrahierter_text": doc.extracted_text,
                "ocr_konfidenz": doc.ocr_confidence,
                "dateigroesse_bytes": doc.file_size,
                "hochgeladen_am": doc.upload_date.isoformat() if doc.upload_date else None,
                "verarbeitet_am": doc.processed_date.isoformat() if doc.processed_date else None,
            })

        # Audit Log (nur eigene Aktivitäten, anonymisiert)
        audit_result = await db.execute(
            select(AuditLog)
            .where(AuditLog.user_id == user.id)
            .order_by(AuditLog.created_at.desc())
            .limit(1000)
        )

        activity_log: List[Dict[str, Any]] = []
        for log in audit_result.scalars().all():
            activity_log.append({
                "aktion": log.action,
                "ressource_typ": log.resource_type,
                "ressource_id": str(log.resource_id) if log.resource_id else None,
                "zeitpunkt": log.created_at.isoformat() if log.created_at else None,
            })

        return {
            "profile": profile,
            "documents": documents,
            "activity_log": activity_log,
            "export_metadaten": {
                "exportiert_am": datetime.now(timezone.utc).isoformat(),
                "dokumente_gesamt": len(documents),
                "aktivitaeten_gesamt": len(activity_log),
            }
        }

    def _to_csv(self, documents: List[Dict[str, Any]]) -> str:
        """Konvertiert Dokumente zu CSV."""
        if not documents:
            return "dokument_id,dateiname,status,hochgeladen_am\n"

        import csv
        from io import StringIO

        output = StringIO()
        fieldnames = list(documents[0].keys())
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(documents)

        return output.getvalue()

    def _generate_readme(self, user: User, export: DataExport) -> str:
        """Generiert README für den Export."""
        return f"""DATENEXPORT - Ablage-System OCR
================================

Exportiert für: {user.email}
Benutzer-ID: {str(user.id)[:8]}...
Exportdatum: {export.requested_at.strftime('%d.%m.%Y %H:%M') if export.requested_at else 'N/A'}
Format: {export.format.upper() if hasattr(export.format, 'upper') else export.format}

Inhalt dieses Exports:
----------------------
- profil.json: Ihre Benutzerdaten und Kontoeinstellungen
- dokumente.{export.format if isinstance(export.format, str) else export.format.value}: Ihre hochgeladenen Dokumente und deren Metadaten
- aktivitaet.json: Ihre Aktivitäten im System (letzte 1000 Einträge)
- LIESMICH.txt: Diese Datei

Datenschutzhinweise:
-------------------
Dieser Export wurde gemäß Art. 20 DSGVO (Recht auf Datenübertragbarkeit) erstellt.
Die Daten liegen in einem strukturierten, gängigen und maschinenlesbaren Format vor.

Der Export ist bis {export.expires_at.strftime('%d.%m.%Y') if export.expires_at else 'N/A'} gültig
und wird danach automatisch gelöscht.

Bei Fragen:
-----------
Kontaktieren Sie uns unter datenschutz@ablage-system.de

Generiert von Ablage-System OCR
Feinpoliert und durchdacht.
"""

    async def get_exports_for_user(
        self,
        db: AsyncSession,
        user_id: UUID
    ) -> List[DataExport]:
        """Gibt alle Exports eines Benutzers zurück."""
        result = await db.execute(
            select(DataExport)
            .where(DataExport.user_id == user_id)
            .order_by(DataExport.requested_at.desc())
            .limit(20)
        )
        return list(result.scalars().all())

    async def get_export(
        self,
        db: AsyncSession,
        export_id: UUID,
        user_id: UUID
    ) -> Optional[DataExport]:
        """Gibt einen spezifischen Export zurück (mit Berechtigungsprüfung)."""
        export = await db.get(DataExport, export_id)
        if export and export.user_id == user_id:
            return export
        return None

    async def get_download_path(
        self,
        db: AsyncSession,
        export_id: UUID,
        user_id: UUID
    ) -> str:
        """
        Gibt den Download-Pfad zurück.

        Args:
            db: Database session
            export_id: Export UUID
            user_id: User UUID (für Berechtigungsprüfung)

        Returns:
            Pfad zur ZIP-Datei

        Raises:
            ExportError: Bei fehlender Berechtigung oder abgelaufenem Export
        """
        export = await db.get(DataExport, export_id)

        if not export or export.user_id != user_id:
            raise ExportError("Export nicht gefunden oder keine Berechtigung")

        if export.status != ExportStatus.COMPLETED:
            raise ExportError(f"Export nicht bereit. Status: {export.status}")

        if export.expires_at and datetime.now(timezone.utc) > export.expires_at:
            export.status = ExportStatus.EXPIRED
            await db.commit()
            raise ExportError("Export abgelaufen. Bitte neuen Export anfordern.")

        # Zähle Downloads
        export.download_count += 1
        await db.commit()

        logger.info(
            "data_export_downloaded",
            export_id=str(export_id),
            download_count=export.download_count
        )

        return export.file_path

    async def cleanup_expired_exports(
        self,
        db: AsyncSession
    ) -> int:
        """
        Löscht abgelaufene Exports (für Celery Task).

        Returns:
            Anzahl gelöschter Exports
        """
        now = datetime.now(timezone.utc)
        result = await db.execute(
            select(DataExport).where(
                DataExport.expires_at <= now,
                DataExport.status != ExportStatus.EXPIRED
            )
        )

        count = 0
        for export in result.scalars().all():
            # Lösche Datei
            if export.file_path:
                try:
                    Path(export.file_path).unlink(missing_ok=True)
                except Exception as e:
                    logger.warning(
                        "export_file_delete_failed",
                        export_id=str(export.id),
                        **safe_error_log(e)
                    )

            export.status = ExportStatus.EXPIRED
            count += 1

        await db.commit()

        logger.info("expired_exports_cleaned", count=count)
        return count


# Singleton-Instanz
_export_service: Optional[DataExportService] = None


def get_data_export_service() -> DataExportService:
    """Get global Data Export Service instance."""
    global _export_service
    if _export_service is None:
        _export_service = DataExportService()
    return _export_service
