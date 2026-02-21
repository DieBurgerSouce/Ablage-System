"""Field-Level Encryption Service.

Verwaltet die Verschluesselung sensitiver Datenbankfelder,
Key-Rotation und Migration bestehender Daten.

DSGVO Art. 32 - Sicherheit der Verarbeitung:
Verschluesselung als technische Massnahme zum Schutz personenbezogener Daten.

Feinpoliert und durchdacht - Enterprise Encryption Management.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import text, update, select, func
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.core.encryption import (
    encrypt_data,
    decrypt_data,
    is_encrypted,
    EncryptionError,
)
from app.db.models_encryption import EncryptedFieldMeta, KeyRotationLog

logger = structlog.get_logger(__name__)


# Registry aller verschluesselten Felder
ENCRYPTED_FIELDS: List[Dict[str, str]] = [
    {"table": "companies", "column": "iban", "aad": "companies.iban"},
    {"table": "companies", "column": "bic", "aad": "companies.bic"},
    {"table": "companies", "column": "vat_id", "aad": "companies.vat_id"},
    {"table": "companies", "column": "tax_number", "aad": "companies.tax_number"},
    {"table": "business_entities", "column": "iban", "aad": "business_entities.iban"},
    {"table": "business_entities", "column": "bic", "aad": "business_entities.bic"},
    {"table": "business_entities", "column": "vat_id", "aad": "business_entities.vat_id"},
    {"table": "business_entities", "column": "tax_number", "aad": "business_entities.tax_number"},
    {"table": "bank_transactions", "column": "counterparty_iban", "aad": "bank_transactions.counterparty_iban"},
    {"table": "bank_transactions", "column": "counterparty_bic", "aad": "bank_transactions.counterparty_bic"},
]


class FieldEncryptionService:
    """Service fuer Field-Level Encryption Management.

    Stellt Methoden bereit fuer:
    - Verschluesselung bestehender Klartext-Daten
    - Key-Rotation (Re-Verschluesselung mit neuem Key)
    - Status-Abfrage und Verifizierung
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialisiert den Service mit einer Datenbank-Session.

        Args:
            session: Async SQLAlchemy Session.
        """
        self.session = session

    async def encrypt_existing_data(
        self,
        table_name: str,
        column_name: str,
        batch_size: int = 500,
    ) -> int:
        """Verschluesselt bestehende Klartext-Daten in einer Spalte.

        Verarbeitet Daten in Batches um Speicher zu schonen.
        Ueberspringt bereits verschluesselte Werte (Base64-Pattern-Erkennung).

        Args:
            table_name: Name der Tabelle.
            column_name: Name der Spalte.
            batch_size: Anzahl Zeilen pro Batch.

        Returns:
            Anzahl verschluesselter Zeilen.

        Raises:
            ValueError: Wenn table_name oder column_name ungueltig sind.
        """
        # Whitelist-Validierung gegen SQL-Injection (CWE-89)
        field_entry = self._validate_field(table_name, column_name)
        aad = field_entry["aad"]

        total_encrypted = 0
        offset = 0

        logger.info(
            "field_encryption_started",
            table=table_name,
            column=column_name,
            batch_size=batch_size,
        )

        while True:
            # Lade Batch mit nicht-verschluesselten Werten
            query = text(
                f"SELECT id, {column_name} FROM {table_name} "  # noqa: S608
                f"WHERE {column_name} IS NOT NULL "
                f"AND {column_name} != '' "
                f"ORDER BY id "
                f"LIMIT :batch_size OFFSET :offset"
            )
            result = await self.session.execute(
                query,
                {"batch_size": batch_size, "offset": offset},
            )
            rows = result.fetchall()

            if not rows:
                break

            batch_encrypted = 0
            for row in rows:
                row_id = row[0]
                current_value = row[1]

                # Ueberspringen falls bereits verschluesselt
                if is_encrypted(current_value):
                    continue

                try:
                    encrypted_value = encrypt_data(
                        current_value, associated_data=aad
                    )
                    update_query = text(
                        f"UPDATE {table_name} "  # noqa: S608
                        f"SET {column_name} = :encrypted_value "
                        f"WHERE id = :row_id"
                    )
                    await self.session.execute(
                        update_query,
                        {
                            "encrypted_value": encrypted_value,
                            "row_id": row_id,
                        },
                    )
                    batch_encrypted += 1
                except EncryptionError:
                    logger.warning(
                        "field_encryption_row_failed",
                        table=table_name,
                        column=column_name,
                        row_id=str(row_id),
                    )
                    continue

            total_encrypted += batch_encrypted
            offset += batch_size

            # Commit nach jedem Batch fuer Fortschritts-Sicherung
            await self.session.commit()

            logger.info(
                "field_encryption_batch_complete",
                table=table_name,
                column=column_name,
                batch_encrypted=batch_encrypted,
                total_encrypted=total_encrypted,
            )

        # Aktualisiere Metadaten
        await self._update_field_meta(table_name, column_name, total_encrypted)
        await self.session.commit()

        logger.info(
            "field_encryption_completed",
            table=table_name,
            column=column_name,
            total_encrypted=total_encrypted,
        )

        return total_encrypted

    async def rotate_key(
        self,
        table_name: str,
        column_name: str,
        batch_size: int = 500,
    ) -> int:
        """Rotiert den Encryption Key fuer eine Spalte.

        1. Entschluesselt mit aktuellem Key
        2. Verschluesselt mit neuem Key
        3. Aktualisiert EncryptedFieldMeta
        4. Protokolliert in KeyRotationLog

        Args:
            table_name: Name der Tabelle.
            column_name: Name der Spalte.
            batch_size: Anzahl Zeilen pro Batch.

        Returns:
            Anzahl re-verschluesselter Zeilen.

        Raises:
            ValueError: Wenn table_name oder column_name ungueltig sind.
        """
        field_entry = self._validate_field(table_name, column_name)
        aad = field_entry["aad"]

        # Lade aktuelle Key-Version
        meta = await self._get_field_meta(table_name, column_name)
        old_version = meta.key_version if meta else 1
        new_version = old_version + 1

        # Erstelle Rotations-Log
        rotation_log = KeyRotationLog(
            table_name=table_name,
            column_name=column_name,
            old_key_version=old_version,
            new_key_version=new_version,
            status="in_progress",
            started_at=datetime.now(timezone.utc),
        )
        self.session.add(rotation_log)
        await self.session.flush()

        total_rotated = 0

        try:
            # Zaehle betroffene Zeilen
            count_query = text(
                f"SELECT COUNT(*) FROM {table_name} "  # noqa: S608
                f"WHERE {column_name} IS NOT NULL "
                f"AND {column_name} != ''"
            )
            count_result = await self.session.execute(count_query)
            total_rows = count_result.scalar() or 0
            rotation_log.rows_total = total_rows

            offset = 0
            while True:
                query = text(
                    f"SELECT id, {column_name} FROM {table_name} "  # noqa: S608
                    f"WHERE {column_name} IS NOT NULL "
                    f"AND {column_name} != '' "
                    f"ORDER BY id "
                    f"LIMIT :batch_size OFFSET :offset"
                )
                result = await self.session.execute(
                    query,
                    {"batch_size": batch_size, "offset": offset},
                )
                rows = result.fetchall()

                if not rows:
                    break

                for row in rows:
                    row_id = row[0]
                    current_value = row[1]

                    try:
                        # Entschluesseln
                        plaintext = decrypt_data(current_value, associated_data=aad)

                        # Neu verschluesseln (mit aktuellem Key - nach Key-Rotation)
                        new_encrypted = encrypt_data(plaintext, associated_data=aad)

                        update_query = text(
                            f"UPDATE {table_name} "  # noqa: S608
                            f"SET {column_name} = :new_value "
                            f"WHERE id = :row_id"
                        )
                        await self.session.execute(
                            update_query,
                            {"new_value": new_encrypted, "row_id": row_id},
                        )
                        total_rotated += 1
                    except EncryptionError:
                        logger.warning(
                            "key_rotation_row_failed",
                            table=table_name,
                            column=column_name,
                            row_id=str(row_id),
                        )
                        continue

                offset += batch_size
                rotation_log.rows_processed = total_rotated
                await self.session.commit()

            # Rotation abschliessen
            rotation_log.status = "completed"
            rotation_log.rows_processed = total_rotated
            rotation_log.completed_at = datetime.now(timezone.utc)

            # Aktualisiere Metadaten
            if meta:
                meta.key_version = new_version
                meta.rotated_at = datetime.now(timezone.utc)
                meta.row_count = total_rotated
                meta.status = "active"

            await self.session.commit()

            logger.info(
                "key_rotation_completed",
                table=table_name,
                column=column_name,
                old_version=old_version,
                new_version=new_version,
                rows_rotated=total_rotated,
            )

        except Exception as exc:
            rotation_log.status = "failed"
            rotation_log.error_message = str(exc)[:500]
            rotation_log.completed_at = datetime.now(timezone.utc)
            await self.session.commit()

            logger.error(
                "key_rotation_failed",
                table=table_name,
                column=column_name,
                error=str(exc),
            )
            raise

        return total_rotated

    async def get_encryption_status(self) -> List[Dict[str, str]]:
        """Gibt den Verschluesselungsstatus aller Felder zurueck.

        Returns:
            Liste mit Status-Informationen pro verschluesseltem Feld.
        """
        result_list: List[Dict[str, str]] = []

        for field in ENCRYPTED_FIELDS:
            meta = await self._get_field_meta(field["table"], field["column"])

            if meta:
                status_entry: Dict[str, str] = {
                    "tabelle": field["table"],
                    "spalte": field["column"],
                    "algorithmus": meta.encryption_algorithm,
                    "key_version": str(meta.key_version),
                    "status": meta.status,
                    "zeilen_verschluesselt": str(meta.row_count),
                    "letzte_rotation": (
                        meta.rotated_at.isoformat() if meta.rotated_at else "Nie"
                    ),
                }
            else:
                status_entry = {
                    "tabelle": field["table"],
                    "spalte": field["column"],
                    "algorithmus": "Nicht konfiguriert",
                    "key_version": "0",
                    "status": "nicht_initialisiert",
                    "zeilen_verschluesselt": "0",
                    "letzte_rotation": "Nie",
                }
            result_list.append(status_entry)

        return result_list

    async def verify_encryption(
        self,
        table_name: str,
        column_name: str,
        sample_size: int = 10,
    ) -> Dict[str, object]:
        """Verifiziert dass Daten korrekt verschluesselt/entschluesselt werden.

        Liest eine Stichprobe verschluesselter Werte und prueft, ob sie
        entschluesselt werden koennen.

        Args:
            table_name: Name der Tabelle.
            column_name: Name der Spalte.
            sample_size: Anzahl zu pruefender Zeilen.

        Returns:
            Dict mit Verifizierungsergebnissen.

        Raises:
            ValueError: Wenn table_name oder column_name ungueltig sind.
        """
        field_entry = self._validate_field(table_name, column_name)
        aad = field_entry["aad"]

        query = text(
            f"SELECT id, {column_name} FROM {table_name} "  # noqa: S608
            f"WHERE {column_name} IS NOT NULL "
            f"AND {column_name} != '' "
            f"ORDER BY RANDOM() "
            f"LIMIT :sample_size"
        )
        result = await self.session.execute(
            query, {"sample_size": sample_size}
        )
        rows = result.fetchall()

        total = len(rows)
        encrypted_count = 0
        decryptable_count = 0
        plaintext_count = 0
        errors = 0

        for row in rows:
            current_value = row[1]

            if is_encrypted(current_value):
                encrypted_count += 1
                try:
                    decrypted = decrypt_data(current_value, associated_data=aad)
                    if decrypted:
                        decryptable_count += 1
                except EncryptionError:
                    errors += 1
            else:
                plaintext_count += 1

        verification_result: Dict[str, object] = {
            "tabelle": table_name,
            "spalte": column_name,
            "stichprobe": total,
            "verschluesselt": encrypted_count,
            "entschluesselbar": decryptable_count,
            "klartext": plaintext_count,
            "fehler": errors,
            "intakt": errors == 0 and plaintext_count == 0,
        }

        logger.info(
            "encryption_verification_complete",
            **{k: str(v) for k, v in verification_result.items()},
        )

        return verification_result

    # =========================================================================
    # Private Hilfsmethoden
    # =========================================================================

    def _validate_field(
        self, table_name: str, column_name: str
    ) -> Dict[str, str]:
        """Validiert dass table/column in der Whitelist steht (CWE-89 Schutz).

        Args:
            table_name: Name der Tabelle.
            column_name: Name der Spalte.

        Returns:
            Matching field entry aus ENCRYPTED_FIELDS.

        Raises:
            ValueError: Wenn das Feld nicht in der Whitelist steht.
        """
        for field in ENCRYPTED_FIELDS:
            if field["table"] == table_name and field["column"] == column_name:
                return field

        raise ValueError(
            f"Ungueltiges Feld: {table_name}.{column_name}. "
            f"Nur registrierte verschluesselte Felder sind erlaubt."
        )

    async def _get_field_meta(
        self, table_name: str, column_name: str
    ) -> Optional[EncryptedFieldMeta]:
        """Laedt die Metadaten fuer ein verschluesseltes Feld.

        Args:
            table_name: Name der Tabelle.
            column_name: Name der Spalte.

        Returns:
            EncryptedFieldMeta oder None.
        """
        query = select(EncryptedFieldMeta).where(
            EncryptedFieldMeta.table_name == table_name,
            EncryptedFieldMeta.column_name == column_name,
            EncryptedFieldMeta.status != "deprecated",
        ).order_by(EncryptedFieldMeta.key_version.desc())

        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def _update_field_meta(
        self, table_name: str, column_name: str, row_count: int
    ) -> None:
        """Aktualisiert die Metadaten nach Verschluesselung.

        Args:
            table_name: Name der Tabelle.
            column_name: Name der Spalte.
            row_count: Anzahl verschluesselter Zeilen.
        """
        meta = await self._get_field_meta(table_name, column_name)
        if meta:
            meta.row_count = row_count
            meta.status = "active"
        else:
            new_meta = EncryptedFieldMeta(
                table_name=table_name,
                column_name=column_name,
                encryption_key_id="primary",
                encryption_algorithm="AES-256-GCM",
                key_version=1,
                row_count=row_count,
                status="active",
            )
            self.session.add(new_meta)
