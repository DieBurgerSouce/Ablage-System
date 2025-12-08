# -*- coding: utf-8 -*-
"""
SQLite to PostgreSQL Migration Script for OCR Training Samples.

Migriert 9.997 Dokumente aus SQLite nach PostgreSQL.
Verwendet psycopg2 (sync) fuer direkte Verbindung.
"""

import hashlib
import sqlite3
from uuid import uuid4


def run_migration() -> None:
    """Fuehre direkte Migration durch."""
    import psycopg2
    from psycopg2.extras import execute_values

    print("=== DIREKTE MIGRATION SQLite -> PostgreSQL ===")

    # SQLite lesen
    sqlite_path = "Trainings_Data/_validation_system/training_data.db"
    conn_sqlite = sqlite3.connect(sqlite_path)
    conn_sqlite.row_factory = sqlite3.Row
    cursor = conn_sqlite.execute("SELECT * FROM documents")
    rows = cursor.fetchall()
    print(f"SQLite Dokumente: {len(rows)}")

    # PostgreSQL verbinden (direkt ueber Port 5434)
    conn_pg = psycopg2.connect(
        host="localhost",
        port=5434,
        database="ablage_system",
        user="ablage_admin",
        password="ablage123!secure",
    )
    conn_pg.autocommit = False
    cur_pg = conn_pg.cursor()

    # Pruefe ob Tabelle leer
    cur_pg.execute("SELECT COUNT(*) FROM ocr_training_samples")
    count = cur_pg.fetchone()[0]
    print(f"PostgreSQL existierende Samples: {count}")

    if count > 0:
        print("Tabelle nicht leer - ueberspringe Migration")
        conn_sqlite.close()
        conn_pg.close()
        return

    # Migriere in Batches
    batch_size = 500
    migrated = 0
    total = len(rows)

    for i in range(0, total, batch_size):
        batch = rows[i : i + batch_size]
        values_list = []

        for row in batch:
            file_hash = row["file_hash"] or hashlib.sha256(
                (row["file_path"] or "").encode()
            ).hexdigest()
            language = row["doc_language"] or "de"
            doc_type = row["doc_type"]
            status = row["ground_truth_status"] or "pending"

            # Map status
            status_map = {
                "pending": "pending",
                "annotated": "annotated",
                "verified": "verified",
                "rejected": "rejected",
                "needs_review": "pending",
            }
            status = status_map.get(status, "pending")

            values_list.append(
                (
                    str(uuid4()),  # id
                    row["file_path"] or "",  # file_path
                    file_hash,  # file_hash
                    row["thumbnail_path"],  # thumbnail_path
                    row["ocr_text"] if status == "verified" else None,  # ground_truth_text
                    language or "de",  # language
                    doc_type,  # document_type
                    "medium",  # difficulty
                    False,  # has_umlauts
                    False,  # has_fraktur
                    False,  # has_tables
                    bool(row["has_handwriting"]),  # has_handwriting
                    bool(row["has_stamps"]),  # has_stamps
                    bool(row["has_signatures"]),  # has_signatures
                    status,  # status
                    "[]",  # umlaut_words
                    "{}",  # extracted_fields
                )
            )

        # Bulk insert mit execute_values
        insert_sql = """
            INSERT INTO ocr_training_samples
            (id, file_path, file_hash, thumbnail_path, ground_truth_text,
             language, document_type, difficulty, has_umlauts, has_fraktur,
             has_tables, has_handwriting, has_stamps, has_signatures,
             status, umlaut_words, extracted_fields)
            VALUES %s
        """
        execute_values(cur_pg, insert_sql, values_list)
        conn_pg.commit()

        migrated += len(batch)
        print(f"  Migriert: {migrated}/{total}")

    # Verifiziere
    cur_pg.execute("SELECT COUNT(*) FROM ocr_training_samples")
    final_count = cur_pg.fetchone()[0]
    print("")
    print("=== MIGRATION ABGESCHLOSSEN ===")
    print(f"PostgreSQL Samples: {final_count}")

    conn_sqlite.close()
    conn_pg.close()


if __name__ == "__main__":
    run_migration()
