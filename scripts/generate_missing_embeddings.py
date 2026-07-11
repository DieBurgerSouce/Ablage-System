#!/usr/bin/env python
"""Generate embeddings for documents missing them.

This script can be used to:
1. Generate embeddings for existing documents after migration
2. Fix documents where embedding generation failed
3. Regenerate all embeddings when switching models

Usage:
    python scripts/generate_missing_embeddings.py --dry-run
    python scripts/generate_missing_embeddings.py --batch-size 16
    python scripts/generate_missing_embeddings.py --max-docs 100
    python scripts/generate_missing_embeddings.py --user-id <uuid>
"""

import asyncio
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import UUID

import click

# Add app to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.models import Document


async def generate_missing_embeddings(
    batch_size: int = 8,
    dry_run: bool = False,
    max_docs: Optional[int] = None,
    user_id: Optional[str] = None,
    force_regenerate: bool = False,
) -> dict:
    """Generate embeddings for documents missing them.

    Args:
        batch_size: Batch size for GPU processing
        dry_run: Only show what would be processed
        max_docs: Maximum documents to process
        user_id: Filter to specific user's documents
        force_regenerate: Regenerate existing embeddings

    Returns:
        Dictionary with processing statistics
    """
    # Late import to avoid circular imports
    from app.services.embedding_service import EmbeddingService

    # Create database connection
    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    async_session_maker = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    start_time = datetime.utcnow()
    stats = {
        "total_found": 0,
        "processed": 0,
        "skipped": 0,
        "failed": 0,
        "errors": [],
    }

    async with async_session_maker() as session:
        # RLS-Bypass session-level (Restrunde 272-274): das Skript scannt
        # company-uebergreifend Dokumente ohne Embedding — kontextlos saehe
        # es 0 Zeilen. Muster: app.db.session.arm_rls_bypass.
        from app.db.session import arm_rls_bypass

        await arm_rls_bypass(session)

        # Build query for documents without embeddings
        query = select(Document).where(
            Document.extracted_text.isnot(None),
            Document.extracted_text != "",
        )

        if not force_regenerate:
            query = query.where(Document.embedding.is_(None))

        if user_id:
            query = query.where(Document.owner_id == UUID(user_id))

        if max_docs:
            query = query.limit(max_docs)

        # Count total documents
        count_query = select(func.count()).select_from(query.subquery())
        count_result = await session.execute(count_query)
        total = count_result.scalar() or 0

        stats["total_found"] = total

        click.echo(f"\nGefunden: {total} Dokumente ohne Embeddings")

        if total == 0:
            click.echo("Keine Dokumente zu verarbeiten.")
            return stats

        if dry_run:
            click.echo("\n[DRY-RUN] Keine Änderungen vorgenommen.")

            # Show sample of documents
            sample_query = query.limit(10)
            result = await session.execute(sample_query)
            documents = result.scalars().all()

            click.echo("\nBeispiel-Dokumente (erste 10):")
            for doc in documents:
                text_preview = (
                    doc.extracted_text[:50] + "..."
                    if len(doc.extracted_text) > 50
                    else doc.extracted_text
                )
                click.echo(f"  - {doc.id}: {doc.filename or 'Unbekannt'}")
                click.echo(f"    Text: {text_preview}")

            return stats

        # Initialize embedding service
        click.echo("\nLade Embedding-Modell...")
        embedding_service = EmbeddingService()

        # Load all documents for processing
        result = await session.execute(query)
        documents = result.scalars().all()

        # Process in batches
        total_batches = (len(documents) + batch_size - 1) // batch_size

        with click.progressbar(
            length=len(documents),
            label="Generiere Embeddings",
            show_pos=True,
            show_percent=True,
        ) as progress:
            for batch_idx in range(0, len(documents), batch_size):
                batch = documents[batch_idx : batch_idx + batch_size]
                batch_num = batch_idx // batch_size + 1

                try:
                    # Collect texts for batch
                    texts = [doc.extracted_text for doc in batch]

                    # Generate embeddings
                    embeddings = await embedding_service.generate_batch_embeddings_async(
                        texts, is_query=False
                    )

                    # Update documents
                    now = datetime.utcnow()
                    for doc, embedding in zip(batch, embeddings):
                        doc.embedding = embedding
                        doc.embedding_updated_at = now
                        doc.embedding_model = settings.EMBEDDING_MODEL
                        stats["processed"] += 1

                    await session.commit()

                except Exception as e:
                    error_msg = f"Batch {batch_num}: {str(e)}"
                    stats["errors"].append(error_msg)
                    stats["failed"] += len(batch)
                    click.echo(f"\nFehler: {error_msg}", err=True)

                    # Try to process batch individually
                    for doc in batch:
                        try:
                            embedding = await embedding_service.generate_embedding_async(
                                doc.extracted_text, is_query=False
                            )
                            doc.embedding = embedding
                            doc.embedding_updated_at = datetime.utcnow()
                            doc.embedding_model = settings.EMBEDDING_MODEL
                            stats["processed"] += 1
                            stats["failed"] -= 1
                            await session.commit()
                        except Exception as e2:
                            stats["errors"].append(
                                f"Dokument {doc.id}: {str(e2)}"
                            )

                progress.update(len(batch))

    # Calculate duration
    duration = (datetime.utcnow() - start_time).total_seconds()
    stats["duration_seconds"] = duration

    # Print summary
    click.echo("\n" + "=" * 50)
    click.echo("Zusammenfassung:")
    click.echo(f"  Gefunden:     {stats['total_found']}")
    click.echo(f"  Verarbeitet:  {stats['processed']}")
    click.echo(f"  Übersprungen: {stats['skipped']}")
    click.echo(f"  Fehlgeschlagen: {stats['failed']}")
    click.echo(f"  Dauer:        {duration:.1f} Sekunden")

    if stats["errors"]:
        click.echo(f"\nFehler ({len(stats['errors'])}):")
        for error in stats["errors"][:10]:  # Show first 10 errors
            click.echo(f"  - {error}")
        if len(stats["errors"]) > 10:
            click.echo(f"  ... und {len(stats['errors']) - 10} weitere")

    return stats


@click.command()
@click.option(
    "--batch-size",
    default=8,
    help="Batch-Größe für GPU-Verarbeitung (Standard: 8)",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Nur anzeigen, was verarbeitet werden würde",
)
@click.option(
    "--max-docs",
    default=None,
    type=int,
    help="Maximale Anzahl zu verarbeitender Dokumente",
)
@click.option(
    "--user-id",
    default=None,
    type=str,
    help="Nur Dokumente eines bestimmten Benutzers verarbeiten",
)
@click.option(
    "--force-regenerate",
    is_flag=True,
    help="Vorhandene Embeddings neu generieren",
)
def main(
    batch_size: int,
    dry_run: bool,
    max_docs: Optional[int],
    user_id: Optional[str],
    force_regenerate: bool,
) -> None:
    """Generiert Embeddings für Dokumente ohne Embeddings.

    Beispiele:

        # Trockenlauf - zeigt was verarbeitet werden würde
        python scripts/generate_missing_embeddings.py --dry-run

        # Mit größeren Batches (mehr VRAM benötigt)
        python scripts/generate_missing_embeddings.py --batch-size 16

        # Nur erste 100 Dokumente
        python scripts/generate_missing_embeddings.py --max-docs 100

        # Alle Embeddings neu generieren (z.B. nach Modellwechsel)
        python scripts/generate_missing_embeddings.py --force-regenerate
    """
    click.echo("=" * 50)
    click.echo("Ablage-System: Embedding-Migrations-Skript")
    click.echo("=" * 50)
    click.echo(f"\nKonfiguration:")
    click.echo(f"  Modell:      {settings.EMBEDDING_MODEL}")
    click.echo(f"  Dimension:   {settings.EMBEDDING_DIMENSION}")
    click.echo(f"  Batch-Größe: {batch_size}")
    click.echo(f"  Dry-Run:     {dry_run}")
    click.echo(f"  Max Docs:    {max_docs or 'Alle'}")
    click.echo(f"  User-ID:     {user_id or 'Alle'}")
    click.echo(f"  Force Regen: {force_regenerate}")

    try:
        asyncio.run(
            generate_missing_embeddings(
                batch_size=batch_size,
                dry_run=dry_run,
                max_docs=max_docs,
                user_id=user_id,
                force_regenerate=force_regenerate,
            )
        )
    except KeyboardInterrupt:
        click.echo("\n\nAbgebrochen durch Benutzer.")
        sys.exit(1)
    except Exception as e:
        click.echo(f"\nFehler: {str(e)}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
