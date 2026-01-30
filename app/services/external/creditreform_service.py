# -*- coding: utf-8 -*-
"""
Creditreform Integration Service.

Anbindung an Creditreform fuer Bonitaetspruefungen:
- Unternehmensdaten abrufen
- Bonitaets-Scores
- Insolvenz-Monitoring
- Kreditlimit-Empfehlungen

Vision 2.0 Feature: Erweiterte Integrationen
Feinpoliert und durchdacht.
"""

import logging
import hashlib
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, Dict, Any, List
from uuid import UUID
from enum import Enum

import httpx
from pydantic import BaseModel, Field
from redis.asyncio import Redis

from app.core.config import settings

logger = logging.getLogger(__name__)


class CreditRating(str, Enum):
    """Creditreform Bonitaetsindex."""
    EXCELLENT = "100"    # Ausgezeichnete Bonitaet
    VERY_GOOD = "150"    # Sehr gute Bonitaet
    GOOD = "200"         # Gute Bonitaet
    SATISFACTORY = "250" # Zufriedenstellende Bonitaet
    ADEQUATE = "300"     # Ausreichende Bonitaet
    WEAK = "350"         # Schwache Bonitaet
    VERY_WEAK = "400"    # Sehr schwache Bonitaet
    CRITICAL = "500"     # Kritische Bonitaet
    INSOLVENT = "600"    # Insolvenz


class CreditCheckResult(BaseModel):
    """Ergebnis einer Bonitaetspruefung."""
    crefo_id: str = Field(..., description="Creditreform ID")
    company_name: str
    legal_form: Optional[str] = None
    address: Optional[Dict[str, str]] = None

    # Bonitaetsdaten
    credit_index: int = Field(..., ge=100, le=600, description="Bonitaetsindex (100-600)")
    credit_rating: str  # Enum value
    probability_of_default: float = Field(..., ge=0, le=100, description="Ausfallwahrscheinlichkeit in %")

    # Finanzdaten
    recommended_credit_limit: Optional[Decimal] = None
    revenue: Optional[Decimal] = None
    employees: Optional[int] = None
    founded_year: Optional[int] = None

    # Status
    is_active: bool = True
    insolvency_status: Optional[str] = None  # None, "opened", "pending", "rejected"
    last_updated: datetime

    # Warnungen
    warnings: List[str] = Field(default_factory=list)
    negative_features: List[str] = Field(default_factory=list)


class CreditMonitoringEvent(BaseModel):
    """Ereignis aus dem Monitoring."""
    event_type: str
    event_date: datetime
    description: str
    severity: str  # info, warning, critical
    details: Optional[Dict[str, Any]] = None


class CreditreformService:
    """
    Service fuer Creditreform-Anbindung.

    Unterstuetzt:
    - Einzelabfragen
    - Batch-Abfragen
    - Monitoring-Alerts
    - Caching fuer Kostenoptimierung
    """

    # API-Konfiguration
    BASE_URL = "https://api.creditreform.de/v1"  # Placeholder
    CACHE_TTL = 86400  # 24 Stunden

    # Kosten-Tracking
    COST_PER_QUERY = Decimal("2.50")  # EUR pro Abfrage

    def __init__(self, redis_client: Optional[Redis] = None):
        """
        Initialisiere Service.

        Args:
            redis_client: Optional Redis fuer Caching
        """
        self.redis = redis_client
        self.api_key = getattr(settings, "CREDITREFORM_API_KEY", None)
        self.api_secret = getattr(settings, "CREDITREFORM_API_SECRET", None)

        # Mock-Modus wenn keine Credentials
        self.mock_mode = not (self.api_key and self.api_secret)

        if self.mock_mode:
            logger.warning("Creditreform: Running in MOCK mode (no credentials)")

    async def check_credit(
        self,
        company_name: Optional[str] = None,
        crefo_id: Optional[str] = None,
        vat_id: Optional[str] = None,
        address: Optional[Dict[str, str]] = None,
        use_cache: bool = True,
    ) -> CreditCheckResult:
        """
        Fuehre Bonitaetspruefung durch.

        Args:
            company_name: Firmenname
            crefo_id: Creditreform-ID (falls bekannt)
            vat_id: USt-ID
            address: Adresse fuer Identifikation
            use_cache: Cache nutzen

        Returns:
            CreditCheckResult mit Bonitaetsdaten

        Raises:
            ValueError: Wenn keine Identifikationsdaten
            httpx.HTTPError: Bei API-Fehler
        """
        if not any([company_name, crefo_id, vat_id]):
            raise ValueError("Mindestens company_name, crefo_id oder vat_id erforderlich")

        # Cache-Key generieren
        cache_key = self._generate_cache_key(company_name, crefo_id, vat_id)

        # Cache pruefen
        if use_cache and self.redis:
            cached = await self._get_cached(cache_key)
            if cached:
                # SECURITY: Keine PII (cache_key) in Logs (CWE-532)
                logger.info("creditreform_cache_hit")
                return CreditCheckResult(**cached)

        # API-Abfrage oder Mock
        if self.mock_mode:
            result = self._generate_mock_result(company_name, crefo_id, vat_id)
        else:
            result = await self._api_check_credit(company_name, crefo_id, vat_id, address)

        # Cache speichern
        if self.redis:
            await self._set_cached(cache_key, result.model_dump())

        return result

    async def get_insolvency_status(
        self,
        crefo_id: str,
    ) -> Dict[str, Any]:
        """
        Pruefe Insolvenz-Status.

        Args:
            crefo_id: Creditreform-ID

        Returns:
            Insolvenz-Informationen
        """
        if self.mock_mode:
            return {
                "crefo_id": crefo_id,
                "insolvency_status": None,
                "insolvency_date": None,
                "insolvency_court": None,
                "is_active": True,
            }

        # Echte API-Abfrage
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/insolvency/{crefo_id}",
                headers=self._get_headers(),
                timeout=30.0,
            )
            response.raise_for_status()
            return response.json()

    async def batch_check(
        self,
        entities: List[Dict[str, str]],
    ) -> List[CreditCheckResult]:
        """
        Batch-Bonitaetspruefung fuer mehrere Unternehmen.

        Args:
            entities: Liste von Identifikationsdaten
                      [{"company_name": "...", "vat_id": "..."}, ...]

        Returns:
            Liste von CreditCheckResult
        """
        results = []

        for entity in entities:
            try:
                result = await self.check_credit(
                    company_name=entity.get("company_name"),
                    crefo_id=entity.get("crefo_id"),
                    vat_id=entity.get("vat_id"),
                    address=entity.get("address"),
                )
                results.append(result)
            except Exception as e:
                # SECURITY: Keine PII (entity) und keine Exception-Details in Logs (CWE-532)
                logger.error("creditreform_batch_check_failed", error_type=type(e).__name__)
                # Fuege Fehler-Ergebnis hinzu - generische Fehlermeldung
                results.append(self._generate_error_result(entity, "Abfrage fehlgeschlagen"))

        return results

    async def get_monitoring_events(
        self,
        crefo_id: str,
        since: Optional[datetime] = None,
    ) -> List[CreditMonitoringEvent]:
        """
        Hole Monitoring-Ereignisse.

        Args:
            crefo_id: Creditreform-ID
            since: Nur Ereignisse seit diesem Zeitpunkt

        Returns:
            Liste von Monitoring-Ereignissen
        """
        if self.mock_mode:
            # Mock-Events
            return [
                CreditMonitoringEvent(
                    event_type="address_change",
                    event_date=datetime.utcnow() - timedelta(days=30),
                    description="Adressaenderung registriert",
                    severity="info",
                ),
            ]

        async with httpx.AsyncClient() as client:
            params = {"since": since.isoformat()} if since else {}
            response = await client.get(
                f"{self.BASE_URL}/monitoring/{crefo_id}/events",
                headers=self._get_headers(),
                params=params,
                timeout=30.0,
            )
            response.raise_for_status()

            events = response.json().get("events", [])
            return [CreditMonitoringEvent(**e) for e in events]

    async def start_monitoring(
        self,
        crefo_id: str,
        webhook_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Starte Monitoring fuer ein Unternehmen.

        Args:
            crefo_id: Creditreform-ID
            webhook_url: URL fuer Benachrichtigungen

        Returns:
            Monitoring-Konfiguration
        """
        if self.mock_mode:
            return {
                "crefo_id": crefo_id,
                "monitoring_active": True,
                "monitoring_id": f"MON-{crefo_id}",
                "webhook_url": webhook_url,
            }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.BASE_URL}/monitoring",
                headers=self._get_headers(),
                json={
                    "crefo_id": crefo_id,
                    "webhook_url": webhook_url,
                    "events": ["insolvency", "address_change", "management_change", "rating_change"],
                },
                timeout=30.0,
            )
            response.raise_for_status()
            return response.json()

    async def stop_monitoring(
        self,
        crefo_id: str,
    ) -> bool:
        """
        Stoppe Monitoring.

        Args:
            crefo_id: Creditreform-ID

        Returns:
            True wenn erfolgreich
        """
        if self.mock_mode:
            return True

        async with httpx.AsyncClient() as client:
            response = await client.delete(
                f"{self.BASE_URL}/monitoring/{crefo_id}",
                headers=self._get_headers(),
                timeout=30.0,
            )
            return response.status_code == 204

    def calculate_internal_score(
        self,
        credit_result: CreditCheckResult,
        payment_history: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Berechne internen Risiko-Score.

        Kombiniert Creditreform-Daten mit eigenen Erfahrungen.

        Args:
            credit_result: Creditreform-Ergebnis
            payment_history: Optionale interne Zahlungshistorie

        Returns:
            Kombinierter Score mit Empfehlungen
        """
        # Basis-Score aus Creditreform (invertiert: niedriger = besser)
        base_score = 100 - ((credit_result.credit_index - 100) / 5)
        base_score = max(0, min(100, base_score))

        # Anpassungen basierend auf Warnungen
        adjustments = 0
        for warning in credit_result.warnings:
            adjustments -= 5
        for neg in credit_result.negative_features:
            adjustments -= 10

        # Insolvenz-Anpassung
        if credit_result.insolvency_status:
            if credit_result.insolvency_status == "opened":
                adjustments -= 100
            elif credit_result.insolvency_status == "pending":
                adjustments -= 50

        # Interne Historie einbeziehen
        if payment_history:
            avg_delay = payment_history.get("avg_delay_days", 0)
            if avg_delay > 30:
                adjustments -= min(20, avg_delay / 2)

            default_rate = payment_history.get("default_rate", 0)
            if default_rate > 0.05:
                adjustments -= default_rate * 100

        final_score = max(0, min(100, base_score + adjustments))

        # Risiko-Level
        if final_score >= 80:
            risk_level = "low"
            recommendation = "Normale Geschaeftsbeziehung empfohlen"
        elif final_score >= 60:
            risk_level = "medium"
            recommendation = "Regelmaessige Ueberwachung empfohlen"
        elif final_score >= 40:
            risk_level = "high"
            recommendation = "Vorkasse oder Kreditlimit reduzieren"
        else:
            risk_level = "critical"
            recommendation = "Geschaeftsbeziehung nicht empfohlen"

        return {
            "internal_score": round(final_score, 2),
            "creditreform_score": credit_result.credit_index,
            "risk_level": risk_level,
            "recommendation": recommendation,
            "recommended_credit_limit": float(credit_result.recommended_credit_limit) if credit_result.recommended_credit_limit else None,
            "adjustments_applied": adjustments,
        }

    # =========================================================================
    # Private Methods
    # =========================================================================

    def _get_headers(self) -> Dict[str, str]:
        """Generiere API-Headers."""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "X-API-Secret": self.api_secret or "",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _generate_cache_key(
        self,
        company_name: Optional[str],
        crefo_id: Optional[str],
        vat_id: Optional[str],
    ) -> str:
        """Generiere Cache-Key."""
        key_parts = [
            company_name or "",
            crefo_id or "",
            vat_id or "",
        ]
        key_string = "|".join(key_parts)
        return f"crefo:{hashlib.md5(key_string.encode()).hexdigest()}"

    async def _get_cached(self, key: str) -> Optional[Dict]:
        """Hole aus Cache."""
        if not self.redis:
            return None

        try:
            import json
            data = await self.redis.get(key)
            if data:
                return json.loads(data)
        except Exception as e:
            # SECURITY: Keine Exception-Details in Logs (CWE-532) - koennte PII enthalten
            logger.warning("creditreform_cache_read_error", error_type=type(e).__name__)

        return None

    async def _set_cached(self, key: str, data: Dict) -> None:
        """Speichere in Cache."""
        if not self.redis:
            return

        try:
            import json
            await self.redis.setex(key, self.CACHE_TTL, json.dumps(data, default=str))
        except Exception as e:
            # SECURITY: Keine Exception-Details in Logs (CWE-532) - koennte PII enthalten
            logger.warning("creditreform_cache_write_error", error_type=type(e).__name__)

    async def _api_check_credit(
        self,
        company_name: Optional[str],
        crefo_id: Optional[str],
        vat_id: Optional[str],
        address: Optional[Dict[str, str]],
    ) -> CreditCheckResult:
        """Echte API-Abfrage."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.BASE_URL}/credit-check",
                headers=self._get_headers(),
                json={
                    "company_name": company_name,
                    "crefo_id": crefo_id,
                    "vat_id": vat_id,
                    "address": address,
                },
                timeout=60.0,
            )
            response.raise_for_status()

            data = response.json()
            return CreditCheckResult(**data)

    def _generate_mock_result(
        self,
        company_name: Optional[str],
        crefo_id: Optional[str],
        vat_id: Optional[str],
    ) -> CreditCheckResult:
        """Generiere Mock-Ergebnis fuer Tests."""
        import random

        # Deterministischer "Zufall" basierend auf Namen
        name_hash = hash(company_name or crefo_id or vat_id or "unknown")
        random.seed(name_hash)

        # Generiere realistische Werte
        credit_indices = [100, 150, 200, 250, 300, 350]
        weights = [5, 20, 35, 25, 10, 5]  # Normalverteilung
        credit_index = random.choices(credit_indices, weights=weights)[0]

        rating_map = {
            100: CreditRating.EXCELLENT,
            150: CreditRating.VERY_GOOD,
            200: CreditRating.GOOD,
            250: CreditRating.SATISFACTORY,
            300: CreditRating.ADEQUATE,
            350: CreditRating.WEAK,
        }

        pod_map = {
            100: 0.1, 150: 0.3, 200: 0.8, 250: 2.0, 300: 5.0, 350: 12.0
        }

        limit_map = {
            100: 500000, 150: 250000, 200: 100000, 250: 50000, 300: 20000, 350: 5000
        }

        warnings = []
        negative = []

        if credit_index >= 300:
            warnings.append("Erhoehtes Ausfallrisiko")
        if credit_index >= 350:
            negative.append("Zahlungsstoerungen gemeldet")

        return CreditCheckResult(
            crefo_id=crefo_id or f"DE{abs(name_hash) % 100000000:08d}",
            company_name=company_name or "Unbekannt GmbH",
            legal_form="GmbH",
            address={
                "street": "Musterstrasse 123",
                "postal_code": "12345",
                "city": "Musterstadt",
                "country": "DE",
            },
            credit_index=credit_index,
            credit_rating=rating_map[credit_index].value,
            probability_of_default=pod_map[credit_index],
            recommended_credit_limit=Decimal(str(limit_map[credit_index])),
            revenue=Decimal(str(random.randint(100000, 10000000))),
            employees=random.randint(5, 500),
            founded_year=random.randint(1970, 2020),
            is_active=True,
            insolvency_status=None,
            last_updated=datetime.utcnow(),
            warnings=warnings,
            negative_features=negative,
        )

    def _generate_error_result(
        self,
        entity: Dict[str, str],
        error: str,
    ) -> CreditCheckResult:
        """Generiere Fehler-Ergebnis."""
        return CreditCheckResult(
            crefo_id="ERROR",
            company_name=entity.get("company_name", "Unknown"),
            credit_index=600,
            credit_rating=CreditRating.CRITICAL.value,
            probability_of_default=100.0,
            is_active=False,
            last_updated=datetime.utcnow(),
            # SECURITY: Keine Exception-Details in User-Facing Responses (CWE-209)
            warnings=["Abfrage fehlgeschlagen"],
            negative_features=["Keine Bonitaetsdaten verfuegbar"],
        )
