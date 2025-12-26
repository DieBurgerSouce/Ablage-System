#!/usr/bin/env python3
"""
Migration Script: pgvector -> Qdrant via REST API

Migriert alle Embeddings aus rag_document_chunks nach Qdrant.
Nutzt REST API da gRPC-Client einen Bug hat (leere Vektoren).
"""
import asyncio
import httpx
import json
import sys
from uuid import UUID

# Add app to path
sys.path.insert(0, "/app")

from sqlalchemy import text
from app.db.session import async_session_factory


QDRANT_URL = "http://qdrant:6333"
COLLECTION_NAME = "ablage_chunks"
BATCH_SIZE = 50


def parse_embedding(embedding_str: str) -> list[float]:
    """Parse PostgreSQL array string to float list."""
    if not embedding_str:
        return []
    # Remove brackets and split
    clean = embedding_str.strip("[]{}").replace(" ", "")
    if not clean:
        return []
    return [float(x) for x in clean.split(",")]


async def ensure_collection_exists(client: httpx.AsyncClient) -> bool:
    """Ensure Qdrant collection exists with correct dimension."""
    # Check if collection exists
    resp = await client.get(f"{QDRANT_URL}/collections/{COLLECTION_NAME}")

    if resp.status_code == 200:
        info = resp.json()
        dim = info.get("result", {}).get("config", {}).get("params", {}).get("vectors", {}).get("size", 0)
        if dim == 1024:
            print(f"Collection {COLLECTION_NAME} existiert mit Dimension {dim}")
            return True
        else:
            print(f"Collection hat falsche Dimension {dim}, lösche und erstelle neu...")
            await client.delete(f"{QDRANT_URL}/collections/{COLLECTION_NAME}")

    # Create collection
    create_payload = {
        "vectors": {
            "size": 1024,
            "distance": "Cosine"
        }
    }
    resp = await client.put(
        f"{QDRANT_URL}/collections/{COLLECTION_NAME}",
        json=create_payload
    )
    if resp.status_code in (200, 201):
        print(f"Collection {COLLECTION_NAME} erstellt")
        return True
    else:
        print(f"Fehler beim Erstellen der Collection: {resp.status_code} - {resp.text}")
        return False


async def upsert_batch(client: httpx.AsyncClient, points: list[dict]) -> int:
    """Upsert a batch of points to Qdrant."""
    payload = {"points": points}
    resp = await client.put(
        f"{QDRANT_URL}/collections/{COLLECTION_NAME}/points",
        json=payload,
        timeout=60.0
    )
    if resp.status_code == 200:
        return len(points)
    else:
        print(f"Batch-Fehler: {resp.status_code} - {resp.text[:200]}")
        return 0


async def migrate_all_chunks():
    """Migrate all chunks from PostgreSQL to Qdrant."""
    print("=" * 60)
    print("Starte Migration: pgvector -> Qdrant")
    print("=" * 60)

    async with httpx.AsyncClient() as client:
        # Ensure collection exists
        if not await ensure_collection_exists(client):
            print("FEHLER: Collection konnte nicht erstellt werden")
            return

        # Get all chunks from PostgreSQL
        async with async_session_factory() as session:
            # Count total
            count_result = await session.execute(
                text("SELECT COUNT(*) FROM rag_document_chunks WHERE embedding IS NOT NULL")
            )
            total = count_result.scalar()
            print(f"\nGefunden: {total} Chunks mit Embeddings")

            # Fetch all chunks
            result = await session.execute(
                text("""
                    SELECT
                        id::text,
                        document_id::text,
                        chunk_index,
                        content,
                        embedding::text
                    FROM rag_document_chunks
                    WHERE embedding IS NOT NULL
                    ORDER BY created_at
                """)
            )
            rows = result.fetchall()

        # Process in batches
        migrated = 0
        skipped = 0
        batch = []

        for row in rows:
            chunk_id, document_id, chunk_index, content, embedding_str = row

            # Parse embedding
            embedding = parse_embedding(embedding_str)
            if len(embedding) != 1024:
                print(f"  SKIP {chunk_id}: Dimension {len(embedding)} != 1024")
                skipped += 1
                continue

            # Create point
            point = {
                "id": chunk_id,  # UUID as string
                "vector": embedding,
                "payload": {
                    "document_id": document_id,
                    "chunk_index": chunk_index,
                    "content": content[:500] if content else "",  # Truncate for payload
                    "content_length": len(content) if content else 0
                }
            }
            batch.append(point)

            # Upsert when batch is full
            if len(batch) >= BATCH_SIZE:
                count = await upsert_batch(client, batch)
                migrated += count
                print(f"  Batch migriert: {migrated}/{total} ({100*migrated/total:.1f}%)")
                batch = []

        # Final batch
        if batch:
            count = await upsert_batch(client, batch)
            migrated += count

        print("\n" + "=" * 60)
        print(f"Migration abgeschlossen!")
        print(f"  Migriert: {migrated}")
        print(f"  Übersprungen: {skipped}")
        print(f"  Gesamt: {total}")
        print("=" * 60)

        # Verify
        resp = await client.get(f"{QDRANT_URL}/collections/{COLLECTION_NAME}")
        if resp.status_code == 200:
            info = resp.json()
            points_count = info.get("result", {}).get("points_count", 0)
            print(f"\nQdrant Collection '{COLLECTION_NAME}': {points_count} Punkte")


if __name__ == "__main__":
    asyncio.run(migrate_all_chunks())
