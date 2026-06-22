"""Document Chunking Service für RAG Intelligence Layer.

Semantisches Chunking von Dokumenten für optimale Retrieval-Performance.
Unterstützt dokumenttyp-spezifische Chunking-Strategien mit Layout-Erhalt.
"""

import re
import yaml
import asyncio
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from uuid import UUID
from datetime import datetime, timezone
from dataclasses import dataclass, field

import structlog
import tiktoken

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document, RAGDocumentChunk, RAGSectionType
from app.services.embedding_service import get_embedding_service
from app.core.config import settings
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


@dataclass
class ChunkConfig:
    """Konfiguration für Chunking einer spezifischen Dokumentart."""
    chunk_size: int = 512
    overlap: int = 50
    min_chunk_size: int = 100
    max_chunk_size: int = 2048
    preserve_tables: bool = True
    preserve_paragraphs: bool = True
    preserve_sections: bool = False
    preserve_line_items: bool = False
    section_markers: List[str] = field(default_factory=list)
    extract_metadata: List[str] = field(default_factory=list)


@dataclass
class Chunk:
    """Repraesentiert einen Text-Chunk mit Metadaten."""
    text: str
    index: int
    tokens: int
    page_number: Optional[int] = None
    section_type: RAGSectionType = RAGSectionType.UNKNOWN
    bounding_box: Optional[Dict[str, float]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class DocumentChunkingService:
    """Service für intelligentes Document Chunking.

    Implementiert dokumenttyp-spezifisches semantisches Chunking mit:
    - Respektierung natürlicher Textgrenzen (Sätze, Absätze)
    - Tabellen-Erhalt
    - Section-Erkennung
    - Token-basierte Chunk-Größen
    - Overlap für Kontext-Kontinuität
    """

    def __init__(self) -> None:
        """Initialisiert den Chunking Service."""
        self._config: Optional[Dict[str, Any]] = None
        self._tokenizer: Optional[tiktoken.Encoding] = None
        self._embedding_service = get_embedding_service()

    def _load_config(self) -> Dict[str, Any]:
        """Laedt die Chunking-Konfiguration aus YAML."""
        if self._config is not None:
            return self._config

        config_path = Path(settings.BASE_DIR) / "config" / "chunking.yaml"

        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    self._config = yaml.safe_load(f)
                logger.info("chunking_config_loaded", path=str(config_path))
            except Exception as e:
                logger.error("chunking_config_load_failed", **safe_error_log(e))
                self._config = self._default_config()
        else:
            logger.warning("chunking_config_not_found", path=str(config_path))
            self._config = self._default_config()

        return self._config

    def _default_config(self) -> Dict[str, Any]:
        """Gibt die Default-Konfiguration zurück."""
        return {
            "global": {
                "default_strategy": "semantic",
                "embedding_model": "multilingual-e5-large",
                "embedding_dimensions": 1024,
                "tokenizer": "tiktoken",
                "tokenizer_model": "cl100k_base",
            },
            "strategies": {
                "semantic": {
                    "min_chunk_size": 100,
                    "max_chunk_size": 512,
                    "overlap": 50,
                    "respect_sentences": True,
                    "respect_paragraphs": True,
                }
            },
            "document_types": {
                "sonstige": {
                    "chunk_size": 512,
                    "overlap": 50,
                    "preserve_paragraphs": True,
                }
            },
        }

    def _get_tokenizer(self) -> tiktoken.Encoding:
        """Gibt den Tokenizer zurück (Lazy Loading)."""
        if self._tokenizer is None:
            config = self._load_config()
            model = config.get("global", {}).get("tokenizer_model", "cl100k_base")
            self._tokenizer = tiktoken.get_encoding(model)
        return self._tokenizer

    def _count_tokens(self, text: str) -> int:
        """Zaehlt die Anzahl Tokens in einem Text."""
        tokenizer = self._get_tokenizer()
        return len(tokenizer.encode(text))

    def _get_chunk_config(self, document_type: Optional[str]) -> ChunkConfig:
        """Gibt die Chunk-Konfiguration für einen Dokumenttyp zurück."""
        config = self._load_config()
        doc_types = config.get("document_types", {})

        # Document type normalisieren
        doc_type = (document_type or "sonstige").lower()

        if doc_type in doc_types:
            type_config = doc_types[doc_type]
        else:
            type_config = doc_types.get("sonstige", {})

        return ChunkConfig(
            chunk_size=type_config.get("chunk_size", 512),
            overlap=type_config.get("overlap", 50),
            min_chunk_size=config.get("global", {}).get("min_chunk_size", 100),
            max_chunk_size=config.get("global", {}).get("max_chunk_size", 2048),
            preserve_tables=type_config.get("preserve_tables", True),
            preserve_paragraphs=type_config.get("preserve_paragraphs", True),
            preserve_sections=type_config.get("preserve_sections", False),
            preserve_line_items=type_config.get("preserve_line_items", False),
            section_markers=type_config.get("section_markers", []),
            extract_metadata=type_config.get("extract_metadata", []),
        )

    def _detect_section_type(self, text: str) -> RAGSectionType:
        """Erkennt den Section-Typ eines Text-Chunks."""
        config = self._load_config()
        section_config = config.get("sections", {}).get("types", {})

        text_lower = text.strip().lower()
        text_start = text.strip()[:100]

        # Header-Erkennung
        if re.match(r'^#+\s', text_start):
            return RAGSectionType.HEADER
        if re.match(r'^[A-Z][A-Za-z\s]+:$', text_start):
            return RAGSectionType.HEADER
        if re.match(r'^\d+\.\s+[A-Z]', text_start):
            return RAGSectionType.HEADER

        # Tabellen-Erkennung
        if '|' in text and text.count('|') >= 2:
            return RAGSectionType.TABLE
        if '\t' in text and text.count('\t') >= 2:
            return RAGSectionType.TABLE

        # Listen-Erkennung
        if re.match(r'^[-*]\s', text_start):
            return RAGSectionType.LIST
        if re.match(r'^\d+\)\s', text_start):
            return RAGSectionType.LIST
        if re.match(r'^[a-z]\)\s', text_start):
            return RAGSectionType.LIST

        # Footer-Erkennung
        if re.match(r'^seite\s+\d+', text_lower):
            return RAGSectionType.FOOTER
        if re.match(r'^\d+\s*$', text_start):
            return RAGSectionType.FOOTER
        if 'stand:' in text_lower:
            return RAGSectionType.FOOTER

        # Default: Paragraph
        return RAGSectionType.PARAGRAPH

    def _split_into_sentences(self, text: str) -> List[str]:
        """Teilt Text in Sätze (deutsch-optimiert)."""
        # Deutsche Satzenden: . ! ? plus Abkürzungen berücksichtigen
        # Nicht trennen bei: Dr. Prof. Str. Nr. z.B. u.a. etc.
        abbreviations = r'(?<!Dr)(?<!Prof)(?<!Str)(?<!Nr)(?<!z\.B)(?<!u\.a)(?<!etc)(?<!bzw)(?<!usw)'
        sentence_endings = abbreviations + r'[.!?]\s+'

        sentences = re.split(sentence_endings, text)
        return [s.strip() for s in sentences if s.strip()]

    def _split_into_paragraphs(self, text: str) -> List[str]:
        """Teilt Text in Absätze."""
        # Doppelte Zeilenumbrueche als Paragraph-Grenzen
        paragraphs = re.split(r'\n\s*\n', text)
        return [p.strip() for p in paragraphs if p.strip()]

    def _extract_tables(self, text: str) -> Tuple[str, List[str]]:
        """Extrahiert Tabellen aus Text.

        Returns:
            Tuple von (Text ohne Tabellen, Liste von Tabellen)
        """
        tables: List[str] = []
        text_without_tables = text

        # Markdown-Tabellen erkennen
        table_pattern = r'(\|[^\n]+\|(?:\n\|[^\n]+\|)+)'
        matches = re.findall(table_pattern, text)
        for match in matches:
            tables.append(match)
            text_without_tables = text_without_tables.replace(match, '\n[TABLE_PLACEHOLDER]\n')

        return text_without_tables, tables

    def _semantic_split(
        self,
        text: str,
        config: ChunkConfig
    ) -> List[Chunk]:
        """Semantisches Chunking mit Respektierung von Textgrenzen.

        Args:
            text: Zu chunkender Text
            config: Chunking-Konfiguration

        Returns:
            Liste von Chunks
        """
        chunks: List[Chunk] = []
        current_chunk = ""
        current_tokens = 0
        chunk_index = 0

        # Tabellen extrahieren falls konfiguriert
        tables: List[str] = []
        if config.preserve_tables:
            text, tables = self._extract_tables(text)

        # In Paragraphen aufteilen
        paragraphs = self._split_into_paragraphs(text)

        for para in paragraphs:
            # Paragraph-Tokens zaehlen
            para_tokens = self._count_tokens(para)

            # Paragraph passt in aktuellen Chunk
            if current_tokens + para_tokens <= config.chunk_size:
                if current_chunk:
                    current_chunk += "\n\n"
                current_chunk += para
                current_tokens = self._count_tokens(current_chunk)

            # Paragraph zu gross - auf Satzebene aufteilen
            elif para_tokens > config.chunk_size:
                # Aktuellen Chunk speichern falls nicht leer
                if current_chunk and current_tokens >= config.min_chunk_size:
                    chunks.append(Chunk(
                        text=current_chunk,
                        index=chunk_index,
                        tokens=current_tokens,
                        section_type=self._detect_section_type(current_chunk)
                    ))
                    chunk_index += 1

                # Paragraph in Sätze aufteilen
                sentences = self._split_into_sentences(para)
                current_chunk = ""
                current_tokens = 0

                for sentence in sentences:
                    sent_tokens = self._count_tokens(sentence)

                    if current_tokens + sent_tokens <= config.chunk_size:
                        if current_chunk:
                            current_chunk += " "
                        current_chunk += sentence
                        current_tokens = self._count_tokens(current_chunk)
                    else:
                        # Chunk speichern
                        if current_chunk and current_tokens >= config.min_chunk_size:
                            chunks.append(Chunk(
                                text=current_chunk,
                                index=chunk_index,
                                tokens=current_tokens,
                                section_type=self._detect_section_type(current_chunk)
                            ))
                            chunk_index += 1

                        # Overlap: Letzte Sätze mitnehmen
                        if config.overlap > 0 and current_chunk:
                            overlap_text = self._get_overlap(current_chunk, config.overlap)
                            current_chunk = overlap_text + " " + sentence
                        else:
                            current_chunk = sentence
                        current_tokens = self._count_tokens(current_chunk)

            # Neuen Chunk starten
            else:
                # Aktuellen Chunk speichern
                if current_chunk and current_tokens >= config.min_chunk_size:
                    chunks.append(Chunk(
                        text=current_chunk,
                        index=chunk_index,
                        tokens=current_tokens,
                        section_type=self._detect_section_type(current_chunk)
                    ))
                    chunk_index += 1

                # Overlap: Ende des vorherigen Chunks mitnehmen
                if config.overlap > 0 and current_chunk:
                    overlap_text = self._get_overlap(current_chunk, config.overlap)
                    current_chunk = overlap_text + "\n\n" + para
                else:
                    current_chunk = para
                current_tokens = self._count_tokens(current_chunk)

        # Letzten Chunk speichern
        if current_chunk and current_tokens >= config.min_chunk_size:
            chunks.append(Chunk(
                text=current_chunk,
                index=chunk_index,
                tokens=current_tokens,
                section_type=self._detect_section_type(current_chunk)
            ))

        # Tabellen als separate Chunks hinzufuegen
        for table in tables:
            chunk_index += 1
            chunks.append(Chunk(
                text=table,
                index=chunk_index,
                tokens=self._count_tokens(table),
                section_type=RAGSectionType.TABLE
            ))

        return chunks

    def _get_overlap(self, text: str, overlap_tokens: int) -> str:
        """Extrahiert Overlap-Text vom Ende eines Chunks."""
        tokenizer = self._get_tokenizer()
        tokens = tokenizer.encode(text)

        if len(tokens) <= overlap_tokens:
            return text

        overlap_token_ids = tokens[-overlap_tokens:]
        return tokenizer.decode(overlap_token_ids)

    async def chunk_document(
        self,
        db: AsyncSession,
        document_id: UUID,
        strategy: str = "semantic",
        generate_embeddings: bool = True
    ) -> List[RAGDocumentChunk]:
        """Chunked ein Dokument und speichert die Chunks.

        Args:
            db: Datenbank-Session
            document_id: ID des Dokuments
            strategy: Chunking-Strategie (semantic, fixed, document_type)
            generate_embeddings: Embeddings für Chunks generieren

        Returns:
            Liste der erstellten RAGDocumentChunk-Objekte
        """
        # Dokument laden
        result = await db.execute(
            select(Document).where(Document.id == document_id)
        )
        document = result.scalar_one_or_none()

        if not document:
            raise ValueError(f"Dokument {document_id} nicht gefunden")

        if not document.extracted_text:
            raise ValueError(f"Dokument {document_id} hat keinen OCR-Text")

        logger.info(
            "chunking_document",
            document_id=str(document_id),
            strategy=strategy,
            text_length=len(document.extracted_text)
        )

        # Chunk-Konfiguration basierend auf Dokumenttyp
        # document_type kann entweder Enum oder String sein
        if document.document_type:
            doc_type = document.document_type.value if hasattr(document.document_type, 'value') else document.document_type
        else:
            doc_type = None
        config = self._get_chunk_config(doc_type)

        # Chunking durchführen
        if strategy == "fixed":
            chunks = self._fixed_split(document.extracted_text, config)
        else:  # semantic oder document_type
            chunks = self._semantic_split(document.extracted_text, config)

        logger.info(
            "chunking_completed",
            document_id=str(document_id),
            chunks_created=len(chunks),
            total_tokens=sum(c.tokens for c in chunks)
        )

        # Existierende Chunks löschen
        await db.execute(
            RAGDocumentChunk.__table__.delete().where(
                RAGDocumentChunk.document_id == document_id
            )
        )

        # Neue Chunks erstellen
        db_chunks: List[RAGDocumentChunk] = []
        for chunk in chunks:
            db_chunk = RAGDocumentChunk(
                document_id=document_id,
                chunk_index=chunk.index,
                chunk_text=chunk.text,
                chunk_tokens=chunk.tokens,
                page_number=chunk.page_number,
                section_type=chunk.section_type,
                bounding_box=chunk.bounding_box,
            )
            db.add(db_chunk)
            db_chunks.append(db_chunk)

        await db.flush()

        # Embeddings generieren
        if generate_embeddings:
            await self._generate_chunk_embeddings(db_chunks)

        await db.commit()

        logger.info(
            "chunks_saved",
            document_id=str(document_id),
            chunks_count=len(db_chunks)
        )

        return db_chunks

    def _fixed_split(self, text: str, config: ChunkConfig) -> List[Chunk]:
        """Fixes Chunking mit konstanter Größe."""
        chunks: List[Chunk] = []
        tokenizer = self._get_tokenizer()
        tokens = tokenizer.encode(text)

        chunk_size = config.chunk_size
        overlap = config.overlap

        i = 0
        chunk_index = 0

        while i < len(tokens):
            # Chunk-Tokens extrahieren
            chunk_tokens = tokens[i:i + chunk_size]
            chunk_text = tokenizer.decode(chunk_tokens)

            if len(chunk_text.strip()) > 0:
                chunks.append(Chunk(
                    text=chunk_text.strip(),
                    index=chunk_index,
                    tokens=len(chunk_tokens),
                    section_type=self._detect_section_type(chunk_text)
                ))
                chunk_index += 1

            # Nächste Position mit Overlap.
            # GUARD: Schritt MUSS >= 1 sein, sonst Endlosschleife (terminiert nie),
            # falls overlap >= chunk_size oder chunk_size <= 0 (degenerierte Config).
            i += max(1, chunk_size - overlap)

        return chunks

    async def _generate_chunk_embeddings(
        self,
        chunks: List[RAGDocumentChunk]
    ) -> None:
        """Generiert Embeddings für alle Chunks.

        Args:
            chunks: Liste von RAGDocumentChunk-Objekten
        """
        if not chunks:
            return

        logger.info(
            "generating_chunk_embeddings",
            chunk_count=len(chunks)
        )

        # Texte extrahieren
        texts = [chunk.chunk_text for chunk in chunks]

        # Batch-Embeddings generieren
        embeddings = await self._embedding_service.generate_batch_embeddings_async(
            texts,
            is_query=False  # Dokument-Embeddings (passage: prefix)
        )

        # Embeddings zu Chunks zuweisen
        embedding_model = self._embedding_service.model_name
        now = datetime.now(timezone.utc)

        for chunk, embedding in zip(chunks, embeddings):
            chunk.embedding = embedding
            chunk.embedding_model = embedding_model
            chunk.embedding_created_at = now

        logger.info(
            "chunk_embeddings_generated",
            chunk_count=len(chunks),
            embedding_model=embedding_model
        )

    async def get_document_chunks(
        self,
        db: AsyncSession,
        document_id: UUID
    ) -> List[RAGDocumentChunk]:
        """Laedt alle Chunks eines Dokuments.

        Args:
            db: Datenbank-Session
            document_id: Dokument-ID

        Returns:
            Liste von RAGDocumentChunk-Objekten
        """
        result = await db.execute(
            select(RAGDocumentChunk)
            .where(RAGDocumentChunk.document_id == document_id)
            .order_by(RAGDocumentChunk.chunk_index)
        )
        return list(result.scalars().all())

    async def delete_document_chunks(
        self,
        db: AsyncSession,
        document_id: UUID
    ) -> int:
        """Löscht alle Chunks eines Dokuments.

        Args:
            db: Datenbank-Session
            document_id: Dokument-ID

        Returns:
            Anzahl gelöschter Chunks
        """
        result = await db.execute(
            RAGDocumentChunk.__table__.delete().where(
                RAGDocumentChunk.document_id == document_id
            ).returning(RAGDocumentChunk.id)
        )
        deleted_count = len(result.fetchall())
        await db.commit()

        logger.info(
            "chunks_deleted",
            document_id=str(document_id),
            deleted_count=deleted_count
        )

        return deleted_count

    async def rechunk_document(
        self,
        db: AsyncSession,
        document_id: UUID,
        strategy: str = "semantic"
    ) -> List[RAGDocumentChunk]:
        """Chunked ein Dokument neu (löscht existierende Chunks).

        Args:
            db: Datenbank-Session
            document_id: Dokument-ID
            strategy: Chunking-Strategie

        Returns:
            Neue Chunks
        """
        # Existierende Chunks löschen
        await self.delete_document_chunks(db, document_id)

        # Neu chunken
        return await self.chunk_document(
            db, document_id, strategy, generate_embeddings=True
        )


# Singleton-Instanz
_chunking_service: Optional[DocumentChunkingService] = None


def get_chunking_service() -> DocumentChunkingService:
    """Gibt die Chunking-Service-Instanz zurück."""
    global _chunking_service
    if _chunking_service is None:
        _chunking_service = DocumentChunkingService()
    return _chunking_service
