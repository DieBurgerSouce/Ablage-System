# -*- coding: utf-8 -*-
"""Regressionstest F-P2-007 (Perception-Audit 2026-07-12).

RAGBatchJob.job_type/.status (und Document.document_type) sind
String-Spalten: aus der DB geladene Zeilen liefern str. `.value` darauf
crashte /rag/jobs* und /inventory/goods-receipts/unprocessed-delivery-notes
mit HTTP 500, sobald eine einzige Zeile existierte. _enum_wert() serialisiert
beide Welten (str aus DB, Enum aus frischem Request-Code) tolerant.
"""
from enum import Enum

from app.api.v1.rag.jobs import _enum_wert


class _BeispielStatus(str, Enum):
    PENDING = "pending"
    FAILED = "failed"


def test_str_aus_db_bleibt_str():
    assert _enum_wert("failed") == "failed"
    assert _enum_wert("customer_card_sync") == "customer_card_sync"


def test_enum_wird_auf_value_reduziert():
    assert _enum_wert(_BeispielStatus.PENDING) == "pending"
    assert _enum_wert(_BeispielStatus.FAILED) == "failed"


def test_nicht_str_werte_werden_stringifiziert():
    # defensiv: kaputte Altdaten dürfen die Serialisierung nie crashen
    assert _enum_wert(42) == "42"
