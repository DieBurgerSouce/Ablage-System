#!/usr/bin/env python3
"""
data-consistency-check.py - PostgreSQL und MinIO Konsistenzpruefung

Prueft Datenkonsistenz zwischen PostgreSQL und MinIO:
- Verwaiste Dateien in MinIO (ohne DB-Eintrag)
- Fehlende Dateien (DB-Eintrag ohne MinIO-Objekt)
- Hash-Validierung fuer Integritaet
- Automatische Reparatur-Optionen

Verwendung:
    python scripts/data-consistency-check.py [--repair] [--dry-run]
"""

import argparse
import asyncio
import hashlib
import json
import sys
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple
from uuid import UUID

try:
    from minio import Minio
    from minio.error import S3Error
    import asyncpg
except ImportError:
    print("Benoetigte Pakete: pip install minio asyncpg")
    sys.exit(1)


# Konfiguration
POSTGRES_URL = "postgresql://postgres:postgres@localhost:5433/ablage"
MINIO_ENDPOINT = "localhost:9000"
MINIO_ACCESS_KEY = "minioadmin"
MINIO_SECRET_KEY = "minioadmin123"
MINIO_BUCKET = "documents"
MINIO_SECURE = False


class ConsistencyChecker:
    """Prueft Konsistenz zwischen PostgreSQL und MinIO."""

    def __init__(
        self,
        postgres_url: str = POSTGRES_URL,
        minio_endpoint: str = MINIO_ENDPOINT,
        minio_access_key: str = MINIO_ACCESS_KEY,
        minio_secret_key: str = MINIO_SECRET_KEY,
        minio_bucket: str = MINIO_BUCKET,
    ):
        """Initialisiert den Checker.

        Args:
            postgres_url: PostgreSQL Connection URL
            minio_endpoint: MinIO Server Endpoint
            minio_access_key: MinIO Access Key
            minio_secret_key: MinIO Secret Key
            minio_bucket: MinIO Bucket Name
        """
        self.postgres_url = postgres_url
        self.minio_bucket = minio_bucket

        # MinIO Client
        self.minio_client = Minio(
            minio_endpoint,
            access_key=minio_access_key,
            secret_key=minio_secret_key,
            secure=MINIO_SECURE,
        )

        # Ergebnisse
        self.results = {
            "timestamp": datetime.utcnow().isoformat(),
            "db_documents": 0,
            "minio_objects": 0,
            "orphaned_in_minio": [],
            "missing_in_minio": [],
            "hash_mismatches": [],
            "size_mismatches": [],
        }

    async def get_db_documents(self) -> Dict[str, Dict]:
        """Holt alle Dokumente aus PostgreSQL.

        Returns:
            Dict mit storage_path als Key und Document-Info als Value
        """
        documents = {}

        conn = await asyncpg.connect(self.postgres_url)
        try:
            rows = await conn.fetch(
                """
                SELECT
                    id,
                    filename,
                    storage_path,
                    file_size,
                    file_hash,
                    status,
                    deleted_at
                FROM documents
                WHERE deleted_at IS NULL
                """
            )

            for row in rows:
                storage_path = row["storage_path"]
                if storage_path:
                    documents[storage_path] = {
                        "id": str(row["id"]),
                        "filename": row["filename"],
                        "file_size": row["file_size"],
                        "file_hash": row["file_hash"],
                        "status": row["status"],
                    }

            self.results["db_documents"] = len(documents)

        finally:
            await conn.close()

        return documents

    def get_minio_objects(self) -> Dict[str, Dict]:
        """Holt alle Objekte aus MinIO.

        Returns:
            Dict mit Object-Name als Key und Object-Info als Value
        """
        objects = {}

        try:
            # Pruefe ob Bucket existiert
            if not self.minio_client.bucket_exists(self.minio_bucket):
                print(f"Bucket '{self.minio_bucket}' existiert nicht!")
                return objects

            # Liste alle Objekte
            for obj in self.minio_client.list_objects(
                self.minio_bucket, recursive=True
            ):
                objects[obj.object_name] = {
                    "size": obj.size,
                    "etag": obj.etag.strip('"') if obj.etag else None,
                    "last_modified": obj.last_modified.isoformat()
                    if obj.last_modified
                    else None,
                }

            self.results["minio_objects"] = len(objects)

        except S3Error as e:
            print(f"MinIO Fehler: {e}")

        return objects

    def calculate_file_hash(self, object_name: str) -> Optional[str]:
        """Berechnet MD5-Hash einer MinIO-Datei.

        Args:
            object_name: MinIO Object Name

        Returns:
            MD5-Hash als Hex-String oder None bei Fehler
        """
        try:
            response = self.minio_client.get_object(self.minio_bucket, object_name)
            hasher = hashlib.md5()

            for chunk in response.stream(32 * 1024):
                hasher.update(chunk)

            response.close()
            response.release_conn()

            return hasher.hexdigest()

        except Exception as e:
            print(f"Hash-Berechnung fehlgeschlagen fuer {object_name}: {e}")
            return None

    async def check_consistency(
        self, verify_hashes: bool = False
    ) -> Dict:
        """Fuehrt Konsistenzpruefung durch.

        Args:
            verify_hashes: Ob Hash-Validierung durchgefuehrt werden soll

        Returns:
            Dict mit Pruefergebnissen
        """
        print("Lade Dokumente aus PostgreSQL...")
        db_docs = await self.get_db_documents()
        print(f"  {len(db_docs)} Dokumente gefunden")

        print("Lade Objekte aus MinIO...")
        minio_objs = self.get_minio_objects()
        print(f"  {len(minio_objs)} Objekte gefunden")

        db_paths = set(db_docs.keys())
        minio_paths = set(minio_objs.keys())

        # 1. Verwaiste Dateien in MinIO (ohne DB-Eintrag)
        orphaned = minio_paths - db_paths
        for path in orphaned:
            self.results["orphaned_in_minio"].append(
                {
                    "path": path,
                    "size": minio_objs[path]["size"],
                    "last_modified": minio_objs[path]["last_modified"],
                }
            )

        # 2. Fehlende Dateien in MinIO (DB-Eintrag ohne Datei)
        missing = db_paths - minio_paths
        for path in missing:
            self.results["missing_in_minio"].append(
                {
                    "path": path,
                    "document_id": db_docs[path]["id"],
                    "filename": db_docs[path]["filename"],
                }
            )

        # 3. Groessen-Vergleich fuer existierende Dateien
        common = db_paths & minio_paths
        for path in common:
            db_size = db_docs[path]["file_size"]
            minio_size = minio_objs[path]["size"]

            if db_size and minio_size and db_size != minio_size:
                self.results["size_mismatches"].append(
                    {
                        "path": path,
                        "document_id": db_docs[path]["id"],
                        "db_size": db_size,
                        "minio_size": minio_size,
                    }
                )

        # 4. Hash-Validierung (optional, langsam)
        if verify_hashes:
            print("Verifiziere Hashes (dies kann dauern)...")
            for i, path in enumerate(common):
                if db_docs[path]["file_hash"]:
                    actual_hash = self.calculate_file_hash(path)
                    if actual_hash and actual_hash != db_docs[path]["file_hash"]:
                        self.results["hash_mismatches"].append(
                            {
                                "path": path,
                                "document_id": db_docs[path]["id"],
                                "expected_hash": db_docs[path]["file_hash"],
                                "actual_hash": actual_hash,
                            }
                        )

                if (i + 1) % 100 == 0:
                    print(f"  {i + 1}/{len(common)} geprueft...")

        return self.results

    async def repair_orphaned(self, dry_run: bool = True) -> List[str]:
        """Loescht verwaiste Dateien aus MinIO.

        Args:
            dry_run: Wenn True, nur simulieren

        Returns:
            Liste der geloeschten Pfade
        """
        deleted = []

        for item in self.results["orphaned_in_minio"]:
            path = item["path"]
            if dry_run:
                print(f"[DRY-RUN] Wuerde loeschen: {path}")
            else:
                try:
                    self.minio_client.remove_object(self.minio_bucket, path)
                    print(f"Geloescht: {path}")
                    deleted.append(path)
                except S3Error as e:
                    print(f"Fehler beim Loeschen von {path}: {e}")

        return deleted

    async def repair_missing(self, dry_run: bool = True) -> List[str]:
        """Markiert Dokumente ohne Datei als fehlerhaft in DB.

        Args:
            dry_run: Wenn True, nur simulieren

        Returns:
            Liste der aktualisierten Document-IDs
        """
        updated = []

        if not self.results["missing_in_minio"]:
            return updated

        conn = await asyncpg.connect(self.postgres_url)
        try:
            for item in self.results["missing_in_minio"]:
                doc_id = item["document_id"]
                if dry_run:
                    print(f"[DRY-RUN] Wuerde Status setzen fuer: {doc_id}")
                else:
                    await conn.execute(
                        """
                        UPDATE documents
                        SET status = 'file_missing',
                            updated_at = NOW()
                        WHERE id = $1
                        """,
                        UUID(doc_id),
                    )
                    print(f"Status aktualisiert: {doc_id}")
                    updated.append(doc_id)

            if not dry_run and updated:
                await conn.execute("COMMIT")

        finally:
            await conn.close()

        return updated

    def print_report(self) -> None:
        """Gibt Bericht aus."""
        print("\n" + "=" * 60)
        print("  Konsistenzpruefung - Ergebnis")
        print("=" * 60)

        print(f"\nZeitstempel: {self.results['timestamp']}")
        print(f"DB Dokumente: {self.results['db_documents']}")
        print(f"MinIO Objekte: {self.results['minio_objects']}")

        # Verwaiste Dateien
        orphaned_count = len(self.results["orphaned_in_minio"])
        status = "🔴" if orphaned_count > 0 else "🟢"
        print(f"\n{status} Verwaiste Dateien in MinIO: {orphaned_count}")
        if orphaned_count > 0 and orphaned_count <= 10:
            for item in self.results["orphaned_in_minio"]:
                print(f"   - {item['path']} ({item['size']} bytes)")
        elif orphaned_count > 10:
            print(f"   (Zeige erste 10 von {orphaned_count})")
            for item in self.results["orphaned_in_minio"][:10]:
                print(f"   - {item['path']} ({item['size']} bytes)")

        # Fehlende Dateien
        missing_count = len(self.results["missing_in_minio"])
        status = "🔴" if missing_count > 0 else "🟢"
        print(f"\n{status} Fehlende Dateien in MinIO: {missing_count}")
        if missing_count > 0 and missing_count <= 10:
            for item in self.results["missing_in_minio"]:
                print(f"   - {item['filename']} (ID: {item['document_id'][:8]}...)")
        elif missing_count > 10:
            print(f"   (Zeige erste 10 von {missing_count})")
            for item in self.results["missing_in_minio"][:10]:
                print(f"   - {item['filename']} (ID: {item['document_id'][:8]}...)")

        # Groessen-Unterschiede
        size_count = len(self.results["size_mismatches"])
        status = "🔴" if size_count > 0 else "🟢"
        print(f"\n{status} Groessen-Unterschiede: {size_count}")
        for item in self.results["size_mismatches"][:5]:
            print(
                f"   - {item['path']}: DB={item['db_size']}, MinIO={item['minio_size']}"
            )

        # Hash-Unterschiede
        hash_count = len(self.results["hash_mismatches"])
        if hash_count > 0:
            print(f"\n🔴 Hash-Unterschiede: {hash_count}")
            for item in self.results["hash_mismatches"][:5]:
                print(f"   - {item['path']}: Daten korrupt!")

        # Zusammenfassung
        total_issues = orphaned_count + missing_count + size_count + hash_count
        print("\n" + "-" * 60)
        if total_issues == 0:
            print("✅ Keine Konsistenzprobleme gefunden!")
        else:
            print(f"⚠️  {total_issues} Problem(e) gefunden")
            print("\nReparatur-Optionen:")
            print(
                "  --repair --dry-run  Zeigt was repariert werden wuerde"
            )
            print("  --repair            Fuehrt Reparatur durch")

        print("=" * 60)


async def main():
    """Hauptfunktion."""
    parser = argparse.ArgumentParser(
        description="PostgreSQL/MinIO Konsistenzpruefung fuer Ablage-System"
    )
    parser.add_argument(
        "--repair",
        action="store_true",
        help="Reparatur durchfuehren"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Nur simulieren (mit --repair)"
    )
    parser.add_argument(
        "--verify-hashes",
        action="store_true",
        help="Hash-Validierung (langsam)"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="JSON-Output"
    )
    parser.add_argument(
        "--postgres-url",
        default=POSTGRES_URL,
        help=f"PostgreSQL URL (default: {POSTGRES_URL})"
    )
    parser.add_argument(
        "--minio-endpoint",
        default=MINIO_ENDPOINT,
        help=f"MinIO Endpoint (default: {MINIO_ENDPOINT})"
    )

    args = parser.parse_args()

    checker = ConsistencyChecker(
        postgres_url=args.postgres_url,
        minio_endpoint=args.minio_endpoint,
    )

    # Konsistenzpruefung durchfuehren
    await checker.check_consistency(verify_hashes=args.verify_hashes)

    if args.json:
        print(json.dumps(checker.results, indent=2, default=str))
    else:
        checker.print_report()

    # Reparatur wenn gewuenscht
    if args.repair:
        print("\n" + "=" * 60)
        print("  Reparatur")
        print("=" * 60)

        dry_run = args.dry_run
        if dry_run:
            print("(DRY-RUN Modus - keine aenderungen)")

        # Verwaiste Dateien loeschen
        if checker.results["orphaned_in_minio"]:
            print(f"\nLoesche {len(checker.results['orphaned_in_minio'])} verwaiste Dateien...")
            deleted = await checker.repair_orphaned(dry_run=dry_run)
            print(f"  {len(deleted)} Dateien geloescht")

        # Fehlende Dateien markieren
        if checker.results["missing_in_minio"]:
            print(f"\nMarkiere {len(checker.results['missing_in_minio'])} fehlende Dokumente...")
            updated = await checker.repair_missing(dry_run=dry_run)
            print(f"  {len(updated)} Dokumente aktualisiert")


if __name__ == "__main__":
    asyncio.run(main())
