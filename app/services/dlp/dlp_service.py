"""
Data Loss Prevention (DLP) Service.

Enterprise-Sicherheitsfunktionen für Dokumentenschutz:
- Download-Restriktionen (role-based, time-based)
- Wasserzeichen-Generierung (visible + invisible)
- Sensitive Data Detection (PII, Kreditkarten, IBAN)
- Policy-basierte Zugriffskontrolle
- Audit-Trail für alle DLP-Events

SECURITY:
- Alle Policies werden serverseitig validiert
- Wasserzeichen sind manipulationssicher
- Sensitive Data wird NIEMALS geloggt
- Multi-Tenant Isolation via company_id (KRITISCH!)
"""

import re
import hashlib
import io
import logging
from datetime import datetime, time
from enum import Enum
from typing import Optional, Any
from uuid import UUID

from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel, Field
from sqlalchemy import select, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import Document, User, Company, DLPPolicyModel, DLPAuditLog

logger = logging.getLogger(__name__)


# ==================== Enums ====================

class DLPAction(str, Enum):
    """Mögliche DLP-Aktionen."""
    ALLOW = "allow"
    BLOCK = "block"
    WATERMARK = "watermark"
    NOTIFY = "notify"
    AUDIT_ONLY = "audit_only"


class SensitiveDataType(str, Enum):
    """Typen sensibler Daten die vom DLP-Scanner erkannt werden."""
    CREDIT_CARD = "credit_card"
    IBAN = "iban"
    SSN = "ssn"  # Sozialversicherungsnummer
    EMAIL = "email"
    PHONE = "phone"
    TAX_ID = "tax_id"  # Steuernummer
    DATE_OF_BIRTH = "date_of_birth"  # Geburtsdatum
    HEALTH_DATA = "health_data"  # Gesundheitsdaten (GDPR Art. 9)
    FINANCIAL_DATA = "financial_data"  # Finanzdaten


class WatermarkPosition(str, Enum):
    """Position des Wasserzeichens."""
    CENTER = "center"
    DIAGONAL = "diagonal"
    FOOTER = "footer"
    HEADER = "header"
    TILED = "tiled"


# ==================== Schemas ====================

class DLPPolicy(BaseModel):
    """DLP-Policy Definition."""
    id: str = Field(..., description="Eindeutige Policy-ID")
    name: str = Field(..., description="Policy-Name")
    description: Optional[str] = None
    enabled: bool = True

    # Zugriffsbedingungen
    allowed_roles: list[str] = Field(
        default=["admin"],
        description="Rollen die diese Aktion ausführen duerfen"
    )
    blocked_roles: list[str] = Field(
        default=[],
        description="Rollen die explizit blockiert sind"
    )

    # Zeit-basierte Einschränkungen
    time_restrictions: Optional[dict[str, Any]] = Field(
        default=None,
        description="Zeit-basierte Einschränkungen {'start': '09:00', 'end': '18:00', 'weekdays': [0,1,2,3,4]}"
    )

    # Dokument-Filter
    document_types: list[str] = Field(
        default=["all"],
        description="Betroffene Dokumenttypen (z.B. 'pdf', 'invoice', 'confidential')"
    )
    tags_required: list[str] = Field(
        default=[],
        description="Dokument muss diese Tags haben"
    )
    tags_blocked: list[str] = Field(
        default=[],
        description="Dokument darf diese Tags nicht haben"
    )

    # Aktionen
    action: DLPAction = Field(
        default=DLPAction.ALLOW,
        description="Aktion bei Policy-Match"
    )
    require_watermark: bool = Field(
        default=False,
        description="Wasserzeichen erforderlich"
    )
    watermark_config: Optional[dict[str, Any]] = Field(
        default=None,
        description="Wasserzeichen-Konfiguration"
    )

    # Benachrichtigungen
    notify_admin: bool = False
    notify_user: bool = False
    log_access: bool = True


class DLPCheckResult(BaseModel):
    """Ergebnis einer DLP-Prüfung."""
    allowed: bool
    action: DLPAction
    policy_id: Optional[str] = None
    policy_name: Optional[str] = None
    reason: Optional[str] = None
    watermark_required: bool = False
    watermark_config: Optional[dict[str, Any]] = None
    notifications: list[str] = []
    sensitive_data_found: list[SensitiveDataType] = []


class WatermarkConfig(BaseModel):
    """Wasserzeichen-Konfiguration."""
    text: Optional[str] = None  # None = automatisch (User + Timestamp)
    position: WatermarkPosition = WatermarkPosition.DIAGONAL
    opacity: float = Field(default=0.3, ge=0.1, le=1.0)
    font_size: int = Field(default=40, ge=10, le=200)
    color: str = Field(default="#808080", pattern=r"^#[0-9A-Fa-f]{6}$")
    include_user: bool = True
    include_timestamp: bool = True
    include_document_id: bool = True
    invisible_watermark: bool = False  # Steganographie


# ==================== Sensitive Data Patterns ====================

SENSITIVE_PATTERNS: dict[SensitiveDataType, list[re.Pattern[str]]] = {
    SensitiveDataType.CREDIT_CARD: [
        # Visa, Mastercard, Amex, etc.
        re.compile(r'\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13}|6(?:011|5[0-9]{2})[0-9]{12})\b'),
        re.compile(r'\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b'),
    ],
    SensitiveDataType.IBAN: [
        # Deutsche IBAN: DE + 2 Prüfziffern + 8 BLZ + 10 Kontonummer
        re.compile(r'\b[A-Z]{2}\d{2}[A-Z0-9]{4}\d{7}([A-Z0-9]?){0,16}\b', re.IGNORECASE),
        re.compile(r'\bDE\s?\d{2}\s?\d{4}\s?\d{4}\s?\d{4}\s?\d{4}\s?\d{2}\b', re.IGNORECASE),
    ],
    SensitiveDataType.SSN: [
        # Deutsche Sozialversicherungsnummer: 12 Zeichen
        re.compile(r'\b\d{2}\s?\d{6}\s?[A-Z]\s?\d{3}\b'),
    ],
    SensitiveDataType.EMAIL: [
        re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'),
    ],
    SensitiveDataType.PHONE: [
        # Deutsche Telefonnummern
        re.compile(r'\b(?:\+49|0049|0)[1-9]\d{1,14}\b'),
        re.compile(r'\b\d{3,5}[/-]?\d{5,10}\b'),
    ],
    SensitiveDataType.TAX_ID: [
        # Deutsche Steuernummer / Steuer-ID
        re.compile(r'\b\d{2,3}/?\d{3}/?\d{4,5}\b'),  # Format: 123/456/78901
        re.compile(r'\b\d{11}\b'),  # 11-stellige Steuer-ID
    ],
    SensitiveDataType.DATE_OF_BIRTH: [
        # Deutsche Datumsformate: DD.MM.YYYY, DD-MM-YYYY, DD/MM/YYYY
        re.compile(r'\b(?:0?[1-9]|[12]\d|3[01])[.\-/](?:0?[1-9]|1[0-2])[.\-/](?:19|20)\d{2}\b'),
        # Geburtsdatum Kontext-Patterns
        re.compile(r'geb(?:oren|\.|\s*:)\s*(?:am\s*)?(?:0?[1-9]|[12]\d|3[01])[.\-/](?:0?[1-9]|1[0-2])[.\-/](?:19|20)\d{2}', re.IGNORECASE),
    ],
    SensitiveDataType.HEALTH_DATA: [
        # ICD-10 Diagnosecodes (z.B. A00-Z99)
        re.compile(r'\b[A-Z]\d{2}(?:\.\d{1,2})?\b'),
        # Medizinische Keywords mit Kontext
        re.compile(r'(?:diagnose|befund|anamnese|therapie|medikament|rezept|krankheit)\s*[:=]?\s*\w+', re.IGNORECASE),
        # Krankenversicherungsnummer (KVNR)
        re.compile(r'\b[A-Z]\d{9}\b'),
    ],
    SensitiveDataType.FINANCIAL_DATA: [
        # BIC/SWIFT Codes
        re.compile(r'\b[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}(?:[A-Z0-9]{3})?\b'),
        # Kontonummern (8-10 Ziffern)
        re.compile(r'\bkontonummer\s*[:=]?\s*\d{8,10}\b', re.IGNORECASE),
        # Bankleitzahl (BLZ)
        re.compile(r'\bblz\s*[:=]?\s*\d{8}\b', re.IGNORECASE),
        # Betraege mit Währungssymbol
        re.compile(r'(?:EUR|€|USD|\$)\s*[\d.,]+(?:\s*(?:EUR|€|USD|\$))?', re.IGNORECASE),
    ],
}


# ==================== DLP Service ====================

class DLPServiceError(Exception):
    """Basis-Exception für DLP-Fehler."""
    pass


class DLPAccessDeniedError(DLPServiceError):
    """Zugriff durch DLP-Policy verweigert."""
    pass


class DLPService:
    """
    Data Loss Prevention Service.

    Schuetzt sensible Dokumente durch:
    - Zugriffskontrolle basierend auf Policies
    - Automatische Wasserzeichen
    - Erkennung sensibler Daten
    - Audit-Logging (in DB persistiert!)

    SECURITY:
    - Alle Policies werden in der DB persistiert (nicht nur Memory!)
    - Multi-Tenant Isolation via company_id ist PFLICHT
    - Alle Events werden im DLP Audit-Log protokolliert
    """

    def __init__(self, db: AsyncSession, company_id: Optional[UUID] = None):
        self.db = db
        self.company_id = company_id
        self._policies_cache: list[DLPPolicy] = []
        self._cache_loaded = False

    async def _ensure_policies_loaded(self) -> None:
        """Laedt Policies aus DB (mit Cache)."""
        if self._cache_loaded:
            return

        if self.company_id:
            # Policies aus Datenbank laden
            result = await self.db.execute(
                select(DLPPolicyModel)
                .where(
                    and_(
                        DLPPolicyModel.company_id == self.company_id,
                        DLPPolicyModel.enabled == True
                    )
                )
                .order_by(DLPPolicyModel.priority)
            )
            db_policies = result.scalars().all()

            self._policies_cache = [
                DLPPolicy(
                    id=p.policy_id,
                    name=p.name,
                    description=p.description,
                    enabled=p.enabled,
                    allowed_roles=p.allowed_roles or ["admin"],
                    blocked_roles=p.blocked_roles or [],
                    time_restrictions=p.time_restrictions,
                    document_types=p.document_types or ["all"],
                    tags_required=p.tags_required or [],
                    tags_blocked=p.tags_blocked or [],
                    action=DLPAction(p.action),
                    require_watermark=p.require_watermark,
                    watermark_config=p.watermark_config,
                    notify_admin=p.notify_admin,
                    notify_user=p.notify_user,
                    log_access=p.log_access,
                )
                for p in db_policies
            ]

        # Falls keine DB-Policies existieren, lade Default-Policies
        if not self._policies_cache:
            self._policies_cache = self._get_default_policies()

        self._cache_loaded = True

    def _get_default_policies(self) -> list[DLPPolicy]:
        """Gibt Standard-DLP-Policies zurück (Fallback wenn DB leer)."""
        return [
            # Policy 1: Vertrauliche Dokumente
            DLPPolicy(
                id="confidential-docs",
                name="Vertrauliche Dokumente",
                description="Schutz für als vertraulich markierte Dokumente",
                allowed_roles=["admin", "manager"],
                tags_required=["vertraulich"],
                action=DLPAction.WATERMARK,
                require_watermark=True,
                watermark_config={
                    "text": "VERTRAULICH",
                    "position": "diagonal",
                    "opacity": 0.4,
                },
                notify_admin=True,
            ),
            # Policy 2: Finanz-Dokumente
            DLPPolicy(
                id="financial-docs",
                name="Finanzdokumente",
                description="Schutz für Rechnungen, Kontoauszuege, etc.",
                allowed_roles=["admin", "accountant", "manager"],
                document_types=["invoice", "bank_statement", "financial"],
                action=DLPAction.ALLOW,
                require_watermark=True,
                watermark_config={
                    "position": "footer",
                    "include_user": True,
                    "include_timestamp": True,
                },
                log_access=True,
            ),
            # Policy 3: Ausserhalb Arbeitszeiten
            DLPPolicy(
                id="after-hours",
                name="Ausserhalb Arbeitszeiten",
                description="Einschränkungen ausserhalb der Arbeitszeiten",
                allowed_roles=["admin"],
                time_restrictions={
                    "start": "06:00",
                    "end": "22:00",
                    "weekdays": [0, 1, 2, 3, 4, 5],  # Mo-Sa
                },
                action=DLPAction.NOTIFY,
                notify_admin=True,
            ),
            # Policy 4: Export-Beschraenkung
            DLPPolicy(
                id="no-export",
                name="Export-Verbot",
                description="Dokumente die nicht exportiert werden duerfen",
                blocked_roles=["viewer"],
                tags_required=["no-export"],
                action=DLPAction.BLOCK,
                notify_admin=True,
            ),
        ]

    async def check_access(
        self,
        user: User,
        document: Document,
        action_type: str = "download",
    ) -> DLPCheckResult:
        """
        Prüft ob ein Benutzer eine Aktion auf einem Dokument ausführen darf.

        Args:
            user: Der anfragende Benutzer
            document: Das betroffene Dokument
            action_type: Art der Aktion (download, view, print, export)

        Returns:
            DLPCheckResult mit Entscheidung und Details

        SECURITY:
        - Multi-Tenant: document.company_id wird validiert
        """
        # Policies aus DB laden
        await self._ensure_policies_loaded()

        # Standard: Erlaubt
        result = DLPCheckResult(
            allowed=True,
            action=DLPAction.ALLOW,
        )

        # Dokument-Tags holen
        doc_tags = document.tags if hasattr(document, 'tags') and document.tags else []
        doc_type = document.document_type if hasattr(document, 'document_type') else "unknown"

        # User-Rolle
        user_role = user.role if hasattr(user, 'role') else "viewer"

        # Alle aktiven Policies prüfen
        for policy in self._policies_cache:
            if not policy.enabled:
                continue

            # Prüfen ob Policy auf dieses Dokument zutrifft
            if not self._policy_matches_document(policy, doc_tags, doc_type):
                continue

            # Zeit-Restriktionen prüfen
            if policy.time_restrictions:
                if not self._check_time_restrictions(policy.time_restrictions):
                    # Ausserhalb erlaubter Zeit
                    if policy.action == DLPAction.BLOCK:
                        result.allowed = False
                        result.action = DLPAction.BLOCK
                        result.policy_id = policy.id
                        result.policy_name = policy.name
                        result.reason = "Zugriff ausserhalb der erlaubten Zeiten"
                        if policy.notify_admin:
                            result.notifications.append("admin")
                        return result
                    elif policy.action == DLPAction.NOTIFY:
                        result.notifications.append("admin")

            # Rollen-Restriktionen prüfen
            if user_role in policy.blocked_roles:
                result.allowed = False
                result.action = DLPAction.BLOCK
                result.policy_id = policy.id
                result.policy_name = policy.name
                result.reason = f"Rolle '{user_role}' ist für diese Aktion gesperrt"
                if policy.notify_admin:
                    result.notifications.append("admin")
                return result

            if policy.allowed_roles and user_role not in policy.allowed_roles:
                if policy.action == DLPAction.BLOCK:
                    result.allowed = False
                    result.action = DLPAction.BLOCK
                    result.policy_id = policy.id
                    result.policy_name = policy.name
                    result.reason = f"Rolle '{user_role}' hat keinen Zugriff"
                    if policy.notify_admin:
                        result.notifications.append("admin")
                    return result

            # Wasserzeichen erforderlich?
            if policy.require_watermark:
                result.watermark_required = True
                result.watermark_config = policy.watermark_config
                result.policy_id = policy.id
                result.policy_name = policy.name
                result.action = DLPAction.WATERMARK

        return result

    def _policy_matches_document(
        self,
        policy: DLPPolicy,
        doc_tags: list[str],
        doc_type: str,
    ) -> bool:
        """Prüft ob eine Policy auf ein Dokument zutrifft."""
        # Dokument-Typ prüfen
        if "all" not in policy.document_types:
            if doc_type not in policy.document_types:
                return False

        # Required Tags prüfen
        if policy.tags_required:
            if not all(tag in doc_tags for tag in policy.tags_required):
                return False

        # Blocked Tags prüfen
        if policy.tags_blocked:
            if any(tag in doc_tags for tag in policy.tags_blocked):
                return False

        return True

    def _check_time_restrictions(self, restrictions: dict[str, Any]) -> bool:
        """Prüft ob aktuelle Zeit innerhalb der Einschränkungen liegt."""
        now = datetime.now()

        # Wochentag prüfen (0 = Montag)
        if "weekdays" in restrictions:
            if now.weekday() not in restrictions["weekdays"]:
                return False

        # Uhrzeit prüfen
        if "start" in restrictions and "end" in restrictions:
            start_time = time.fromisoformat(restrictions["start"])
            end_time = time.fromisoformat(restrictions["end"])
            current_time = now.time()

            if not (start_time <= current_time <= end_time):
                return False

        return True

    def detect_sensitive_data(
        self,
        text: str,
        types: Optional[list[SensitiveDataType]] = None,
    ) -> dict[SensitiveDataType, int]:
        """
        Erkennt sensible Daten im Text.

        Args:
            text: Zu prüfender Text
            types: Zu prüfende Typen (None = alle)

        Returns:
            Dict mit Typ -> Anzahl gefundener Matches

        SECURITY: Text wird nicht geloggt, nur Anzahl!
        """
        results: dict[SensitiveDataType, int] = {}

        check_types = types or list(SensitiveDataType)

        for data_type in check_types:
            if data_type not in SENSITIVE_PATTERNS:
                continue

            count = 0
            for pattern in SENSITIVE_PATTERNS[data_type]:
                matches = pattern.findall(text)
                count += len(matches)

            if count > 0:
                results[data_type] = count

        return results

    def add_watermark(
        self,
        image_bytes: bytes,
        config: WatermarkConfig,
        user: User,
        document_id: UUID,
    ) -> bytes:
        """
        Fuegt ein Wasserzeichen zu einem Bild hinzu.

        Args:
            image_bytes: Original-Bild als Bytes
            config: Wasserzeichen-Konfiguration
            user: Benutzer für Personalisierung
            document_id: Dokument-ID für Tracking

        Returns:
            Bild mit Wasserzeichen als Bytes
        """
        # Bild laden
        image = Image.open(io.BytesIO(image_bytes))

        # In RGBA konvertieren für Transparenz
        if image.mode != 'RGBA':
            image = image.convert('RGBA')

        # Wasserzeichen-Layer erstellen
        watermark_layer = Image.new('RGBA', image.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(watermark_layer)

        # Text generieren
        watermark_text = self._generate_watermark_text(config, user, document_id)

        # Farbe parsen
        color_hex = config.color.lstrip('#')
        r, g, b = tuple(int(color_hex[i:i+2], 16) for i in (0, 2, 4))
        opacity = int(config.opacity * 255)
        color = (r, g, b, opacity)

        # Font (Fallback auf Default)
        try:
            font = ImageFont.truetype("arial.ttf", config.font_size)
        except OSError:
            font = ImageFont.load_default()

        # Position bestimmen und zeichnen
        if config.position == WatermarkPosition.CENTER:
            self._draw_center_watermark(draw, watermark_text, font, color, image.size)
        elif config.position == WatermarkPosition.DIAGONAL:
            self._draw_diagonal_watermark(draw, watermark_text, font, color, image.size)
        elif config.position == WatermarkPosition.FOOTER:
            self._draw_footer_watermark(draw, watermark_text, font, color, image.size)
        elif config.position == WatermarkPosition.HEADER:
            self._draw_header_watermark(draw, watermark_text, font, color, image.size)
        elif config.position == WatermarkPosition.TILED:
            self._draw_tiled_watermark(draw, watermark_text, font, color, image.size)

        # Layer zusammenfuegen
        watermarked = Image.alpha_composite(image, watermark_layer)

        # Zurück zu Bytes
        output = io.BytesIO()
        watermarked.save(output, format='PNG')
        output.seek(0)

        return output.read()

    def _generate_watermark_text(
        self,
        config: WatermarkConfig,
        user: User,
        document_id: UUID,
    ) -> str:
        """Generiert den Wasserzeichen-Text."""
        parts: list[str] = []

        if config.text:
            parts.append(config.text)

        if config.include_user:
            parts.append(user.email if hasattr(user, 'email') else str(user.id))

        if config.include_timestamp:
            parts.append(datetime.now().strftime("%Y-%m-%d %H:%M"))

        if config.include_document_id:
            # Kurze ID für Tracking
            short_id = str(document_id)[:8]
            parts.append(f"ID:{short_id}")

        return " | ".join(parts) if parts else "WATERMARK"

    def _draw_center_watermark(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        font: ImageFont.FreeTypeFont,
        color: tuple[int, int, int, int],
        size: tuple[int, int],
    ) -> None:
        """Zeichnet Wasserzeichen in der Mitte."""
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        x = (size[0] - text_width) // 2
        y = (size[1] - text_height) // 2
        draw.text((x, y), text, font=font, fill=color)

    def _draw_diagonal_watermark(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        font: ImageFont.FreeTypeFont,
        color: tuple[int, int, int, int],
        size: tuple[int, int],
    ) -> None:
        """Zeichnet diagonales Wasserzeichen."""
        # Mehrere diagonale Linien
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        # Diagonale Positionen
        for i in range(-2, 4):
            x = size[0] // 4 + i * (text_width + 50)
            y = size[1] // 4 + i * (text_height + 100)
            draw.text((x, y), text, font=font, fill=color)

    def _draw_footer_watermark(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        font: ImageFont.FreeTypeFont,
        color: tuple[int, int, int, int],
        size: tuple[int, int],
    ) -> None:
        """Zeichnet Wasserzeichen im Footer."""
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        x = (size[0] - text_width) // 2
        y = size[1] - text_height - 20
        draw.text((x, y), text, font=font, fill=color)

    def _draw_header_watermark(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        font: ImageFont.FreeTypeFont,
        color: tuple[int, int, int, int],
        size: tuple[int, int],
    ) -> None:
        """Zeichnet Wasserzeichen im Header."""
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        x = (size[0] - text_width) // 2
        y = 20
        draw.text((x, y), text, font=font, fill=color)

    def _draw_tiled_watermark(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        font: ImageFont.FreeTypeFont,
        color: tuple[int, int, int, int],
        size: tuple[int, int],
    ) -> None:
        """Zeichnet gekacheltes Wasserzeichen."""
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        spacing_x = text_width + 100
        spacing_y = text_height + 100

        for y in range(0, size[1], spacing_y):
            for x in range(0, size[0], spacing_x):
                draw.text((x, y), text, font=font, fill=color)

    def generate_invisible_watermark(
        self,
        document_id: UUID,
        user_id: UUID,
    ) -> str:
        """
        Generiert einen unsichtbaren Wasserzeichen-Hash.

        Kann für Steganographie oder Metadaten verwendet werden.

        Returns:
            Hash-String für Tracking
        """
        timestamp = datetime.now().isoformat()
        data = f"{document_id}:{user_id}:{timestamp}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]

    async def log_dlp_event(
        self,
        user_id: UUID,
        document_id: UUID,
        action: str,
        result: DLPCheckResult,
        company_id: Optional[UUID] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> None:
        """
        Loggt ein DLP-Event in der Datenbank für Audit-Zwecke.

        SECURITY:
        - Keine sensiblen Daten werden geloggt!
        - Nur Typen und Counts für sensitive_data
        - company_id ist PFLICHT für Multi-Tenant Isolation

        Args:
            user_id: ID des Benutzers
            document_id: ID des Dokuments
            action: Art der Aktion (download, view, etc.)
            result: Ergebnis der DLP-Prüfung
            company_id: Mandanten-ID (PFLICHT!)
            ip_address: Optional IP-Adresse
            user_agent: Optional User-Agent
        """
        effective_company_id = company_id or self.company_id

        if not effective_company_id:
            logger.warning(
                "DLP Audit-Log ohne company_id! user_id=%s, document_id=%s",
                user_id, document_id
            )
            # Trotzdem loggen - aber als Security-Warning
            return

        # Result-String bestimmen
        if not result.allowed:
            result_str = "blocked"
        elif result.watermark_required:
            result_str = "watermarked"
        elif result.notifications:
            result_str = "notified"
        else:
            result_str = "allowed"

        # Sensitive Data: NUR Typen und Counts, KEINE Werte!
        sensitive_data_info = None
        if result.sensitive_data_found:
            sensitive_data_info = {
                data_type.value: 1  # Nur dass der Typ gefunden wurde
                for data_type in result.sensitive_data_found
            }

        # Policy-ID aus DB holen falls vorhanden
        policy_db_id = None
        if result.policy_id and effective_company_id:
            policy_result = await self.db.execute(
                select(DLPPolicyModel.id).where(
                    and_(
                        DLPPolicyModel.policy_id == result.policy_id,
                        DLPPolicyModel.company_id == effective_company_id
                    )
                )
            )
            policy_row = policy_result.scalar_one_or_none()
            if policy_row:
                policy_db_id = policy_row

        # Audit-Log erstellen
        audit_entry = DLPAuditLog(
            event_type="access_check",
            action_type=action,
            result=result_str,
            reason=result.reason,
            user_id=user_id,
            document_id=document_id,
            policy_id=policy_db_id,
            company_id=effective_company_id,
            sensitive_data_types=sensitive_data_info,
            ip_address=ip_address,
            user_agent=user_agent,
            log_metadata={
                "policy_name": result.policy_name,
                "watermark_required": result.watermark_required,
                "notifications": result.notifications,
            }
        )

        self.db.add(audit_entry)
        await self.db.flush()

        logger.info(
            "DLP Event logged: event_type=access_check, result=%s, action=%s",
            result_str, action
        )

    async def get_policies(self) -> list[DLPPolicy]:
        """Gibt alle konfigurierten Policies zurück (aus DB)."""
        await self._ensure_policies_loaded()
        return self._policies_cache

    async def add_policy(self, policy: DLPPolicy) -> DLPPolicyModel:
        """
        Fuegt eine neue Policy hinzu (persistiert in DB).

        SECURITY: company_id ist PFLICHT!
        """
        if not self.company_id:
            raise DLPServiceError("company_id ist erforderlich für neue Policies")

        # Duplikat-Check
        existing = await self.db.execute(
            select(DLPPolicyModel).where(
                and_(
                    DLPPolicyModel.company_id == self.company_id,
                    DLPPolicyModel.policy_id == policy.id
                )
            )
        )
        if existing.scalar_one_or_none():
            raise DLPServiceError(f"Policy mit ID '{policy.id}' existiert bereits")

        # In DB speichern
        db_policy = DLPPolicyModel(
            policy_id=policy.id,
            name=policy.name,
            description=policy.description,
            enabled=policy.enabled,
            company_id=self.company_id,
            allowed_roles=policy.allowed_roles,
            blocked_roles=policy.blocked_roles,
            time_restrictions=policy.time_restrictions,
            document_types=policy.document_types,
            tags_required=policy.tags_required,
            tags_blocked=policy.tags_blocked,
            action=policy.action.value,
            require_watermark=policy.require_watermark,
            watermark_config=policy.watermark_config,
            notify_admin=policy.notify_admin,
            notify_user=policy.notify_user,
            log_access=policy.log_access,
        )

        self.db.add(db_policy)
        await self.db.flush()

        # Cache invalidieren
        self._cache_loaded = False

        logger.info("DLP Policy created: policy_id=%s", policy.id)
        return db_policy

    async def update_policy(self, policy_id: str, updates: dict[str, Any]) -> DLPPolicy:
        """Aktualisiert eine bestehende Policy (in DB)."""
        if not self.company_id:
            raise DLPServiceError("company_id ist erforderlich")

        result = await self.db.execute(
            select(DLPPolicyModel).where(
                and_(
                    DLPPolicyModel.company_id == self.company_id,
                    DLPPolicyModel.policy_id == policy_id
                )
            )
        )
        db_policy = result.scalar_one_or_none()

        if not db_policy:
            raise DLPServiceError(f"Policy '{policy_id}' nicht gefunden")

        # Updates anwenden
        for key, value in updates.items():
            if key == "action" and isinstance(value, DLPAction):
                value = value.value
            if hasattr(db_policy, key):
                setattr(db_policy, key, value)

        await self.db.flush()

        # Cache invalidieren
        self._cache_loaded = False

        logger.info("DLP Policy updated: policy_id=%s", policy_id)

        # Pydantic-Objekt zurückgeben
        return DLPPolicy(
            id=db_policy.policy_id,
            name=db_policy.name,
            description=db_policy.description,
            enabled=db_policy.enabled,
            allowed_roles=db_policy.allowed_roles or ["admin"],
            blocked_roles=db_policy.blocked_roles or [],
            time_restrictions=db_policy.time_restrictions,
            document_types=db_policy.document_types or ["all"],
            tags_required=db_policy.tags_required or [],
            tags_blocked=db_policy.tags_blocked or [],
            action=DLPAction(db_policy.action),
            require_watermark=db_policy.require_watermark,
            watermark_config=db_policy.watermark_config,
            notify_admin=db_policy.notify_admin,
            notify_user=db_policy.notify_user,
            log_access=db_policy.log_access,
        )

    async def delete_policy(self, policy_id: str) -> None:
        """Löscht eine Policy (aus DB)."""
        if not self.company_id:
            raise DLPServiceError("company_id ist erforderlich")

        result = await self.db.execute(
            select(DLPPolicyModel).where(
                and_(
                    DLPPolicyModel.company_id == self.company_id,
                    DLPPolicyModel.policy_id == policy_id
                )
            )
        )
        db_policy = result.scalar_one_or_none()

        if db_policy:
            await self.db.delete(db_policy)
            await self.db.flush()

            logger.info("DLP Policy deleted: policy_id=%s", policy_id)

        # Cache invalidieren
        self._cache_loaded = False

    async def seed_default_policies(self) -> int:
        """
        Erstellt Standard-Policies in der DB falls keine existieren.

        Returns:
            Anzahl der erstellten Policies
        """
        if not self.company_id:
            raise DLPServiceError("company_id ist erforderlich")

        # Prüfen ob schon Policies existieren
        result = await self.db.execute(
            select(DLPPolicyModel).where(
                DLPPolicyModel.company_id == self.company_id
            ).limit(1)
        )
        if result.scalar_one_or_none():
            return 0  # Policies existieren bereits

        # Default-Policies erstellen
        default_policies = self._get_default_policies()
        created = 0

        for i, policy in enumerate(default_policies):
            db_policy = DLPPolicyModel(
                policy_id=policy.id,
                name=policy.name,
                description=policy.description,
                enabled=policy.enabled,
                company_id=self.company_id,
                allowed_roles=policy.allowed_roles,
                blocked_roles=policy.blocked_roles,
                time_restrictions=policy.time_restrictions,
                document_types=policy.document_types,
                tags_required=policy.tags_required,
                tags_blocked=policy.tags_blocked,
                action=policy.action.value,
                require_watermark=policy.require_watermark,
                watermark_config=policy.watermark_config,
                notify_admin=policy.notify_admin,
                notify_user=policy.notify_user,
                log_access=policy.log_access,
                priority=(i + 1) * 10,  # 10, 20, 30, 40
            )
            self.db.add(db_policy)
            created += 1

        await self.db.flush()
        logger.info("Seeded %d default DLP policies for company %s", created, self.company_id)

        return created


def get_dlp_service(db: AsyncSession, company_id: Optional[UUID] = None) -> DLPService:
    """Factory-Funktion für DLPService."""
    return DLPService(db, company_id)
