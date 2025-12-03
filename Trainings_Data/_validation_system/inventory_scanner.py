#!/usr/bin/env python3
"""
ABLAGE-SYSTEM: Training Data Inventory Scanner
Scannt alle Dokumente und erstellt eine SQLite-Datenbank mit Metadaten + Thumbnails
"""

import os
import sys
import sqlite3
import json
import hashlib
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import argparse

# PIL für Bildverarbeitung
try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("WARNING: Pillow not installed. Install with: pip install Pillow")

# ============================================================================
# CONFIGURATION
# ============================================================================

DEFAULT_BASE_PATH = r"C:\Users\benfi\Ablage_System\Trainings_Data"
DEFAULT_DB_PATH = r"C:\Users\benfi\Ablage_System\Trainings_Data\_validation_system\training_data.db"
THUMBNAIL_DIR = r"C:\Users\benfi\Ablage_System\Trainings_Data\_validation_system\thumbnails"
THUMBNAIL_SIZE = (400, 566)  # A4 ratio at reasonable size

# ============================================================================
# DATABASE SETUP
# ============================================================================

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT NOT NULL UNIQUE,
    file_name TEXT NOT NULL,
    folder_name TEXT NOT NULL,
    file_size_bytes INTEGER,
    file_format TEXT,
    width_px INTEGER,
    height_px INTEGER,
    dpi INTEGER,
    page_count INTEGER DEFAULT 1,
    color_mode TEXT,
    file_hash TEXT,
    thumbnail_path TEXT,
    doc_type TEXT,
    doc_language TEXT,
    doc_company TEXT,
    doc_date DATE,
    has_handwriting BOOLEAN DEFAULT FALSE,
    has_stamps BOOLEAN DEFAULT FALSE,
    has_signatures BOOLEAN DEFAULT FALSE,
    scan_quality TEXT,
    is_in_sample_set BOOLEAN DEFAULT FALSE,
    ground_truth_status TEXT DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ground_truth (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL UNIQUE,
    full_text TEXT,
    extracted_invoice_number TEXT,
    extracted_date TEXT,
    extracted_total_amount TEXT,
    extracted_vat_amount TEXT,
    extracted_sender_name TEXT,
    extracted_recipient_name TEXT,
    contains_umlauts BOOLEAN DEFAULT FALSE,
    umlaut_words TEXT,
    annotated_by TEXT DEFAULT 'manual',
    annotation_notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (document_id) REFERENCES documents(id)
);

CREATE TABLE IF NOT EXISTS ocr_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL,
    backend_name TEXT NOT NULL,
    backend_version TEXT,
    raw_text TEXT,
    structured_output TEXT,
    confidence_score REAL,
    processing_time_ms INTEGER,
    character_error_rate REAL,
    word_error_rate REAL,
    umlaut_accuracy REAL,
    error_details TEXT,
    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (document_id) REFERENCES documents(id)
);

CREATE INDEX IF NOT EXISTS idx_documents_folder ON documents(folder_name);
CREATE INDEX IF NOT EXISTS idx_documents_type ON documents(doc_type);
CREATE INDEX IF NOT EXISTS idx_documents_sample ON documents(is_in_sample_set);
CREATE INDEX IF NOT EXISTS idx_ground_truth_doc ON ground_truth(document_id);
CREATE INDEX IF NOT EXISTS idx_ocr_results_doc ON ocr_results(document_id);
CREATE INDEX IF NOT EXISTS idx_ocr_results_backend ON ocr_results(backend_name);
"""

def init_database(db_path):
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    return conn


# ============================================================================
# FILE SCANNING
# ============================================================================

def get_file_hash(file_path, block_size=65536):
    hasher = hashlib.md5()
    with open(file_path, 'rb') as f:
        for block in iter(lambda: f.read(block_size), b''):
            hasher.update(block)
    return hasher.hexdigest()


def extract_image_metadata(file_path):
    metadata = {'width_px': None, 'height_px': None, 'dpi': None, 'page_count': 1, 'color_mode': None}
    if not PIL_AVAILABLE:
        return metadata
    try:
        with Image.open(file_path) as img:
            metadata['width_px'] = img.width
            metadata['height_px'] = img.height
            metadata['color_mode'] = img.mode
            if 'dpi' in img.info:
                dpi = img.info['dpi']
                metadata['dpi'] = int(dpi[0]) if isinstance(dpi, tuple) else int(dpi)
            try:
                page_count = 0
                while True:
                    img.seek(page_count)
                    page_count += 1
            except EOFError:
                metadata['page_count'] = page_count
    except Exception as e:
        print(f"  Warning: Could not extract metadata from {file_path}: {e}")
    return metadata


def create_thumbnail(file_path, thumbnail_dir, file_hash):
    if not PIL_AVAILABLE:
        return None
    thumbnail_path = os.path.join(thumbnail_dir, f"{file_hash}.png")
    if os.path.exists(thumbnail_path):
        return thumbnail_path
    try:
        with Image.open(file_path) as img:
            if img.mode == '1':
                img = img.convert('L')
            if img.mode in ('RGBA', 'LA', 'P', 'L'):
                img = img.convert('RGB')
            img.thumbnail(THUMBNAIL_SIZE, Image.Resampling.LANCZOS)
            img.save(thumbnail_path, 'PNG', optimize=True)
        return thumbnail_path
    except Exception as e:
        print(f"  Warning: Could not create thumbnail for {file_path}: {e}")
        return None


def scan_document(file_path, base_path, thumbnail_dir):
    file_name = os.path.basename(file_path)
    folder_name = os.path.basename(os.path.dirname(file_path))
    file_ext = os.path.splitext(file_name)[1].upper().replace('.', '')
    stat = os.stat(file_path)
    file_hash = get_file_hash(file_path)
    img_meta = extract_image_metadata(file_path)
    thumbnail_path = create_thumbnail(file_path, thumbnail_dir, file_hash)
    return {
        'file_path': file_path, 'file_name': file_name, 'folder_name': folder_name,
        'file_size_bytes': stat.st_size, 'file_format': file_ext,
        'width_px': img_meta['width_px'], 'height_px': img_meta['height_px'],
        'dpi': img_meta['dpi'], 'page_count': img_meta['page_count'],
        'color_mode': img_meta['color_mode'], 'file_hash': file_hash,
        'thumbnail_path': thumbnail_path
    }


def scan_all_documents(base_path, db_path, thumbnail_dir, max_workers=4):
    os.makedirs(thumbnail_dir, exist_ok=True)
    conn = init_database(db_path)
    cursor = conn.cursor()
    
    files = []
    for root, dirs, filenames in os.walk(base_path):
        if '_validation_system' in root:
            continue
        for filename in filenames:
            if filename.upper().endswith(('.TIF', '.TIFF', '.PDF')):
                files.append(os.path.join(root, filename))
    
    print(f"Found {len(files)} documents to scan")
    stats = {'total': len(files), 'processed': 0, 'errors': 0, 'by_format': {}, 'by_folder': {}}
    
    for i, file_path in enumerate(files):
        try:
            doc_data = scan_document(file_path, base_path, thumbnail_dir)
            cursor.execute("""
                INSERT OR REPLACE INTO documents 
                (file_path, file_name, folder_name, file_size_bytes, file_format,
                 width_px, height_px, dpi, page_count, color_mode, file_hash, thumbnail_path)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (doc_data['file_path'], doc_data['file_name'], doc_data['folder_name'],
                  doc_data['file_size_bytes'], doc_data['file_format'],
                  doc_data['width_px'], doc_data['height_px'], doc_data['dpi'],
                  doc_data['page_count'], doc_data['color_mode'],
                  doc_data['file_hash'], doc_data['thumbnail_path']))
            
            stats['processed'] += 1
            fmt = doc_data['file_format']
            folder = doc_data['folder_name']
            stats['by_format'][fmt] = stats['by_format'].get(fmt, 0) + 1
            stats['by_folder'][folder] = stats['by_folder'].get(folder, 0) + 1
            
            if (i + 1) % 100 == 0:
                print(f"  Progress: {i + 1}/{len(files)} ({(i+1)*100//len(files)}%)")
                conn.commit()
        except Exception as e:
            print(f"  Error processing {file_path}: {e}")
            stats['errors'] += 1
    
    conn.commit()
    conn.close()
    return stats


# ============================================================================
# SAMPLE SET SELECTION
# ============================================================================

def select_sample_set(db_path, sample_size=200):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("UPDATE documents SET is_in_sample_set = FALSE")
    cursor.execute("SELECT folder_name, COUNT(*) as cnt FROM documents GROUP BY folder_name")
    folders = cursor.fetchall()
    total_docs = sum(f[1] for f in folders)
    
    for folder_name, count in folders:
        folder_sample = max(1, int(sample_size * count / total_docs))
        cursor.execute("""
            UPDATE documents SET is_in_sample_set = TRUE 
            WHERE id IN (SELECT id FROM documents WHERE folder_name = ? ORDER BY RANDOM() LIMIT ?)
        """, (folder_name, folder_sample))
    
    conn.commit()
    cursor.execute("SELECT COUNT(*) FROM documents WHERE is_in_sample_set = TRUE")
    actual_sample = cursor.fetchone()[0]
    conn.close()
    return actual_sample


def generate_report(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    report = []
    report.append("=" * 70)
    report.append("ABLAGE-SYSTEM: Training Data Inventory Report")
    report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append("=" * 70)
    
    cursor.execute("SELECT COUNT(*) FROM documents")
    total = cursor.fetchone()[0]
    report.append(f"\nTotal Documents: {total:,}")
    
    cursor.execute("SELECT SUM(file_size_bytes) FROM documents")
    total_size = cursor.fetchone()[0] or 0
    report.append(f"Total Size: {total_size / (1024*1024):.2f} MB")
    
    report.append("\nBy Format:")
    cursor.execute("SELECT file_format, COUNT(*), SUM(file_size_bytes) FROM documents GROUP BY file_format")
    for fmt, cnt, size in cursor.fetchall():
        report.append(f"  {fmt}: {cnt:,} files ({size/(1024*1024):.2f} MB)")
    
    report.append("\nBy Folder:")
    cursor.execute("SELECT folder_name, COUNT(*) FROM documents GROUP BY folder_name ORDER BY folder_name")
    for folder, cnt in cursor.fetchall():
        report.append(f"  {folder}: {cnt:,} files")
    
    cursor.execute("SELECT COUNT(*) FROM documents WHERE is_in_sample_set = TRUE")
    sample_count = cursor.fetchone()[0]
    report.append(f"\nSample Set Size: {sample_count} documents")
    
    conn.close()
    return "\n".join(report)


# ============================================================================
# MAIN
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description='Scan training data documents')
    parser.add_argument('--base-path', default=DEFAULT_BASE_PATH, help='Base path to scan')
    parser.add_argument('--db-path', default=DEFAULT_DB_PATH, help='SQLite database path')
    parser.add_argument('--thumbnail-dir', default=THUMBNAIL_DIR, help='Directory for thumbnails')
    parser.add_argument('--sample-size', type=int, default=200, help='Number of documents in sample set')
    parser.add_argument('--skip-scan', action='store_true', help='Skip scanning, only select sample')
    parser.add_argument('--report-only', action='store_true', help='Only generate report')
    
    args = parser.parse_args()
    
    print("=" * 70)
    print("ABLAGE-SYSTEM: Training Data Inventory Scanner")
    print("=" * 70)
    print()
    
    if args.report_only:
        print(generate_report(args.db_path))
        return
    
    if not args.skip_scan:
        print(f"Scanning: {args.base_path}")
        print(f"Database: {args.db_path}")
        print(f"Thumbnails: {args.thumbnail_dir}")
        print()
        
        stats = scan_all_documents(args.base_path, args.db_path, args.thumbnail_dir)
        
        print()
        print(f"Scan Complete!")
        print(f"  Processed: {stats['processed']}")
        print(f"  Errors: {stats['errors']}")
        print(f"  By Format: {stats['by_format']}")
        print()
    
    print(f"Selecting sample set ({args.sample_size} documents)...")
    sample_count = select_sample_set(args.db_path, args.sample_size)
    print(f"  Selected {sample_count} documents for validation")
    print()
    
    print(generate_report(args.db_path))


if __name__ == '__main__':
    main()
