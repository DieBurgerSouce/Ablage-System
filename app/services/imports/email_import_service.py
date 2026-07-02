"""Email Import Service.

Orchestriert den Import von E-Mail-Anhaengen via IMAP:
- IMAP-Verbindungsmanagement
- E-Mail-Abruf und -Parsing
- Anhang-Extraktion
- Integration mit Document-Pipeline

Feinpoliert und durchdacht - Enterprise-grade Email Import.
"""

import email
import hashlib
import re
from datetime import datetime, timezone
from email.header import decode_header
from email.message import Message
from email.utils import parsedate_to_datetime
from typing import Optional, List, Dict, Tuple, BinaryIO
from uuid import UUID, uuid4
import structlog

from sqlalchemy import select, and_, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.encryption import encrypt_data, decrypt_data, EncryptionError
from app.core.config import settings
from app.core.malware_scanner import scan_content
from app.core.safe_errors import safe_error_log, safe_error_detail
from app.services.events.event_bus import EventBus, EventType

logger = structlog.get_logger(__name__)


# ============================================================================
# IMAP Client Import (optional dependency)
# ============================================================================

try:
    from imapclient import IMAPClient
    IMAP_AVAILABLE = True
except ImportError:
    IMAP_AVAILABLE = False
    IMAPClient = None
    logger.warning("imapclient not installed - email import disabled")


# ============================================================================
# Constants
# ============================================================================

# Maximale Anhang-Größe (50 MB)
MAX_ATTACHMENT_SIZE = 50 * 1024 * 1024

# W2-21b SSRF-Schutz: nur Standard-IMAP-Ports erlaubt (143=STARTTLS, 993=SSL)
ALLOWED_IMAP_PORTS = {143, 993}

# Erlaubte MIME-Types für Dokument-Import
ALLOWED_MIME_TYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/tiff",
    "image/tif",
    "image/gif",
    "image/bmp",
    "image/webp",
}

# Erlaubte Dateiendungen
ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif", ".gif", ".bmp", ".webp"}


# ============================================================================
# Data Classes
# ============================================================================

class EmailAttachment:
    """Repraesentiert einen E-Mail-Anhang."""

    def __init__(
        self,
        filename: str,
        content: bytes,
        mime_type: str,
        content_id: Optional[str] = None,
    ):
        self.filename = filename
        self.content = content
        self.mime_type = mime_type
        self.content_id = content_id
        self.file_hash = hashlib.sha256(content).hexdigest()
        self.size = len(content)


class ParsedEmail:
    """Repraesentiert eine geparste E-Mail."""

    def __init__(
        self,
        uid: int,
        message_id: str,
        from_address: str,
        subject: str,
        date: Optional[datetime],
        attachments: List[EmailAttachment],
        body_text: Optional[str] = None,
        body_html: Optional[str] = None,
    ):
        self.uid = uid
        self.message_id = message_id
        self.from_address = from_address
        self.subject = subject
        self.date = date
        self.attachments = attachments
        self.body_text = body_text
        self.body_html = body_html


class EmailImportResult:
    """Ergebnis eines Email-Imports."""

    def __init__(self):
        self.emails_processed: int = 0
        self.attachments_extracted: int = 0
        self.documents_created: int = 0
        self.duplicates_skipped: int = 0
        self.errors: List[Dict] = []
        self.created_document_ids: List[UUID] = []


# ============================================================================
# Email Import Service
# ============================================================================

class EmailImportService:
    """Service für E-Mail-Import via IMAP.

    Features:
    - IMAP-Verbindung mit SSL/TLS
    - Credential-Verschlüsselung (AES-256-GCM)
    - Anhang-Extraktion mit MIME-Typ-Validierung
    - Duplikat-Erkennung via SHA256
    - Integration mit Document-Pipeline
    """

    def __init__(self, db: AsyncSession):
        """Initialisiert den Email Import Service.

        Args:
            db: Async Database Session
        """
        self.db = db

    # ========================================================================
    # Connection Management
    # ========================================================================

    def _validate_imap_target(self, server: str, port: int) -> None:
        """Validiert IMAP-Ziel gegen SSRF (W2-21b).

        Prueft Port-Whitelist und loest den Host auf; jede aufgeloeste IP wird
        gegen private/loopback/link-local-Ranges geprueft. Fail-closed: bei
        ungueltigem Host/Port oder blockierter IP wird die Verbindung verweigert.

        Raises:
            ConnectionError: Wenn Port oder Ziel-IP nicht erlaubt ist.
        """
        import socket

        from app.core.security_auth import is_ip_blocked_for_ssrf

        # 1. Port-Whitelist (143=STARTTLS, 993=SSL)
        if port not in ALLOWED_IMAP_PORTS:
            logger.warning("imap_ssrf_blocked_port", port=port)
            raise ConnectionError(
                f"IMAP-Port nicht erlaubt: {port} (erlaubt: 143, 993)"
            )

        # 2. Host muss gesetzt sein
        host = (server or "").strip()
        if not host:
            logger.warning("imap_ssrf_empty_host")
            raise ConnectionError("IMAP-Server-Host fehlt")

        # 3. Alle aufgeloesten IPs gegen SSRF-Ranges pruefen (fail-closed)
        try:
            addr_infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
        except (socket.gaierror, OSError, UnicodeError) as exc:
            logger.warning("imap_ssrf_dns_failed", server=host, error=str(exc))
            raise ConnectionError(f"IMAP-Server-Host nicht aufloesbar: {host}")

        resolved_ips = {info[4][0] for info in addr_infos}
        if not resolved_ips:
            logger.warning("imap_ssrf_no_ip", server=host)
            raise ConnectionError(f"IMAP-Server-Host nicht aufloesbar: {host}")

        for ip_str in resolved_ips:
            if is_ip_blocked_for_ssrf(ip_str):
                logger.warning("imap_ssrf_blocked_ip", server=host)
                raise ConnectionError(
                    "IMAP-Ziel verweist auf eine nicht erlaubte (interne) Adresse"
                )

    def _create_imap_connection(
        self,
        server: str,
        port: int,
        username: str,
        password: str,
        use_ssl: bool = True,
        use_starttls: bool = False,
    ) -> "IMAPClient":
        """Erstellt IMAP-Verbindung.

        Args:
            server: IMAP Server Hostname
            port: IMAP Port (993 für SSL, 143 für STARTTLS)
            username: IMAP Username
            password: IMAP Passwort (entschlüsselt)
            use_ssl: SSL verwenden
            use_starttls: STARTTLS verwenden

        Returns:
            IMAPClient Instanz

        Raises:
            RuntimeError: Wenn imapclient nicht installiert
            ConnectionError: Bei Verbindungsfehlern
        """
        if not IMAP_AVAILABLE:
            raise RuntimeError(
                "E-Mail-Import nicht verfügbar. "
                "Bitte 'pip install imapclient' ausführen."
            )

        # W2-21b SSRF-Schutz: user-gesetzter imap_server/imap_port wird gegen
        # Port-Whitelist und private/link-local-IPs geprueft (fail-closed),
        # bevor eine Verbindung aufgebaut wird.
        self._validate_imap_target(server, port)

        try:
            client = IMAPClient(server, port=port, ssl=use_ssl)

            if use_starttls and not use_ssl:
                client.starttls()

            client.login(username, password)

            logger.info(
                "imap_connected",
                server=server,
                port=port,
                ssl=use_ssl,
            )

            return client

        except Exception as e:
            logger.error(
                "imap_connection_failed",
                server=server,
                port=port,
                **safe_error_log(e),
            )
            raise ConnectionError(f"IMAP-Verbindung fehlgeschlagen: {e}")

    async def test_connection(self, config_id: UUID, user_id: UUID) -> Dict:
        """Testet IMAP-Verbindung für eine Konfiguration.

        Args:
            config_id: Email-Import-Konfigurations-ID
            user_id: User-ID für Berechtigungsprüfung

        Returns:
            Dict mit Test-Ergebnis (success, message, folder_count)
        """
        from app.db.models import EmailImportConfig

        # Config laden
        config = await self._get_config(config_id, user_id)
        if not config:
            return {
                "success": False,
                "message": "Konfiguration nicht gefunden",
            }

        try:
            # Credentials entschlüsseln
            username = decrypt_data(
                config.username_encrypted,
                associated_data=f"email_config:{config_id}"
            )
            password = decrypt_data(
                config.password_encrypted,
                associated_data=f"email_config:{config_id}"
            )

            # Verbindung testen
            client = self._create_imap_connection(
                server=config.imap_server,
                port=config.imap_port,
                username=username,
                password=password,
                use_ssl=config.use_ssl,
                use_starttls=config.use_starttls,
            )

            # Ordner auflisten
            folders = client.list_folders()
            folder_count = len(folders)

            client.logout()

            # Status aktualisieren
            await self._update_connection_status(
                config_id, "connected", None
            )

            return {
                "success": True,
                "message": f"Verbindung erfolgreich. {folder_count} Ordner gefunden.",
                "folder_count": folder_count,
                "folders": [f[2] for f in folders[:20]],  # Erste 20 Ordnernamen
            }

        except EncryptionError as e:
            return {
                "success": False,
                "message": "Credentials konnten nicht entschlüsselt werden",
            }
        except Exception as e:
            await self._update_connection_status(
                config_id, "error", safe_error_detail(e, "Email-Import")
            )
            return {
                "success": False,
                "message": f"Verbindungsfehler: {e}",
            }

    # ========================================================================
    # Email Sync
    # ========================================================================

    async def sync_emails(
        self,
        config_id: UUID,
        user_id: UUID,
        max_emails: int = 100,
    ) -> EmailImportResult:
        """Synchronisiert E-Mails für eine Konfiguration.

        Args:
            config_id: Email-Import-Konfigurations-ID
            user_id: User-ID
            max_emails: Maximale Anzahl zu verarbeitender Emails

        Returns:
            EmailImportResult mit Statistiken
        """
        from app.db.models import EmailImportConfig, ImportLog

        result = EmailImportResult()
        batch_id = uuid4()

        # Config laden
        config = await self._get_config(config_id, user_id)
        if not config:
            result.errors.append({
                "type": "config_error",
                "message": "Konfiguration nicht gefunden",
            })
            return result

        if not config.is_active:
            result.errors.append({
                "type": "config_inactive",
                "message": "Konfiguration ist deaktiviert",
            })
            return result

        client = None
        try:
            # Credentials entschlüsseln
            username = decrypt_data(
                config.username_encrypted,
                associated_data=f"email_config:{config_id}"
            )
            password = decrypt_data(
                config.password_encrypted,
                associated_data=f"email_config:{config_id}"
            )

            # Verbinden
            client = self._create_imap_connection(
                server=config.imap_server,
                port=config.imap_port,
                username=username,
                password=password,
                use_ssl=config.use_ssl,
                use_starttls=config.use_starttls,
            )

            # Ordner auswählen
            folder = config.imap_folder or "INBOX"
            client.select_folder(folder, readonly=False)

            # Neue Nachrichten suchen (UIDs größer als last_uid)
            search_criteria = ["UID", f"{config.last_uid + 1}:*"]

            # Filter anwenden wenn konfiguriert
            if config.filter_from_addresses:
                for addr in config.filter_from_addresses[:5]:  # Max 5 Filter
                    search_criteria.extend(["FROM", addr])

            uids = client.search(search_criteria)

            # Auf max_emails begrenzen
            uids = sorted(uids)[:max_emails]

            if not uids:
                logger.info(
                    "no_new_emails",
                    config_id=str(config_id),
                    folder=folder,
                )
                await self._update_sync_timestamp(config_id)
                return result

            logger.info(
                "processing_emails",
                config_id=str(config_id),
                email_count=len(uids),
            )

            # Emails verarbeiten
            for uid in uids:
                try:
                    # Email abrufen
                    raw_messages = client.fetch([uid], ["RFC822", "ENVELOPE"])
                    if uid not in raw_messages:
                        continue

                    raw_email = raw_messages[uid][b"RFC822"]
                    parsed = self._parse_email(uid, raw_email)
                    result.emails_processed += 1

                    # Anhaenge verarbeiten
                    for attachment in parsed.attachments:
                        doc_result = await self._process_attachment(
                            config=config,
                            email=parsed,
                            attachment=attachment,
                            batch_id=batch_id,
                            user_id=user_id,
                        )

                        if doc_result.get("success"):
                            result.attachments_extracted += 1
                            result.documents_created += 1
                            if doc_result.get("document_id"):
                                result.created_document_ids.append(
                                    doc_result["document_id"]
                                )
                        elif doc_result.get("duplicate"):
                            result.duplicates_skipped += 1

                    # Email verschieben wenn konfiguriert
                    if config.processed_folder:
                        try:
                            client.move([uid], config.processed_folder)
                        except Exception as move_error:
                            logger.warning(
                                "email_move_failed",
                                uid=uid,
                                error=str(move_error),
                            )

                    # UID aktualisieren
                    if uid > config.last_uid:
                        await self._update_last_uid(config_id, uid)

                except Exception as email_error:
                    result.errors.append({
                        "uid": uid,
                        "error": str(email_error),
                    })
                    logger.warning(
                        "email_processing_failed",
                        uid=uid,
                        error=str(email_error),
                    )

            # Sync-Timestamp aktualisieren
            await self._update_sync_timestamp(config_id)
            await self._update_connection_status(config_id, "connected", None)

            # Statistiken aktualisieren
            await self._update_stats(
                config_id,
                emails_processed=result.emails_processed,
                documents_created=result.documents_created,
            )

            logger.info(
                "email_sync_completed",
                config_id=str(config_id),
                emails_processed=result.emails_processed,
                documents_created=result.documents_created,
            )

        except Exception as e:
            await self._update_connection_status(config_id, "error", safe_error_detail(e, "Email-Import"))
            result.errors.append({
                "type": "sync_error",
                "message": safe_error_detail(e, "Email"),
            })
            logger.error(
                "email_sync_failed",
                config_id=str(config_id),
                **safe_error_log(e),
            )

        finally:
            if client:
                try:
                    client.logout()
                except Exception as e:
                    logger.debug(
                        "imap_logout_failed",
                        error_type=type(e).__name__,
                    )

        return result

    # ========================================================================
    # Email Parsing
    # ========================================================================

    def _parse_email(self, uid: int, raw_email: bytes) -> ParsedEmail:
        """Parst eine rohe E-Mail.

        Args:
            uid: IMAP UID
            raw_email: Rohe Email-Bytes

        Returns:
            ParsedEmail Objekt
        """
        msg = email.message_from_bytes(raw_email)

        # Headers extrahieren
        message_id = msg.get("Message-ID", f"<unknown-{uid}>")
        from_addr = self._decode_header(msg.get("From", "")) or "(Kein Absender)"
        subject = self._decode_header(msg.get("Subject", "(Kein Betreff)"))

        # Datum parsen
        date = None
        date_str = msg.get("Date")
        if date_str:
            try:
                date = parsedate_to_datetime(date_str)
            except Exception as e:
                logger.debug(
                    "email_date_parsing_fallback",
                    uid=uid,
                    error_type=type(e).__name__,
                )
                date = datetime.now(timezone.utc)

        # Body und Anhaenge extrahieren
        body_text = None
        body_html = None
        attachments = []

        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition", ""))

            # Text-Body
            if content_type == "text/plain" and "attachment" not in content_disposition:
                try:
                    body_text = part.get_payload(decode=True).decode(
                        part.get_content_charset() or "utf-8", errors="replace"
                    )
                except Exception as e:
                    logger.debug(
                        "email_text_body_decode_failed",
                        uid=uid,
                        error_type=type(e).__name__,
                    )

            # HTML-Body
            elif content_type == "text/html" and "attachment" not in content_disposition:
                try:
                    body_html = part.get_payload(decode=True).decode(
                        part.get_content_charset() or "utf-8", errors="replace"
                    )
                except Exception as e:
                    logger.debug(
                        "email_html_body_decode_failed",
                        uid=uid,
                        error_type=type(e).__name__,
                    )

            # Anhang
            elif "attachment" in content_disposition or part.get_filename():
                attachment = self._extract_attachment(part)
                if attachment:
                    attachments.append(attachment)

        return ParsedEmail(
            uid=uid,
            message_id=message_id,
            from_address=from_addr,
            subject=subject,
            date=date,
            attachments=attachments,
            body_text=body_text,
            body_html=body_html,
        )

    def _decode_header(self, header: str) -> str:
        """Dekodiert einen E-Mail-Header.

        Args:
            header: Roher Header-String

        Returns:
            Dekodierter String
        """
        if not header:
            return ""

        decoded_parts = []
        for part, encoding in decode_header(header):
            if isinstance(part, bytes):
                decoded_parts.append(
                    part.decode(encoding or "utf-8", errors="replace")
                )
            else:
                decoded_parts.append(part)

        return " ".join(decoded_parts)

    def _extract_attachment(self, part: Message) -> Optional[EmailAttachment]:
        """Extrahiert einen Anhang aus einem Email-Part.

        Args:
            part: Email Message Part

        Returns:
            EmailAttachment oder None wenn ungültig
        """
        filename = part.get_filename()
        if not filename:
            return None

        # Filename dekodieren
        filename = self._decode_header(filename)

        # Dateiendung prüfen
        extension = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if extension not in ALLOWED_EXTENSIONS:
            logger.debug(
                "attachment_extension_not_allowed",
                filename=filename,
                extension=extension,
            )
            return None

        # Content extrahieren
        try:
            content = part.get_payload(decode=True)
            if not content:
                return None
        except Exception:
            return None

        # Größe prüfen
        if len(content) > MAX_ATTACHMENT_SIZE:
            logger.warning(
                "attachment_too_large",
                filename=filename,
                size=len(content),
                max_size=MAX_ATTACHMENT_SIZE,
            )
            return None

        # MIME-Type prüfen
        mime_type = part.get_content_type()
        if mime_type not in ALLOWED_MIME_TYPES:
            # Fallback: Extension-basierte Erkennung
            mime_map = {
                ".pdf": "application/pdf",
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".tiff": "image/tiff",
                ".tif": "image/tiff",
            }
            mime_type = mime_map.get(extension, mime_type)
            if mime_type not in ALLOWED_MIME_TYPES:
                logger.debug(
                    "attachment_mime_not_allowed",
                    filename=filename,
                    mime_type=mime_type,
                )
                return None

        # Content-ID für Inline-Bilder
        content_id = part.get("Content-ID", "").strip("<>")

        return EmailAttachment(
            filename=filename,
            content=content,
            mime_type=mime_type,
            content_id=content_id or None,
        )

    # ========================================================================
    # Document Processing
    # ========================================================================

    async def _process_attachment(
        self,
        config,
        email: ParsedEmail,
        attachment: EmailAttachment,
        batch_id: UUID,
        user_id: UUID,
    ) -> Dict:
        """Verarbeitet einen Anhang und erstellt ein Dokument.

        Args:
            config: EmailImportConfig
            email: ParsedEmail
            attachment: EmailAttachment
            batch_id: Batch-ID für Import-Log
            user_id: User-ID

        Returns:
            Dict mit Ergebnis (success, document_id, duplicate, error)
        """
        from app.db.models import ImportLog

        # Import-Log erstellen
        import_log = ImportLog(
            id=uuid4(),
            user_id=user_id,
            source_type="email",
            email_config_id=config.id,
            batch_id=batch_id,
            email_uid=email.uid,
            email_message_id=email.message_id,
            email_from=email.from_address[:255] if email.from_address else None,
            email_subject=email.subject[:500] if email.subject else None,
            email_date=email.date,
            original_filename=attachment.filename[:255],
            file_hash=attachment.file_hash,
            file_size=attachment.size,
            mime_type=attachment.mime_type,
            status="processing",
        )
        self.db.add(import_log)
        await self.db.flush()

        # Publish IMPORT_STARTED event
        try:
            event_bus = EventBus()
            await event_bus.publish_event(
                EventType.IMPORT_STARTED,
                payload={
                    "source_type": "email",
                    "config_id": str(config.id),
                    "filename": attachment.filename,
                    "file_size": attachment.size,
                    "email_from": email.from_address,
                    "email_subject": email.subject,
                },
                source="email_import",
            )
        except Exception:
            pass  # EventBus failures must not block imports

        try:
            # Duplikat-Check via File-Hash
            existing = await self._check_duplicate_by_hash(
                user_id, attachment.file_hash
            )
            if existing:
                import_log.status = "skipped"
                import_log.error_code = "duplicate"
                import_log.error_message = f"Duplikat von Dokument {existing}"
                await self.db.commit()
                return {"duplicate": True, "existing_document_id": existing}

            # Malware-Scan
            if not await self._scan_attachment(attachment):
                import_log.status = "failed"
                import_log.error_code = "malware_detected"
                import_log.error_message = "Potenzielle Schadsoftware erkannt"
                await self.db.commit()
                return {"success": False, "error": "Malware detected"}

            # Dokument erstellen
            document_id = await self._create_document(
                user_id=user_id,
                config=config,
                email=email,
                attachment=attachment,
            )

            # Entity-Matching via EmailSenderMatcher
            await self._match_and_link_entity(
                document_id=document_id,
                email=email,
                user_id=user_id,
            )

            # Import Rules ausführen
            await self._apply_import_rules(
                document_id=document_id,
                email=email,
                attachment=attachment,
                config=config,
                user_id=user_id,
            )

            # E-Rechnung (ZUGFeRD/Factur-X/XRechnung) aus PDF/XML automatisch
            # extrahieren + mit dem Dokument verknuepfen (best-effort).
            await self._extract_einvoice_if_present(
                document_id=document_id,
                attachment=attachment,
                user_id=user_id,
            )

            # Import-Log aktualisieren
            import_log.status = "completed"
            import_log.document_id = document_id
            import_log.completed_at = datetime.now(timezone.utc)
            import_log.processing_duration_ms = int(
                (datetime.now(timezone.utc) - import_log.started_at).total_seconds() * 1000
            )

            # Publish IMPORT_COMPLETED event
            try:
                await event_bus.publish_event(
                    EventType.IMPORT_COMPLETED,
                    payload={
                        "source_type": "email",
                        "config_id": str(config.id),
                        "document_id": str(document_id),
                        "filename": attachment.filename,
                        "processing_duration_ms": import_log.processing_duration_ms,
                    },
                    source="email_import",
                )
            except Exception:
                pass

            await self.db.commit()

            return {"success": True, "document_id": document_id}

        except Exception as e:
            import_log.status = "failed"
            import_log.error_message = safe_error_detail(e, "Email")
            await self.db.commit()

            # Publish IMPORT_FAILED event
            try:
                await event_bus.publish_event(
                    EventType.IMPORT_FAILED,
                    payload={
                        "source_type": "email",
                        "config_id": str(config.id),
                        "filename": attachment.filename,
                        "error": str(e),
                    },
                    source="email_import",
                )
            except Exception:
                pass

            return {"success": False, **safe_error_log(e)}

    async def _extract_einvoice_if_present(
        self,
        document_id: UUID,
        attachment: EmailAttachment,
        user_id: UUID,
    ) -> None:
        """Best-effort E-Rechnungs-Extraktion aus einem PDF/XML-Anhang.

        Versucht, eingebettete strukturierte Rechnungsdaten (ZUGFeRD/Factur-X im
        PDF, oder XRechnung-XML) zu parsen und als EInvoiceDocument mit dem
        Dokument zu verknuepfen. Schliesst die OPEN-44-Luecke: ein per E-Mail
        empfangenes ZUGFeRD-PDF wird nicht mehr nur als Plain-PDF abgelegt.

        DARF DEN E-MAIL-IMPORT NIEMALS BRECHEN: vollstaendig geguarded. Bei
        Nicht-E-Rechnungen ein No-Op (parser_service liefert success=False;
        parse_and_store flush't dann nichts). parse_and_store committet nicht
        selbst -> der EInvoiceDocument-Eintrag wird vom aeusseren commit
        persistiert.
        """
        fname = (attachment.filename or "").lower()
        if not (fname.endswith(".pdf") or fname.endswith(".xml")):
            return
        try:
            from app.services.einvoice.parser_service import get_parser_service

            parser = get_parser_service()
            result = await parser.parse_and_store(
                file_content=attachment.content,
                filename=attachment.filename,
                document_id=document_id,
                db=self.db,
                user_id=user_id,
            )
            if getattr(result, "success", False):
                fmt = getattr(result, "format_detected", None)
                logger.info(
                    "email_import_einvoice_extracted",
                    document_id=str(document_id),
                    format=getattr(fmt, "value", None),
                )
        except Exception as e:
            # E-Rechnungs-Extraktion ist reine Anreicherung - Fehler nicht fatal
            # fuer den Import. Sichtbar loggen statt still schlucken.
            logger.warning(
                "email_import_einvoice_extraction_failed",
                document_id=str(document_id),
                **safe_error_log(e),
            )

    async def _check_duplicate_by_hash(
        self, user_id: UUID, file_hash: str
    ) -> Optional[UUID]:
        """Prüft ob ein Dokument mit gleichem Hash bereits existiert.

        Args:
            user_id: User-ID
            file_hash: SHA256 Hash des Dateiinhalts

        Returns:
            Document-ID wenn Duplikat existiert, sonst None
        """
        from app.db.models import Document

        result = await self.db.execute(
            select(Document.id).where(
                and_(
                    Document.owner_id == user_id,
                    Document.checksum == file_hash,
                )
            ).limit(1)
        )
        existing = result.scalar_one_or_none()
        return existing

    async def _scan_attachment(self, attachment: EmailAttachment) -> bool:
        """Scannt Anhang auf Malware.

        Args:
            attachment: EmailAttachment

        Returns:
            True wenn sicher, False wenn Malware erkannt
        """
        try:
            result = await scan_content(
                content=attachment.content,
                filename=attachment.filename,
            )
            return result.get("is_safe", False)
        except Exception as e:
            logger.warning(
                "malware_scan_failed",
                filename=attachment.filename,
                **safe_error_log(e),
            )
            # Bei Scan-Fehler: Konservativ ablehnen
            return False

    async def _create_document(
        self,
        user_id: UUID,
        config,
        email: ParsedEmail,
        attachment: EmailAttachment,
    ) -> UUID:
        """Erstellt ein Dokument aus einem Anhang.

        Args:
            user_id: User-ID
            config: EmailImportConfig
            email: ParsedEmail
            attachment: EmailAttachment

        Returns:
            Document-ID
        """
        from app.services.document_service import DocumentService
        from app.services.storage_service import StorageService

        # Storage Service für MinIO Upload
        storage = StorageService()

        # Datei in MinIO speichern
        storage_path = await storage.upload_document(
            content=attachment.content,
            filename=attachment.filename,
            user_id=user_id,
            mime_type=attachment.mime_type,
        )

        # Document Service für DB-Eintrag
        doc_service = DocumentService(self.db)

        # Metadaten aus Email extrahieren
        metadata = {
            "import_source": "email",
            "email_from": email.from_address,
            "email_subject": email.subject,
            "email_date": email.date.isoformat() if email.date else None,
            "email_message_id": email.message_id,
        }

        # Dokument erstellen
        document = await doc_service.create(
            user_id=user_id,
            filename=attachment.filename,
            storage_path=storage_path,
            mime_type=attachment.mime_type,
            file_size=attachment.size,
            file_hash=attachment.file_hash,
            folder_id=config.default_folder_id,
            metadata=metadata,
            auto_classify=config.auto_classify,
            auto_ocr=config.auto_ocr,
        )

        return document.id

    async def _match_and_link_entity(
        self,
        document_id: UUID,
        email: ParsedEmail,
        user_id: UUID,
    ) -> None:
        """Matcht Email-Absender gegen BusinessEntities und verknüpft das Dokument.

        Verwendet den EmailSenderMatcherService für intelligentes Matching:
        - Bei Confidence >= 85%: Automatische Verknüpfung mit Entity
        - Bei Confidence < 85%: Speichert Vorschläge in Metadaten

        Args:
            document_id: ID des erstellten Dokuments
            email: ParsedEmail mit Absender-Informationen
            user_id: User-ID für Berechtigungsprüfung
        """
        from app.services.imports import get_email_sender_matcher
        from app.db.models import Document

        try:
            # EmailSenderMatcher mit User-spezifischen Settings laden
            matcher = await get_email_sender_matcher(self.db, user_id)

            # Matching durchführen
            match_result = await matcher.match_sender(
                from_address=email.from_address,
                subject=email.subject,
            )

            logger.info(
                "email_entity_match_result",
                document_id=str(document_id),
                entity_id=str(match_result.entity_id) if match_result.entity_id else None,
                confidence=match_result.confidence,
                strategy=match_result.match_strategy,
            )

            # Dokument aktualisieren
            if match_result.entity_id and match_result.confidence >= 0.85:
                # Hohe Confidence: Automatisch verknüpfen
                await self.db.execute(
                    update(Document).where(Document.id == document_id).values(
                        entity_id=match_result.entity_id,
                        metadata=Document.metadata.concat({
                            "entity_match": {
                                "auto_linked": True,
                                "confidence": match_result.confidence,
                                "strategy": match_result.match_strategy,
                                "details": match_result.match_details,
                            }
                        })
                    )
                )
                logger.info(
                    "document_auto_linked_to_entity",
                    document_id=str(document_id),
                    entity_id=str(match_result.entity_id),
                    entity_name=match_result.entity_name,
                    confidence=match_result.confidence,
                )

            elif match_result.suggestions:
                # Niedrige Confidence aber Vorschläge vorhanden: Speichern für Validierung
                suggestions_data = [
                    {
                        "entity_id": str(s.entity_id),
                        "entity_name": s.entity_name,
                        "entity_type": s.entity_type,
                        "confidence": s.confidence,
                        "match_reason": s.match_reason,
                    }
                    for s in match_result.suggestions[:3]  # Max 3 Vorschläge
                ]

                await self.db.execute(
                    update(Document).where(Document.id == document_id).values(
                        metadata=Document.metadata.concat({
                            "entity_suggestions": suggestions_data,
                            "entity_match": {
                                "auto_linked": False,
                                "confidence": match_result.confidence,
                                "strategy": match_result.match_strategy,
                                "needs_validation": True,
                            }
                        })
                    )
                )
                logger.info(
                    "document_entity_suggestions_saved",
                    document_id=str(document_id),
                    suggestion_count=len(suggestions_data),
                )

        except Exception as e:
            # Fehler im Matching sollte Import nicht blockieren
            logger.warning(
                "email_entity_matching_failed",
                document_id=str(document_id),
                **safe_error_log(e),
            )

    async def _apply_import_rules(
        self,
        document_id: UUID,
        email: ParsedEmail,
        attachment: EmailAttachment,
        config,
        user_id: UUID,
    ) -> None:
        """Wendet Import-Regeln auf das erstellte Dokument an.

        Args:
            document_id: ID des erstellten Dokuments
            email: ParsedEmail mit Absender-Informationen
            attachment: EmailAttachment
            config: EmailImportConfig
            user_id: User-ID
        """
        from app.services.imports import ImportRuleService
        from app.db.models import Document

        try:
            rule_service = ImportRuleService(self.db)

            # Metadaten für Rule-Matching aufbauen
            metadata = {
                "sender_email": email.from_address,
                "sender_name": self._extract_display_name(email.from_address),
                "subject": email.subject,
                "email_date": email.date.isoformat() if email.date else None,
                "filename": attachment.filename,
                "file_extension": self._get_file_extension(attachment.filename),
                "file_size": attachment.size,
                "mime_type": attachment.mime_type,
            }

            # Regeln evaluieren
            matches = await rule_service.evaluate_rules(
                user_id=user_id,
                metadata=metadata,
                source_type="email",
                config_id=config.id,
            )

            if not matches:
                logger.debug(
                    "no_import_rules_matched",
                    document_id=str(document_id),
                )
                return

            # Aktionen konsolidieren
            actions = rule_service.apply_actions(matches)

            logger.info(
                "import_rules_matched",
                document_id=str(document_id),
                rule_count=len(matches),
                actions=list(actions.keys()),
            )

            # Publish IMPORT_RULE_APPLIED event
            try:
                rule_event_bus = EventBus()
                await rule_event_bus.publish_event(
                    EventType.IMPORT_RULE_APPLIED,
                    payload={
                        "source_type": "email",
                        "document_id": str(document_id),
                        "rule_count": len(matches),
                        "actions": list(actions.keys()),
                    },
                    source="email_import",
                )
            except Exception:
                pass

            # Aktionen anwenden
            await self._execute_rule_actions(
                document_id=document_id,
                actions=actions,
                user_id=user_id,
            )

        except Exception as e:
            # Fehler in Import Rules sollte Import nicht blockieren
            logger.warning(
                "import_rules_execution_failed",
                document_id=str(document_id),
                **safe_error_log(e),
            )

    async def _execute_rule_actions(
        self,
        document_id: UUID,
        actions: Dict,
        user_id: UUID,
    ) -> None:
        """Führt die konsolidierten Rule-Actions aus.

        Args:
            document_id: Dokument-ID
            actions: Konsolidierte Aktionen
            user_id: User-ID
        """
        from app.db.models import Document

        update_values = {}
        metadata_updates = {}

        for action_key, action_value in actions.items():
            if action_key == "assign_folder_id" and action_value:
                # Ordner-Zuweisung
                try:
                    update_values["folder_id"] = UUID(str(action_value))
                    logger.info(
                        "rule_action_assign_folder",
                        document_id=str(document_id),
                        folder_id=str(action_value),
                    )
                except ValueError:
                    logger.warning(
                        "invalid_folder_id_in_rule",
                        action_value=action_value,
                    )

            elif action_key == "assign_tags" and action_value:
                # Tags hinzufuegen (als Metadata)
                if isinstance(action_value, list):
                    metadata_updates["rule_tags"] = action_value
                    logger.info(
                        "rule_action_assign_tags",
                        document_id=str(document_id),
                        tags=action_value,
                    )

            elif action_key == "assign_document_type" and action_value:
                # Dokumenttyp setzen
                update_values["document_type"] = action_value
                logger.info(
                    "rule_action_assign_document_type",
                    document_id=str(document_id),
                    document_type=action_value,
                )

            elif action_key == "skip_ocr" and action_value:
                # OCR überspringen (via Metadata)
                metadata_updates["skip_ocr"] = True
                logger.info(
                    "rule_action_skip_ocr",
                    document_id=str(document_id),
                )

            elif action_key == "priority_ocr" and action_value:
                # Prioritäts-OCR (via Metadata)
                metadata_updates["priority_ocr"] = True
                logger.info(
                    "rule_action_priority_ocr",
                    document_id=str(document_id),
                )

            elif action_key == "set_status" and action_value:
                update_values["status"] = action_value
                logger.info(
                    "rule_action_set_status",
                    document_id=str(document_id),
                    status=action_value,
                )

            elif action_key == "add_metadata" and action_value:
                # Zusätzliche Metadaten
                if isinstance(action_value, dict):
                    metadata_updates.update(action_value)

            elif action_key == "notify_users" and action_value:
                metadata_updates["notify_users"] = action_value
                # Dispatch actual notifications via AlertCenter
                try:
                    from app.services.alert_center_service import AlertCenterService
                    from app.db.models_alert import AlertCategory, AlertSeverity
                    alert_service = AlertCenterService(self.db)
                    user_ids = action_value if isinstance(action_value, list) else [action_value]
                    for uid in user_ids:
                        await alert_service.create_alert(
                            company_id=UUID(str(uid)),
                            alert_code="WORK_003",
                            category=AlertCategory.WORKFLOW,
                            severity=AlertSeverity.LOW,
                            title="Import-Regel ausgeloest",
                            message=f"Dokument {document_id} wurde durch eine Import-Regel verarbeitet.",
                            source_type="email_import",
                            source_id=str(document_id),
                            document_id=document_id,
                            assigned_to_id=UUID(str(uid)),
                            metadata={"source": "email_import"},
                        )
                except Exception as e:
                    logger.warning(
                        "notify_users_dispatch_failed",
                        document_id=str(document_id),
                        error=str(e),
                    )

        # Dokument aktualisieren
        if update_values or metadata_updates:
            stmt = update(Document).where(Document.id == document_id)

            if update_values:
                stmt = stmt.values(**update_values)

            if metadata_updates:
                stmt = stmt.values(
                    metadata=Document.metadata.concat({
                        "import_rule_actions": metadata_updates
                    })
                )

            await self.db.execute(stmt)
            logger.info(
                "document_updated_by_rules",
                document_id=str(document_id),
                update_fields=list(update_values.keys()),
                metadata_fields=list(metadata_updates.keys()),
            )

    def _extract_display_name(self, from_address: str) -> Optional[str]:
        """Extrahiert den Display-Namen aus einer E-Mail-Adresse.

        Args:
            from_address: z.B. "Max Müller <max@example.com>"

        Returns:
            Display-Name oder None
        """
        if not from_address:
            return None

        # Pattern: "Name <email>" oder nur "email"
        match = re.match(r'^"?([^"<]+)"?\s*<', from_address)
        if match:
            return match.group(1).strip()
        return None

    def _get_file_extension(self, filename: str) -> str:
        """Extrahiert die Dateiendung.

        Args:
            filename: Dateiname

        Returns:
            Dateiendung mit Punkt (z.B. ".pdf") oder leer
        """
        if not filename or "." not in filename:
            return ""
        return "." + filename.rsplit(".", 1)[-1].lower()

    # ========================================================================
    # CRUD Operations
    # ========================================================================

    async def create_config(
        self,
        user_id: UUID,
        name: str,
        imap_server: str,
        imap_port: int,
        username: str,
        password: str,
        use_ssl: bool = True,
        use_starttls: bool = False,
        imap_folder: str = "INBOX",
        processed_folder: Optional[str] = None,
        error_folder: Optional[str] = None,
        sync_interval_minutes: int = 15,
        filter_from_addresses: Optional[List[str]] = None,
        filter_subject_patterns: Optional[List[str]] = None,
        filter_attachment_types: Optional[List[str]] = None,
        extract_attachments_only: bool = True,
        include_email_body_as_document: bool = False,
        auto_classify: bool = True,
        auto_ocr: bool = True,
        default_folder_id: Optional[UUID] = None,
        company_id: Optional[UUID] = None,
    ) -> UUID:
        """Erstellt eine neue Email-Import-Konfiguration.

        Args:
            user_id: User-ID
            name: Konfigurations-Name
            imap_server: IMAP Server Hostname
            imap_port: IMAP Port
            username: IMAP Username
            password: IMAP Passwort (Klartext - wird verschlüsselt)
            use_ssl: SSL verwenden
            use_starttls: STARTTLS verwenden
            imap_folder: IMAP Ordner
            processed_folder: Ordner für verarbeitete Emails
            error_folder: Ordner für fehlerhafte Emails
            sync_interval_minutes: Sync-Intervall
            filter_from_addresses: Filter für Absender
            filter_subject_patterns: Filter für Betreff
            filter_attachment_types: Filter für Anhangs-Typen
            extract_attachments_only: Nur Anhaenge importieren
            include_email_body_as_document: Email-Body als Dokument speichern
            auto_classify: Automatisch klassifizieren
            auto_ocr: Automatisch OCR ausführen
            default_folder_id: Standard-Ordner für Dokumente
            company_id: Firma-ID

        Returns:
            Config-ID
        """
        from app.db.models import EmailImportConfig

        config_id = uuid4()

        # Credentials verschlüsseln
        username_encrypted = encrypt_data(
            username,
            associated_data=f"email_config:{config_id}"
        )
        password_encrypted = encrypt_data(
            password,
            associated_data=f"email_config:{config_id}"
        )

        config = EmailImportConfig(
            id=config_id,
            user_id=user_id,
            company_id=company_id,
            name=name,
            imap_server=imap_server,
            imap_port=imap_port,
            use_ssl=use_ssl,
            use_starttls=use_starttls,
            username_encrypted=username_encrypted,
            password_encrypted=password_encrypted,
            imap_folder=imap_folder,
            processed_folder=processed_folder,
            error_folder=error_folder,
            sync_interval_minutes=sync_interval_minutes,
            filter_from_addresses=filter_from_addresses or [],
            filter_subject_patterns=filter_subject_patterns or [],
            filter_attachment_types=filter_attachment_types or [],
            extract_attachments_only=extract_attachments_only,
            include_email_body_as_document=include_email_body_as_document,
            auto_classify=auto_classify,
            auto_ocr=auto_ocr,
            default_folder_id=default_folder_id,
            is_active=True,
            connection_status="pending",
        )

        self.db.add(config)
        await self.db.commit()

        logger.info(
            "email_config_created",
            config_id=str(config_id),
            user_id=str(user_id),
            imap_server=imap_server,
        )

        return config_id

    async def update_config(
        self,
        config_id: UUID,
        user_id: UUID,
        **updates,
    ) -> bool:
        """Aktualisiert eine Email-Import-Konfiguration.

        Args:
            config_id: Config-ID
            user_id: User-ID für Berechtigungsprüfung
            **updates: Zu aktualisierende Felder

        Returns:
            True wenn erfolgreich
        """
        from app.db.models import EmailImportConfig

        config = await self._get_config(config_id, user_id)
        if not config:
            return False

        # Passwort separat behandeln (verschlüsseln)
        if "password" in updates:
            updates["password_encrypted"] = encrypt_data(
                updates.pop("password"),
                associated_data=f"email_config:{config_id}"
            )

        # Username separat behandeln
        if "username" in updates:
            updates["username_encrypted"] = encrypt_data(
                updates.pop("username"),
                associated_data=f"email_config:{config_id}"
            )

        # Updates anwenden
        for key, value in updates.items():
            if hasattr(config, key):
                setattr(config, key, value)

        await self.db.commit()

        logger.info(
            "email_config_updated",
            config_id=str(config_id),
            updated_fields=list(updates.keys()),
        )

        return True

    async def delete_config(
        self,
        config_id: UUID,
        user_id: UUID,
    ) -> bool:
        """Löscht eine Email-Import-Konfiguration.

        Args:
            config_id: Config-ID
            user_id: User-ID für Berechtigungsprüfung

        Returns:
            True wenn erfolgreich
        """
        from app.db.models import EmailImportConfig

        config = await self._get_config(config_id, user_id)
        if not config:
            return False

        await self.db.delete(config)
        await self.db.commit()

        logger.info(
            "email_config_deleted",
            config_id=str(config_id),
        )

        return True

    async def get_config(
        self,
        config_id: UUID,
        user_id: UUID,
    ) -> Optional[Dict]:
        """Holt eine Email-Import-Konfiguration.

        Args:
            config_id: Config-ID
            user_id: User-ID für Berechtigungsprüfung

        Returns:
            Config-Dict (ohne Credentials) oder None
        """
        config = await self._get_config(config_id, user_id)
        if not config:
            return None

        return {
            "id": config.id,
            "name": config.name,
            "imap_server": config.imap_server,
            "imap_port": config.imap_port,
            "use_ssl": config.use_ssl,
            "use_starttls": config.use_starttls,
            "imap_folder": config.imap_folder,
            "processed_folder": config.processed_folder,
            "error_folder": config.error_folder,
            "sync_interval_minutes": config.sync_interval_minutes,
            "filter_from_addresses": config.filter_from_addresses,
            "filter_subject_patterns": config.filter_subject_patterns,
            "filter_attachment_types": config.filter_attachment_types,
            "extract_attachments_only": config.extract_attachments_only,
            "include_email_body_as_document": config.include_email_body_as_document,
            "auto_classify": config.auto_classify,
            "auto_ocr": config.auto_ocr,
            "default_folder_id": config.default_folder_id,
            "company_id": config.company_id,
            "is_active": config.is_active,
            "connection_status": config.connection_status,
            "last_sync_at": config.last_sync_at,
            "last_uid": config.last_uid,
            "total_emails_processed": config.total_emails_processed,
            "total_documents_created": config.total_documents_created,
            "last_error": config.last_error,
            "error_count": config.error_count,
            "created_at": config.created_at,
            "updated_at": config.updated_at,
        }

    async def list_configs(
        self,
        user_id: UUID,
        company_id: Optional[UUID] = None,
        active_only: bool = False,
    ) -> List[Dict]:
        """Listet alle Email-Import-Konfigurationen eines Users.

        Args:
            user_id: User-ID
            company_id: Optional Company-Filter
            active_only: Nur aktive Konfigurationen

        Returns:
            Liste von Config-Dicts
        """
        from app.db.models import EmailImportConfig

        query = select(EmailImportConfig).where(
            EmailImportConfig.user_id == user_id
        )

        if company_id:
            query = query.where(EmailImportConfig.company_id == company_id)

        if active_only:
            query = query.where(EmailImportConfig.is_active == True)

        query = query.order_by(EmailImportConfig.created_at.desc())

        result = await self.db.execute(query)
        configs = result.scalars().all()

        return [
            {
                "id": c.id,
                "name": c.name,
                "imap_server": c.imap_server,
                "imap_folder": c.imap_folder,
                "is_active": c.is_active,
                "connection_status": c.connection_status,
                "last_sync_at": c.last_sync_at,
                "total_documents_created": c.total_documents_created,
            }
            for c in configs
        ]

    # ========================================================================
    # Helper Methods
    # ========================================================================

    async def _get_config(self, config_id: UUID, user_id: UUID):
        """Holt Config mit Berechtigungsprüfung."""
        from app.db.models import EmailImportConfig

        result = await self.db.execute(
            select(EmailImportConfig).where(
                and_(
                    EmailImportConfig.id == config_id,
                    EmailImportConfig.user_id == user_id,
                )
            )
        )
        return result.scalar_one_or_none()

    async def _update_connection_status(
        self,
        config_id: UUID,
        status: str,
        error: Optional[str],
    ) -> None:
        """Aktualisiert den Verbindungsstatus."""
        from app.db.models import EmailImportConfig

        values = {"connection_status": status}
        if error:
            values["last_error"] = error[:500]
            values["error_count"] = EmailImportConfig.error_count + 1
        else:
            values["last_error"] = None

        await self.db.execute(
            update(EmailImportConfig)
            .where(EmailImportConfig.id == config_id)
            .values(**values)
        )
        await self.db.commit()

    async def _update_sync_timestamp(self, config_id: UUID) -> None:
        """Aktualisiert den Sync-Timestamp."""
        from app.db.models import EmailImportConfig

        await self.db.execute(
            update(EmailImportConfig)
            .where(EmailImportConfig.id == config_id)
            .values(last_sync_at=datetime.now(timezone.utc))
        )
        await self.db.commit()

    async def _update_last_uid(self, config_id: UUID, uid: int) -> None:
        """Aktualisiert die letzte verarbeitete UID."""
        from app.db.models import EmailImportConfig

        await self.db.execute(
            update(EmailImportConfig)
            .where(EmailImportConfig.id == config_id)
            .values(last_uid=uid)
        )
        # Kein Commit - wird mit nächster Operation committed

    async def _update_stats(
        self,
        config_id: UUID,
        emails_processed: int,
        documents_created: int,
    ) -> None:
        """Aktualisiert die Statistiken."""
        from app.db.models import EmailImportConfig


        await self.db.execute(
            update(EmailImportConfig)
            .where(EmailImportConfig.id == config_id)
            .values(
                total_emails_processed=EmailImportConfig.total_emails_processed + emails_processed,
                total_documents_created=EmailImportConfig.total_documents_created + documents_created,
            )
        )
        await self.db.commit()
