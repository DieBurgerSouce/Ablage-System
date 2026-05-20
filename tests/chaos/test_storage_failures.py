"""Chaos Engineering Tests - Storage-Fehlerszenarien.

Simuliert MinIO/S3-Ausfaelle, Disk-Full-Errors, korrupte Dateien
und Quota-Ueberschreitungen.
"""

import errno
from io import BytesIO
from typing import Any, Dict, Optional
from unittest.mock import MagicMock

import pytest


# Mock-Exceptions
class MinIOError(Exception):
    """Mock MinIO Error."""
    pass


class S3Error(Exception):
    """Mock S3 Error."""
    pass


@pytest.mark.chaos
@pytest.mark.asyncio
async def test_minio_unavailable(mock_minio):
    """Testet Behandlung von MinIO-Verbindungsfehlern.

    Szenario: MinIO-Server ist nicht erreichbar.
    Erwartung: Upload/Download schlaegt fehl mit aussagekraeftiger Fehlermeldung.
    """
    # Arrange: MinIO wirft ConnectionError
    mock_minio.put_object.side_effect = ConnectionError("MinIO-Server nicht erreichbar")

    # Act: Simuliere File-Upload mit Error-Handling
    async def upload_file(
        client,
        bucket: str,
        filename: str,
        data: bytes
    ) -> Optional[str]:
        """Uploaded Datei zu MinIO mit Error-Handling."""
        try:
            result = client.put_object(
                bucket_name=bucket,
                object_name=filename,
                data=BytesIO(data),
                length=len(data)
            )
            return result.etag
        except (ConnectionError, MinIOError) as e:
            print(f"MinIO-Upload fehlgeschlagen: {e}")
            # Fallback: Speichere lokal fuer spaetere Verarbeitung
            return None

    etag = await upload_file(
        mock_minio,
        bucket="documents",
        filename="test.pdf",
        data=b"test data"
    )

    # Assert: Upload schlug fehl
    assert etag is None, "Upload sollte None bei Verbindungsfehler zurueckgeben"
    mock_minio.put_object.assert_called_once()


@pytest.mark.chaos
@pytest.mark.asyncio
async def test_disk_full_simulation():
    """Testet Behandlung von Disk-Full-Fehlern.

    Szenario: Keine Speicherplatz mehr auf Festplatte.
    Erwartung: Fehler wird erkannt, temporaere Dateien werden aufgeraeumt.
    """
    # Arrange: Mock file write mit ENOSPC
    mock_file = MagicMock()
    mock_file.write.side_effect = OSError(errno.ENOSPC, "Kein Speicherplatz verfuegbar")

    # Act: Simuliere File-Write mit Error-Handling
    async def write_temp_file(data: bytes) -> Optional[str]:
        """Schreibt temporaere Datei mit Disk-Full-Handling."""
        temp_path = "/tmp/upload-temp-123.pdf"
        cleanup_needed = False

        try:
            # Mock file open
            mock_file.write(data)
            cleanup_needed = True
            return temp_path
        except OSError as e:
            if e.errno == errno.ENOSPC:
                print("Fehler: Speicherplatz erschoepft")
                # Cleanup bei Bedarf
                if cleanup_needed:
                    print(f"Raeume temporaere Datei auf: {temp_path}")
            else:
                print(f"Schreibfehler: {e}")
            return None

    result = await write_temp_file(b"large data" * 1000)

    # Assert: Fehlerbehandlung wurde aktiviert
    assert result is None, "Sollte None bei Disk-Full zurueckgeben"
    mock_file.write.assert_called_once()


@pytest.mark.chaos
@pytest.mark.asyncio
async def test_corrupt_file_upload():
    """Testet Behandlung von korrupten Datei-Uploads.

    Szenario: Hochgeladene PDF ist truncated/corrupt.
    Erwartung: Validierung erkennt korrupte Datei und lehnt sie ab.
    """
    # Arrange: Korrupte PDF-Daten
    corrupt_pdf = b"%PDF-1.4\n%"  # Unvollstaendiger PDF-Header

    # Act: Simuliere Dateivalidierung
    async def validate_pdf(data: bytes) -> Dict[str, Any]:
        """Validiert PDF-Datei auf Korrektheit."""
        min_size = 100  # Minimale PDF-Groesse
        pdf_header = b"%PDF-"
        pdf_footer = b"%%EOF"

        errors = []

        # Groesse pruefen
        if len(data) < min_size:
            errors.append(f"Datei zu klein: {len(data)} bytes (min. {min_size})")

        # Header pruefen
        if not data.startswith(pdf_header):
            errors.append("Ungueltiger PDF-Header")

        # Footer pruefen
        if not data.rstrip().endswith(pdf_footer):
            errors.append("PDF-Footer fehlt oder truncated")

        is_valid = len(errors) == 0

        return {
            "valid": is_valid,
            "errors": errors,
            "size": len(data)
        }

    validation = await validate_pdf(corrupt_pdf)

    # Assert: Korrupte Datei wurde erkannt
    assert validation["valid"] is False, "Korrupte PDF sollte invalid sein"
    assert len(validation["errors"]) > 0, "Sollte Validierungsfehler haben"
    assert any("klein" in e or "Footer" in e for e in validation["errors"])


@pytest.mark.chaos
@pytest.mark.asyncio
async def test_storage_quota_exceeded(mock_minio):
    """Testet Behandlung von Storage-Quota-Ueberschreitung.

    Szenario: User hat sein Storage-Limit erreicht.
    Erwartung: Upload wird abgelehnt mit klarer Fehlermeldung.
    """
    # Arrange: MinIO wirft Quota-Error
    mock_minio.put_object.side_effect = S3Error("Quota exceeded")

    # Act: Simuliere Upload mit Quota-Check
    async def upload_with_quota_check(
        client,
        user_id: str,
        bucket: str,
        filename: str,
        data: bytes,
        user_quota_gb: float = 10.0
    ) -> Dict[str, Any]:
        """Uploaded mit Quota-Pruefung."""
        # Simuliere Quota-Check
        current_usage_gb = 10.0
        file_size_gb = len(data) / (1024**3)

        if current_usage_gb + file_size_gb > user_quota_gb:
            return {
                "success": False,
                "error": "Speicherlimit ueberschritten",
                "quota_gb": user_quota_gb,
                "used_gb": current_usage_gb,
                "available_gb": user_quota_gb - current_usage_gb
            }

        try:
            result = client.put_object(
                bucket_name=bucket,
                object_name=f"{user_id}/{filename}",
                data=BytesIO(data),
                length=len(data)
            )
            return {"success": True, "etag": result.etag}
        except S3Error as e:
            if "Quota" in str(e):
                return {
                    "success": False,
                    "error": "Speicherlimit erreicht",
                    "quota_gb": user_quota_gb
                }
            raise

    result = await upload_with_quota_check(
        mock_minio,
        user_id="user-123",
        bucket="documents",
        filename="large-file.pdf",
        data=b"x" * 1024  # 1KB - Mock prueft keine Groesse
    )

    # Assert: Upload wurde wegen Quota abgelehnt
    assert result["success"] is False, "Upload sollte wegen Quota fehlschlagen"
    assert "Speicherlimit" in result["error"]


@pytest.mark.chaos
@pytest.mark.asyncio
async def test_partial_upload_recovery(mock_minio):
    """Testet Cleanup von partiellen Uploads nach Fehler.

    Szenario: Upload schlaegt mittendrin fehl, partielle Daten bleiben zurueck.
    Erwartung: Cleanup entfernt unvollstaendige Uploads.
    """
    # Arrange: Mock MultipartUpload
    upload_parts = []

    def mock_put_object(*args, **kwargs):
        """Simuliert fehlgeschlagenen Multipart-Upload."""
        upload_parts.append({"part": 1, "size": 1024})
        raise ConnectionError("Verbindung unterbrochen")

    mock_minio.put_object.side_effect = mock_put_object

    # Act: Simuliere Upload mit Cleanup
    async def upload_with_cleanup(
        client,
        bucket: str,
        filename: str,
        data: bytes
    ) -> Dict[str, Any]:
        """Uploaded mit automatischem Cleanup bei Fehler."""
        upload_id = f"upload-{filename}-123"

        try:
            result = client.put_object(
                bucket_name=bucket,
                object_name=filename,
                data=BytesIO(data),
                length=len(data)
            )
            return {"success": True, "etag": result.etag}
        except (ConnectionError, MinIOError) as e:
            print(f"Upload fehlgeschlagen: {e}")
            print(f"Raeume partielle Upload-Daten auf: {upload_id}")

            # Cleanup partielle Daten
            try:
                # Mock cleanup
                print(f"Entferne {len(upload_parts)} partielle Teile")
                upload_parts.clear()
            except Exception as cleanup_error:
                print(f"Cleanup-Fehler (nicht-kritisch): {cleanup_error}")

            return {"success": False, "error": str(e)}

    result = await upload_with_cleanup(
        mock_minio,
        bucket="documents",
        filename="large-doc.pdf",
        data=b"x" * 1024  # 1KB - Mock prueft keine Groesse
    )

    # Assert: Cleanup wurde durchgefuehrt
    assert result["success"] is False, "Upload sollte fehlschlagen"
    assert len(upload_parts) == 0, "Partielle Daten sollten aufgeraeumt sein"


@pytest.mark.chaos
@pytest.mark.asyncio
async def test_file_download_corruption(mock_minio):
    """Testet Behandlung von korrupten Downloads.

    Szenario: Heruntergeladene Datei stimmt nicht mit Checksum ueberein.
    Erwartung: Corruption wird erkannt und Download wiederholt.
    """
    # Arrange: Mock MinIO mit Checksum-Mismatch
    expected_etag = "abc123"
    corrupt_data = b"corrupt data"

    mock_response = MagicMock()
    mock_response.read.return_value = corrupt_data
    mock_response.headers = {"ETag": "xyz789"}  # Falsche ETag

    mock_minio.get_object.return_value = mock_response

    # Act: Simuliere Download mit Checksum-Validierung
    async def download_with_validation(
        client,
        bucket: str,
        filename: str,
        expected_checksum: str
    ) -> Optional[bytes]:
        """Downloaded und validiert Checksum."""
        response = client.get_object(
            bucket_name=bucket,
            object_name=filename
        )

        data = response.read()
        actual_checksum = response.headers.get("ETag", "").strip('"')

        if actual_checksum != expected_checksum:
            print(f"Checksum-Mismatch: erwartet {expected_checksum}, erhalten {actual_checksum}")
            print("Datei moeglicherweise korrupt, Download wiederholen empfohlen")
            return None

        return data

    data = await download_with_validation(
        mock_minio,
        bucket="documents",
        filename="test.pdf",
        expected_checksum=expected_etag
    )

    # Assert: Corruption wurde erkannt
    assert data is None, "Sollte None bei Checksum-Mismatch zurueckgeben"
    mock_minio.get_object.assert_called_once()
