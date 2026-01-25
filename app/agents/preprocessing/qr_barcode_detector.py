# -*- coding: utf-8 -*-
"""
QR-Code & Barcode Detection Agent.

Ermoeglicht:
- SEPA-QR Code Erkennung (EPC-Standard)
- EAN-13/EAN-8 Barcode Erkennung
- Code-128, Code-39, QR-Codes
- Auto-Fill von Zahlungsdaten aus SEPA-QR
- Produkt-Lookup via EAN

Feinpoliert und durchdacht - Codes zuverlaessig erkennen.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import structlog

from app.agents.base import AgentCategory, PreprocessingAgent

logger = structlog.get_logger(__name__)


# =============================================================================
# Enums
# =============================================================================


class CodeType(str, Enum):
    """Typen von erkannten Codes."""
    QR_CODE = "qr_code"
    SEPA_QR = "sepa_qr"           # EPC QR-Code fuer Ueberweisungen
    EAN_13 = "ean_13"             # 13-stelliger Produktcode
    EAN_8 = "ean_8"               # 8-stelliger Produktcode
    CODE_128 = "code_128"         # Logistik-Barcode
    CODE_39 = "code_39"           # Alphanumerischer Barcode
    DATA_MATRIX = "data_matrix"   # 2D Matrix Code
    PDF_417 = "pdf_417"           # Stacked Barcode (Ausweise)
    UNKNOWN = "unknown"


class CodeCategory(str, Enum):
    """Kategorien von Codes."""
    PAYMENT = "payment"           # Zahlungs-relevante Codes
    PRODUCT = "product"           # Produkt-IDs (EAN)
    LOGISTICS = "logistics"       # Versand/Tracking
    DOCUMENT = "document"         # Dokument-IDs
    URL = "url"                   # Web-Links
    OTHER = "other"


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class SEPAPaymentData:
    """SEPA-Zahlungsdaten aus EPC QR-Code."""
    bic: Optional[str] = None          # Bank Identifier Code
    iban: str = ""                      # IBAN des Empfaengers
    recipient_name: str = ""            # Name des Empfaengers
    amount: Optional[float] = None      # Betrag in EUR
    currency: str = "EUR"
    reference: str = ""                 # Verwendungszweck/Referenz
    remittance_text: str = ""           # Unstrukturierter Verwendungszweck
    purpose_code: str = ""              # SEPA Purpose Code
    origin_identification: str = ""     # Identifikation des Auftraggebers

    @property
    def is_valid(self) -> bool:
        """Pruefen ob minimale SEPA-Daten vorhanden."""
        return bool(self.iban and self.recipient_name)

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiere zu Dictionary."""
        return {
            "bic": self.bic,
            "iban": self.iban,
            "recipient_name": self.recipient_name,
            "amount": self.amount,
            "currency": self.currency,
            "reference": self.reference,
            "remittance_text": self.remittance_text,
            "purpose_code": self.purpose_code,
            "origin_identification": self.origin_identification,
            "is_valid": self.is_valid,
        }


@dataclass
class DetectedCode:
    """Ein erkannter Code im Dokument."""
    code_type: CodeType
    category: CodeCategory
    data: str                           # Rohdaten des Codes
    confidence: float                   # 0-1
    x: int                              # Position X
    y: int                              # Position Y
    width: int
    height: int
    parsed_data: Optional[Dict[str, Any]] = None  # Geparste Daten
    sepa_payment: Optional[SEPAPaymentData] = None  # SEPA-Daten falls vorhanden

    @property
    def bbox(self) -> Tuple[int, int, int, int]:
        """Bounding Box als Tuple."""
        return (self.x, self.y, self.width, self.height)

    @property
    def area(self) -> int:
        """Flaeche in Pixeln."""
        return self.width * self.height

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiere zu Dictionary."""
        result = {
            "code_type": self.code_type.value,
            "category": self.category.value,
            "data": self.data,
            "confidence": round(self.confidence, 3),
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "parsed_data": self.parsed_data,
        }
        if self.sepa_payment:
            result["sepa_payment"] = self.sepa_payment.to_dict()
        return result


@dataclass
class CodeDetectionResult:
    """Ergebnis der Code-Erkennung."""
    codes: List[DetectedCode]
    has_payment_codes: bool
    has_product_codes: bool
    total_codes: int
    sepa_payments: List[SEPAPaymentData]
    analysis_details: Dict[str, Any] = field(default_factory=dict)

    @property
    def primary_sepa_payment(self) -> Optional[SEPAPaymentData]:
        """Erstes gueltiges SEPA-Payment."""
        for payment in self.sepa_payments:
            if payment.is_valid:
                return payment
        return None


# =============================================================================
# SEPA EPC QR Parser
# =============================================================================


class SEPAQRParser:
    """
    Parser fuer SEPA EPC QR-Codes (European Payments Council).

    EPC QR-Code Format:
    - Service Tag: BCD
    - Version: 001 oder 002
    - Character Set: 1 (UTF-8)
    - Identification: SCT (SEPA Credit Transfer)
    - BIC (optional in Version 002)
    - Recipient Name
    - IBAN
    - Amount (optional): EUR[Betrag]
    - Purpose Code (optional)
    - Reference (optional)
    - Remittance Text (optional)
    - Information (optional)
    """

    # EPC QR Standard Trennzeichen
    SEPARATOR = "\n"
    SERVICE_TAG = "BCD"
    VERSIONS = ["001", "002"]
    CHARSETS = {"1": "UTF-8", "2": "ISO-8859-1", "3": "ISO-8859-2"}
    IDENTIFICATION = "SCT"

    def parse(self, qr_data: str) -> Optional[SEPAPaymentData]:
        """
        Parse SEPA EPC QR-Code.

        Args:
            qr_data: Rohdaten aus QR-Code

        Returns:
            SEPAPaymentData oder None wenn kein EPC QR
        """
        if not qr_data:
            return None

        lines = qr_data.strip().split(self.SEPARATOR)

        # Mindestens 4 Zeilen fuer gueltigen EPC QR
        if len(lines) < 4:
            return None

        try:
            # Service Tag pruefen
            if lines[0].upper() != self.SERVICE_TAG:
                return None

            # Version pruefen
            version = lines[1] if len(lines) > 1 else ""
            if version not in self.VERSIONS:
                return None

            # Charset (Index 2)
            # charset = self.CHARSETS.get(lines[2], "UTF-8")

            # Identification (Index 3)
            if len(lines) > 3 and lines[3].upper() != self.IDENTIFICATION:
                return None

            # Parse Felder
            payment = SEPAPaymentData()

            # BIC (Index 4) - kann leer sein in Version 002
            if len(lines) > 4 and lines[4]:
                payment.bic = lines[4].strip()

            # Recipient Name (Index 5)
            if len(lines) > 5:
                payment.recipient_name = lines[5].strip()

            # IBAN (Index 6)
            if len(lines) > 6:
                payment.iban = lines[6].strip().replace(" ", "")

            # Amount (Index 7) - Format: EUR[Betrag]
            if len(lines) > 7 and lines[7]:
                amount_str = lines[7].strip()
                payment.amount, payment.currency = self._parse_amount(amount_str)

            # Purpose Code (Index 8)
            if len(lines) > 8:
                payment.purpose_code = lines[8].strip()

            # Reference (Index 9) - Strukturierter Verwendungszweck
            if len(lines) > 9:
                payment.reference = lines[9].strip()

            # Remittance Text (Index 10) - Unstrukturierter Verwendungszweck
            if len(lines) > 10:
                payment.remittance_text = lines[10].strip()

            # Origin Identification (Index 11)
            if len(lines) > 11:
                payment.origin_identification = lines[11].strip()

            # Validiere IBAN
            if payment.iban and not self._validate_iban(payment.iban):
                logger.warning("sepa_qr_invalid_iban", iban=payment.iban[:4] + "****")
                # Trotzdem zurueckgeben, IBAN koennte korrigiert werden

            return payment

        except Exception as e:
            logger.warning("sepa_qr_parse_error", error=str(e))
            return None

    def _parse_amount(self, amount_str: str) -> Tuple[Optional[float], str]:
        """Parse Betrag aus EPC Format (z.B. 'EUR123.45')."""
        currency = "EUR"
        amount = None

        try:
            # Format: EUR[Betrag] oder [Betrag]
            if amount_str.upper().startswith("EUR"):
                amount_str = amount_str[3:]
            elif len(amount_str) >= 3 and amount_str[:3].isalpha():
                currency = amount_str[:3].upper()
                amount_str = amount_str[3:]

            if amount_str:
                # Deutsches Format (Komma) oder internationales (Punkt)
                amount_str = amount_str.replace(",", ".")
                amount = float(amount_str)

        except (ValueError, IndexError):
            pass

        return amount, currency

    def _validate_iban(self, iban: str) -> bool:
        """Einfache IBAN-Validierung."""
        iban = iban.replace(" ", "").upper()

        # Laenge pruefen (DE = 22 Zeichen)
        if len(iban) < 15 or len(iban) > 34:
            return False

        # Laendercode pruefen
        if not iban[:2].isalpha():
            return False

        # Pruefziffer pruefen (vereinfacht)
        if not iban[2:4].isdigit():
            return False

        return True


# =============================================================================
# Barcode Validators
# =============================================================================


class BarcodeValidator:
    """Validierung verschiedener Barcode-Formate."""

    @staticmethod
    def validate_ean13(code: str) -> bool:
        """Validiere EAN-13 Pruefsumme."""
        if not code or len(code) != 13 or not code.isdigit():
            return False

        try:
            odd_sum = sum(int(code[i]) for i in range(0, 12, 2))
            even_sum = sum(int(code[i]) for i in range(1, 12, 2))
            check_digit = (10 - (odd_sum + even_sum * 3) % 10) % 10
            return int(code[12]) == check_digit
        except (ValueError, IndexError):
            return False

    @staticmethod
    def validate_ean8(code: str) -> bool:
        """Validiere EAN-8 Pruefsumme."""
        if not code or len(code) != 8 or not code.isdigit():
            return False

        try:
            odd_sum = sum(int(code[i]) for i in range(0, 7, 2))
            even_sum = sum(int(code[i]) for i in range(1, 7, 2))
            check_digit = (10 - (odd_sum * 3 + even_sum) % 10) % 10
            return int(code[7]) == check_digit
        except (ValueError, IndexError):
            return False


# =============================================================================
# QR & Barcode Detector Agent
# =============================================================================


class QRBarcodeDetectorAgent(PreprocessingAgent):
    """
    Agent zur Erkennung von QR-Codes und Barcodes.

    Unterstuetzte Formate:
    - QR-Code (inkl. SEPA EPC)
    - EAN-13, EAN-8
    - Code-128, Code-39
    - DataMatrix, PDF-417

    Verwendet pyzbar fuer Barcode-Decoding.
    """

    # Mapping von pyzbar Typen zu CodeType
    PYZBAR_TYPE_MAP = {
        "QRCODE": CodeType.QR_CODE,
        "EAN13": CodeType.EAN_13,
        "EAN8": CodeType.EAN_8,
        "CODE128": CodeType.CODE_128,
        "CODE39": CodeType.CODE_39,
        "DATAMATRIX": CodeType.DATA_MATRIX,
        "PDF417": CodeType.PDF_417,
    }

    def __init__(self) -> None:
        """Initialisiere QR/Barcode Detector."""
        super().__init__(name="qr_barcode_detector")
        self._pyzbar_available = False
        self._cv2_available = False
        self._sepa_parser = SEPAQRParser()
        self._barcode_validator = BarcodeValidator()

        # Pruefe Verfuegbarkeit
        try:
            import pyzbar.pyzbar  # noqa: F401
            self._pyzbar_available = True
        except ImportError:
            logger.warning("pyzbar_not_available", hint="pip install pyzbar")

        try:
            import cv2  # noqa: F401
            self._cv2_available = True
        except ImportError:
            logger.warning("opencv_not_available", hint="pip install opencv-python")

        logger.info(
            "QRBarcodeDetectorAgent initialisiert",
            pyzbar_available=self._pyzbar_available,
            cv2_available=self._cv2_available,
        )

    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analysiere Dokument auf QR-Codes und Barcodes.

        Args:
            input_data: Dictionary mit:
                - image: numpy array, PIL Image oder Pfad
                - detect_sepa: bool - SEPA QR-Codes parsen (default: True)
                - detect_products: bool - Produkt-Barcodes erkennen (default: True)
                - metadata: Optional - Dokument-Metadaten

        Returns:
            Dictionary mit CodeDetectionResult
        """
        self.validate_input(input_data, ["image"])

        image = input_data.get("image")
        detect_sepa = input_data.get("detect_sepa", True)
        detect_products = input_data.get("detect_products", True)
        metadata = input_data.get("metadata", {})

        # Konvertiere Bild
        image_array = await self._prepare_image(image)
        if image_array is None:
            return self._create_empty_result(metadata)

        # Erkenne Codes
        detected_codes: List[DetectedCode] = []

        if self._pyzbar_available:
            detected_codes = await self._detect_with_pyzbar(
                image_array,
                detect_sepa=detect_sepa,
                detect_products=detect_products,
            )
        else:
            # Fallback ohne pyzbar - nur Basis-Erkennung
            detected_codes = await self._detect_fallback(image_array)

        # Sammle SEPA-Payments
        sepa_payments = [
            code.sepa_payment
            for code in detected_codes
            if code.sepa_payment and code.sepa_payment.is_valid
        ]

        # Kategorisiere Ergebnisse
        has_payment = any(c.category == CodeCategory.PAYMENT for c in detected_codes)
        has_product = any(c.category == CodeCategory.PRODUCT for c in detected_codes)

        result = CodeDetectionResult(
            codes=detected_codes,
            has_payment_codes=has_payment,
            has_product_codes=has_product,
            total_codes=len(detected_codes),
            sepa_payments=sepa_payments,
            analysis_details={
                "image_dimensions": {
                    "height": image_array.shape[0],
                    "width": image_array.shape[1],
                },
                "pyzbar_available": self._pyzbar_available,
                "metadata": metadata,
            },
        )

        logger.info(
            "qr_barcode_detection_complete",
            total_codes=result.total_codes,
            has_payment_codes=result.has_payment_codes,
            has_product_codes=result.has_product_codes,
            sepa_payments_found=len(sepa_payments),
        )

        return {
            "result": result,
            "codes": [c.to_dict() for c in detected_codes],
            "total_codes": result.total_codes,
            "has_payment_codes": result.has_payment_codes,
            "has_product_codes": result.has_product_codes,
            "sepa_payments": [p.to_dict() for p in sepa_payments],
            "primary_sepa_payment": (
                result.primary_sepa_payment.to_dict()
                if result.primary_sepa_payment
                else None
            ),
        }

    async def _prepare_image(self, image: Any) -> Optional[np.ndarray]:
        """Konvertiere Eingabe zu numpy array."""
        try:
            if isinstance(image, str):
                # Bild-Pfad laden
                try:
                    from PIL import Image
                    pil_image = Image.open(image)
                    return np.array(pil_image)
                except ImportError:
                    if self._cv2_available:
                        import cv2
                        return cv2.imread(image)
                    return None
                except Exception as e:
                    logger.warning("image_load_error", path=image, error=str(e))
                    return None

            if isinstance(image, np.ndarray):
                return image

            # PIL Image
            if hasattr(image, "mode") and hasattr(image, "size"):
                return np.array(image)

            return None

        except Exception as e:
            logger.warning("image_preparation_error", error=str(e))
            return None

    async def _detect_with_pyzbar(
        self,
        image: np.ndarray,
        detect_sepa: bool = True,
        detect_products: bool = True,
    ) -> List[DetectedCode]:
        """Erkenne Codes mit pyzbar."""
        detected: List[DetectedCode] = []

        try:
            from pyzbar import pyzbar

            # Konvertiere zu Grayscale falls noetig
            if len(image.shape) == 3:
                if self._cv2_available:
                    import cv2
                    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
                else:
                    gray = np.mean(image, axis=2).astype(np.uint8)
            else:
                gray = image

            # Dekodiere alle Codes
            decoded_objects = pyzbar.decode(gray)

            for obj in decoded_objects:
                # Extrahiere Daten
                try:
                    data = obj.data.decode("utf-8")
                except UnicodeDecodeError:
                    data = obj.data.decode("latin-1")

                # Bestimme Code-Typ
                pyzbar_type = obj.type
                code_type = self.PYZBAR_TYPE_MAP.get(pyzbar_type, CodeType.UNKNOWN)

                # Extrahiere Position
                rect = obj.rect
                x, y, w, h = rect.left, rect.top, rect.width, rect.height

                # Kategorisiere und parse
                category = CodeCategory.OTHER
                parsed_data: Optional[Dict[str, Any]] = None
                sepa_payment: Optional[SEPAPaymentData] = None

                # QR-Code: SEPA EPC pruefen
                if code_type == CodeType.QR_CODE and detect_sepa:
                    sepa_payment = self._sepa_parser.parse(data)
                    if sepa_payment and sepa_payment.is_valid:
                        code_type = CodeType.SEPA_QR
                        category = CodeCategory.PAYMENT
                        parsed_data = sepa_payment.to_dict()

                # URL erkennen
                if category == CodeCategory.OTHER and self._is_url(data):
                    category = CodeCategory.URL
                    parsed_data = {"url": data}

                # EAN Barcodes
                if code_type in (CodeType.EAN_13, CodeType.EAN_8) and detect_products:
                    category = CodeCategory.PRODUCT
                    is_valid = (
                        self._barcode_validator.validate_ean13(data)
                        if code_type == CodeType.EAN_13
                        else self._barcode_validator.validate_ean8(data)
                    )
                    parsed_data = {
                        "ean": data,
                        "valid_checksum": is_valid,
                    }

                # Code-128/39: oft Logistik
                if code_type in (CodeType.CODE_128, CodeType.CODE_39):
                    # Pruefe auf Tracking-Nummern Muster
                    if self._is_tracking_number(data):
                        category = CodeCategory.LOGISTICS
                    else:
                        category = CodeCategory.DOCUMENT

                # Confidence basierend auf Qualitaet
                # pyzbar gibt keine direkte Qualitaet, nutze Groesse als Proxy
                min_size = 20
                quality_factor = min(1.0, (w * h) / (min_size * min_size * 10))
                confidence = 0.8 + 0.2 * quality_factor

                detected.append(DetectedCode(
                    code_type=code_type,
                    category=category,
                    data=data,
                    confidence=confidence,
                    x=x,
                    y=y,
                    width=w,
                    height=h,
                    parsed_data=parsed_data,
                    sepa_payment=sepa_payment,
                ))

        except Exception as e:
            logger.warning("pyzbar_detection_error", error=str(e))

        return detected

    async def _detect_fallback(self, image: np.ndarray) -> List[DetectedCode]:
        """Fallback-Erkennung ohne pyzbar (sehr eingeschraenkt)."""
        # Ohne pyzbar koennen wir nur versuchen, QR-Code-Muster zu finden
        # Dies ist ein Stub fuer den Fall dass pyzbar nicht verfuegbar ist
        logger.warning("qr_barcode_detection_fallback_no_pyzbar")
        return []

    def _is_url(self, data: str) -> bool:
        """Pruefen ob Daten eine URL sind."""
        data_lower = data.lower()
        return data_lower.startswith(("http://", "https://", "www."))

    def _is_tracking_number(self, data: str) -> bool:
        """Pruefen ob Daten eine Tracking-Nummer sein koennten."""
        # Typische Tracking-Nummer-Muster
        import re

        patterns = [
            r"^\d{12,22}$",           # Numerisch, 12-22 Stellen
            r"^JJD\d{18}$",           # DHL Express
            r"^00340\d{15}$",         # DHL Paket
            r"^1Z[A-Z0-9]{16}$",      # UPS
            r"^[A-Z]{2}\d{9}DE$",     # Deutsche Post Brief
        ]

        for pattern in patterns:
            if re.match(pattern, data):
                return True

        return False

    def _create_empty_result(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Erstelle leeres Ergebnis."""
        result = CodeDetectionResult(
            codes=[],
            has_payment_codes=False,
            has_product_codes=False,
            total_codes=0,
            sepa_payments=[],
            analysis_details={"error": "Bild konnte nicht verarbeitet werden", "metadata": metadata},
        )

        return {
            "result": result,
            "codes": [],
            "total_codes": 0,
            "has_payment_codes": False,
            "has_product_codes": False,
            "sepa_payments": [],
            "primary_sepa_payment": None,
        }


# =============================================================================
# Singleton und Convenience Functions
# =============================================================================


_qr_barcode_detector: Optional[QRBarcodeDetectorAgent] = None


def get_qr_barcode_detector() -> QRBarcodeDetectorAgent:
    """Hole globale QRBarcodeDetectorAgent-Instanz."""
    global _qr_barcode_detector
    if _qr_barcode_detector is None:
        _qr_barcode_detector = QRBarcodeDetectorAgent()
    return _qr_barcode_detector


async def detect_codes(
    image: Any,
    detect_sepa: bool = True,
    detect_products: bool = True,
) -> CodeDetectionResult:
    """
    Convenience-Funktion zur Code-Erkennung.

    Args:
        image: Bild als numpy array, PIL Image oder Pfad
        detect_sepa: SEPA QR-Codes parsen
        detect_products: Produkt-Barcodes erkennen

    Returns:
        CodeDetectionResult
    """
    detector = get_qr_barcode_detector()
    result = await detector.execute({
        "image": image,
        "detect_sepa": detect_sepa,
        "detect_products": detect_products,
    })
    return result["result"]["result"]


async def extract_sepa_payment(image: Any) -> Optional[SEPAPaymentData]:
    """
    Extrahiere SEPA-Zahlungsdaten aus Bild.

    Args:
        image: Bild mit potentiellem SEPA QR-Code

    Returns:
        SEPAPaymentData oder None
    """
    detector = get_qr_barcode_detector()
    result = await detector.execute({
        "image": image,
        "detect_sepa": True,
        "detect_products": False,
    })
    primary = result["result"].get("primary_sepa_payment")
    if primary:
        # Rekonstruiere SEPAPaymentData aus Dict
        return SEPAPaymentData(
            bic=primary.get("bic"),
            iban=primary.get("iban", ""),
            recipient_name=primary.get("recipient_name", ""),
            amount=primary.get("amount"),
            currency=primary.get("currency", "EUR"),
            reference=primary.get("reference", ""),
            remittance_text=primary.get("remittance_text", ""),
            purpose_code=primary.get("purpose_code", ""),
            origin_identification=primary.get("origin_identification", ""),
        )
    return None


async def has_payment_codes(image: Any) -> bool:
    """Schnelle Pruefung ob Bild Zahlungs-relevante Codes enthaelt."""
    detector = get_qr_barcode_detector()
    result = await detector.execute({
        "image": image,
        "detect_sepa": True,
        "detect_products": False,
    })
    return result["result"]["has_payment_codes"]


async def extract_ean_codes(image: Any) -> List[str]:
    """Extrahiere alle EAN-Codes aus Bild."""
    detector = get_qr_barcode_detector()
    result = await detector.execute({
        "image": image,
        "detect_sepa": False,
        "detect_products": True,
    })
    return [
        code["data"]
        for code in result["result"]["codes"]
        if code["code_type"] in ("ean_13", "ean_8")
    ]
