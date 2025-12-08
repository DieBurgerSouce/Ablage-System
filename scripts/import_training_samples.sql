-- Import OCR Training Samples from CSV
COPY ocr_training_samples (
    id, file_path, file_hash, thumbnail_path, ground_truth_text,
    language, document_type, difficulty, has_umlauts, has_fraktur,
    has_tables, has_handwriting, has_stamps, has_signatures,
    status, umlaut_words, extracted_fields
) FROM '/var/lib/postgresql/migration_export.csv' WITH (FORMAT csv, QUOTE '"', NULL '');

-- Verify import
SELECT COUNT(*) as imported_count FROM ocr_training_samples;
