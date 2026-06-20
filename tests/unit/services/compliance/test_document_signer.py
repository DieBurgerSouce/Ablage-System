# -*- coding: utf-8 -*-
"""Tests fuer den internen GoBD-DocumentSigner (RSA-PSS, on-premises)."""
import base64

from app.services.compliance.document_signer import DocumentSigner, SIGNATURE_ALG


def test_sign_then_verify_roundtrip(tmp_path):
    signer = DocumentSigner(tmp_path)
    data = b"%PDF-1.4 Verfahrensdokumentation v1.0.0 ..."
    res = signer.sign(data)
    assert res["alg"] == SIGNATURE_ALG
    assert res["cert_serial"]
    assert "BEGIN CERTIFICATE" in res["cert_pem"]
    base64.b64decode(res["signature"])  # gueltiges base64
    assert signer.verify(data, res["signature"]) is True


def test_tampered_data_fails_verification(tmp_path):
    signer = DocumentSigner(tmp_path)
    data = b"original content"
    res = signer.sign(data)
    # Manipulierte Bytes -> Signaturpruefung schlaegt fehl
    assert signer.verify(b"tampered content", res["signature"]) is False
    # Original bleibt gueltig
    assert signer.verify(data, res["signature"]) is True


def test_key_persists_across_instances(tmp_path):
    """Eine zweite Signer-Instanz auf demselben Verzeichnis nutzt denselben Schluessel
    -> Alt-Signaturen bleiben nach Neustart verifizierbar (kein Re-Generieren)."""
    s1 = DocumentSigner(tmp_path)
    data = b"persisted doc"
    res = s1.sign(data)
    s2 = DocumentSigner(tmp_path)  # laedt vorhandenen Schluessel/Zertifikat
    assert s2.verify(data, res["signature"]) is True
    assert s2.sign(data)["cert_serial"] == res["cert_serial"]  # selbes Zertifikat


def test_render_pdf_produces_signed_verifiable_pdf(tmp_path):
    """Render+Sign-Kern end-to-end (ohne DB/MinIO): das gerenderte PDF ist gueltig
    und die interne Signatur darueber verifiziert; Manipulation faellt auf."""
    from types import SimpleNamespace
    from app.services.procedure_doc_service import ProcedureDocService

    version = SimpleNamespace(
        version="1.0.0",
        generated_at="2026-06-20T00:00:00+00:00",
        content_hash="a" * 64,
        content={
            "Verarbeitung": {"OCR-Backend": "DeepSeek", "Schritte": ["Upload", "OCR", "Ablage"]},
            "Sicherheit": "JWT httpOnly + CSRF",
            "Aufbewahrung": "10 Jahre (GoBD)",
        },
    )
    pdf = ProcedureDocService()._render_pdf(version)
    assert pdf[:5] == b"%PDF-"
    assert len(pdf) > 800

    signer = DocumentSigner(tmp_path)
    sig = signer.sign(pdf)
    assert signer.verify(pdf, sig["signature"]) is True
    assert signer.verify(pdf + b"x", sig["signature"]) is False  # Manipulation
