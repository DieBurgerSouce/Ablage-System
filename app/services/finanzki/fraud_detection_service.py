"""
Fraud Detection Service

KI-gestuetzte Betrugserkennung mit mehreren Erkennungsmethoden:
- Duplikat-Rechnungen (Hash + Fuzzy-Match)
- Preis-Anomalien (vs. Historie + Markt)
- Phantom-Lieferanten (keine Lieferung, nur Zahlung)
- Interne Unterschlagung (Spesen-Muster, Kick-Backs)
- Netzwerk-Analyse (Shell-Companies, Strohmaenner)
"""

import hashlib
import structlog
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import and_, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    BusinessEntity,
    Document,
    InvoiceTracking,
    BankTransaction,
)

logger = structlog.get_logger(__name__)


class FraudType(str, Enum):
    """Arten von erkanntem Betrug"""
    DUPLICATE_INVOICE = "duplicate_invoice"
    PRICE_ANOMALY = "price_anomaly"
    PHANTOM_SUPPLIER = "phantom_supplier"
    EXPENSE_FRAUD = "expense_fraud"
    KICKBACK = "kickback"
    SHELL_COMPANY = "shell_company"
    ROUND_AMOUNT = "round_amount"
    SPLIT_INVOICE = "split_invoice"
    WEEKEND_INVOICE = "weekend_invoice"


class RiskLevel(str, Enum):
    """Risikostufen"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class FraudDetectionService:
    """
    Umfassender Fraud Detection Service.

    Kombiniert regelbasierte und ML-basierte Erkennung
    für verschiedene Betrugsarten.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        # Konfigurations-Schwellwerte
        self.config = {
            "price_deviation_threshold": 0.30,  # 30% Abweichung
            "duplicate_similarity_threshold": 0.85,  # 85% Ähnlichkeit
            "phantom_supplier_days": 90,  # Keine Lieferung seit 90 Tagen
            "expense_pattern_threshold": 5,  # Min. 5 ähnliche Buchungen
            "kickback_percentage_range": (0.05, 0.15),  # 5-15% Kickback-Muster
            "round_amount_threshold": 1000,  # Runde Betraege ab 1000 EUR
            "split_invoice_window_days": 7,  # Split innerhalb 7 Tagen
            "approval_threshold": 5000,  # Genehmigungsgrenze
        }

    async def analyze_all(
        self,
        company_id: UUID,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> dict[str, Any]:
        """
        Führt alle Fraud-Detection-Analysen durch.

        Returns:
            Umfassender Fraud-Report mit allen Erkennungen
        """
        if not start_date:
            start_date = datetime.utcnow() - timedelta(days=90)
        if not end_date:
            end_date = datetime.utcnow()

        results = {
            "company_id": str(company_id),
            "analysis_period": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
            },
            "summary": {
                "total_alerts": 0,
                "critical": 0,
                "high": 0,
                "medium": 0,
                "low": 0,
                "estimated_risk_amount": Decimal("0"),
            },
            "alerts": [],
            "analyzed_at": datetime.utcnow().isoformat(),
        }

        # Alle Analysen parallel ausführen
        analyses = [
            self._detect_duplicate_invoices(company_id, start_date, end_date),
            self._detect_price_anomalies(company_id, start_date, end_date),
            self._detect_phantom_suppliers(company_id),
            self._detect_expense_fraud(company_id, start_date, end_date),
            self._detect_kickback_patterns(company_id, start_date, end_date),
            self._detect_shell_companies(company_id),
            self._detect_round_amounts(company_id, start_date, end_date),
            self._detect_split_invoices(company_id, start_date, end_date),
            self._detect_weekend_invoices(company_id, start_date, end_date),
        ]

        for analysis_coro in analyses:
            try:
                alerts = await analysis_coro
                results["alerts"].extend(alerts)
            except Exception as e:
                logger.error("fraud_analysis_error", error=str(e))

        # Summary berechnen
        for alert in results["alerts"]:
            results["summary"]["total_alerts"] += 1
            results["summary"][alert["risk_level"]] += 1
            if alert.get("amount"):
                results["summary"]["estimated_risk_amount"] += Decimal(str(alert["amount"]))

        results["summary"]["estimated_risk_amount"] = float(
            results["summary"]["estimated_risk_amount"]
        )

        return results

    async def _detect_duplicate_invoices(
        self,
        company_id: UUID,
        start_date: datetime,
        end_date: datetime,
    ) -> list[dict[str, Any]]:
        """
        Erkennt Duplikat-Rechnungen mittels Hash und Fuzzy-Match.

        Methoden:
        - Exakter Hash-Match (Rechnungsnummer + Betrag + Lieferant)
        - Fuzzy-Match (ähnliche Betraege, ähnliches Datum)
        """
        alerts = []

        # Alle Rechnungen im Zeitraum laden
        query = (
            select(InvoiceTracking)
            .where(
                and_(
                    InvoiceTracking.company_id == company_id,
                    InvoiceTracking.created_at >= start_date,
                    InvoiceTracking.created_at <= end_date,
                )
            )
            .order_by(InvoiceTracking.created_at)
        )
        result = await self.db.execute(query)
        invoices = result.scalars().all()

        # Hash-basierte Duplikaterkennung
        seen_hashes: dict[str, list[InvoiceTracking]] = {}
        for invoice in invoices:
            # Hash aus Rechnungsnummer, Betrag (gerundet) und Entity
            hash_key = self._create_invoice_hash(invoice)
            if hash_key in seen_hashes:
                seen_hashes[hash_key].append(invoice)
            else:
                seen_hashes[hash_key] = [invoice]

        # Duplikate melden
        for hash_key, dupes in seen_hashes.items():
            if len(dupes) > 1:
                first = dupes[0]
                for dupe in dupes[1:]:
                    alerts.append({
                        "type": FraudType.DUPLICATE_INVOICE,
                        "risk_level": RiskLevel.HIGH,
                        "title": "Mögliche Duplikat-Rechnung",
                        "description": f"Rechnung {dupe.invoice_number or dupe.id} "
                                       f"ist möglicherweise ein Duplikat von {first.invoice_number or first.id}",
                        "invoice_id": str(dupe.id),
                        "related_invoice_id": str(first.id),
                        "amount": float(dupe.total_amount) if dupe.total_amount else None,
                        "detected_at": datetime.utcnow().isoformat(),
                        "confidence": 0.95,
                    })

        # Fuzzy-Match für ähnliche Betraege am gleichen Tag
        by_date: dict[str, list[InvoiceTracking]] = {}
        for invoice in invoices:
            date_key = invoice.created_at.date().isoformat() if invoice.created_at else "unknown"
            if date_key not in by_date:
                by_date[date_key] = []
            by_date[date_key].append(invoice)

        for date_key, day_invoices in by_date.items():
            if len(day_invoices) < 2:
                continue
            for i, inv1 in enumerate(day_invoices):
                for inv2 in day_invoices[i + 1:]:
                    if self._are_similar_amounts(inv1.total_amount, inv2.total_amount):
                        # Bereits als exaktes Duplikat erfasst?
                        if self._create_invoice_hash(inv1) == self._create_invoice_hash(inv2):
                            continue
                        alerts.append({
                            "type": FraudType.DUPLICATE_INVOICE,
                            "risk_level": RiskLevel.MEDIUM,
                            "title": "Ähnliche Rechnungen am gleichen Tag",
                            "description": f"Rechnungen {inv1.invoice_number or inv1.id} "
                                           f"und {inv2.invoice_number or inv2.id} haben ähnliche Betraege",
                            "invoice_id": str(inv1.id),
                            "related_invoice_id": str(inv2.id),
                            "amount": float(inv1.total_amount) if inv1.total_amount else None,
                            "detected_at": datetime.utcnow().isoformat(),
                            "confidence": 0.75,
                        })

        return alerts

    async def _detect_price_anomalies(
        self,
        company_id: UUID,
        start_date: datetime,
        end_date: datetime,
    ) -> list[dict[str, Any]]:
        """
        Erkennt Preis-Anomalien gegenüber historischen Daten.

        Vergleicht aktuelle Preise mit:
        - Historischem Durchschnitt pro Lieferant
        - Standardabweichung
        """
        alerts = []

        # Historische Durchschnitte pro Entity berechnen
        hist_query = (
            select(
                InvoiceTracking.entity_id,
                func.avg(InvoiceTracking.total_amount).label("avg_amount"),
                func.stddev(InvoiceTracking.total_amount).label("stddev_amount"),
                func.count(InvoiceTracking.id).label("invoice_count"),
            )
            .where(
                and_(
                    InvoiceTracking.company_id == company_id,
                    InvoiceTracking.created_at < start_date,
                    InvoiceTracking.entity_id.isnot(None),
                )
            )
            .group_by(InvoiceTracking.entity_id)
            .having(func.count(InvoiceTracking.id) >= 3)  # Min. 3 historische Rechnungen
        )
        hist_result = await self.db.execute(hist_query)
        historical = {row.entity_id: row for row in hist_result}

        # Aktuelle Rechnungen prüfen
        current_query = (
            select(InvoiceTracking)
            .where(
                and_(
                    InvoiceTracking.company_id == company_id,
                    InvoiceTracking.created_at >= start_date,
                    InvoiceTracking.created_at <= end_date,
                    InvoiceTracking.entity_id.isnot(None),
                )
            )
        )
        current_result = await self.db.execute(current_query)
        current_invoices = current_result.scalars().all()

        for invoice in current_invoices:
            if invoice.entity_id not in historical:
                continue

            hist = historical[invoice.entity_id]
            if not hist.avg_amount or not invoice.total_amount:
                continue

            avg = float(hist.avg_amount)
            stddev = float(hist.stddev_amount) if hist.stddev_amount else avg * 0.1
            amount = float(invoice.total_amount)

            # Z-Score berechnen
            if stddev > 0:
                z_score = abs(amount - avg) / stddev
            else:
                z_score = 0

            # Prozentuale Abweichung
            deviation = abs(amount - avg) / avg if avg > 0 else 0

            if z_score > 2 or deviation > self.config["price_deviation_threshold"]:
                risk_level = RiskLevel.HIGH if z_score > 3 else RiskLevel.MEDIUM
                alerts.append({
                    "type": FraudType.PRICE_ANOMALY,
                    "risk_level": risk_level,
                    "title": "Ungewoehnlicher Rechnungsbetrag",
                    "description": f"Rechnung {invoice.invoice_number or invoice.id} weicht "
                                   f"{deviation*100:.1f}% vom historischen Durchschnitt ab",
                    "invoice_id": str(invoice.id),
                    "entity_id": str(invoice.entity_id),
                    "amount": amount,
                    "expected_amount": avg,
                    "deviation_percent": deviation * 100,
                    "z_score": z_score,
                    "detected_at": datetime.utcnow().isoformat(),
                    "confidence": min(0.95, 0.5 + z_score * 0.15),
                })

        return alerts

    async def _detect_phantom_suppliers(
        self,
        company_id: UUID,
    ) -> list[dict[str, Any]]:
        """
        Erkennt Phantom-Lieferanten: Zahlungen ohne korrespondierende Lieferungen.

        Kriterien:
        - Nur Rechnungen, keine anderen Dokumenttypen
        - Hohe Zahlungsbetraege
        - Keine Lieferscheine/Bestellungen
        """
        alerts = []
        threshold_days = self.config["phantom_supplier_days"]
        cutoff_date = datetime.utcnow() - timedelta(days=threshold_days)

        # Lieferanten mit nur Rechnungen (keine Lieferscheine/Bestellungen)
        query = text("""
            WITH supplier_docs AS (
                SELECT
                    be.id as entity_id,
                    be.name as entity_name,
                    d.doc_type,
                    COUNT(*) as doc_count,
                    SUM(CASE WHEN it.total_amount IS NOT NULL THEN it.total_amount ELSE 0 END) as total_paid
                FROM business_entities be
                LEFT JOIN documents d ON d.entity_id = be.id AND d.company_id = :company_id
                LEFT JOIN invoice_tracking it ON it.entity_id = be.id AND it.company_id = :company_id
                WHERE be.entity_type = 'supplier'
                AND be.company_id = :company_id
                GROUP BY be.id, be.name, d.doc_type
            )
            SELECT
                entity_id,
                entity_name,
                SUM(total_paid) as total_paid,
                SUM(CASE WHEN doc_type = 'invoice' THEN doc_count ELSE 0 END) as invoice_count,
                SUM(CASE WHEN doc_type IN ('delivery_note', 'order', 'quote') THEN doc_count ELSE 0 END) as other_doc_count
            FROM supplier_docs
            GROUP BY entity_id, entity_name
            HAVING SUM(CASE WHEN doc_type = 'invoice' THEN doc_count ELSE 0 END) > 0
            AND SUM(CASE WHEN doc_type IN ('delivery_note', 'order', 'quote') THEN doc_count ELSE 0 END) = 0
            AND SUM(total_paid) > 5000
        """)

        result = await self.db.execute(query, {"company_id": str(company_id)})
        suspects = result.fetchall()

        for suspect in suspects:
            alerts.append({
                "type": FraudType.PHANTOM_SUPPLIER,
                "risk_level": RiskLevel.HIGH,
                "title": "Möglicher Phantom-Lieferant",
                "description": f"Lieferant '{suspect.entity_name}' hat {suspect.invoice_count} Rechnungen "
                               f"aber keine Lieferscheine/Bestellungen",
                "entity_id": str(suspect.entity_id),
                "entity_name": suspect.entity_name,
                "amount": float(suspect.total_paid) if suspect.total_paid else 0,
                "invoice_count": suspect.invoice_count,
                "detected_at": datetime.utcnow().isoformat(),
                "confidence": 0.70,
            })

        return alerts

    async def _detect_expense_fraud(
        self,
        company_id: UUID,
        start_date: datetime,
        end_date: datetime,
    ) -> list[dict[str, Any]]:
        """
        Erkennt Spesen-Betrug durch Muster-Analyse.

        Muster:
        - Häufige gleiche Betraege
        - Runde Betraege unter Genehmigungsgrenze
        - Wochenend-Buchungen
        """
        alerts = []

        # Spesen-Dokumente laden
        query = (
            select(Document)
            .where(
                and_(
                    Document.company_id == company_id,
                    Document.document_type == "expense",
                    Document.created_at >= start_date,
                    Document.created_at <= end_date,
                )
            )
        )
        result = await self.db.execute(query)
        expenses = result.scalars().all()

        # Betrags-Häufigkeit analysieren
        amount_frequency: dict[float, list[Document]] = {}
        for expense in expenses:
            amount = expense.extracted_data.get("amount") if expense.extracted_data else None
            if amount:
                amount = round(float(amount), 2)
                if amount not in amount_frequency:
                    amount_frequency[amount] = []
                amount_frequency[amount].append(expense)

        # Verdaechtig häufige Betraege
        for amount, docs in amount_frequency.items():
            if len(docs) >= self.config["expense_pattern_threshold"]:
                alerts.append({
                    "type": FraudType.EXPENSE_FRAUD,
                    "risk_level": RiskLevel.MEDIUM,
                    "title": "Verdaechtiges Spesen-Muster",
                    "description": f"Der Betrag {amount:.2f} EUR erscheint {len(docs)}x in Spesen",
                    "amount": amount,
                    "occurrence_count": len(docs),
                    "document_ids": [str(d.id) for d in docs[:5]],
                    "detected_at": datetime.utcnow().isoformat(),
                    "confidence": 0.65,
                })

        # Betraege knapp unter Genehmigungsgrenze
        approval_threshold = self.config["approval_threshold"]
        suspicious_threshold = approval_threshold * 0.95  # 95% der Grenze

        near_threshold = [
            e for e in expenses
            if e.extracted_data
            and e.extracted_data.get("amount")
            and suspicious_threshold <= float(e.extracted_data["amount"]) < approval_threshold
        ]

        if len(near_threshold) >= 3:
            alerts.append({
                "type": FraudType.EXPENSE_FRAUD,
                "risk_level": RiskLevel.HIGH,
                "title": "Betraege knapp unter Genehmigungsgrenze",
                "description": f"{len(near_threshold)} Spesen liegen knapp unter "
                               f"der Genehmigungsgrenze von {approval_threshold} EUR",
                "count": len(near_threshold),
                "document_ids": [str(e.id) for e in near_threshold[:5]],
                "detected_at": datetime.utcnow().isoformat(),
                "confidence": 0.80,
            })

        return alerts

    async def _detect_kickback_patterns(
        self,
        company_id: UUID,
        start_date: datetime,
        end_date: datetime,
    ) -> list[dict[str, Any]]:
        """
        Erkennt potenzielle Kickback-Muster.

        Indikatoren:
        - Konstante prozentuale Aufschlaege
        - Runde Betraege bei Aufschlaegen
        - Unuebliche Preisanstiege nach Lieferantenwechsel
        """
        alerts = []

        # Preisanstiege nach neuen Lieferanten analysieren
        query = text("""
            WITH price_changes AS (
                SELECT
                    it.entity_id,
                    be.name as entity_name,
                    it.total_amount,
                    it.created_at,
                    LAG(it.total_amount) OVER (
                        PARTITION BY it.entity_id
                        ORDER BY it.created_at
                    ) as prev_amount
                FROM invoice_tracking it
                JOIN business_entities be ON be.id = it.entity_id
                WHERE it.company_id = :company_id
                AND it.created_at BETWEEN :start_date AND :end_date
                AND it.total_amount IS NOT NULL
            )
            SELECT
                entity_id,
                entity_name,
                total_amount,
                prev_amount,
                (total_amount - prev_amount) / NULLIF(prev_amount, 0) as change_ratio
            FROM price_changes
            WHERE prev_amount IS NOT NULL
            AND (total_amount - prev_amount) / NULLIF(prev_amount, 0)
                BETWEEN :min_ratio AND :max_ratio
        """)

        result = await self.db.execute(
            query,
            {
                "company_id": str(company_id),
                "start_date": start_date,
                "end_date": end_date,
                "min_ratio": self.config["kickback_percentage_range"][0],
                "max_ratio": self.config["kickback_percentage_range"][1],
            }
        )

        suspicious = result.fetchall()

        # Gruppiere nach Entity und zaehle konsistente Aufschlaege
        entity_patterns: dict[str, list] = {}
        for row in suspicious:
            if row.entity_id not in entity_patterns:
                entity_patterns[row.entity_id] = []
            entity_patterns[row.entity_id].append({
                "name": row.entity_name,
                "ratio": float(row.change_ratio) if row.change_ratio else 0,
            })

        for entity_id, patterns in entity_patterns.items():
            if len(patterns) >= 3:
                avg_ratio = sum(p["ratio"] for p in patterns) / len(patterns)
                alerts.append({
                    "type": FraudType.KICKBACK,
                    "risk_level": RiskLevel.HIGH,
                    "title": "Mögliches Kickback-Muster",
                    "description": f"Lieferant '{patterns[0]['name']}' zeigt konsistente "
                                   f"Preisaufschlaege von ca. {avg_ratio*100:.1f}%",
                    "entity_id": str(entity_id),
                    "pattern_count": len(patterns),
                    "average_markup": avg_ratio * 100,
                    "detected_at": datetime.utcnow().isoformat(),
                    "confidence": 0.60,
                })

        return alerts

    async def _detect_shell_companies(
        self,
        company_id: UUID,
    ) -> list[dict[str, Any]]:
        """
        Erkennt potenzielle Shell-Companies durch Netzwerk-Analyse.

        Indikatoren:
        - Gleiche Bankverbindung bei verschiedenen Lieferanten
        - Gleiche Adresse
        - Ähnliche Namen
        """
        alerts = []

        # Lieferanten mit gleicher IBAN
        iban_query = text("""
            SELECT
                iban,
                ARRAY_AGG(DISTINCT id) as entity_ids,
                ARRAY_AGG(DISTINCT name) as entity_names,
                COUNT(DISTINCT id) as entity_count
            FROM business_entities
            WHERE company_id = :company_id
            AND entity_type = 'supplier'
            AND iban IS NOT NULL
            AND iban != ''
            GROUP BY iban
            HAVING COUNT(DISTINCT id) > 1
        """)

        result = await self.db.execute(iban_query, {"company_id": str(company_id)})
        shared_ibans = result.fetchall()

        for row in shared_ibans:
            alerts.append({
                "type": FraudType.SHELL_COMPANY,
                "risk_level": RiskLevel.CRITICAL,
                "title": "Mehrere Lieferanten mit gleicher IBAN",
                "description": f"{row.entity_count} Lieferanten teilen sich IBAN {row.iban[:10]}...",
                "iban_masked": f"{row.iban[:4]}...{row.iban[-4:]}",
                "entity_names": row.entity_names,
                "entity_count": row.entity_count,
                "detected_at": datetime.utcnow().isoformat(),
                "confidence": 0.90,
            })

        # Lieferanten mit gleicher Adresse
        address_query = text("""
            SELECT
                street,
                city,
                postal_code,
                ARRAY_AGG(DISTINCT id) as entity_ids,
                ARRAY_AGG(DISTINCT name) as entity_names,
                COUNT(DISTINCT id) as entity_count
            FROM business_entities
            WHERE company_id = :company_id
            AND entity_type = 'supplier'
            AND street IS NOT NULL
            AND street != ''
            GROUP BY street, city, postal_code
            HAVING COUNT(DISTINCT id) > 1
        """)

        result = await self.db.execute(address_query, {"company_id": str(company_id)})
        shared_addresses = result.fetchall()

        for row in shared_addresses:
            alerts.append({
                "type": FraudType.SHELL_COMPANY,
                "risk_level": RiskLevel.HIGH,
                "title": "Mehrere Lieferanten an gleicher Adresse",
                "description": f"{row.entity_count} Lieferanten an {row.street}, {row.postal_code} {row.city}",
                "address": f"{row.street}, {row.postal_code} {row.city}",
                "entity_names": row.entity_names,
                "entity_count": row.entity_count,
                "detected_at": datetime.utcnow().isoformat(),
                "confidence": 0.75,
            })

        return alerts

    async def _detect_round_amounts(
        self,
        company_id: UUID,
        start_date: datetime,
        end_date: datetime,
    ) -> list[dict[str, Any]]:
        """
        Erkennt verdaechtig viele runde Betraege.

        Runde Betraege sind ungewoehnlich bei echten Geschäftsvorgaengen.
        """
        alerts = []
        threshold = self.config["round_amount_threshold"]

        query = (
            select(InvoiceTracking)
            .where(
                and_(
                    InvoiceTracking.company_id == company_id,
                    InvoiceTracking.created_at >= start_date,
                    InvoiceTracking.created_at <= end_date,
                    InvoiceTracking.total_amount >= threshold,
                )
            )
        )
        result = await self.db.execute(query)
        invoices = result.scalars().all()

        round_invoices = []
        for invoice in invoices:
            if invoice.total_amount and self._is_round_amount(float(invoice.total_amount)):
                round_invoices.append(invoice)

        # Mehr als 20% runde Betraege ist verdaechtig
        if invoices and len(round_invoices) / len(invoices) > 0.20:
            alerts.append({
                "type": FraudType.ROUND_AMOUNT,
                "risk_level": RiskLevel.MEDIUM,
                "title": "Ungewoehnlich viele runde Betraege",
                "description": f"{len(round_invoices)} von {len(invoices)} Rechnungen "
                               f"({len(round_invoices)/len(invoices)*100:.1f}%) haben runde Betraege",
                "round_count": len(round_invoices),
                "total_count": len(invoices),
                "invoice_ids": [str(i.id) for i in round_invoices[:10]],
                "detected_at": datetime.utcnow().isoformat(),
                "confidence": 0.55,
            })

        return alerts

    async def _detect_split_invoices(
        self,
        company_id: UUID,
        start_date: datetime,
        end_date: datetime,
    ) -> list[dict[str, Any]]:
        """
        Erkennt Invoice-Splitting zur Umgehung von Genehmigungsgrenzen.

        Mehrere Rechnungen vom gleichen Lieferanten in kurzem Zeitraum,
        die zusammen die Genehmigungsgrenze überschreiten.
        """
        alerts = []
        window_days = self.config["split_invoice_window_days"]
        approval_threshold = self.config["approval_threshold"]

        query = text("""
            WITH invoice_windows AS (
                SELECT
                    it.entity_id,
                    be.name as entity_name,
                    it.id as invoice_id,
                    it.invoice_number,
                    it.total_amount,
                    it.created_at,
                    SUM(it.total_amount) OVER (
                        PARTITION BY it.entity_id
                        ORDER BY it.created_at
                        RANGE BETWEEN INTERVAL :window_days DAY PRECEDING AND CURRENT ROW
                    ) as rolling_total,
                    COUNT(*) OVER (
                        PARTITION BY it.entity_id
                        ORDER BY it.created_at
                        RANGE BETWEEN INTERVAL :window_days DAY PRECEDING AND CURRENT ROW
                    ) as invoice_count
                FROM invoice_tracking it
                JOIN business_entities be ON be.id = it.entity_id
                WHERE it.company_id = :company_id
                AND it.created_at BETWEEN :start_date AND :end_date
                AND it.total_amount IS NOT NULL
                AND it.total_amount < :threshold
            )
            SELECT DISTINCT
                entity_id,
                entity_name,
                rolling_total,
                invoice_count
            FROM invoice_windows
            WHERE invoice_count >= 2
            AND rolling_total > :threshold
            AND total_amount < :threshold
        """)

        result = await self.db.execute(
            query,
            {
                "company_id": str(company_id),
                "start_date": start_date,
                "end_date": end_date,
                "window_days": f"{window_days}",
                "threshold": approval_threshold,
            }
        )

        splits = result.fetchall()

        for row in splits:
            alerts.append({
                "type": FraudType.SPLIT_INVOICE,
                "risk_level": RiskLevel.HIGH,
                "title": "Mögliches Invoice-Splitting",
                "description": f"Lieferant '{row.entity_name}' hat {row.invoice_count} Rechnungen "
                               f"in {window_days} Tagen mit Gesamtsumme {float(row.rolling_total):.2f} EUR",
                "entity_id": str(row.entity_id),
                "entity_name": row.entity_name,
                "invoice_count": row.invoice_count,
                "total_amount": float(row.rolling_total),
                "threshold": approval_threshold,
                "detected_at": datetime.utcnow().isoformat(),
                "confidence": 0.70,
            })

        return alerts

    async def _detect_weekend_invoices(
        self,
        company_id: UUID,
        start_date: datetime,
        end_date: datetime,
    ) -> list[dict[str, Any]]:
        """
        Erkennt Rechnungen die am Wochenende erstellt wurden.

        Wochenend-Rechnungen können auf manuelle Manipulation hindeuten.
        """
        alerts = []

        query = text("""
            SELECT
                id,
                invoice_number,
                total_amount,
                created_at,
                EXTRACT(DOW FROM created_at) as day_of_week
            FROM invoice_tracking
            WHERE company_id = :company_id
            AND created_at BETWEEN :start_date AND :end_date
            AND EXTRACT(DOW FROM created_at) IN (0, 6)
        """)

        result = await self.db.execute(
            query,
            {
                "company_id": str(company_id),
                "start_date": start_date,
                "end_date": end_date,
            }
        )

        weekend_invoices = result.fetchall()

        if len(weekend_invoices) >= 5:
            total_amount = sum(float(i.total_amount) for i in weekend_invoices if i.total_amount)
            alerts.append({
                "type": FraudType.WEEKEND_INVOICE,
                "risk_level": RiskLevel.LOW,
                "title": "Wochenend-Rechnungen erkannt",
                "description": f"{len(weekend_invoices)} Rechnungen wurden am Wochenende erstellt",
                "count": len(weekend_invoices),
                "total_amount": total_amount,
                "invoice_ids": [str(i.id) for i in weekend_invoices[:10]],
                "detected_at": datetime.utcnow().isoformat(),
                "confidence": 0.40,
            })

        return alerts

    # ==================== Helper Methods ====================

    def _create_invoice_hash(self, invoice: InvoiceTracking) -> str:
        """Erstellt einen Hash zur Duplikat-Erkennung."""
        components = [
            str(invoice.invoice_number or "").lower().strip(),
            f"{float(invoice.total_amount or 0):.2f}",
            str(invoice.entity_id or ""),
        ]
        combined = "|".join(components)
        return hashlib.md5(combined.encode()).hexdigest()

    def _are_similar_amounts(
        self,
        amount1: Optional[Decimal],
        amount2: Optional[Decimal],
        tolerance: float = 0.02,  # 2% Toleranz
    ) -> bool:
        """Prüft ob zwei Betraege ähnlich sind."""
        if not amount1 or not amount2:
            return False
        a1, a2 = float(amount1), float(amount2)
        if a1 == 0 or a2 == 0:
            return False
        diff = abs(a1 - a2) / max(a1, a2)
        return diff <= tolerance

    def _is_round_amount(self, amount: float) -> bool:
        """Prüft ob ein Betrag verdaechtig rund ist."""
        # Rund auf 100, 500, 1000 etc.
        return (
            amount >= 100 and (
                amount % 1000 == 0 or
                amount % 500 == 0 or
                (amount % 100 == 0 and amount % 50 == 0)
            )
        )


# Singleton-artige Factory
async def get_fraud_detection_service(db: AsyncSession) -> FraudDetectionService:
    """Factory für FraudDetectionService."""
    return FraudDetectionService(db)
