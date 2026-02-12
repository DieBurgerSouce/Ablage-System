# -*- coding: utf-8 -*-
"""
EML/MSG Datei-Parser fuer Drag&Drop E-Mail-Import.

Parst .eml und .msg Dateien und extrahiert Metadaten und Anhaenge.
"""

import email
import email.header
import email.utils
import io
import mimetypes
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Tuple

import structlog

logger = structlog.get_logger(__name__)

# Max file size: 50MB
MAX_FILE_SIZE = 50 * 1024 * 1024
# Max body preview length
MAX_BODY_PREVIEW = 500
# Allowed MIME types for importable attachments
IMPORTABLE_MIME_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/tiff",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/csv",
    "text/plain",
}


@dataclass
class EmlAttachment:
    """Einzelner Anhang aus einer E-Mail-Datei."""

    index: int
    filename: str
    size: int
    mime_type: str
    content: bytes
    is_importable: bool


@dataclass
class ParsedEmail:
    """Ergebnis des E-Mail-Parsens."""

    subject: str
    sender: str
    sender_name: str
    date: Optional[datetime]
    body_preview: str
    attachments: List[EmlAttachment] = field(default_factory=list)
    message_id: Optional[str] = None


def validate_eml_file(content: bytes) -> Tuple[bool, str]:
    """Validiert eine .eml-Datei vor dem Parsen.

    Args:
        content: Rohe Datei-Bytes

    Returns:
        Tuple aus (ist_gueltig, fehlermeldung)
    """
    if len(content) > MAX_FILE_SIZE:
        return False, f"Datei zu gro\u00df (max. {MAX_FILE_SIZE // (1024 * 1024)}MB)"
    if len(content) < 20:
        return False, "Datei ist zu klein oder leer"
    # Check for basic email headers
    header_check = content[:1000].lower()
    if (
        b"from:" not in header_check
        and b"received:" not in header_check
        and b"mime-version:" not in header_check
    ):
        return False, "Keine g\u00fcltige E-Mail-Datei (fehlende Header)"
    return True, ""


def _decode_header(header_value: Optional[str]) -> str:
    """Dekodiert RFC 2047 kodierte E-Mail-Header.

    Args:
        header_value: Roher Header-String

    Returns:
        Dekodierter String
    """
    if not header_value:
        return ""
    decoded_parts = email.header.decode_header(header_value)
    result_parts: List[str] = []
    for part, charset in decoded_parts:
        if isinstance(part, bytes):
            result_parts.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            result_parts.append(str(part))
    return " ".join(result_parts)


def _extract_body_preview(msg: email.message.Message) -> str:
    """Extrahiert eine Textvorschau aus der E-Mail.

    Args:
        msg: Geparste E-Mail-Nachricht

    Returns:
        Vorschautext (max. MAX_BODY_PREVIEW Zeichen)
    """
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    body = payload.decode(charset, errors="replace")
                    break
            elif content_type == "text/html" and not body:
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    html = payload.decode(charset, errors="replace")
                    body = re.sub(r"<[^>]+>", " ", html)
                    body = re.sub(r"\s+", " ", body).strip()
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            body = payload.decode(charset, errors="replace")

    return body[:MAX_BODY_PREVIEW].strip()


def _extract_attachments(msg: email.message.Message) -> List[EmlAttachment]:
    """Extrahiert Anh\u00e4nge aus einer E-Mail-Nachricht.

    Args:
        msg: Geparste E-Mail-Nachricht

    Returns:
        Liste der Anh\u00e4nge
    """
    attachments: List[EmlAttachment] = []
    idx = 0
    for part in msg.walk():
        content_disposition = str(part.get("Content-Disposition", ""))
        if "attachment" not in content_disposition and "inline" not in content_disposition:
            continue
        filename = part.get_filename()
        if not filename:
            continue
        filename = _decode_header(filename)
        payload = part.get_payload(decode=True)
        if not payload:
            continue
        mime_type = (
            part.get_content_type()
            or mimetypes.guess_type(filename)[0]
            or "application/octet-stream"
        )
        attachments.append(
            EmlAttachment(
                index=idx,
                filename=filename,
                size=len(payload),
                mime_type=mime_type,
                content=payload,
                is_importable=mime_type in IMPORTABLE_MIME_TYPES,
            )
        )
        idx += 1
    return attachments


def parse_eml_file(content: bytes) -> ParsedEmail:
    """Parst eine .eml-Datei und extrahiert Metadaten und Anh\u00e4nge.

    Args:
        content: Rohe .eml-Datei als Bytes

    Returns:
        ParsedEmail mit Metadaten und Anh\u00e4ngen
    """
    msg = email.message_from_bytes(content)

    subject = _decode_header(msg.get("Subject"))
    from_header = msg.get("From", "")
    sender_name, sender_email = email.utils.parseaddr(from_header)
    sender_name = _decode_header(sender_name) if sender_name else ""

    date_str = msg.get("Date")
    parsed_date: Optional[datetime] = None
    if date_str:
        try:
            parsed_date = email.utils.parsedate_to_datetime(date_str)
        except Exception as e:
            logger.debug(
                "eml_date_parsing_fallback",
                error_type=type(e).__name__,
            )

    message_id = msg.get("Message-ID")

    return ParsedEmail(
        subject=subject,
        sender=sender_email,
        sender_name=sender_name,
        date=parsed_date,
        body_preview=_extract_body_preview(msg),
        attachments=_extract_attachments(msg),
        message_id=message_id,
    )


def parse_msg_file(content: bytes) -> ParsedEmail:
    """Parst eine .msg-Datei (Outlook-Format).

    Erfordert die extract-msg Bibliothek.

    Args:
        content: Rohe .msg-Datei als Bytes

    Returns:
        ParsedEmail mit Metadaten und Anh\u00e4ngen

    Raises:
        ValueError: Wenn extract-msg nicht installiert ist
    """
    try:
        import extract_msg  # type: ignore[import-untyped]
    except ImportError:
        logger.warning(
            "extract_msg_nicht_installiert",
            hinweis=".msg-Dateien k\u00f6nnen nicht verarbeitet werden",
        )
        raise ValueError(
            "Verarbeitung von .msg-Dateien nicht verf\u00fcgbar "
            "(extract-msg nicht installiert)"
        )

    msg = extract_msg.Message(io.BytesIO(content))

    attachments: List[EmlAttachment] = []
    for idx, att in enumerate(msg.attachments):
        att_filename = att.longFilename or att.shortFilename or f"anhang_{idx}"
        mime_type = (
            mimetypes.guess_type(att_filename)[0] or "application/octet-stream"
        )
        data = att.data if isinstance(att.data, bytes) else b""
        attachments.append(
            EmlAttachment(
                index=idx,
                filename=att_filename,
                size=len(data),
                mime_type=mime_type,
                content=data,
                is_importable=mime_type in IMPORTABLE_MIME_TYPES,
            )
        )

    parsed_date: Optional[datetime] = None
    if msg.date:
        try:
            parsed_date = msg.date if isinstance(msg.date, datetime) else None
        except Exception:
            pass

    return ParsedEmail(
        subject=msg.subject or "",
        sender=msg.sender or "",
        sender_name=msg.sender or "",
        date=parsed_date,
        body_preview=(msg.body or "")[:MAX_BODY_PREVIEW].strip(),
        attachments=attachments,
        message_id=msg.messageId,
    )
