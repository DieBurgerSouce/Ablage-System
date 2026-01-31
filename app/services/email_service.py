# -*- coding: utf-8 -*-
"""
Email Service fuer Ablage-System.

Zentrale Email-Versand-Komponente fuer:
- Zahlungserinnerungen und Mahnungen (Dunning)
- Willkommenspakete (Onboarding)
- System-Benachrichtigungen

Unterstuetzt:
- SMTP mit TLS
- HTML und Text Email Templates
- Asynchroner Versand via aiosmtplib
- Retry-Logik mit Exponential Backoff
- Jinja2 Template-Rendering

Feinpoliert und durchdacht - Enterprise Email in Produktion.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING
from uuid import UUID

import aiosmtplib
import structlog
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.core.config import settings
from app.core.safe_errors import safe_error_log, safe_error_detail

if TYPE_CHECKING:
    from app.db.models import BusinessEntity, InvoiceTracking, Company


logger = structlog.get_logger(__name__)


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class EmailResult:
    """Ergebnis einer Email-Versand-Operation."""
    success: bool
    recipient: str
    subject: str
    message_id: Optional[str] = None
    error: Optional[str] = None
    retry_count: int = 0
    sent_at: Optional[datetime] = None


@dataclass
class DunningEmailData:
    """Daten fuer Mahnungs-Emails."""
    # Empfaenger
    recipient_email: str
    recipient_name: str
    customer_number: Optional[str] = None

    # Rechnungsdaten
    invoice_number: str = ""
    invoice_date: Optional[datetime] = None
    due_date: Optional[datetime] = None
    amount: Decimal = Decimal("0.00")
    currency: str = "EUR"
    outstanding_amount: Decimal = Decimal("0.00")

    # Mahndaten
    dunning_level: int = 0
    days_overdue: int = 0
    dunning_fee: Decimal = Decimal("0.00")
    interest_amount: Decimal = Decimal("0.00")
    total_amount: Decimal = Decimal("0.00")
    payment_deadline: Optional[datetime] = None

    # Bankverbindung (unsere)
    company_name: str = ""
    company_iban: str = ""
    company_bic: str = ""
    company_bank_name: str = ""
    payment_reference: str = ""

    # Kontaktdaten
    contact_phone: str = ""
    contact_email: str = ""


@dataclass
class WelcomeEmailData:
    """Daten fuer Willkommens-Emails."""
    recipient_email: str
    recipient_name: str
    customer_number: str
    company_name: str = ""
    credit_limit: Decimal = Decimal("10000.00")
    payment_terms: str = "net_14"
    payment_terms_days: int = 14
    portal_url: Optional[str] = None
    contact_phone: str = ""
    contact_email: str = ""


# =============================================================================
# Email Service
# =============================================================================


class EmailService:
    """
    Zentrale Email-Service-Klasse.

    Features:
    - Asynchroner SMTP-Versand
    - Jinja2 Template-Rendering
    - Retry-Logik mit Exponential Backoff
    - HTML und Plain-Text Support
    """

    def __init__(
        self,
        template_dir: Optional[Path] = None,
        smtp_host: Optional[str] = None,
        smtp_port: Optional[int] = None,
        smtp_user: Optional[str] = None,
        smtp_password: Optional[str] = None,
        smtp_from: Optional[str] = None,
        smtp_tls: bool = True,
    ):
        """
        Initialisiere EmailService.

        Args:
            template_dir: Verzeichnis mit Email-Templates (default: app/templates/email)
            smtp_host: SMTP Server Host
            smtp_port: SMTP Server Port
            smtp_user: SMTP Benutzername
            smtp_password: SMTP Passwort
            smtp_from: Absender-Email
            smtp_tls: TLS verwenden
        """
        # SMTP-Konfiguration aus settings oder Parameter
        self.smtp_host = smtp_host or settings.SMTP_HOST
        self.smtp_port = smtp_port or settings.SMTP_PORT or 587
        self.smtp_user = smtp_user or settings.SMTP_USER
        self.smtp_password = smtp_password or (
            settings.SMTP_PASSWORD.get_secret_value() if settings.SMTP_PASSWORD else None
        )
        self.smtp_from = smtp_from or settings.SMTP_FROM_EMAIL or "noreply@ablage-system.local"
        self.smtp_tls = smtp_tls if smtp_tls is not None else settings.SMTP_TLS

        # Template-Engine
        if template_dir is None:
            template_dir = Path(__file__).parent.parent / "templates" / "email"

        self._template_dir = template_dir
        self._jinja_env: Optional[Environment] = None

        # Konfiguration validieren
        self._is_configured = bool(self.smtp_host and self.smtp_user and self.smtp_password)

        if not self._is_configured:
            logger.warning(
                "email_service_nicht_konfiguriert",
                smtp_host=self.smtp_host,
                smtp_user=self.smtp_user,
                message="SMTP nicht konfiguriert - Emails werden nur geloggt"
            )
        else:
            logger.info(
                "email_service_initialisiert",
                smtp_host=self.smtp_host,
                smtp_port=self.smtp_port,
                smtp_from=self.smtp_from,
                template_dir=str(template_dir),
            )

    @property
    def is_configured(self) -> bool:
        """Prueft ob SMTP konfiguriert ist."""
        return self._is_configured

    def _get_jinja_env(self) -> Environment:
        """Lazy-Init der Jinja2 Environment."""
        if self._jinja_env is None:
            # Templates-Verzeichnis erstellen falls nicht vorhanden
            self._template_dir.mkdir(parents=True, exist_ok=True)

            self._jinja_env = Environment(
                loader=FileSystemLoader(str(self._template_dir)),
                autoescape=select_autoescape(["html", "xml"]),
                trim_blocks=True,
                lstrip_blocks=True,
            )

            # Custom Filter fuer Formatierung
            self._jinja_env.filters["currency"] = self._format_currency
            self._jinja_env.filters["date"] = self._format_date
            self._jinja_env.filters["date_short"] = self._format_date_short

        return self._jinja_env

    @staticmethod
    def _format_currency(value: Decimal | float, currency: str = "EUR") -> str:
        """Formatiert Betrag als Waehrung."""
        if isinstance(value, float):
            value = Decimal(str(value))
        symbols = {"EUR": "€", "USD": "$", "GBP": "£", "CHF": "CHF"}
        symbol = symbols.get(currency, currency)
        return f"{value:,.2f} {symbol}".replace(",", "X").replace(".", ",").replace("X", ".")

    @staticmethod
    def _format_date(value: datetime | None, format_str: str = "%d.%m.%Y") -> str:
        """Formatiert Datum im deutschen Format."""
        if value is None:
            return ""
        return value.strftime(format_str)

    @staticmethod
    def _format_date_short(value: datetime | None) -> str:
        """Formatiert Datum kurz."""
        if value is None:
            return ""
        return value.strftime("%d.%m.%y")

    # =========================================================================
    # Core Send Methods
    # =========================================================================

    async def send_email(
        self,
        to: str,
        subject: str,
        html_body: str,
        text_body: Optional[str] = None,
        attachments: Optional[List[Path]] = None,
        reply_to: Optional[str] = None,
        max_retries: int = 3,
    ) -> EmailResult:
        """
        Sendet eine Email.

        Args:
            to: Empfaenger-Adresse
            subject: Betreff
            html_body: HTML-Inhalt
            text_body: Plain-Text-Inhalt (optional)
            attachments: Anhaenge (optional)
            reply_to: Reply-To Adresse (optional)
            max_retries: Maximale Wiederholungsversuche

        Returns:
            EmailResult mit Status
        """
        # Wenn nicht konfiguriert, nur loggen
        if not self._is_configured:
            logger.info(
                "email_mock_send",
                to=to,
                subject=subject,
                message="SMTP nicht konfiguriert - Email nicht gesendet",
            )
            return EmailResult(
                success=True,
                recipient=to,
                subject=subject,
                message_id="mock-" + str(hash(f"{to}{subject}"))[:8],
                sent_at=datetime.now(timezone.utc),
            )

        # Email zusammenstellen
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self.smtp_from
        msg["To"] = to
        if reply_to:
            msg["Reply-To"] = reply_to

        # Plain-Text (Fallback)
        if text_body:
            text_part = MIMEText(text_body, "plain", "utf-8")
            msg.attach(text_part)

        # HTML
        html_part = MIMEText(html_body, "html", "utf-8")
        msg.attach(html_part)

        # Anhaenge
        if attachments:
            for attachment_path in attachments:
                if attachment_path.exists():
                    with open(attachment_path, "rb") as f:
                        part = MIMEBase("application", "octet-stream")
                        part.set_payload(f.read())
                        encoders.encode_base64(part)
                        part.add_header(
                            "Content-Disposition",
                            f"attachment; filename={attachment_path.name}",
                        )
                        msg.attach(part)

        # Versand mit Retry-Logik
        last_error: Optional[str] = None
        for attempt in range(1, max_retries + 1):
            try:
                # Verbindung herstellen
                smtp = aiosmtplib.SMTP(
                    hostname=self.smtp_host,
                    port=self.smtp_port,
                    use_tls=self.smtp_tls,
                    timeout=30,
                )

                await smtp.connect()

                if self.smtp_user and self.smtp_password:
                    await smtp.login(self.smtp_user, self.smtp_password)

                # Email senden
                response = await smtp.send_message(msg)

                await smtp.quit()

                logger.info(
                    "email_gesendet",
                    to=to,
                    subject=subject,
                    attempt=attempt,
                )

                return EmailResult(
                    success=True,
                    recipient=to,
                    subject=subject,
                    message_id=str(hash(f"{to}{subject}{datetime.now()}"))[:12],
                    sent_at=datetime.now(timezone.utc),
                    retry_count=attempt - 1,
                )

            except Exception as e:
                last_error = safe_error_detail(e, "SMTP")
                logger.warning(
                    "email_versand_fehlgeschlagen",
                    to=to,
                    attempt=attempt,
                    max_retries=max_retries,
                    **safe_error_log(e),
                )

                if attempt < max_retries:
                    # Exponential Backoff
                    await asyncio.sleep(2 ** attempt)

        logger.error(
            "email_versand_endgueltig_fehlgeschlagen",
            to=to,
            subject=subject,
            error=last_error,
        )

        return EmailResult(
            success=False,
            recipient=to,
            subject=subject,
            error=last_error,
            retry_count=max_retries,
        )

    # =========================================================================
    # Dunning Emails (Mahnwesen)
    # =========================================================================

    async def send_payment_reminder(
        self,
        entity: "BusinessEntity",
        invoice: "InvoiceTracking",
        company: "Company",
    ) -> EmailResult:
        """
        Sendet freundliche Zahlungserinnerung (Mahnstufe 0).

        Args:
            entity: Geschaeftspartner
            invoice: Rechnungsverfolgung
            company: Absender-Firma

        Returns:
            EmailResult
        """
        if not entity.email:
            return EmailResult(
                success=False,
                recipient="",
                subject="",
                error="Keine Email-Adresse fuer Entity vorhanden",
            )

        # Daten aufbereiten
        data = self._prepare_dunning_data(entity, invoice, company, dunning_level=0)

        # Template rendern
        html_body = self._render_dunning_email(data, template_name="payment_reminder.html")
        text_body = self._render_dunning_email_text(data)

        subject = f"Zahlungserinnerung - Rechnung {invoice.invoice_number}"

        return await self.send_email(
            to=data.recipient_email,
            subject=subject,
            html_body=html_body,
            text_body=text_body,
            reply_to=data.contact_email,
        )

    async def send_dunning_letter(
        self,
        entity: "BusinessEntity",
        invoice: "InvoiceTracking",
        company: "Company",
        dunning_level: int = 1,
    ) -> EmailResult:
        """
        Sendet Mahnung (Mahnstufe 1-3).

        Args:
            entity: Geschaeftspartner
            invoice: Rechnungsverfolgung
            company: Absender-Firma
            dunning_level: Mahnstufe (1, 2 oder 3)

        Returns:
            EmailResult
        """
        if not entity.email:
            return EmailResult(
                success=False,
                recipient="",
                subject="",
                error="Keine Email-Adresse fuer Entity vorhanden",
            )

        if dunning_level < 1:
            dunning_level = 1
        elif dunning_level > 3:
            dunning_level = 3

        # Daten aufbereiten
        data = self._prepare_dunning_data(entity, invoice, company, dunning_level=dunning_level)

        # Template waehlen
        template_map = {
            1: "dunning_level_1.html",
            2: "dunning_level_2.html",
            3: "dunning_level_final.html",
        }
        template_name = template_map.get(dunning_level, "dunning_level_1.html")

        # Template rendern
        html_body = self._render_dunning_email(data, template_name=template_name)
        text_body = self._render_dunning_email_text(data)

        # Betreff je Mahnstufe
        subject_map = {
            1: f"1. Mahnung - Rechnung {invoice.invoice_number}",
            2: f"2. Mahnung - Rechnung {invoice.invoice_number}",
            3: f"Letzte Mahnung vor Inkasso - Rechnung {invoice.invoice_number}",
        }
        subject = subject_map.get(dunning_level, f"Mahnung - Rechnung {invoice.invoice_number}")

        return await self.send_email(
            to=data.recipient_email,
            subject=subject,
            html_body=html_body,
            text_body=text_body,
            reply_to=data.contact_email,
        )

    def _prepare_dunning_data(
        self,
        entity: "BusinessEntity",
        invoice: "InvoiceTracking",
        company: "Company",
        dunning_level: int,
    ) -> DunningEmailData:
        """Bereitet Daten fuer Mahnungs-Email auf."""
        from datetime import timedelta

        # Mahngebuehren je Stufe
        dunning_fees = {0: Decimal("0.00"), 1: Decimal("5.00"), 2: Decimal("10.00"), 3: Decimal("15.00")}
        dunning_fee = dunning_fees.get(dunning_level, Decimal("0.00"))

        # Tage ueberfaellig berechnen
        days_overdue = 0
        if invoice.due_date:
            delta = datetime.now(timezone.utc) - invoice.due_date
            days_overdue = max(0, delta.days)

        # Verzugszinsen (vereinfacht: 9% p.a. B2B)
        interest_rate = Decimal("0.09")
        base_amount = Decimal(str(invoice.amount or 0))
        interest_amount = (base_amount * interest_rate * days_overdue) / Decimal("365")
        interest_amount = interest_amount.quantize(Decimal("0.01"))

        # Ausstehender Betrag
        outstanding = base_amount - Decimal(str(invoice.paid_amount or 0))
        total = outstanding + dunning_fee + interest_amount

        # Zahlungsfrist (7-14 Tage je Mahnstufe)
        deadline_days = {0: 14, 1: 14, 2: 10, 3: 7}
        payment_deadline = datetime.now(timezone.utc) + timedelta(days=deadline_days.get(dunning_level, 14))

        return DunningEmailData(
            recipient_email=entity.email or "",
            recipient_name=entity.display_name or entity.name,
            customer_number=entity.primary_customer_number,
            invoice_number=invoice.invoice_number or "",
            invoice_date=invoice.invoice_date,
            due_date=invoice.due_date,
            amount=base_amount,
            currency=invoice.currency or "EUR",
            outstanding_amount=outstanding,
            dunning_level=dunning_level,
            days_overdue=days_overdue,
            dunning_fee=dunning_fee,
            interest_amount=interest_amount,
            total_amount=total,
            payment_deadline=payment_deadline,
            company_name=company.name if company else "",
            company_iban=company.iban if company else "",
            company_bic=company.bic if company else "",
            company_bank_name=company.bank_name if company else "",
            payment_reference=f"RE-{invoice.invoice_number}",
            contact_phone=company.phone if company else "",
            contact_email=company.email if company else "",
        )

    def _render_dunning_email(self, data: DunningEmailData, template_name: str) -> str:
        """Rendert HTML-Email aus Template."""
        try:
            env = self._get_jinja_env()
            template = env.get_template(template_name)
            return template.render(data=data)
        except Exception as e:
            logger.warning(
                "email_template_nicht_gefunden",
                template=template_name,
                **safe_error_log(e),
            )
            # Fallback: Inline-HTML generieren
            return self._generate_fallback_dunning_html(data)

    def _render_dunning_email_text(self, data: DunningEmailData) -> str:
        """Generiert Plain-Text Version der Mahnung."""
        level_titles = {
            0: "Freundliche Zahlungserinnerung",
            1: "1. Mahnung",
            2: "2. Mahnung",
            3: "Letzte Mahnung vor Inkasso",
        }
        title = level_titles.get(data.dunning_level, "Mahnung")

        text = f"""
{title}

Sehr geehrte Damen und Herren,

zur folgenden Rechnung steht noch eine Zahlung aus:

Rechnung:       {data.invoice_number}
Rechnungsdatum: {self._format_date(data.invoice_date)}
Faelligkeit:    {self._format_date(data.due_date)}

Offener Betrag: {self._format_currency(data.outstanding_amount)}
"""

        if data.dunning_fee > 0:
            text += f"Mahngebuehr:    {self._format_currency(data.dunning_fee)}\n"

        if data.interest_amount > 0:
            text += f"Verzugszinsen:  {self._format_currency(data.interest_amount)}\n"

        text += f"""
Gesamtbetrag:   {self._format_currency(data.total_amount)}

Bitte ueberweisen Sie den Gesamtbetrag bis zum {self._format_date(data.payment_deadline)}.

Bankverbindung:
IBAN: {data.company_iban}
BIC:  {data.company_bic}
Bank: {data.company_bank_name}
Verwendungszweck: {data.payment_reference}

Mit freundlichen Gruessen
{data.company_name}
"""
        return text.strip()

    def _generate_fallback_dunning_html(self, data: DunningEmailData) -> str:
        """Generiert Fallback-HTML wenn Template fehlt."""
        level_titles = {
            0: "Freundliche Zahlungserinnerung",
            1: "1. Mahnung",
            2: "2. Mahnung",
            3: "Letzte Mahnung vor Inkasso",
        }
        title = level_titles.get(data.dunning_level, "Mahnung")

        return f"""
<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <title>{title}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; color: #333; }}
        h1 {{ color: #cc0000; }}
        table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
        th, td {{ border: 1px solid #ccc; padding: 10px; text-align: left; }}
        th {{ background: #f0f0f0; }}
        .amount {{ text-align: right; font-family: monospace; }}
        .total {{ background: #ffffcc; font-weight: bold; }}
        .bank {{ background: #f9f9f9; padding: 15px; margin: 20px 0; }}
    </style>
</head>
<body>
    <h1>{title}</h1>

    <p>Sehr geehrte Damen und Herren,</p>

    <p>zur folgenden Rechnung steht noch eine Zahlung aus:</p>

    <table>
        <tr>
            <th>Position</th>
            <th class="amount">Betrag</th>
        </tr>
        <tr>
            <td>Rechnung {data.invoice_number} vom {self._format_date(data.invoice_date)}</td>
            <td class="amount">{self._format_currency(data.outstanding_amount)}</td>
        </tr>
        {"<tr><td>Mahngebuehr</td><td class='amount'>" + self._format_currency(data.dunning_fee) + "</td></tr>" if data.dunning_fee > 0 else ""}
        {"<tr><td>Verzugszinsen</td><td class='amount'>" + self._format_currency(data.interest_amount) + "</td></tr>" if data.interest_amount > 0 else ""}
        <tr class="total">
            <td>Gesamtbetrag</td>
            <td class="amount">{self._format_currency(data.total_amount)}</td>
        </tr>
    </table>

    <p>Bitte ueberweisen Sie den Gesamtbetrag bis zum <strong>{self._format_date(data.payment_deadline)}</strong>.</p>

    <div class="bank">
        <strong>Bankverbindung:</strong><br>
        IBAN: {data.company_iban}<br>
        BIC: {data.company_bic}<br>
        Bank: {data.company_bank_name}<br>
        Verwendungszweck: {data.payment_reference}
    </div>

    <p>Mit freundlichen Gruessen<br>{data.company_name}</p>
</body>
</html>
"""

    # =========================================================================
    # Welcome Emails (Onboarding)
    # =========================================================================

    async def send_welcome_package(
        self,
        entity: "BusinessEntity",
        company: "Company",
        credit_limit: Optional[Decimal] = None,
        payment_terms_days: int = 14,
    ) -> EmailResult:
        """
        Sendet Willkommenspaket an neuen Kunden.

        Args:
            entity: Neuer Geschaeftspartner
            company: Unsere Firma
            credit_limit: Kreditlimit
            payment_terms_days: Zahlungsziel in Tagen

        Returns:
            EmailResult
        """
        if not entity.email:
            return EmailResult(
                success=False,
                recipient="",
                subject="",
                error="Keine Email-Adresse fuer Entity vorhanden",
            )

        # Daten aufbereiten
        data = WelcomeEmailData(
            recipient_email=entity.email,
            recipient_name=entity.display_name or entity.name,
            customer_number=entity.primary_customer_number or "",
            company_name=company.name if company else "",
            credit_limit=credit_limit or Decimal("10000.00"),
            payment_terms=f"net_{payment_terms_days}",
            payment_terms_days=payment_terms_days,
            contact_phone=company.phone if company else "",
            contact_email=company.email if company else "",
        )

        # Template rendern
        html_body = self._render_welcome_email(data)
        text_body = self._render_welcome_email_text(data)

        subject = f"Willkommen bei {data.company_name}"

        return await self.send_email(
            to=data.recipient_email,
            subject=subject,
            html_body=html_body,
            text_body=text_body,
            reply_to=data.contact_email,
        )

    def _render_welcome_email(self, data: WelcomeEmailData) -> str:
        """Rendert Welcome-Email als HTML."""
        try:
            env = self._get_jinja_env()
            template = env.get_template("welcome.html")
            return template.render(data=data)
        except Exception:
            # Fallback
            return self._generate_fallback_welcome_html(data)

    def _render_welcome_email_text(self, data: WelcomeEmailData) -> str:
        """Generiert Plain-Text Version der Welcome-Email."""
        return f"""
Willkommen bei {data.company_name}!

Sehr geehrte(r) {data.recipient_name},

vielen Dank fuer Ihr Vertrauen! Ihr Kundenkonto wurde erfolgreich eingerichtet.

Ihre Kundennummer: {data.customer_number}

Konditionen:
- Kreditlimit: {self._format_currency(data.credit_limit)}
- Zahlungsziel: {data.payment_terms_days} Tage netto

Bei Fragen stehen wir Ihnen gerne zur Verfuegung:
Tel: {data.contact_phone}
Email: {data.contact_email}

Mit freundlichen Gruessen
{data.company_name}
""".strip()

    def _generate_fallback_welcome_html(self, data: WelcomeEmailData) -> str:
        """Generiert Fallback-HTML fuer Welcome-Email."""
        return f"""
<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <title>Willkommen bei {data.company_name}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; color: #333; }}
        h1 {{ color: #2563eb; }}
        .info-box {{ background: #f0f9ff; padding: 15px; margin: 20px 0; border-radius: 8px; }}
        .highlight {{ font-weight: bold; color: #1d4ed8; }}
    </style>
</head>
<body>
    <h1>Willkommen bei {data.company_name}!</h1>

    <p>Sehr geehrte(r) {data.recipient_name},</p>

    <p>vielen Dank fuer Ihr Vertrauen! Ihr Kundenkonto wurde erfolgreich eingerichtet.</p>

    <div class="info-box">
        <p><strong>Ihre Kundennummer:</strong> <span class="highlight">{data.customer_number}</span></p>
        <p><strong>Kreditlimit:</strong> {self._format_currency(data.credit_limit)}</p>
        <p><strong>Zahlungsziel:</strong> {data.payment_terms_days} Tage netto</p>
    </div>

    <p>Bei Fragen stehen wir Ihnen gerne zur Verfuegung:</p>
    <p>Tel: {data.contact_phone}<br>Email: {data.contact_email}</p>

    <p>Mit freundlichen Gruessen<br><strong>{data.company_name}</strong></p>
</body>
</html>
"""

    # =========================================================================
    # Contract Notification Methods
    # =========================================================================

    async def send_contract_deadline_reminder(
        self,
        contract_id: UUID,
        contract_title: str,
        contract_number: Optional[str],
        deadline_type: str,
        deadline_date: Any,
        days_remaining: int,
        recipient_user_id: Optional[UUID],
        company_id: UUID,
    ) -> EmailResult:
        """
        Sendet Email-Erinnerung fuer Vertragsfristen.

        Args:
            contract_id: Vertrags-ID
            contract_title: Vertragstitel
            contract_number: Vertragsnummer
            deadline_type: 'notice_deadline' oder 'end_date'
            deadline_date: Datum der Frist
            days_remaining: Tage bis zur Frist
            recipient_user_id: User-ID des Empfaengers
            company_id: Firmen-ID

        Returns:
            EmailResult
        """
        # Empfaenger-Email ermitteln
        recipient_email = await self._get_user_email(recipient_user_id)
        if not recipient_email:
            return EmailResult(
                success=False,
                recipient="",
                subject="",
                error="Keine Email-Adresse fuer Benutzer gefunden",
            )

        # Deadline-Typ formatieren
        deadline_type_de = (
            "Kuendigungsfrist" if deadline_type == "notice_deadline"
            else "Vertragsende"
        )
        deadline_date_str = (
            deadline_date.strftime("%d.%m.%Y") if deadline_date else "unbekannt"
        )

        subject = f"[WICHTIG] {deadline_type_de} in {days_remaining} Tagen - {contract_title}"

        # Text-Body
        text_body = f"""
VERTRAGSFRIST-ERINNERUNG

Vertrag: {contract_title}
{f"Vertragsnummer: {contract_number}" if contract_number else ""}

{deadline_type_de}: {deadline_date_str}
Verbleibende Tage: {days_remaining}

{'DRINGEND: Die Frist laeuft in weniger als 7 Tagen ab!' if days_remaining <= 7 else ''}

Bitte pruefen Sie den Vertrag und ergreifen Sie ggf. erforderliche Massnahmen.

---
Diese Nachricht wurde automatisch vom Ablage-System generiert.
""".strip()

        # HTML-Body
        urgency_color = "#dc2626" if days_remaining <= 7 else "#f59e0b"
        html_body = f"""
<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <title>Vertragsfrist-Erinnerung</title>
</head>
<body style="font-family: Arial, sans-serif; margin: 20px; color: #333;">
    <h1 style="color: {urgency_color};">Vertragsfrist-Erinnerung</h1>

    <div style="background: #f0f9ff; padding: 15px; margin: 20px 0; border-radius: 8px; border-left: 4px solid {urgency_color};">
        <p><strong>Vertrag:</strong> {contract_title}</p>
        {f"<p><strong>Vertragsnummer:</strong> {contract_number}</p>" if contract_number else ""}
        <p><strong>{deadline_type_de}:</strong> {deadline_date_str}</p>
        <p><strong>Verbleibende Tage:</strong> <span style="color: {urgency_color}; font-weight: bold;">{days_remaining}</span></p>
    </div>

    {'<p style="color: #dc2626; font-weight: bold;">⚠️ DRINGEND: Die Frist laeuft in weniger als 7 Tagen ab!</p>' if days_remaining <= 7 else ''}

    <p>Bitte pruefen Sie den Vertrag und ergreifen Sie ggf. erforderliche Massnahmen.</p>

    <hr style="margin-top: 30px; border: none; border-top: 1px solid #e5e7eb;">
    <p style="font-size: 0.8em; color: #6b7280;">Diese Nachricht wurde automatisch vom Ablage-System generiert.</p>
</body>
</html>
"""

        return await self.send_email(
            to=recipient_email,
            subject=subject,
            html_body=html_body,
            text_body=text_body,
        )

    async def send_contract_milestone_reminder(
        self,
        contract_id: UUID,
        contract_title: str,
        milestone_title: str,
        scheduled_date: Any,
        days_remaining: int,
        recipient_user_id: Optional[UUID],
        company_id: UUID,
    ) -> EmailResult:
        """
        Sendet Email-Erinnerung fuer Vertrags-Meilensteine.

        Args:
            contract_id: Vertrags-ID
            contract_title: Vertragstitel
            milestone_title: Meilenstein-Titel
            scheduled_date: Faelligkeitsdatum
            days_remaining: Tage bis zur Faelligkeit
            recipient_user_id: User-ID des Empfaengers
            company_id: Firmen-ID

        Returns:
            EmailResult
        """
        recipient_email = await self._get_user_email(recipient_user_id)
        if not recipient_email:
            return EmailResult(
                success=False,
                recipient="",
                subject="",
                error="Keine Email-Adresse fuer Benutzer gefunden",
            )

        scheduled_date_str = (
            scheduled_date.strftime("%d.%m.%Y") if scheduled_date else "unbekannt"
        )

        subject = f"Meilenstein faellig in {days_remaining} Tagen - {milestone_title}"

        text_body = f"""
MEILENSTEIN-ERINNERUNG

Vertrag: {contract_title}
Meilenstein: {milestone_title}

Faelligkeitsdatum: {scheduled_date_str}
Verbleibende Tage: {days_remaining}

{'DRINGEND: Der Meilenstein ist in weniger als 7 Tagen faellig!' if days_remaining <= 7 else ''}

Bitte stellen Sie sicher, dass alle erforderlichen Arbeiten rechtzeitig abgeschlossen werden.

---
Diese Nachricht wurde automatisch vom Ablage-System generiert.
""".strip()

        urgency_color = "#dc2626" if days_remaining <= 7 else "#f59e0b"
        html_body = f"""
<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <title>Meilenstein-Erinnerung</title>
</head>
<body style="font-family: Arial, sans-serif; margin: 20px; color: #333;">
    <h1 style="color: {urgency_color};">Meilenstein-Erinnerung</h1>

    <div style="background: #fef3c7; padding: 15px; margin: 20px 0; border-radius: 8px; border-left: 4px solid {urgency_color};">
        <p><strong>Vertrag:</strong> {contract_title}</p>
        <p><strong>Meilenstein:</strong> {milestone_title}</p>
        <p><strong>Faelligkeitsdatum:</strong> {scheduled_date_str}</p>
        <p><strong>Verbleibende Tage:</strong> <span style="color: {urgency_color}; font-weight: bold;">{days_remaining}</span></p>
    </div>

    {'<p style="color: #dc2626; font-weight: bold;">⚠️ DRINGEND: Der Meilenstein ist in weniger als 7 Tagen faellig!</p>' if days_remaining <= 7 else ''}

    <p>Bitte stellen Sie sicher, dass alle erforderlichen Arbeiten rechtzeitig abgeschlossen werden.</p>

    <hr style="margin-top: 30px; border: none; border-top: 1px solid #e5e7eb;">
    <p style="font-size: 0.8em; color: #6b7280;">Diese Nachricht wurde automatisch vom Ablage-System generiert.</p>
</body>
</html>
"""

        return await self.send_email(
            to=recipient_email,
            subject=subject,
            html_body=html_body,
            text_body=text_body,
        )

    async def _get_user_email(self, user_id: Optional[UUID]) -> Optional[str]:
        """Ermittelt Email-Adresse eines Benutzers aus der DB."""
        if not user_id:
            return None

        try:
            from app.db.session import async_session_maker
            from app.db.models import User

            async with async_session_maker() as db:
                user = await db.get(User, user_id)
                if user and user.email:
                    return user.email
                return None
        except Exception as e:
            logger.warning(
                "email_user_lookup_failed",
                user_id=str(user_id),
                error_type=type(e).__name__,
            )
            return None


# =============================================================================
# Factory Function
# =============================================================================


_email_service_instance: Optional[EmailService] = None


def get_email_service() -> EmailService:
    """
    Factory-Funktion fuer EmailService (Singleton).

    Returns:
        EmailService Instanz
    """
    global _email_service_instance

    if _email_service_instance is None:
        _email_service_instance = EmailService()

    return _email_service_instance
