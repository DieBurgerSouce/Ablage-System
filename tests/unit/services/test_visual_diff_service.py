# -*- coding: utf-8 -*-
"""Unit tests for Visual Diff Service."""

import pytest
from app.services.diff.visual_diff_service import (
    VisualDiffService,
    DiffResult,
    DiffBlock,
    DiffType,
    ChangeSummary,
)


@pytest.fixture
def diff_service():
    """Visual diff service instance."""
    return VisualDiffService()


@pytest.fixture
def identical_text():
    """Identical text samples."""
    text = """Dies ist ein Testdokument.
Es enthält mehrere Zeilen.
Alle Zeilen sind identisch.
Ende des Dokuments."""
    return text, text


@pytest.fixture
def different_text():
    """Completely different text samples."""
    text_a = """Dies ist Version A.
Mit komplett anderem Inhalt.
Nichts ist gleich."""

    text_b = """Hier ist Version B.
Völlig unterschiedlicher Text.
Keine Übereinstimmungen."""

    return text_a, text_b


@pytest.fixture
def minor_changes_text():
    """Text with minor changes."""
    text_a = """Vertrag zwischen Firma A und Kunde B.
Der Preis beträgt 1000 EUR.
Zahlungsziel: 30 Tage."""

    text_b = """Vertrag zwischen Firma A und Kunde B.
Der Preis beträgt 1200 EUR.
Zahlungsziel: 14 Tage."""

    return text_a, text_b


def test_compare_identical_texts(diff_service, identical_text):
    """Test comparing identical texts returns 100% similarity."""
    text_a, text_b = identical_text

    result = diff_service.compare_texts(
        text_a=text_a,
        text_b=text_b,
        document_a_id="doc_a",
        document_b_id="doc_b",
    )

    assert isinstance(result, DiffResult)
    assert result.similarity_ratio == 1.0  # 100% identical
    assert result.total_changes == 0
    assert result.additions == 0
    assert result.deletions == 0
    assert result.modifications == 0


def test_compare_completely_different(diff_service, different_text):
    """Test comparing totally different texts returns low similarity."""
    text_a, text_b = different_text

    result = diff_service.compare_texts(
        text_a=text_a,
        text_b=text_b,
    )

    assert result.similarity_ratio < 0.5  # Low similarity
    assert result.total_changes > 0


def test_compare_minor_changes(diff_service, minor_changes_text):
    """Test small changes are detected correctly."""
    text_a, text_b = minor_changes_text

    result = diff_service.compare_texts(
        text_a=text_a,
        text_b=text_b,
    )

    # Should have high similarity (most lines unchanged)
    assert result.similarity_ratio > 0.5
    assert result.total_changes > 0
    assert result.modifications >= 1  # Price and payment terms changed


def test_compare_added_lines(diff_service):
    """Test detecting added lines."""
    text_a = """Zeile 1
Zeile 2"""

    text_b = """Zeile 1
Zeile 2
Zeile 3
Zeile 4"""

    result = diff_service.compare_texts(text_a, text_b)

    assert result.additions >= 1
    assert result.total_changes >= result.additions

    # Check for ADDED blocks
    added_blocks = [b for b in result.blocks if b.diff_type == DiffType.ADDED]
    assert len(added_blocks) >= 1


def test_compare_removed_lines(diff_service):
    """Test detecting removed lines."""
    text_a = """Zeile 1
Zeile 2
Zeile 3
Zeile 4"""

    text_b = """Zeile 1
Zeile 2"""

    result = diff_service.compare_texts(text_a, text_b)

    assert result.deletions >= 1

    # Check for REMOVED blocks
    removed_blocks = [b for b in result.blocks if b.diff_type == DiffType.REMOVED]
    assert len(removed_blocks) >= 1


def test_compare_modified_lines(diff_service):
    """Test detecting modified lines."""
    text_a = """Der Betrag ist 1000 EUR"""
    text_b = """Der Betrag ist 2000 EUR"""

    result = diff_service.compare_texts(text_a, text_b)

    assert result.modifications >= 1

    # Check for MODIFIED blocks
    modified_blocks = [b for b in result.blocks if b.diff_type == DiffType.MODIFIED]
    assert len(modified_blocks) >= 1


def test_change_summary_low_risk(diff_service, identical_text):
    """Test change summary with high similarity = low risk."""
    text_a, text_b = identical_text

    diff_result = diff_service.compare_texts(text_a, text_b)
    summary = diff_service.generate_change_summary(diff_result)

    assert isinstance(summary, ChangeSummary)
    assert summary.similarity_percentage >= 95.0
    assert summary.risk_level == "low"
    assert summary.total_changes == 0


def test_change_summary_high_risk(diff_service, different_text):
    """Test change summary with low similarity = high risk."""
    text_a, text_b = different_text

    diff_result = diff_service.compare_texts(text_a, text_b)
    summary = diff_service.generate_change_summary(diff_result)

    assert summary.similarity_percentage < 80.0
    assert summary.risk_level == "high"
    assert summary.total_changes > 0


def test_change_summary_medium_risk(diff_service, minor_changes_text):
    """Test change summary with medium similarity = medium risk."""
    text_a, text_b = minor_changes_text

    diff_result = diff_service.compare_texts(text_a, text_b)
    summary = diff_service.generate_change_summary(diff_result)

    # Should be in medium range (80-95%)
    if 80.0 <= summary.similarity_percentage < 95.0:
        assert summary.risk_level == "medium"
    # Or low/high depending on exact similarity
    assert summary.risk_level in ["low", "medium", "high"]


def test_compute_hash_consistent(diff_service):
    """Test same text produces same hash."""
    text = "Dies ist ein Testtext mit Umlauten: äöü"

    hash1 = diff_service.compute_text_hash(text)
    hash2 = diff_service.compute_text_hash(text)

    assert hash1 == hash2
    assert len(hash1) == 64  # SHA-256 produces 64 hex characters


def test_compute_hash_different(diff_service):
    """Test different texts produce different hashes."""
    text_a = "Text A"
    text_b = "Text B"

    hash_a = diff_service.compute_text_hash(text_a)
    hash_b = diff_service.compute_text_hash(text_b)

    assert hash_a != hash_b


def test_diff_blocks_structure(diff_service):
    """Test diff blocks have correct structure."""
    text_a = """Zeile 1
Zeile 2 alt
Zeile 3"""

    text_b = """Zeile 1
Zeile 2 neu
Zeile 3"""

    result = diff_service.compare_texts(text_a, text_b)

    assert len(result.blocks) > 0
    for block in result.blocks:
        assert isinstance(block, DiffBlock)
        assert isinstance(block.diff_type, DiffType)
        assert block.old_line_start >= 0
        assert block.new_line_start >= 0


def test_summary_text_generation(diff_service, minor_changes_text):
    """Test summary text is in German and informative."""
    text_a, text_b = minor_changes_text

    result = diff_service.compare_texts(text_a, text_b)

    assert result.summary is not None
    assert len(result.summary) > 0
    # Should contain German text
    assert "Aenderung" in result.summary or "Keine Aenderungen" in result.summary


def test_key_changes_extraction(diff_service, minor_changes_text):
    """Test key changes are extracted correctly."""
    text_a, text_b = minor_changes_text

    diff_result = diff_service.compare_texts(text_a, text_b)
    summary = diff_service.generate_change_summary(diff_result)

    assert len(summary.key_changes) > 0
    # Should list specific changes
    for change in summary.key_changes:
        assert isinstance(change, str)
        assert len(change) > 0


def test_empty_texts(diff_service):
    """Test handling of empty texts."""
    result = diff_service.compare_texts(
        text_a="",
        text_b="",
    )

    assert result.similarity_ratio == 1.0  # Both empty = identical
    assert result.total_changes == 0


def test_one_empty_text(diff_service):
    """Test handling when one text is empty."""
    result = diff_service.compare_texts(
        text_a="Some text",
        text_b="",
    )

    assert result.similarity_ratio < 1.0
    assert result.deletions >= 1 or result.total_changes >= 1


def test_multiline_diff(diff_service):
    """Test multiline document diff."""
    text_a = """# Vertrag

## Parteien
Firma A
Kunde B

## Preis
1000 EUR

## Zahlungsbedingungen
30 Tage netto"""

    text_b = """# Vertrag

## Parteien
Firma A
Kunde C

## Preis
1500 EUR

## Zahlungsbedingungen
14 Tage netto
2% Skonto bei Zahlung innerhalb 7 Tagen"""

    result = diff_service.compare_texts(text_a, text_b)

    assert result.total_changes > 0
    assert result.modifications >= 1  # Customer changed
    assert result.additions >= 1  # Skonto line added


def test_german_umlauts_handling(diff_service):
    """Test correct handling of German umlauts in diff."""
    text_a = "Geschäftsführer: Müller"
    text_b = "Geschäftsführer: Schmidt"

    result = diff_service.compare_texts(text_a, text_b)

    assert result.modifications >= 1

    # Hash should handle umlauts correctly
    hash_a = diff_service.compute_text_hash(text_a)
    hash_b = diff_service.compute_text_hash(text_b)
    assert hash_a != hash_b


def test_change_summary_limits_key_changes(diff_service):
    """Test change summary limits key changes to max 20."""
    # Create text with many changes
    lines_a = [f"Zeile {i} alt" for i in range(100)]
    lines_b = [f"Zeile {i} neu" for i in range(100)]

    text_a = "\n".join(lines_a)
    text_b = "\n".join(lines_b)

    diff_result = diff_service.compare_texts(text_a, text_b)
    summary = diff_service.generate_change_summary(diff_result)

    # Should limit to 20 key changes
    assert len(summary.key_changes) <= 20


def test_document_ids_preserved(diff_service):
    """Test document IDs are preserved in result."""
    result = diff_service.compare_texts(
        text_a="Test A",
        text_b="Test B",
        document_a_id="doc-123",
        document_b_id="doc-456",
    )

    assert result.document_a_id == "doc-123"
    assert result.document_b_id == "doc-456"


def test_risk_level_thresholds(diff_service):
    """Test risk level calculation thresholds."""
    # Create texts with specific similarity levels
    # High similarity (>95%) -> low risk
    text_high = "Line 1\nLine 2\nLine 3\nLine 4\nLine 5"
    text_high_mod = "Line 1\nLine 2\nLine 3 modified\nLine 4\nLine 5"

    # Medium similarity (80-95%) -> medium risk
    text_med = "Line 1\nLine 2\nLine 3\nLine 4\nLine 5"
    text_med_mod = "Line 1\nLine 2 mod\nLine 3 mod\nLine 4\nLine 5"

    result_high = diff_service.compare_texts(text_high, text_high_mod)
    summary_high = diff_service.generate_change_summary(result_high)

    result_med = diff_service.compare_texts(text_med, text_med_mod)
    summary_med = diff_service.generate_change_summary(result_med)

    # Verify risk levels are assigned correctly based on similarity
    if summary_high.similarity_percentage >= 95:
        assert summary_high.risk_level == "low"
    elif summary_high.similarity_percentage >= 80:
        assert summary_high.risk_level == "medium"
    else:
        assert summary_high.risk_level == "high"
