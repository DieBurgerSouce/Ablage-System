# -*- coding: utf-8 -*-
"""
Dunning Letter Service.

Generiert professionelle Mahnbriefe als PDF.
BGB §286 konform mit korrekten Verzugszinsen und Mahngebuehren.
"""

from __future__ import annotations

import io
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import UUID

import structlog
from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    BusinessEntity,
    Document,
    DunningRecord,
    InvoiceTracking,
    Company,
)
from app.services.banking.models import DunningLevel
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)

# Template-Verzeichnis
TEMPLATE_DIR = Path(__file__).parent.parent.parent / "templates" / "dunning"


@dataclass
class DunningLetterData:
    """Daten fuer einen Mahnbrief."""

    # Absender (Unternehmen) - Pflichtfelder
    company_name: str
    company_address: str
    company_city: str

    # Empfaenger (Schuldner) - Pflichtfelder
    recipient_name: str
    recipient_address: str
    recipient_city: str

    # Rechnung - Pflichtfelder
    invoice_number: str
    invoice_date: date
    invoice_amount: Decimal
    due_date: date
    outstanding_amount: Decimal

    # Mahnung - Pflichtfelder
    dunning_level: int  # 1-4
    dunning_date: date
    days_overdue: int

    # Gebuehren (BGB §288) - Pflichtfelder
    interest_rate: Decimal  # z.B. 9.12 fuer B2B
    interest_amount: Decimal
    dunning_fee: Decimal
    total_amount: Decimal  # Ausstehend + Zinsen + Gebuehren

    # Fristen - Pflichtfelder
    payment_deadline: date

    # Optionale Felder (Absender)
    company_phone: Optional[str] = None
    company_email: Optional[str] = None
    company_tax_id: Optional[str] = None
    company_bank_name: Optional[str] = None
    company_iban: Optional[str] = None
    company_bic: Optional[str] = None

    # Optionale Felder (Empfaenger)
    recipient_customer_number: Optional[str] = None

    # B2B Pauschale (§288 Abs. 5 BGB)
    b2b_pauschale: Optional[Decimal] = None  # EUR 40

    # Optionale Felder (Mahnung)
    escalation_warning: Optional[str] = None

    # Zusaetzliche optionale Felder
    reference: Optional[str] = None
    notes: Optional[str] = None


class DunningLetterService:
    """Service fuer die Generierung von Mahnbriefen."""

    _instance: Optional["DunningLetterService"] = None

    def __new__(cls) -> "DunningLetterService":
        """Singleton-Pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        """Initialisiert den Service."""
        if self._initialized:
            return

        self._initialized = True

        # Jinja2 Environment
        self._jinja_env = Environment(
            loader=FileSystemLoader(str(TEMPLATE_DIR)),
            autoescape=select_autoescape(["html", "xml"]),
            trim_blocks=True,
            lstrip_blocks=True,
        )

        # Custom Filter registrieren
        self._register_filters()

        # Pruefe ob ReportLab verfuegbar ist
        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import A4
            from reportlab.platypus import SimpleDocTemplate
            self._reportlab_available = True
        except ImportError:
            self._reportlab_available = False
            logger.warning("reportlab_not_available", msg="PDF-Export deaktiviert")

    def _register_filters(self) -> None:
        """Registriert Jinja2 Custom Filter."""

        def format_currency(value: Decimal | float | None) -> str:
            """Formatiert als deutsche Waehrung."""
            if value is None:
                return "0,00 EUR"
            formatted = f"{float(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            return f"{formatted} EUR"

        def format_date(value: date | datetime | None) -> str:
            """Formatiert als deutsches Datum."""
            if value is None:
                return ""
            if isinstance(value, datetime):
                value = value.date()
            return value.strftime("%d.%m.%Y")

        def format_percent(value: Decimal | float | None) -> str:
            """Formatiert als Prozentsatz."""
            if value is None:
                return "0,00 %"
            formatted = f"{float(value):.2f}".replace(".", ",")
            return f"{formatted} %"

        self._jinja_env.filters["currency"] = format_currency
        self._jinja_env.filters["date"] = format_date
        self._jinja_env.filters["percent"] = format_percent

    # =========================================================================
    # Mahnstufen-Konfiguration
    # =========================================================================

    DUNNING_LEVEL_CONFIG = {
        1: {
            "name": "Zahlungserinnerung",
            "title": "Freundliche Zahlungserinnerung",
            "tone": "freundlich",
            "fee": Decimal("0.00"),
            "payment_days": 14,
            "escalation_warning": None,
            "template": "reminder_friendly.html",
        },
        2: {
            "name": "1. Mahnung",
            "title": "Erste Mahnung",
            "tone": "sachlich",
            "fee": Decimal("5.00"),
            "payment_days": 10,
            "escalation_warning": "Bei ausbleibender Zahlung werden wir die Angelegenheit an unser Inkassobüro übergeben.",
            "template": "mahnung_1.html",
        },
        3: {
            "name": "2. Mahnung",
            "title": "Zweite Mahnung",
            "tone": "bestimmt",
            "fee": Decimal("10.00"),
            "payment_days": 7,
            "escalation_warning": "Dies ist unsere letzte Mahnung vor Einschaltung eines Inkassounternehmens.",
            "template": "mahnung_2.html",
        },
        4: {
            "name": "Letzte Mahnung",
            "title": "Letzte Mahnung vor gerichtlichem Mahnverfahren",
            "tone": "streng",
            "fee": Decimal("15.00"),
            "payment_days": 5,
            "escalation_warning": "Bei Nichtzahlung bis zum genannten Termin werden wir ohne weitere Ankündigung das gerichtliche Mahnverfahren einleiten.",
            "template": "mahnung_final.html",
        },
    }

    # =========================================================================
    # BGB §288 Zinssatz-Berechnung
    # =========================================================================

    async def get_base_interest_rate_async(self) -> Decimal:
        """
        Holt den aktuellen Basiszinssatz von der Bundesbank API.

        Der Basiszinssatz wird halbjaehrlich (01.01. und 01.07.) angepasst.
        Verwendet den BundesbankRateService mit Caching und Fallback.

        Returns:
            Aktueller Basiszinssatz
        """
        from app.services.bundesbank_rate_service import get_current_basiszins

        basiszins_data = await get_current_basiszins()
        return basiszins_data.rate

    def get_base_interest_rate(self) -> Decimal:
        """
        Holt den aktuellen Basiszinssatz der Bundesbank (synchron).

        Fuer synchrone Kontexte - verwendet Fallback-Wert.
        Fuer async Kontexte: get_base_interest_rate_async() verwenden.

        Returns:
            Aktueller Basiszinssatz (Fallback-Wert)
        """
        # Synchroner Fallback - fuer async Kontexte get_base_interest_rate_async() nutzen
        from app.services.bundesbank_rate_service import FALLBACK_BASISZINS

        return FALLBACK_BASISZINS

    def calculate_interest_rate(self, is_b2b: bool = True) -> Decimal:
        """
        Berechnet den Verzugszinssatz nach BGB §288.

        Args:
            is_b2b: True fuer B2B (Basiszins + 9%), False fuer B2C (Basiszins + 5%)

        Returns:
            Verzugszinssatz in Prozent
        """
        base_rate = self.get_base_interest_rate()
        if is_b2b:
            return base_rate + Decimal("9.00")  # §288 Abs. 2 BGB
        else:
            return base_rate + Decimal("5.00")  # §288 Abs. 1 BGB

    def calculate_interest(
        self,
        principal: Decimal,
        days_overdue: int,
        interest_rate: Decimal,
    ) -> Decimal:
        """
        Berechnet die Verzugszinsen.

        Formel: Zinsen = Hauptforderung * (Zinssatz / 100) * (Tage / 365)

        Args:
            principal: Hauptforderung
            days_overdue: Tage im Verzug
            interest_rate: Jahreszinssatz in Prozent

        Returns:
            Berechnete Zinsen (auf 2 Dezimalstellen gerundet)
        """
        if days_overdue <= 0:
            return Decimal("0.00")

        interest = principal * (interest_rate / Decimal("100")) * (Decimal(days_overdue) / Decimal("365"))
        return interest.quantize(Decimal("0.01"))

    # =========================================================================
    # Datensammlung
    # =========================================================================

    async def prepare_letter_data(
        self,
        db: AsyncSession,
        dunning_record_id: UUID,
        dunning_level: int,
        is_b2b: bool = True,
    ) -> DunningLetterData:
        """
        Sammelt alle Daten fuer einen Mahnbrief.

        Args:
            db: Datenbank-Session
            dunning_record_id: ID des DunningRecord
            dunning_level: Mahnstufe (1-4)
            is_b2b: True fuer B2B-Kunde

        Returns:
            DunningLetterData mit allen Feldern
        """
        # Lade DunningRecord mit allen Relationen
        from app.db.models import DunningRecord


        dunning_query = select(DunningRecord).where(
            DunningRecord.id == dunning_record_id
        )
        dunning_result = await db.execute(dunning_query)
        dunning = dunning_result.scalar_one_or_none()

        if not dunning:
            raise ValueError(f"DunningRecord nicht gefunden: {dunning_record_id}")

        # Lade InvoiceTracking
        invoice_query = select(InvoiceTracking).where(
            InvoiceTracking.document_id == dunning.document_id
        )
        invoice_result = await db.execute(invoice_query)
        invoice = invoice_result.scalar_one_or_none()

        if not invoice:
            raise ValueError(f"InvoiceTracking nicht gefunden fuer Document: {dunning.document_id}")

        # Lade Document
        doc_query = select(Document).where(Document.id == dunning.document_id)
        doc_result = await db.execute(doc_query)
        document = doc_result.scalar_one_or_none()

        if not document:
            raise ValueError(f"Document nicht gefunden: {dunning.document_id}")

        # Lade Company
        company_query = select(Company).where(Company.id == document.company_id)
        company_result = await db.execute(company_query)
        company = company_result.scalar_one_or_none()

        # Lade BusinessEntity (Schuldner)
        entity = None
        if invoice.entity_id:
            entity_query = select(BusinessEntity).where(
                BusinessEntity.id == invoice.entity_id
            )
            entity_result = await db.execute(entity_query)
            entity = entity_result.scalar_one_or_none()

        # Berechne Werte
        today = date.today()
        due_date = invoice.due_date if invoice.due_date else today
        days_overdue = (today - due_date).days if today > due_date else 0

        outstanding = Decimal(str(invoice.outstanding_amount or invoice.total_amount or 0))
        interest_rate = self.calculate_interest_rate(is_b2b)
        interest_amount = self.calculate_interest(outstanding, days_overdue, interest_rate)

        level_config = self.DUNNING_LEVEL_CONFIG.get(dunning_level, self.DUNNING_LEVEL_CONFIG[1])
        dunning_fee = level_config["fee"]

        # B2B Pauschale (EUR 40 nach §288 Abs. 5 BGB)
        b2b_pauschale = Decimal("40.00") if is_b2b and dunning_level >= 2 else None

        total_amount = outstanding + interest_amount + dunning_fee
        if b2b_pauschale:
            total_amount += b2b_pauschale

        payment_deadline = today + timedelta(days=level_config["payment_days"])

        # Baue DunningLetterData
        return DunningLetterData(
            # Absender
            company_name=company.name if company else "Unbekannt",
            company_address=company.address if company and hasattr(company, 'address') else "",
            company_city=company.city if company and hasattr(company, 'city') else "",
            company_phone=company.phone if company and hasattr(company, 'phone') else None,
            company_email=company.email if company and hasattr(company, 'email') else None,
            company_tax_id=company.tax_id if company and hasattr(company, 'tax_id') else None,
            company_bank_name=company.bank_name if company and hasattr(company, 'bank_name') else None,
            company_iban=company.iban if company and hasattr(company, 'iban') else None,
            company_bic=company.bic if company and hasattr(company, 'bic') else None,
            # Empfaenger
            recipient_name=entity.name if entity else "Unbekannt",
            recipient_address=entity.address if entity and hasattr(entity, 'address') else "",
            recipient_city=entity.city if entity and hasattr(entity, 'city') else "",
            recipient_customer_number=entity.primary_customer_number if entity else None,
            # Rechnung
            invoice_number=invoice.invoice_number or "N/A",
            invoice_date=invoice.invoice_date or today,
            invoice_amount=Decimal(str(invoice.total_amount or 0)),
            due_date=due_date,
            outstanding_amount=outstanding,
            # Mahnung
            dunning_level=dunning_level,
            dunning_date=today,
            days_overdue=days_overdue,
            # Gebuehren
            interest_rate=interest_rate,
            interest_amount=interest_amount,
            dunning_fee=dunning_fee,
            total_amount=total_amount,
            b2b_pauschale=b2b_pauschale,
            # Fristen
            payment_deadline=payment_deadline,
            escalation_warning=level_config.get("escalation_warning"),
            # Zusaetzlich
            reference=f"RE-{invoice.invoice_number}-M{dunning_level}",
        )

    # =========================================================================
    # HTML-Rendering
    # =========================================================================

    def render_html(self, data: DunningLetterData) -> str:
        """
        Rendert einen Mahnbrief als HTML.

        Args:
            data: DunningLetterData mit allen Feldern

        Returns:
            Gerendertes HTML
        """
        level_config = self.DUNNING_LEVEL_CONFIG.get(data.dunning_level, self.DUNNING_LEVEL_CONFIG[1])
        template_name = level_config["template"]

        # Fallback auf generisches Template
        try:
            template = self._jinja_env.get_template(template_name)
        except Exception:
            template = self._jinja_env.get_template("base_dunning.html")

        context = {
            "data": data,
            "level_config": level_config,
            "current_year": date.today().year,
        }

        return template.render(**context)

    # =========================================================================
    # PDF-Generierung
    # =========================================================================

    def render_pdf(self, data: DunningLetterData) -> bytes:
        """
        Generiert einen Mahnbrief als PDF.

        Args:
            data: DunningLetterData mit allen Feldern

        Returns:
            PDF als Bytes
        """
        if not self._reportlab_available:
            raise RuntimeError("ReportLab ist nicht installiert. PDF-Export nicht moeglich.")

        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import cm, mm
        from reportlab.platypus import (
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=2 * cm,
            leftMargin=2 * cm,
            topMargin=2 * cm,
            bottomMargin=2 * cm,
        )

        styles = getSampleStyleSheet()

        # Custom Styles
        styles.add(ParagraphStyle(
            name="CompanyHeader",
            fontSize=10,
            leading=14,
            textColor=colors.HexColor("#333333"),
        ))

        styles.add(ParagraphStyle(
            name="RecipientAddress",
            fontSize=11,
            leading=14,
            textColor=colors.black,
        ))

        styles.add(ParagraphStyle(
            name="DunningTitle",
            fontSize=16,
            leading=20,
            textColor=colors.HexColor("#CC0000"),
            spaceAfter=12,
            fontName="Helvetica-Bold",
        ))

        styles.add(ParagraphStyle(
            name="DunningBody",
            fontSize=11,
            leading=14,
            textColor=colors.black,
            spaceAfter=8,
        ))

        styles.add(ParagraphStyle(
            name="Warning",
            fontSize=11,
            leading=14,
            textColor=colors.HexColor("#CC0000"),
            spaceAfter=8,
            fontName="Helvetica-Bold",
        ))

        level_config = self.DUNNING_LEVEL_CONFIG.get(data.dunning_level, self.DUNNING_LEVEL_CONFIG[1])
        elements = []

        # Absender (klein oben)
        sender_line = f"{data.company_name} • {data.company_address} • {data.company_city}"
        elements.append(Paragraph(sender_line, styles["CompanyHeader"]))
        elements.append(Spacer(1, 1 * cm))

        # Empfaenger
        recipient = f"""
        {data.recipient_name}<br/>
        {data.recipient_address}<br/>
        {data.recipient_city}
        """
        if data.recipient_customer_number:
            recipient += f"<br/><br/>Kundennummer: {data.recipient_customer_number}"
        elements.append(Paragraph(recipient, styles["RecipientAddress"]))
        elements.append(Spacer(1, 1.5 * cm))

        # Datum und Referenz
        date_ref = f"""
        <b>{data.company_city}, {data.dunning_date.strftime('%d.%m.%Y')}</b><br/>
        Unser Zeichen: {data.reference}
        """
        elements.append(Paragraph(date_ref, styles["DunningBody"]))
        elements.append(Spacer(1, 1 * cm))

        # Titel
        elements.append(Paragraph(level_config["title"], styles["DunningTitle"]))
        elements.append(Spacer(1, 0.5 * cm))

        # Einleitungstext
        if data.dunning_level == 1:
            intro = f"""
            Sehr geehrte Damen und Herren,<br/><br/>
            bei der Durchsicht unserer Konten ist uns aufgefallen, dass die folgende
            Rechnung noch nicht beglichen wurde. Sollte sich Ihre Zahlung mit diesem
            Schreiben gekreuzt haben, bitten wir Sie, diese Erinnerung zu ignorieren.
            """
        elif data.dunning_level == 2:
            intro = f"""
            Sehr geehrte Damen und Herren,<br/><br/>
            trotz unserer Zahlungserinnerung ist der unten aufgefuehrte Betrag immer noch
            offen. Wir bitten Sie, die Zahlung umgehend vorzunehmen.
            """
        elif data.dunning_level == 3:
            intro = f"""
            Sehr geehrte Damen und Herren,<br/><br/>
            leider haben Sie auf unsere bisherigen Mahnungen nicht reagiert.
            Die folgende Forderung ist nach wie vor unbeglichen. Wir fordern Sie
            hiermit letztmalig zur Zahlung auf.
            """
        else:
            intro = f"""
            Sehr geehrte Damen und Herren,<br/><br/>
            obwohl wir Sie wiederholt zur Zahlung aufgefordert haben, ist der
            geschuldete Betrag immer noch nicht auf unserem Konto eingegangen.
            Dies ist unsere letzte Mahnung vor Einleitung rechtlicher Schritte.
            """

        elements.append(Paragraph(intro, styles["DunningBody"]))
        elements.append(Spacer(1, 0.5 * cm))

        # Forderungsaufstellung (Tabelle)
        table_data = [
            ["Position", "Betrag"],
            [f"Rechnung {data.invoice_number} vom {data.invoice_date.strftime('%d.%m.%Y')}", f"{float(data.outstanding_amount):,.2f} EUR".replace(",", "X").replace(".", ",").replace("X", ".")],
        ]

        if data.interest_amount > 0:
            table_data.append([
                f"Verzugszinsen ({data.days_overdue} Tage, {float(data.interest_rate):.2f}% p.a.)",
                f"{float(data.interest_amount):,.2f} EUR".replace(",", "X").replace(".", ",").replace("X", "."),
            ])

        if data.dunning_fee > 0:
            table_data.append([
                "Mahngebuehr",
                f"{float(data.dunning_fee):,.2f} EUR".replace(",", "X").replace(".", ",").replace("X", "."),
            ])

        if data.b2b_pauschale:
            table_data.append([
                "Pauschale nach §288 Abs. 5 BGB",
                f"{float(data.b2b_pauschale):,.2f} EUR".replace(",", "X").replace(".", ",").replace("X", "."),
            ])

        table_data.append([
            "Gesamtbetrag",
            f"{float(data.total_amount):,.2f} EUR".replace(",", "X").replace(".", ",").replace("X", "."),
        ])

        table = Table(table_data, colWidths=[12 * cm, 4 * cm])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f0f0f0")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
            ("ALIGN", (0, 0), (0, -1), "LEFT"),
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
            ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#ffffcc")),
        ]))

        elements.append(table)
        elements.append(Spacer(1, 0.5 * cm))

        # Zahlungsfrist
        payment_text = f"""
        Bitte ueberweisen Sie den Gesamtbetrag von <b>{float(data.total_amount):,.2f} EUR</b>
        bis zum <b>{data.payment_deadline.strftime('%d.%m.%Y')}</b> auf unser Konto:
        """.replace(",", "X").replace(".", ",").replace("X", ".")

        elements.append(Paragraph(payment_text, styles["DunningBody"]))
        elements.append(Spacer(1, 0.3 * cm))

        # Bankverbindung
        if data.company_iban:
            bank_info = f"""
            IBAN: {data.company_iban}<br/>
            """
            if data.company_bic:
                bank_info += f"BIC: {data.company_bic}<br/>"
            if data.company_bank_name:
                bank_info += f"Bank: {data.company_bank_name}<br/>"
            bank_info += f"Verwendungszweck: {data.reference}"
            elements.append(Paragraph(bank_info, styles["DunningBody"]))
            elements.append(Spacer(1, 0.5 * cm))

        # Eskalationswarnung
        if data.escalation_warning:
            elements.append(Paragraph(data.escalation_warning, styles["Warning"]))
            elements.append(Spacer(1, 0.5 * cm))

        # Schlussformel
        if data.dunning_level == 1:
            closing = """
            Bei Fragen stehen wir Ihnen gerne zur Verfuegung.<br/><br/>
            Mit freundlichen Gruessen
            """
        else:
            closing = """
            Fuer Rueckfragen stehen wir Ihnen zur Verfuegung.<br/><br/>
            Mit freundlichen Gruessen
            """

        elements.append(Paragraph(closing, styles["DunningBody"]))
        elements.append(Spacer(1, 1 * cm))

        # Unterschrift
        elements.append(Paragraph(data.company_name, styles["DunningBody"]))

        # Rechtlicher Hinweis (klein)
        legal = """
        <font size="8" color="#666666">
        Verzugszinsen berechnet nach §288 BGB. Basiszinssatz der Deutschen Bundesbank
        zuzueglich 9 Prozentpunkte (B2B) bzw. 5 Prozentpunkte (B2C).
        </font>
        """
        elements.append(Spacer(1, 1.5 * cm))
        elements.append(Paragraph(legal, styles["DunningBody"]))

        # PDF generieren
        doc.build(elements)
        pdf_bytes = buffer.getvalue()
        buffer.close()

        logger.info(
            "dunning_letter_pdf_generated",
            dunning_level=data.dunning_level,
            invoice_number=data.invoice_number,
            total_amount=float(data.total_amount),
        )

        return pdf_bytes

    # =========================================================================
    # High-Level API
    # =========================================================================

    async def generate_letter(
        self,
        db: AsyncSession,
        dunning_record_id: UUID,
        dunning_level: int,
        is_b2b: bool = True,
        output_format: str = "pdf",
    ) -> bytes:
        """
        Generiert einen Mahnbrief.

        Args:
            db: Datenbank-Session
            dunning_record_id: ID des DunningRecord
            dunning_level: Mahnstufe (1-4)
            is_b2b: True fuer B2B-Kunde
            output_format: "pdf" oder "html"

        Returns:
            Generierter Mahnbrief als Bytes
        """
        data = await self.prepare_letter_data(
            db=db,
            dunning_record_id=dunning_record_id,
            dunning_level=dunning_level,
            is_b2b=is_b2b,
        )

        if output_format == "html":
            return self.render_html(data).encode("utf-8")
        else:
            return self.render_pdf(data)

    async def generate_batch_letters(
        self,
        db: AsyncSession,
        dunning_records: List[Dict[str, Any]],
        output_format: str = "pdf",
    ) -> List[Dict[str, Any]]:
        """
        Generiert Mahnbriefe im Batch.

        Args:
            db: Datenbank-Session
            dunning_records: Liste von {"id": UUID, "level": int, "is_b2b": bool}
            output_format: "pdf" oder "html"

        Returns:
            Liste von {"id": UUID, "content": bytes, "error": Optional[str]}
        """
        results = []

        for record in dunning_records:
            try:
                content = await self.generate_letter(
                    db=db,
                    dunning_record_id=record["id"],
                    dunning_level=record.get("level", 1),
                    is_b2b=record.get("is_b2b", True),
                    output_format=output_format,
                )
                results.append({
                    "id": record["id"],
                    "content": content,
                    "error": None,
                })
            except Exception as e:
                logger.warning(
                    "dunning_letter_generation_error",
                    dunning_record_id=str(record["id"]),
                    **safe_error_log(e),
                )
                results.append({
                    "id": record["id"],
                    "content": None,
                    "error": safe_error_detail(e, "Vorgang"),
                })

        return results


# Singleton-Instanz
dunning_letter_service = DunningLetterService()
