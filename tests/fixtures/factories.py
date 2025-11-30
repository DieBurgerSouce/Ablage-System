# -*- coding: utf-8 -*-
"""
Test Data Factories für Ablage-System.

Factory-Klassen zur Generierung konsistenter Test-Daten:
- UserFactory: Test-Benutzer erstellen
- DocumentFactory: Test-Dokumente erstellen
- OCRResultFactory: OCR-Ergebnisse generieren
- EntityFactory: Erkannte Entitäten generieren

Feinpoliert und durchdacht - Konsistente Test-Daten.
"""

import hashlib
import random
import string
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from pathlib import Path


# =============================================================================
# Base Factory
# =============================================================================

class BaseFactory:
    """Base class for all factories."""

    _counter: int = 0

    @classmethod
    def _next_id(cls) -> int:
        """Generate sequential ID."""
        cls._counter += 1
        return cls._counter

    @classmethod
    def _random_string(cls, length: int = 8) -> str:
        """Generate random string."""
        return ''.join(random.choices(string.ascii_lowercase, k=length))

    @classmethod
    def _random_uuid(cls) -> str:
        """Generate random UUID."""
        return str(uuid.uuid4())


# =============================================================================
# User Factory
# =============================================================================

class UserFactory(BaseFactory):
    """Factory for creating test users."""

    GERMAN_FIRST_NAMES = [
        "Max", "Maria", "Thomas", "Anna", "Michael", "Sarah",
        "Andreas", "Julia", "Stefan", "Laura", "Markus", "Lisa"
    ]

    GERMAN_LAST_NAMES = [
        "Müller", "Schmidt", "Schneider", "Fischer", "Weber",
        "Meyer", "Wagner", "Becker", "Hoffmann", "Schäfer"
    ]

    @classmethod
    def create(
        cls,
        email: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        role: str = "user",
        is_active: bool = True,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Create a test user dictionary.

        Args:
            email: Email address (auto-generated if None)
            first_name: First name (random German name if None)
            last_name: Last name (random German name if None)
            role: User role (user, admin, viewer)
            is_active: Whether user is active
            **kwargs: Additional user attributes

        Returns:
            User dictionary
        """
        user_id = cls._next_id()
        first = first_name or random.choice(cls.GERMAN_FIRST_NAMES)
        last = last_name or random.choice(cls.GERMAN_LAST_NAMES)

        return {
            "id": cls._random_uuid(),
            "email": email or f"test_{user_id}@example.de",
            "first_name": first,
            "last_name": last,
            "full_name": f"{first} {last}",
            "role": role,
            "is_active": is_active,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "last_login": None,
            "deletion_requested_at": None,
            "deletion_scheduled_for": None,
            **kwargs
        }

    @classmethod
    def create_admin(cls, **kwargs) -> Dict[str, Any]:
        """Create admin user."""
        return cls.create(role="admin", **kwargs)

    @classmethod
    def create_batch(cls, count: int, **kwargs) -> List[Dict[str, Any]]:
        """Create multiple users."""
        return [cls.create(**kwargs) for _ in range(count)]


# =============================================================================
# Document Factory
# =============================================================================

class DocumentFactory(BaseFactory):
    """Factory for creating test documents."""

    DOCUMENT_TYPES = ["invoice", "contract", "letter", "form", "report"]
    GERMAN_TITLES = [
        "Rechnung Nr. {num}",
        "Vertrag vom {date}",
        "Antrag auf {subject}",
        "Bericht über {subject}",
        "Bescheid zum {subject}"
    ]

    @classmethod
    def create(
        cls,
        title: Optional[str] = None,
        document_type: Optional[str] = None,
        file_name: Optional[str] = None,
        content_hash: Optional[str] = None,
        status: str = "processed",
        **kwargs
    ) -> Dict[str, Any]:
        """
        Create a test document dictionary.

        Args:
            title: Document title
            document_type: Type of document
            file_name: Original filename
            content_hash: SHA256 hash of content
            status: Processing status
            **kwargs: Additional attributes

        Returns:
            Document dictionary
        """
        doc_id = cls._next_id()
        doc_type = document_type or random.choice(cls.DOCUMENT_TYPES)

        if not title:
            template = random.choice(cls.GERMAN_TITLES)
            title = template.format(
                num=doc_id,
                date=datetime.now().strftime("%d.%m.%Y"),
                subject=cls._random_string(6)
            )

        return {
            "id": cls._random_uuid(),
            "title": title,
            "document_type": doc_type,
            "file_name": file_name or f"document_{doc_id}.pdf",
            "file_size_bytes": random.randint(50000, 5000000),
            "content_hash": content_hash or hashlib.sha256(
                f"test_content_{doc_id}".encode()
            ).hexdigest(),
            "status": status,
            "language": "de",
            "page_count": random.randint(1, 10),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "processed_at": datetime.now(timezone.utc).isoformat() if status == "processed" else None,
            "owner_id": cls._random_uuid(),
            "tags": [],
            **kwargs
        }

    @classmethod
    def create_invoice(cls, **kwargs) -> Dict[str, Any]:
        """Create invoice document."""
        return cls.create(
            document_type="invoice",
            title=f"Rechnung Nr. {cls._next_id()}",
            **kwargs
        )

    @classmethod
    def create_contract(cls, **kwargs) -> Dict[str, Any]:
        """Create contract document."""
        return cls.create(
            document_type="contract",
            title=f"Vertrag vom {datetime.now().strftime('%d.%m.%Y')}",
            **kwargs
        )

    @classmethod
    def create_pending(cls, **kwargs) -> Dict[str, Any]:
        """Create document with pending status."""
        return cls.create(status="pending", **kwargs)

    @classmethod
    def create_batch(cls, count: int, **kwargs) -> List[Dict[str, Any]]:
        """Create multiple documents."""
        return [cls.create(**kwargs) for _ in range(count)]


# =============================================================================
# OCR Result Factory
# =============================================================================

class OCRResultFactory(BaseFactory):
    """Factory for creating test OCR results."""

    GERMAN_SAMPLE_TEXTS = [
        "Dies ist ein Testdokument mit deutschem Text und Umlauten: äöü ß.",
        "Sehr geehrte Damen und Herren, hiermit übersende ich Ihnen...",
        "Rechnungsbetrag: 1.234,56 EUR inkl. 19% MwSt.",
        "Vertragslaufzeit: 01.01.2025 bis 31.12.2025",
        "Mit freundlichen Grüßen, Max Müller",
    ]

    BACKENDS = ["deepseek", "got_ocr", "surya", "surya_gpu"]

    @classmethod
    def create(
        cls,
        text: Optional[str] = None,
        confidence: Optional[float] = None,
        backend: Optional[str] = None,
        entities: Optional[List[Dict]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Create a test OCR result.

        Args:
            text: Extracted text
            confidence: Confidence score (0.0-1.0)
            backend: OCR backend used
            entities: Extracted entities
            **kwargs: Additional attributes

        Returns:
            OCR result dictionary
        """
        return {
            "text": text or random.choice(cls.GERMAN_SAMPLE_TEXTS),
            "confidence": confidence or round(random.uniform(0.7, 0.99), 4),
            "backend": backend or random.choice(cls.BACKENDS),
            "language": "de",
            "entities": entities or EntityFactory.create_batch(random.randint(0, 5)),
            "processing_time_ms": random.randint(500, 5000),
            "page_count": random.randint(1, 5),
            "word_count": random.randint(50, 500),
            "layout": {
                "type": random.choice(["single_column", "multi_column", "table"]),
                "has_tables": random.choice([True, False]),
                "has_images": random.choice([True, False])
            },
            "confidence_details": {
                "char_confidence": round(random.uniform(0.8, 0.99), 4),
                "word_confidence": round(random.uniform(0.75, 0.98), 4),
                "line_confidence": round(random.uniform(0.7, 0.97), 4)
            },
            **kwargs
        }

    @classmethod
    def create_high_confidence(cls, **kwargs) -> Dict[str, Any]:
        """Create high confidence result (>0.9)."""
        return cls.create(confidence=round(random.uniform(0.9, 0.99), 4), **kwargs)

    @classmethod
    def create_low_confidence(cls, **kwargs) -> Dict[str, Any]:
        """Create low confidence result (<0.7)."""
        return cls.create(confidence=round(random.uniform(0.3, 0.69), 4), **kwargs)

    @classmethod
    def create_for_backend(cls, backend: str, **kwargs) -> Dict[str, Any]:
        """Create result for specific backend."""
        return cls.create(backend=backend, **kwargs)


# =============================================================================
# Entity Factory
# =============================================================================

class EntityFactory(BaseFactory):
    """Factory for creating test entities."""

    ENTITY_TYPES = {
        "PERSON": [
            "Max Müller", "Anna Schmidt", "Thomas Weber",
            "Maria Schneider", "Stefan Hoffmann"
        ],
        "ORGANIZATION": [
            "Deutsche Bank AG", "Siemens AG", "BMW Group",
            "Allianz SE", "SAP SE", "BASF SE"
        ],
        "LOCATION": [
            "Berlin", "München", "Hamburg", "Frankfurt am Main",
            "Köln", "Stuttgart", "Deutschland"
        ],
        "DATE": [
            "01.01.2025", "15.03.2024", "31.12.2025",
            "01.07.2024", "28.02.2025"
        ],
        "AMOUNT": [
            "1.234,56 EUR", "500,00 EUR", "10.000,00 EUR",
            "2.345,67 EUR", "99,99 EUR"
        ],
        "IBAN": [
            "DE89 3704 0044 0532 0130 00",
            "DE12 5001 0517 1234 5678 90"
        ],
        "TAX_NUMBER": [
            "123/456/78901", "987/654/32100"
        ]
    }

    @classmethod
    def create(
        cls,
        entity_type: Optional[str] = None,
        value: Optional[str] = None,
        confidence: Optional[float] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Create a test entity.

        Args:
            entity_type: Type of entity (PERSON, ORGANIZATION, etc.)
            value: Entity value
            confidence: Confidence score
            **kwargs: Additional attributes

        Returns:
            Entity dictionary
        """
        ent_type = entity_type or random.choice(list(cls.ENTITY_TYPES.keys()))
        ent_value = value or random.choice(cls.ENTITY_TYPES.get(ent_type, ["Unknown"]))

        return {
            "type": ent_type,
            "value": ent_value,
            "confidence": confidence or round(random.uniform(0.7, 0.99), 4),
            "start": random.randint(0, 100),
            "end": random.randint(101, 200),
            "source": random.choice(["regex", "spacy_ner", "deepseek"]),
            **kwargs
        }

    @classmethod
    def create_person(cls, name: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """Create PERSON entity."""
        return cls.create(entity_type="PERSON", value=name, **kwargs)

    @classmethod
    def create_organization(cls, name: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """Create ORGANIZATION entity."""
        return cls.create(entity_type="ORGANIZATION", value=name, **kwargs)

    @classmethod
    def create_batch(cls, count: int, **kwargs) -> List[Dict[str, Any]]:
        """Create multiple entities."""
        return [cls.create(**kwargs) for _ in range(count)]


# =============================================================================
# Fixture Loader
# =============================================================================

class FixtureLoader:
    """Helper class to load test fixtures from files."""

    FIXTURES_DIR = Path(__file__).parent

    @classmethod
    def get_sample_image_path(cls, category: str, index: int = 1) -> Path:
        """
        Get path to sample image.

        Args:
            category: Category (invoices, fraktur, tables, etc.)
            index: File index (1-6 typically)

        Returns:
            Path to image file
        """
        category_map = {
            "invoice": "invoices",
            "invoices": "invoices",
            "fraktur": "fraktur",
            "table": "tables",
            "tables": "tables",
            "contract": "contracts",
            "contracts": "contracts",
            "form": "forms",
            "forms": "forms",
            "handwritten": "handwritten",
            "mixed": "mixed"
        }

        folder = category_map.get(category, category)
        prefix = folder.rstrip("s") if folder.endswith("s") else folder

        return cls.FIXTURES_DIR / "german_docs" / folder / f"{prefix}_{index:03d}.png"

    @classmethod
    def get_sample_json_path(cls, category: str, index: int = 1) -> Path:
        """Get path to sample JSON annotation file."""
        image_path = cls.get_sample_image_path(category, index)
        return image_path.with_suffix(".json")

    @classmethod
    def load_sample_annotation(cls, category: str, index: int = 1) -> Dict[str, Any]:
        """Load annotation JSON for sample image."""
        import json
        json_path = cls.get_sample_json_path(category, index)
        if json_path.exists():
            with open(json_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    @classmethod
    def list_samples(cls, category: str) -> List[Path]:
        """List all sample images in category."""
        category_map = {
            "invoice": "invoices",
            "fraktur": "fraktur",
            "table": "tables",
            "contract": "contracts",
            "form": "forms",
            "handwritten": "handwritten",
            "mixed": "mixed"
        }
        folder = category_map.get(category, category)
        folder_path = cls.FIXTURES_DIR / "german_docs" / folder
        if folder_path.exists():
            return sorted(folder_path.glob("*.png"))
        return []


# =============================================================================
# Convenience Functions
# =============================================================================

def create_test_user(**kwargs) -> Dict[str, Any]:
    """Convenience function to create test user."""
    return UserFactory.create(**kwargs)


def create_test_document(**kwargs) -> Dict[str, Any]:
    """Convenience function to create test document."""
    return DocumentFactory.create(**kwargs)


def create_test_ocr_result(**kwargs) -> Dict[str, Any]:
    """Convenience function to create test OCR result."""
    return OCRResultFactory.create(**kwargs)


def create_test_entity(**kwargs) -> Dict[str, Any]:
    """Convenience function to create test entity."""
    return EntityFactory.create(**kwargs)
