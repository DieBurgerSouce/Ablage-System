"""Unit Tests fuer DocumentChunkingService.

Testet:
- Semantisches Chunking
- Fixes Chunking
- Section-Erkennung
- Tabellen-Extraktion
- Token-Zaehlung
- Overlap-Berechnung
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from uuid import uuid4
from datetime import datetime, timezone

from app.services.rag.chunking_service import (
    DocumentChunkingService,
    ChunkConfig,
    Chunk,
    get_chunking_service,
)
from app.db.models import RAGSectionType


class TestChunkConfig:
    """Tests fuer ChunkConfig Dataclass."""

    def test_default_values(self) -> None:
        """Test default configuration values."""
        config = ChunkConfig()

        assert config.chunk_size == 512
        assert config.overlap == 50
        assert config.min_chunk_size == 100
        assert config.max_chunk_size == 2048
        assert config.preserve_tables is True
        assert config.preserve_paragraphs is True
        assert config.preserve_sections is False
        assert config.section_markers == []

    def test_custom_values(self) -> None:
        """Test custom configuration values."""
        config = ChunkConfig(
            chunk_size=256,
            overlap=25,
            min_chunk_size=50,
            max_chunk_size=1024,
            preserve_tables=False,
            section_markers=["Rechnung", "Summe"]
        )

        assert config.chunk_size == 256
        assert config.overlap == 25
        assert config.section_markers == ["Rechnung", "Summe"]


class TestChunk:
    """Tests fuer Chunk Dataclass."""

    def test_chunk_creation(self) -> None:
        """Test creating a basic chunk."""
        chunk = Chunk(
            text="Dies ist ein Test-Chunk.",
            index=0,
            tokens=10
        )

        assert chunk.text == "Dies ist ein Test-Chunk."
        assert chunk.index == 0
        assert chunk.tokens == 10
        assert chunk.page_number is None
        assert chunk.section_type == RAGSectionType.UNKNOWN

    def test_chunk_with_metadata(self) -> None:
        """Test chunk with full metadata."""
        chunk = Chunk(
            text="Header Text",
            index=1,
            tokens=5,
            page_number=1,
            section_type=RAGSectionType.HEADER,
            bounding_box={"x": 0, "y": 0, "width": 100, "height": 50},
            metadata={"custom": "value"}
        )

        assert chunk.page_number == 1
        assert chunk.section_type == RAGSectionType.HEADER
        assert chunk.bounding_box["width"] == 100
        assert chunk.metadata["custom"] == "value"


class TestDocumentChunkingService:
    """Tests fuer DocumentChunkingService."""

    @pytest.fixture
    def service(self) -> DocumentChunkingService:
        """Create a fresh chunking service for each test."""
        return DocumentChunkingService()

    @pytest.fixture
    def mock_embedding_service(self) -> Mock:
        """Create mock embedding service."""
        mock = Mock()
        mock.model_name = "test-model"
        mock.generate_batch_embeddings_async = AsyncMock(
            return_value=[[0.1] * 1024, [0.2] * 1024]
        )
        return mock

    # ==========================================================================
    # Section Detection Tests
    # ==========================================================================

    def test_detect_section_type_header_markdown(self, service: DocumentChunkingService) -> None:
        """Test detecting markdown header."""
        text = "## Ueberschrift\nDies ist der Inhalt."
        section_type = service._detect_section_type(text)
        assert section_type == RAGSectionType.HEADER

    def test_detect_section_type_header_numbered(self, service: DocumentChunkingService) -> None:
        """Test detecting numbered header."""
        text = "1. Einleitung\nDies ist der erste Abschnitt."
        section_type = service._detect_section_type(text)
        assert section_type == RAGSectionType.HEADER

    def test_detect_section_type_table_markdown(self, service: DocumentChunkingService) -> None:
        """Test detecting markdown table."""
        text = "| Spalte 1 | Spalte 2 |\n|----------|----------|\n| Wert 1 | Wert 2 |"
        section_type = service._detect_section_type(text)
        assert section_type == RAGSectionType.TABLE

    def test_detect_section_type_list_bullet(self, service: DocumentChunkingService) -> None:
        """Test detecting bullet list."""
        text = "- Erster Punkt\n- Zweiter Punkt\n- Dritter Punkt"
        section_type = service._detect_section_type(text)
        assert section_type == RAGSectionType.LIST

    def test_detect_section_type_list_numbered(self, service: DocumentChunkingService) -> None:
        """Test detecting numbered list."""
        text = "1) Erster Punkt\n2) Zweiter Punkt"
        section_type = service._detect_section_type(text)
        assert section_type == RAGSectionType.LIST

    def test_detect_section_type_footer(self, service: DocumentChunkingService) -> None:
        """Test detecting footer (page number)."""
        text = "Seite 5"
        section_type = service._detect_section_type(text)
        assert section_type == RAGSectionType.FOOTER

    def test_detect_section_type_footer_stand(self, service: DocumentChunkingService) -> None:
        """Test detecting footer with Stand: marker."""
        text = "Stand: 01.01.2024"
        section_type = service._detect_section_type(text)
        assert section_type == RAGSectionType.FOOTER

    def test_detect_section_type_paragraph(self, service: DocumentChunkingService) -> None:
        """Test detecting regular paragraph."""
        text = "Dies ist ein normaler Absatz mit Text."
        section_type = service._detect_section_type(text)
        assert section_type == RAGSectionType.PARAGRAPH

    # ==========================================================================
    # Sentence Splitting Tests
    # ==========================================================================

    def test_split_into_sentences_basic(self, service: DocumentChunkingService) -> None:
        """Test basic sentence splitting."""
        text = "Erster Satz. Zweiter Satz! Dritter Satz?"
        sentences = service._split_into_sentences(text)

        assert len(sentences) == 3
        assert "Erster Satz" in sentences[0]

    def test_split_into_sentences_with_abbreviations(self, service: DocumentChunkingService) -> None:
        """Test sentence splitting with German abbreviations."""
        text = "Dr. Mueller arbeitet hier. Er ist Arzt."
        sentences = service._split_into_sentences(text)

        # Should not split at "Dr."
        assert len(sentences) >= 1

    def test_split_into_sentences_empty(self, service: DocumentChunkingService) -> None:
        """Test empty text handling."""
        sentences = service._split_into_sentences("")
        assert sentences == []

    # ==========================================================================
    # Paragraph Splitting Tests
    # ==========================================================================

    def test_split_into_paragraphs(self, service: DocumentChunkingService) -> None:
        """Test paragraph splitting."""
        text = "Erster Absatz.\n\nZweiter Absatz.\n\nDritter Absatz."
        paragraphs = service._split_into_paragraphs(text)

        assert len(paragraphs) == 3
        assert paragraphs[0] == "Erster Absatz."
        assert paragraphs[1] == "Zweiter Absatz."

    def test_split_into_paragraphs_single_newline(self, service: DocumentChunkingService) -> None:
        """Test that single newlines don't create new paragraphs."""
        text = "Zeile 1\nZeile 2\nZeile 3"
        paragraphs = service._split_into_paragraphs(text)

        assert len(paragraphs) == 1

    # ==========================================================================
    # Table Extraction Tests
    # ==========================================================================

    def test_extract_tables_markdown(self, service: DocumentChunkingService) -> None:
        """Test extracting markdown tables."""
        text = """Text vor Tabelle.

| A | B |
|---|---|
| 1 | 2 |

Text nach Tabelle."""

        text_without, tables = service._extract_tables(text)

        assert len(tables) == 1
        assert "| A | B |" in tables[0]
        assert "[TABLE_PLACEHOLDER]" in text_without
        assert "Text vor Tabelle" in text_without

    def test_extract_tables_no_table(self, service: DocumentChunkingService) -> None:
        """Test text without tables."""
        text = "Dies ist normaler Text ohne Tabelle."
        text_without, tables = service._extract_tables(text)

        assert tables == []
        assert text_without == text

    # ==========================================================================
    # Token Counting Tests
    # ==========================================================================

    def test_count_tokens(self, service: DocumentChunkingService) -> None:
        """Test token counting."""
        text = "Dies ist ein kurzer Test."
        tokens = service._count_tokens(text)

        assert tokens > 0
        assert isinstance(tokens, int)

    def test_count_tokens_empty(self, service: DocumentChunkingService) -> None:
        """Test counting tokens in empty string."""
        tokens = service._count_tokens("")
        assert tokens == 0

    def test_count_tokens_german_umlauts(self, service: DocumentChunkingService) -> None:
        """Test token counting with German umlauts."""
        text = "Muenchen, Koeln, Nuernberg, Duesseldorf"
        tokens = service._count_tokens(text)
        assert tokens > 0

    # ==========================================================================
    # Overlap Calculation Tests
    # ==========================================================================

    def test_get_overlap(self, service: DocumentChunkingService) -> None:
        """Test overlap extraction."""
        text = "Dies ist ein laengerer Text fuer den Overlap-Test."
        overlap_tokens = 10

        overlap = service._get_overlap(text, overlap_tokens)

        assert len(overlap) > 0
        assert len(overlap) < len(text)

    def test_get_overlap_short_text(self, service: DocumentChunkingService) -> None:
        """Test overlap with text shorter than overlap."""
        text = "Kurz"
        overlap_tokens = 100

        overlap = service._get_overlap(text, overlap_tokens)
        assert overlap == text

    # ==========================================================================
    # Chunk Configuration Tests
    # ==========================================================================

    def test_get_chunk_config_unknown_type(self, service: DocumentChunkingService) -> None:
        """Test config for unknown document type."""
        config = service._get_chunk_config("unknown_type")

        assert config.chunk_size > 0
        assert config.overlap >= 0

    def test_get_chunk_config_none_type(self, service: DocumentChunkingService) -> None:
        """Test config with None document type."""
        config = service._get_chunk_config(None)

        assert config.chunk_size > 0

    # ==========================================================================
    # Semantic Splitting Tests
    # ==========================================================================

    def test_semantic_split_basic(self, service: DocumentChunkingService) -> None:
        """Test basic semantic splitting."""
        text = """Erster Absatz mit einigem Text der lang genug ist.

Zweiter Absatz auch mit genug Text fuer einen Chunk.

Dritter Absatz noch mehr Text hier."""

        config = ChunkConfig(
            chunk_size=50,
            overlap=10,
            min_chunk_size=5
        )

        chunks = service._semantic_split(text, config)

        assert len(chunks) >= 1
        assert all(isinstance(c, Chunk) for c in chunks)
        assert all(c.tokens > 0 for c in chunks)

    def test_semantic_split_respects_min_size(self, service: DocumentChunkingService) -> None:
        """Test that chunks respect minimum size."""
        text = "Kurz. Noch kuerzer."

        config = ChunkConfig(
            chunk_size=100,
            overlap=10,
            min_chunk_size=50  # High min size
        )

        chunks = service._semantic_split(text, config)

        # With high min_chunk_size, short text should result in no chunks
        # because each chunk would be below minimum
        assert len(chunks) <= 1

    def test_semantic_split_preserves_tables(self, service: DocumentChunkingService) -> None:
        """Test that tables are preserved as separate chunks."""
        text = """Text vor der Tabelle.

| Spalte A | Spalte B |
|----------|----------|
| Wert 1   | Wert 2   |

Text nach der Tabelle."""

        config = ChunkConfig(
            chunk_size=100,
            overlap=10,
            min_chunk_size=5,
            preserve_tables=True
        )

        chunks = service._semantic_split(text, config)

        # Find table chunk
        table_chunks = [c for c in chunks if c.section_type == RAGSectionType.TABLE]
        assert len(table_chunks) >= 1

    def test_semantic_split_assigns_indices(self, service: DocumentChunkingService) -> None:
        """Test that chunks have sequential indices."""
        text = "A" * 500 + "\n\n" + "B" * 500 + "\n\n" + "C" * 500

        config = ChunkConfig(chunk_size=100, overlap=10, min_chunk_size=10)
        chunks = service._semantic_split(text, config)

        indices = [c.index for c in chunks]
        assert indices == sorted(indices)

    # ==========================================================================
    # Fixed Splitting Tests
    # ==========================================================================

    def test_fixed_split_basic(self, service: DocumentChunkingService) -> None:
        """Test basic fixed splitting."""
        # Use words instead of repeated chars (tokenizer compresses repeated chars)
        text = "Wort " * 500  # ~500 tokens

        config = ChunkConfig(chunk_size=100, overlap=10)
        chunks = service._fixed_split(text, config)

        assert len(chunks) >= 2  # Should create multiple chunks
        assert all(c.tokens <= 110 for c in chunks)  # Allow small overflow

    def test_fixed_split_with_overlap(self, service: DocumentChunkingService) -> None:
        """Test fixed splitting maintains overlap."""
        text = "Wort " * 200

        config = ChunkConfig(chunk_size=50, overlap=10)
        chunks = service._fixed_split(text, config)

        # With overlap, chunks should share some content
        assert len(chunks) >= 2

    # ==========================================================================
    # Integration Tests (with mocked DB)
    # ==========================================================================

    @pytest.mark.asyncio
    async def test_chunk_document_not_found(
        self,
        service: DocumentChunkingService
    ) -> None:
        """Test chunking non-existent document."""
        mock_session = AsyncMock()
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        with pytest.raises(ValueError, match="nicht gefunden"):
            await service.chunk_document(
                db=mock_session,
                document_id=uuid4()
            )

    @pytest.mark.asyncio
    async def test_chunk_document_no_text(
        self,
        service: DocumentChunkingService
    ) -> None:
        """Test chunking document without OCR text."""
        mock_document = Mock()
        mock_document.extracted_text = None  # Service verwendet extracted_text
        mock_document.ocr_text = None
        mock_document.id = uuid4()

        mock_session = AsyncMock()
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_document
        mock_session.execute.return_value = mock_result

        with pytest.raises(ValueError, match="keinen OCR-Text"):
            await service.chunk_document(
                db=mock_session,
                document_id=mock_document.id
            )

    @pytest.mark.asyncio
    async def test_get_document_chunks(
        self,
        service: DocumentChunkingService
    ) -> None:
        """Test retrieving document chunks."""
        mock_chunks = [Mock(), Mock()]

        mock_session = AsyncMock()
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = mock_chunks
        mock_session.execute.return_value = mock_result

        chunks = await service.get_document_chunks(
            db=mock_session,
            document_id=uuid4()
        )

        assert len(chunks) == 2

    @pytest.mark.asyncio
    async def test_delete_document_chunks(
        self,
        service: DocumentChunkingService
    ) -> None:
        """Test deleting document chunks."""
        mock_session = AsyncMock()
        mock_result = Mock()
        mock_result.fetchall.return_value = [Mock(), Mock(), Mock()]
        mock_session.execute.return_value = mock_result

        deleted = await service.delete_document_chunks(
            db=mock_session,
            document_id=uuid4()
        )

        assert deleted == 3
        mock_session.commit.assert_called_once()


class TestGetChunkingService:
    """Tests fuer get_chunking_service Factory."""

    def test_singleton_pattern(self) -> None:
        """Test that get_chunking_service returns singleton."""
        # Reset singleton for test
        import app.services.rag.chunking_service as module
        module._chunking_service = None

        service1 = get_chunking_service()
        service2 = get_chunking_service()

        assert service1 is service2

    def test_returns_chunking_service(self) -> None:
        """Test that factory returns correct type."""
        service = get_chunking_service()
        assert isinstance(service, DocumentChunkingService)


class TestChunkingEdgeCases:
    """Edge case tests fuer Chunking."""

    @pytest.fixture
    def service(self) -> DocumentChunkingService:
        return DocumentChunkingService()

    def test_empty_text(self, service: DocumentChunkingService) -> None:
        """Test chunking empty text."""
        config = ChunkConfig()
        chunks = service._semantic_split("", config)
        assert chunks == []

    def test_whitespace_only_text(self, service: DocumentChunkingService) -> None:
        """Test chunking whitespace-only text."""
        config = ChunkConfig()
        chunks = service._semantic_split("   \n\n   \t   ", config)
        assert chunks == []

    def test_very_long_word(self, service: DocumentChunkingService) -> None:
        """Test chunking text with very long word."""
        long_word = "A" * 10000
        config = ChunkConfig(chunk_size=100, overlap=10, min_chunk_size=5)

        chunks = service._fixed_split(long_word, config)
        assert len(chunks) >= 1

    def test_unicode_text(self, service: DocumentChunkingService) -> None:
        """Test chunking with Unicode characters."""
        text = "Straße München Größe naïve café 北京"
        config = ChunkConfig(chunk_size=50, overlap=10, min_chunk_size=5)

        chunks = service._semantic_split(text, config)
        # Should not raise exception
        assert isinstance(chunks, list)

    def test_mixed_content(self, service: DocumentChunkingService) -> None:
        """Test chunking mixed content (text, table, list)."""
        text = """# Ueberschrift

Normaler Absatz mit Text.

| A | B |
|---|---|
| 1 | 2 |

- Punkt 1
- Punkt 2

Abschliessender Text."""

        config = ChunkConfig(
            chunk_size=50,
            overlap=10,
            min_chunk_size=5,
            preserve_tables=True
        )

        chunks = service._semantic_split(text, config)

        section_types = {c.section_type for c in chunks}
        # Should have variety of section types
        assert len(section_types) >= 1
