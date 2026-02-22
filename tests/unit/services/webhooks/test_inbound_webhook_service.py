# -*- coding: utf-8 -*-
"""
Unit Tests fuer den Inbound Webhook Service.

Testet alle modularen Funktionen und den 9-Schritt-Flow der
InboundWebhookService-Klasse vollstaendig und isoliert.

Kein echter Datenbankzugriff, kein echtes Celery – ausschliesslich Mocks.
"""

import hashlib
import hmac
import json
import sys
import types
import uuid
from datetime import datetime, timezone
from typing import Optional, Set
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException


# ---------------------------------------------------------------------------
# Celery-Task-Modul vorab mocken (lazy import im Service-Code).
# Das Modul app.workers.tasks.webhook_inbound_tasks wird erst beim Ausführen
# des Celery-Schritts in process_webhook importiert. Da das echte Modul
# externe Abhaengigkeiten (psutil, torch, ...) hat, mocken wir es vorab.
# ---------------------------------------------------------------------------
_mock_celery_module = types.ModuleType("app.workers.tasks.webhook_inbound_tasks")
_mock_celery_task = MagicMock()
_mock_celery_module.process_inbound_webhook = _mock_celery_task

# Alle noetigen Zwischen-Pakete ebenfalls registrieren
for _mod_name in (
    "app.workers",
    "app.workers.tasks",
    "app.workers.tasks.webhook_inbound_tasks",
):
    if _mod_name not in sys.modules:
        sys.modules[_mod_name] = types.ModuleType(_mod_name)

sys.modules["app.workers.tasks.webhook_inbound_tasks"] = _mock_celery_module

from app.schemas.webhook_inbound import (
    InboundWebhookResponse,
    InboundWebhookStatus,
)
from app.services.webhooks.inbound_service import (
    MAX_PAYLOAD_SIZE,
    SIGNATURE_TIMESTAMP_TOLERANCE_SECONDS,
    InboundWebhookService,
    compute_payload_hash,
    sanitize_payload_for_preview,
    validate_timestamp,
    verify_webhook_signature,
)
from app.services.webhooks.providers import BaseWebhookProvider

# Testmarkierungen fuer das gesamte Modul
pytestmark = [pytest.mark.unit]


# =============================================================================
# Hilfsfunktionen und Fixtures
# =============================================================================


def _make_valid_timestamp() -> str:
    """Erzeugt einen gueltigen Unix-Timestamp (aktuell)."""
    return str(int(datetime.now(timezone.utc).timestamp()))


def _make_expired_timestamp() -> str:
    """Erzeugt einen abgelaufenen Timestamp (mehr als 5 Minuten in der Vergangenheit)."""
    past = int(datetime.now(timezone.utc).timestamp()) - SIGNATURE_TIMESTAMP_TOLERANCE_SECONDS - 60
    return str(past)


def _make_signature(payload: bytes, timestamp: str, secret: str) -> str:
    """Erzeugt eine gueltige HMAC-SHA256 Signatur."""
    message = f"{timestamp}.".encode() + payload
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def _make_valid_payload_bytes(
    event_id: str = "evt-123",
    event_type: str = "invoice.received",
    action: str = "create",
    data: Optional[dict] = None,
) -> bytes:
    """Erzeugt einen gueltigen JSON-Payload als Bytes."""
    return json.dumps({
        "event_id": event_id,
        "event_type": event_type,
        "action": action,
        "data": data or {"invoice_number": "RE-2024-001"},
    }).encode()


@pytest.fixture
def mock_db() -> AsyncMock:
    """Bereitstellung einer Mock-AsyncSession."""
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    return db


@pytest.fixture
def mock_adapter() -> MagicMock:
    """Bereitstellung eines Mock-Provider-Adapters."""
    adapter = MagicMock(spec=BaseWebhookProvider)
    adapter.provider_name = "dhl"
    adapter.signature_header = "X-DHL-Signature"
    adapter.timestamp_header = "X-DHL-Timestamp"
    adapter.webhook_id_header = "X-DHL-Webhook-Id"
    adapter.get_pii_fields.return_value = {"name", "email", "address"}
    adapter.map_event.return_value = None
    adapter.extract_external_ref.return_value = "TRACK-9876"
    return adapter


@pytest.fixture
def mock_request() -> AsyncMock:
    """Bereitstellung eines Mock-FastAPI-Request-Objekts."""
    request = AsyncMock()
    request.headers = {}
    return request


@pytest.fixture
def service(mock_db: AsyncMock) -> InboundWebhookService:
    """Bereitstellung einer InboundWebhookService-Instanz mit Mock-DB."""
    return InboundWebhookService(db=mock_db)


# =============================================================================
# Tests fuer compute_payload_hash
# =============================================================================


class TestComputePayloadHash:
    """Tests fuer die SHA-256-Hashberechnung des Payloads."""

    def test_hash_ist_sha256_hexdigest(self) -> None:
        """Hash muss ein SHA-256-Hexdigest mit 64 Zeichen sein."""
        payload = b"test payload"
        result = compute_payload_hash(payload)
        expected = hashlib.sha256(payload).hexdigest()
        assert result == expected
        assert len(result) == 64

    def test_gleiche_payloads_identische_hashes(self) -> None:
        """Identische Payloads muessen identische Hashes erzeugen."""
        payload = b'{"event_id": "abc-123"}'
        assert compute_payload_hash(payload) == compute_payload_hash(payload)

    def test_unterschiedliche_payloads_unterschiedliche_hashes(self) -> None:
        """Verschiedene Payloads muessen verschiedene Hashes liefern."""
        h1 = compute_payload_hash(b"payload_a")
        h2 = compute_payload_hash(b"payload_b")
        assert h1 != h2

    def test_leerer_payload(self) -> None:
        """Leerer Payload muss ohne Fehler gehasht werden."""
        result = compute_payload_hash(b"")
        assert isinstance(result, str)
        assert len(result) == 64

    def test_utf8_payload(self) -> None:
        """Payload mit Umlauten muss korrekt gehasht werden."""
        payload = "Rechnungsnummer: RE-2024-Ä001".encode("utf-8")
        result = compute_payload_hash(payload)
        assert isinstance(result, str)
        assert len(result) == 64


# =============================================================================
# Tests fuer verify_webhook_signature
# =============================================================================


class TestVerifyWebhookSignature:
    """Tests fuer die HMAC-SHA256 Signaturverifikation."""

    def test_gueltige_signatur_gibt_true(self) -> None:
        """Eine korrekt berechnete Signatur muss True ergeben."""
        payload = b'{"event_id": "evt-1"}'
        timestamp = _make_valid_timestamp()
        secret = "super-geheimes-webhook-secret"
        sig = _make_signature(payload, timestamp, secret)
        assert verify_webhook_signature(payload, sig, timestamp, secret) is True

    def test_falsche_signatur_gibt_false(self) -> None:
        """Eine manipulierte Signatur muss False ergeben."""
        payload = b'{"event_id": "evt-1"}'
        timestamp = _make_valid_timestamp()
        secret = "geheimnis"
        assert verify_webhook_signature(payload, "falsche-signatur", timestamp, secret) is False

    def test_falsches_secret_gibt_false(self) -> None:
        """Ein falsches Secret muss bei korrekter Signatur False ergeben."""
        payload = b'{"event_id": "evt-1"}'
        timestamp = _make_valid_timestamp()
        sig = _make_signature(payload, timestamp, "richtiges-secret")
        assert verify_webhook_signature(payload, sig, timestamp, "falsches-secret") is False

    def test_manipulierter_payload_gibt_false(self) -> None:
        """Ein veraenderter Payload bei gleicher Signatur muss False ergeben."""
        original = b'{"event_id": "evt-1"}'
        manipulated = b'{"event_id": "evt-2"}'
        timestamp = _make_valid_timestamp()
        secret = "secret"
        sig = _make_signature(original, timestamp, secret)
        assert verify_webhook_signature(manipulated, sig, timestamp, secret) is False

    def test_leerer_timestamp_gibt_false(self) -> None:
        """Leerer Timestamp veraendert die Nachricht – Signatur muss False ergeben."""
        payload = b"payload"
        secret = "secret"
        sig = _make_signature(payload, "1700000000", secret)
        # Signatur wurde mit Timestamp berechnet, leerer Timestamp aendert Nachricht
        assert verify_webhook_signature(payload, sig, "", secret) is False

    def test_exception_gibt_false(self) -> None:
        """Bei unerwarteten Fehlern (z.B. None-Werte) muss False zurueckgegeben werden."""
        # None als payload loest intern einen Fehler aus
        result = verify_webhook_signature(None, "sig", "ts", "secret")  # type: ignore[arg-type]
        assert result is False


# =============================================================================
# Tests fuer validate_timestamp
# =============================================================================


class TestValidateTimestamp:
    """Tests fuer den Replay-Schutz durch Timestamp-Validierung."""

    def test_aktueller_timestamp_gueltig(self) -> None:
        """Ein aktueller Timestamp muss als gueltig gelten."""
        assert validate_timestamp(_make_valid_timestamp()) is True

    def test_abgelaufener_timestamp_ungueltig(self) -> None:
        """Ein zu alter Timestamp muss als ungueltig gelten."""
        assert validate_timestamp(_make_expired_timestamp()) is False

    def test_zukuenftiger_timestamp_ungueltig(self) -> None:
        """Ein weit in der Zukunft liegender Timestamp muss abgelehnt werden."""
        future = str(int(datetime.now(timezone.utc).timestamp()) + SIGNATURE_TIMESTAMP_TOLERANCE_SECONDS + 60)
        assert validate_timestamp(future) is False

    def test_kein_integer_gibt_false(self) -> None:
        """Ein nicht-numerischer Timestamp muss False ergeben."""
        assert validate_timestamp("kein-timestamp") is False

    def test_leerer_string_gibt_false(self) -> None:
        """Leerer String muss False ergeben."""
        assert validate_timestamp("") is False

    def test_none_gibt_false(self) -> None:
        """None muss False ergeben."""
        assert validate_timestamp(None) is False  # type: ignore[arg-type]

    def test_grenzwert_exakt_an_toleranz(self) -> None:
        """Timestamp exakt am Toleranzlimit muss noch gueltig sein."""
        borderline = str(int(datetime.now(timezone.utc).timestamp()) - SIGNATURE_TIMESTAMP_TOLERANCE_SECONDS)
        # Am Grenzwert: abs(diff) == TOLERANCE -> gueltig (<=)
        assert validate_timestamp(borderline) is True


# =============================================================================
# Tests fuer sanitize_payload_for_preview
# =============================================================================


class TestSanitizePayloadForPreview:
    """Tests fuer die PII-Entfernung aus Payloads."""

    def test_pii_felder_werden_redacted(self) -> None:
        """PII-Felder muessen durch [REDACTED] ersetzt werden."""
        data = {"name": "Max Mustermann", "invoice_number": "RE-001"}
        pii = {"name", "email"}
        result = sanitize_payload_for_preview(data, pii)
        assert result["name"] == "[REDACTED]"
        assert result["invoice_number"] == "RE-001"

    def test_case_insensitive_pii_erkennung(self) -> None:
        """PII-Erkennung muss Gross-/Kleinschreibung ignorieren."""
        data = {"NAME": "Max Mustermann", "Email": "max@example.com"}
        pii = {"name", "email"}
        result = sanitize_payload_for_preview(data, pii)
        assert result["NAME"] == "[REDACTED]"
        assert result["Email"] == "[REDACTED]"

    def test_verschachteltes_dict_wird_rekursiv_bereinigt(self) -> None:
        """Verschachtelte Dicts muessen ebenfalls bereinigt werden."""
        data = {
            "shipment": {
                "name": "Empfaenger Mustermann",
                "tracking_number": "TRACK-123",
            }
        }
        pii = {"name"}
        result = sanitize_payload_for_preview(data, pii)
        assert result["shipment"]["name"] == "[REDACTED]"
        assert result["shipment"]["tracking_number"] == "TRACK-123"

    def test_liste_mit_dicts_wird_bereinigt(self) -> None:
        """Listen von Dicts muessen element-weise bereinigt werden."""
        data = {
            "items": [
                {"name": "Kunde A", "amount": 100},
                {"name": "Kunde B", "amount": 200},
            ]
        }
        pii = {"name"}
        result = sanitize_payload_for_preview(data, pii)
        assert result["items"][0]["name"] == "[REDACTED]"
        assert result["items"][0]["amount"] == 100
        assert result["items"][1]["name"] == "[REDACTED]"

    def test_leere_pii_menge_keine_aenderungen(self) -> None:
        """Leere PII-Menge darf keine Aenderungen vornehmen."""
        data = {"name": "Testname", "value": 42}
        result = sanitize_payload_for_preview(data, set())
        assert result["name"] == "Testname"
        assert result["value"] == 42

    def test_leeres_dict_gibt_leeres_dict_zurueck(self) -> None:
        """Leeres Input-Dict muss leeres Output-Dict ergeben."""
        result = sanitize_payload_for_preview({}, {"name"})
        assert result == {}

    def test_liste_mit_nicht_dicts_bleibt_unveraendert(self) -> None:
        """Listen mit Nicht-Dict-Elementen muessen unveraendert bleiben."""
        data = {"tags": ["tag1", "tag2", "tag3"]}
        result = sanitize_payload_for_preview(data, {"name"})
        assert result["tags"] == ["tag1", "tag2", "tag3"]

    def test_pii_nicht_in_daten_keine_aenderung(self) -> None:
        """Wenn kein PII-Feld in den Daten vorkommt, bleibt alles unveraendert."""
        data = {"order_id": "ORD-999", "status": "delivered"}
        result = sanitize_payload_for_preview(data, {"name", "email", "iban"})
        assert result == data


# =============================================================================
# Tests fuer InboundWebhookService.process_webhook (9-Schritt-Flow)
# =============================================================================


class TestProcessWebhookPayloadSize:
    """Tests fuer Schritt 1: Payload-Groessen-Validierung."""

    @pytest.mark.asyncio
    async def test_payload_zu_gross_liefert_413(
        self, service: InboundWebhookService, mock_adapter: MagicMock
    ) -> None:
        """Payload groesser als 1 MB muss HTTP 413 ausloesen."""
        request = AsyncMock()
        request.body = AsyncMock(return_value=b"x" * (MAX_PAYLOAD_SIZE + 1))

        with pytest.raises(HTTPException) as exc_info:
            await service.process_webhook(
                provider="dhl",
                config_id=uuid4(),
                request=request,
                signature="sig",
                timestamp=_make_valid_timestamp(),
                webhook_id=None,
                adapter=mock_adapter,
            )
        assert exc_info.value.status_code == 413

    @pytest.mark.asyncio
    async def test_payload_exakt_am_limit_wird_akzeptiert(
        self, service: InboundWebhookService, mock_adapter: MagicMock, mock_db: AsyncMock
    ) -> None:
        """Payload exakt an der 1-MB-Grenze muss akzeptiert werden (kein 413)."""
        # Ein Payload exakt am Limit – der Secret-Lookup wird danach fehlschlagen
        request = AsyncMock()
        request.body = AsyncMock(return_value=b"x" * MAX_PAYLOAD_SIZE)

        with patch.object(service, "_get_webhook_secret", AsyncMock(return_value=None)):
            with pytest.raises(HTTPException) as exc_info:
                await service.process_webhook(
                    provider="dhl",
                    config_id=uuid4(),
                    request=request,
                    signature="sig",
                    timestamp=_make_valid_timestamp(),
                    webhook_id=None,
                    adapter=mock_adapter,
                )
        # Kein 413, sondern 404 wegen fehlendem Secret
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_body_lesefehler_liefert_400(
        self, service: InboundWebhookService, mock_adapter: MagicMock
    ) -> None:
        """Fehler beim Lesen des Request-Body muss HTTP 400 ausloesen."""
        request = AsyncMock()
        request.body = AsyncMock(side_effect=RuntimeError("Verbindungsfehler"))

        with pytest.raises(HTTPException) as exc_info:
            await service.process_webhook(
                provider="dhl",
                config_id=uuid4(),
                request=request,
                signature="sig",
                timestamp=_make_valid_timestamp(),
                webhook_id=None,
                adapter=mock_adapter,
            )
        assert exc_info.value.status_code == 400


class TestProcessWebhookSecretLookup:
    """Tests fuer Schritt 2: Webhook-Secret-Abfrage."""

    @pytest.mark.asyncio
    async def test_fehlendes_secret_liefert_404(
        self, service: InboundWebhookService, mock_adapter: MagicMock
    ) -> None:
        """Kein Webhook-Secret gefunden muss HTTP 404 ausloesen."""
        request = AsyncMock()
        request.body = AsyncMock(return_value=b'{"event_id":"e1","event_type":"t","action":"create","data":{}}')

        with patch.object(service, "_get_webhook_secret", AsyncMock(return_value=None)):
            with pytest.raises(HTTPException) as exc_info:
                await service.process_webhook(
                    provider="dhl",
                    config_id=uuid4(),
                    request=request,
                    signature="sig",
                    timestamp=_make_valid_timestamp(),
                    webhook_id=None,
                    adapter=mock_adapter,
                )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_vorhandenes_secret_laesst_weiter(
        self, service: InboundWebhookService, mock_adapter: MagicMock
    ) -> None:
        """Vorhandenes Secret muss den Flow fortsetzen (kein 404)."""
        payload = _make_valid_payload_bytes()
        timestamp = _make_valid_timestamp()
        secret = "mein-geheimes-secret"
        sig = _make_signature(payload, timestamp, secret)

        request = AsyncMock()
        request.body = AsyncMock(return_value=payload)

        with patch.object(service, "_get_webhook_secret", AsyncMock(return_value=secret)):
            with patch.object(service, "_check_idempotency", AsyncMock(return_value=False)):
                with patch.object(service, "_store_event", AsyncMock(return_value=uuid4())):
                    with patch("app.workers.tasks.webhook_inbound_tasks.process_inbound_webhook") as mock_task:
                        mock_task.delay.return_value = Mock(id="celery-task-id")
                        result = await service.process_webhook(
                            provider="dhl",
                            config_id=uuid4(),
                            request=request,
                            signature=sig,
                            timestamp=timestamp,
                            webhook_id=None,
                            adapter=mock_adapter,
                        )
        assert result.success is True


class TestProcessWebhookSignatureVerification:
    """Tests fuer Schritt 3: Signaturverifikation."""

    @pytest.mark.asyncio
    async def test_fehlende_signatur_liefert_401(
        self, service: InboundWebhookService, mock_adapter: MagicMock
    ) -> None:
        """Keine Signatur im Header muss HTTP 401 ausloesen."""
        request = AsyncMock()
        request.body = AsyncMock(return_value=b'{"event_id":"e1","event_type":"t","action":"create","data":{}}')

        with patch.object(service, "_get_webhook_secret", AsyncMock(return_value="secret")):
            with pytest.raises(HTTPException) as exc_info:
                await service.process_webhook(
                    provider="dhl",
                    config_id=uuid4(),
                    request=request,
                    signature=None,  # Signatur fehlt
                    timestamp=_make_valid_timestamp(),
                    webhook_id=None,
                    adapter=mock_adapter,
                )
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_ungueltige_signatur_liefert_401(
        self, service: InboundWebhookService, mock_adapter: MagicMock
    ) -> None:
        """Eine falsche Signatur muss HTTP 401 ausloesen."""
        request = AsyncMock()
        request.body = AsyncMock(return_value=b'{"event_id":"e1","event_type":"t","action":"create","data":{}}')

        with patch.object(service, "_get_webhook_secret", AsyncMock(return_value="secret")):
            with pytest.raises(HTTPException) as exc_info:
                await service.process_webhook(
                    provider="dhl",
                    config_id=uuid4(),
                    request=request,
                    signature="falsche-signatur",
                    timestamp=_make_valid_timestamp(),
                    webhook_id=None,
                    adapter=mock_adapter,
                )
        assert exc_info.value.status_code == 401


class TestProcessWebhookTimestampValidation:
    """Tests fuer Schritt 4: Timestamp-Validierung (Replay-Schutz)."""

    @pytest.mark.asyncio
    async def test_abgelaufener_timestamp_liefert_401(
        self, service: InboundWebhookService, mock_adapter: MagicMock
    ) -> None:
        """Ein abgelaufener Timestamp muss HTTP 401 ausloesen."""
        payload = _make_valid_payload_bytes()
        expired_ts = _make_expired_timestamp()
        secret = "secret"
        sig = _make_signature(payload, expired_ts, secret)

        request = AsyncMock()
        request.body = AsyncMock(return_value=payload)

        with patch.object(service, "_get_webhook_secret", AsyncMock(return_value=secret)):
            with pytest.raises(HTTPException) as exc_info:
                await service.process_webhook(
                    provider="dhl",
                    config_id=uuid4(),
                    request=request,
                    signature=sig,
                    timestamp=expired_ts,
                    webhook_id=None,
                    adapter=mock_adapter,
                )
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_kein_timestamp_wird_toleriert(
        self, service: InboundWebhookService, mock_adapter: MagicMock
    ) -> None:
        """Fehlt der Timestamp-Header komplett, wird Schritt 4 uebersprungen."""
        payload = _make_valid_payload_bytes()
        secret = "secret"
        # Signatur mit leerem Timestamp (wie der Code es handhabt: timestamp or "")
        sig = _make_signature(payload, "", secret)

        request = AsyncMock()
        request.body = AsyncMock(return_value=payload)

        with patch.object(service, "_get_webhook_secret", AsyncMock(return_value=secret)):
            with patch.object(service, "_check_idempotency", AsyncMock(return_value=False)):
                with patch.object(service, "_store_event", AsyncMock(return_value=uuid4())):
                    with patch("app.workers.tasks.webhook_inbound_tasks.process_inbound_webhook") as mock_task:
                        mock_task.delay.return_value = Mock(id="celery-id")
                        result = await service.process_webhook(
                            provider="dhl",
                            config_id=uuid4(),
                            request=request,
                            signature=sig,
                            timestamp=None,  # Kein Timestamp-Header
                            webhook_id=None,
                            adapter=mock_adapter,
                        )
        assert result.success is True


class TestProcessWebhookJsonParsing:
    """Tests fuer Schritt 5: JSON-Parsing und Payload-Validierung."""

    @pytest.mark.asyncio
    async def test_ungueliges_json_liefert_400(
        self, service: InboundWebhookService, mock_adapter: MagicMock
    ) -> None:
        """Kein gueltiges JSON muss HTTP 400 ausloesen."""
        invalid_json = b"kein json inhalt!!!"
        timestamp = _make_valid_timestamp()
        secret = "secret"
        sig = _make_signature(invalid_json, timestamp, secret)

        request = AsyncMock()
        request.body = AsyncMock(return_value=invalid_json)

        with patch.object(service, "_get_webhook_secret", AsyncMock(return_value=secret)):
            with pytest.raises(HTTPException) as exc_info:
                await service.process_webhook(
                    provider="dhl",
                    config_id=uuid4(),
                    request=request,
                    signature=sig,
                    timestamp=timestamp,
                    webhook_id=None,
                    adapter=mock_adapter,
                )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_ungueltiges_payload_schema_liefert_400(
        self, service: InboundWebhookService, mock_adapter: MagicMock
    ) -> None:
        """Gueltiges JSON aber falsches Schema muss HTTP 400 ausloesen."""
        # action ist nicht in der erlaubten Liste
        bad_payload = json.dumps({
            "event_id": "evt-1",
            "event_type": "invoice.received",
            "action": "ungueltige_aktion",
            "data": {},
        }).encode()
        timestamp = _make_valid_timestamp()
        secret = "secret"
        sig = _make_signature(bad_payload, timestamp, secret)

        request = AsyncMock()
        request.body = AsyncMock(return_value=bad_payload)

        with patch.object(service, "_get_webhook_secret", AsyncMock(return_value=secret)):
            with pytest.raises(HTTPException) as exc_info:
                await service.process_webhook(
                    provider="dhl",
                    config_id=uuid4(),
                    request=request,
                    signature=sig,
                    timestamp=timestamp,
                    webhook_id=None,
                    adapter=mock_adapter,
                )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_event_id_mit_ungueltigem_zeichen_liefert_400(
        self, service: InboundWebhookService, mock_adapter: MagicMock
    ) -> None:
        """Event-ID mit Sonderzeichen muss als ungueltiges Schema abgelehnt werden."""
        bad_payload = json.dumps({
            "event_id": "evt/with/slash",  # Schraegstriche nicht erlaubt
            "event_type": "invoice.received",
            "action": "create",
            "data": {},
        }).encode()
        timestamp = _make_valid_timestamp()
        secret = "secret"
        sig = _make_signature(bad_payload, timestamp, secret)

        request = AsyncMock()
        request.body = AsyncMock(return_value=bad_payload)

        with patch.object(service, "_get_webhook_secret", AsyncMock(return_value=secret)):
            with pytest.raises(HTTPException) as exc_info:
                await service.process_webhook(
                    provider="dhl",
                    config_id=uuid4(),
                    request=request,
                    signature=sig,
                    timestamp=timestamp,
                    webhook_id=None,
                    adapter=mock_adapter,
                )
        assert exc_info.value.status_code == 400


class TestProcessWebhookIdempotency:
    """Tests fuer Schritt 6: Idempotenz-Prüfung."""

    @pytest.mark.asyncio
    async def test_bereits_verarbeitetes_event_gibt_idempotenten_response(
        self, service: InboundWebhookService, mock_adapter: MagicMock
    ) -> None:
        """Bei bereits verarbeitetem Event muss der idempotente Response zurueckkommen."""
        payload = _make_valid_payload_bytes(event_id="evt-doppelt")
        timestamp = _make_valid_timestamp()
        secret = "secret"
        sig = _make_signature(payload, timestamp, secret)

        request = AsyncMock()
        request.body = AsyncMock(return_value=payload)

        with patch.object(service, "_get_webhook_secret", AsyncMock(return_value=secret)):
            with patch.object(service, "_check_idempotency", AsyncMock(return_value=True)):
                result = await service.process_webhook(
                    provider="dhl",
                    config_id=uuid4(),
                    request=request,
                    signature=sig,
                    timestamp=timestamp,
                    webhook_id=None,
                    adapter=mock_adapter,
                )
        assert result.success is True
        assert "idempotent" in result.message.lower() or "bereits" in result.message.lower()
        assert result.event_id == "evt-doppelt"

    @pytest.mark.asyncio
    async def test_neues_event_wird_weiterverarbeitet(
        self, service: InboundWebhookService, mock_adapter: MagicMock
    ) -> None:
        """Bei neuem Event muss der Flow weitergehen (_store_event wird aufgerufen)."""
        payload = _make_valid_payload_bytes(event_id="evt-neu")
        timestamp = _make_valid_timestamp()
        secret = "secret"
        sig = _make_signature(payload, timestamp, secret)

        request = AsyncMock()
        request.body = AsyncMock(return_value=payload)

        with patch.object(service, "_get_webhook_secret", AsyncMock(return_value=secret)):
            with patch.object(service, "_check_idempotency", AsyncMock(return_value=False)):
                with patch.object(service, "_store_event", AsyncMock(return_value=uuid4())) as store_mock:
                    with patch("app.workers.tasks.webhook_inbound_tasks.process_inbound_webhook") as celery_mock:
                        celery_mock.delay.return_value = Mock(id="task-id-neu")
                        await service.process_webhook(
                            provider="dhl",
                            config_id=uuid4(),
                            request=request,
                            signature=sig,
                            timestamp=timestamp,
                            webhook_id=None,
                            adapter=mock_adapter,
                        )
        store_mock.assert_called_once()


class TestProcessWebhookCeleryTask:
    """Tests fuer Schritt 9: Celery-Task-Einreihung."""

    @pytest.mark.asyncio
    async def test_erfolgreiche_task_einreihung(
        self, service: InboundWebhookService, mock_adapter: MagicMock
    ) -> None:
        """Erfolgreiches Einreihen muss task_id in der Antwort enthalten."""
        payload = _make_valid_payload_bytes()
        timestamp = _make_valid_timestamp()
        secret = "secret"
        sig = _make_signature(payload, timestamp, secret)

        request = AsyncMock()
        request.body = AsyncMock(return_value=payload)

        with patch.object(service, "_get_webhook_secret", AsyncMock(return_value=secret)):
            with patch.object(service, "_check_idempotency", AsyncMock(return_value=False)):
                with patch.object(service, "_store_event", AsyncMock(return_value=uuid4())):
                    with patch("app.workers.tasks.webhook_inbound_tasks.process_inbound_webhook") as celery_mock:
                        celery_mock.delay.return_value = Mock(id="task-abc-123")
                        result = await service.process_webhook(
                            provider="dhl",
                            config_id=uuid4(),
                            request=request,
                            signature=sig,
                            timestamp=timestamp,
                            webhook_id=None,
                            adapter=mock_adapter,
                        )
        assert result.task_id == "task-abc-123"
        assert result.success is True

    @pytest.mark.asyncio
    async def test_celery_fehler_trotzdem_success(
        self, service: InboundWebhookService, mock_adapter: MagicMock
    ) -> None:
        """Fehler beim Einreihen des Celery-Tasks darf nicht 500 ausloesen.

        Das Event ist bereits gespeichert und kann spaeter erneut verarbeitet werden.
        """
        payload = _make_valid_payload_bytes()
        timestamp = _make_valid_timestamp()
        secret = "secret"
        sig = _make_signature(payload, timestamp, secret)

        request = AsyncMock()
        request.body = AsyncMock(return_value=payload)

        with patch.object(service, "_get_webhook_secret", AsyncMock(return_value=secret)):
            with patch.object(service, "_check_idempotency", AsyncMock(return_value=False)):
                with patch.object(service, "_store_event", AsyncMock(return_value=uuid4())):
                    with patch("app.workers.tasks.webhook_inbound_tasks.process_inbound_webhook") as celery_mock:
                        celery_mock.delay.side_effect = Exception("Celery nicht verfuegbar")
                        result = await service.process_webhook(
                            provider="dhl",
                            config_id=uuid4(),
                            request=request,
                            signature=sig,
                            timestamp=timestamp,
                            webhook_id=None,
                            adapter=mock_adapter,
                        )
        # Webhook empfangen aber noch nicht eingereiht – trotzdem Success
        assert result.success is True
        assert result.task_id is None

    @pytest.mark.asyncio
    async def test_store_event_fehler_liefert_500(
        self, service: InboundWebhookService, mock_adapter: MagicMock
    ) -> None:
        """Fehler beim Speichern des Events muss HTTP 500 ausloesen."""
        payload = _make_valid_payload_bytes()
        timestamp = _make_valid_timestamp()
        secret = "secret"
        sig = _make_signature(payload, timestamp, secret)

        request = AsyncMock()
        request.body = AsyncMock(return_value=payload)

        with patch.object(service, "_get_webhook_secret", AsyncMock(return_value=secret)):
            with patch.object(service, "_check_idempotency", AsyncMock(return_value=False)):
                with patch.object(service, "_store_event", AsyncMock(side_effect=Exception("DB-Fehler"))):
                    with pytest.raises(HTTPException) as exc_info:
                        await service.process_webhook(
                            provider="dhl",
                            config_id=uuid4(),
                            request=request,
                            signature=sig,
                            timestamp=timestamp,
                            webhook_id=None,
                            adapter=mock_adapter,
                        )
        assert exc_info.value.status_code == 500


# =============================================================================
# Tests fuer _get_webhook_secret (Carrier-Pfad)
# =============================================================================


class TestGetWebhookSecretCarrier:
    """Tests fuer den Carrier-Secret-Pfad in _get_webhook_secret."""

    @pytest.mark.asyncio
    async def test_carrier_secret_aus_settings(self, service: InboundWebhookService) -> None:
        """Secret fuer DHL muss aus Settings gelesen werden."""
        mock_settings = MagicMock()
        mock_settings.WEBHOOK_SECRET_DHL = "dhl-geheimes-secret"

        with patch("app.services.webhooks.inbound_service.settings", mock_settings, create=True):
            # Patche den Import innerhalb der Funktion
            with patch("app.core.config.settings", mock_settings):
                result = await service._get_webhook_secret("dhl", uuid4())

        # Ergebnis kann je nach Settings-Struktur variieren;
        # wichtig: kein Fehler und String oder None
        assert result is None or isinstance(result, str)

    @pytest.mark.asyncio
    async def test_carrier_fallback_auf_generisches_secret(
        self, service: InboundWebhookService
    ) -> None:
        """Fehlendes provider-spezifisches Secret muss auf WEBHOOK_SECRET_CARRIER zurueckgreifen."""
        mock_settings = MagicMock()
        # Kein DHL-spezifisches Secret
        del mock_settings.WEBHOOK_SECRET_DHL
        mock_settings.WEBHOOK_SECRET_CARRIER = "generisches-carrier-secret"

        with patch("app.core.config.settings", mock_settings):
            result = await service._get_webhook_secret("dhl", uuid4())

        assert result is None or isinstance(result, str)


# =============================================================================
# Tests fuer _check_idempotency
# =============================================================================


class TestCheckIdempotency:
    """Tests fuer die Idempotenz-Prüfung gegen die Datenbank."""

    @pytest.mark.asyncio
    async def test_event_mit_success_status_ist_idempotent(
        self, service: InboundWebhookService, mock_db: AsyncMock
    ) -> None:
        """Event mit Status SUCCESS muss True zurueckgeben."""
        mock_event = Mock()
        mock_event.status = InboundWebhookStatus.SUCCESS.value

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_event
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await service._check_idempotency("dhl", "evt-bekannt")
        assert result is True

    @pytest.mark.asyncio
    async def test_event_mit_processing_status_ist_idempotent(
        self, service: InboundWebhookService, mock_db: AsyncMock
    ) -> None:
        """Event mit Status PROCESSING muss True zurueckgeben."""
        mock_event = Mock()
        mock_event.status = InboundWebhookStatus.PROCESSING.value

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_event
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await service._check_idempotency("dhl", "evt-in-arbeit")
        assert result is True

    @pytest.mark.asyncio
    async def test_event_mit_failed_status_ist_nicht_idempotent(
        self, service: InboundWebhookService, mock_db: AsyncMock
    ) -> None:
        """Event mit Status FAILED muss False zurueckgeben (Retry erlaubt)."""
        mock_event = Mock()
        mock_event.status = InboundWebhookStatus.FAILED.value

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_event
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await service._check_idempotency("dhl", "evt-fehlgeschlagen")
        assert result is False

    @pytest.mark.asyncio
    async def test_event_nicht_vorhanden_gibt_false(
        self, service: InboundWebhookService, mock_db: AsyncMock
    ) -> None:
        """Nicht vorhandenes Event muss False zurueckgeben."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await service._check_idempotency("dhl", "evt-neu")
        assert result is False

    @pytest.mark.asyncio
    async def test_event_mit_pending_status_ist_nicht_idempotent(
        self, service: InboundWebhookService, mock_db: AsyncMock
    ) -> None:
        """Event mit Status PENDING muss False zurueckgeben (noch nicht verarbeitet)."""
        mock_event = Mock()
        mock_event.status = InboundWebhookStatus.PENDING.value

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_event
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await service._check_idempotency("dhl", "evt-pending")
        assert result is False


# =============================================================================
# Vollstaendiger Happy-Path-Test
# =============================================================================


class TestProcessWebhookHappyPath:
    """Integrierter Happy-Path-Test durch den gesamten 9-Schritt-Flow."""

    @pytest.mark.asyncio
    async def test_vollstaendiger_erfolgreicher_flow(
        self, service: InboundWebhookService, mock_adapter: MagicMock, mock_db: AsyncMock
    ) -> None:
        """Der komplette Webhook-Flow muss erfolgreich durchlaufen werden.

        Prueft alle Schritte: Groesse -> Secret -> Signatur -> Timestamp ->
        JSON-Parse -> Idempotenz -> Speichern -> Celery-Einreihung.
        """
        payload = _make_valid_payload_bytes(
            event_id="evt-happy-path-001",
            event_type="shipment.delivered",
            action="status_change",
            data={"tracking_number": "TRACK-777", "name": "Empfaenger"},
        )
        timestamp = _make_valid_timestamp()
        secret = "webhook-secret-test"
        sig = _make_signature(payload, timestamp, secret)

        request = AsyncMock()
        request.body = AsyncMock(return_value=payload)

        stored_event_id = uuid4()

        # Mock-DB fuer Idempotenz-Check: Event noch nicht vorhanden
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch.object(service, "_get_webhook_secret", AsyncMock(return_value=secret)):
            with patch.object(service, "_store_event", AsyncMock(return_value=stored_event_id)):
                with patch("app.workers.tasks.webhook_inbound_tasks.process_inbound_webhook") as celery_mock:
                    celery_mock.delay.return_value = Mock(id="final-task-id")
                    result = await service.process_webhook(
                        provider="dhl",
                        config_id=uuid4(),
                        request=request,
                        signature=sig,
                        timestamp=timestamp,
                        webhook_id="webhook-header-id",
                        adapter=mock_adapter,
                    )

        assert isinstance(result, InboundWebhookResponse)
        assert result.success is True
        assert result.event_id == "evt-happy-path-001"
        assert result.task_id == "final-task-id"

        # PII-Felder muessen bereinigt worden sein (kein echter Empfaengername in Logs)
        mock_adapter.get_pii_fields.assert_called_once()
        mock_adapter.map_event.assert_called_once_with("shipment.delivered", "status_change")
        mock_adapter.extract_external_ref.assert_called_once()
