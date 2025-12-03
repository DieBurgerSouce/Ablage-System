#!/usr/bin/env python3
"""
ABLAGE-SYSTEM: Training Data Validation Web UI
Flask-basierte Web-Oberfläche für Ground Truth Annotation und Accuracy Vergleich
"""

import os
import sqlite3
from datetime import datetime
from flask import Flask, render_template_string, request, jsonify, send_file, redirect

# ============================================================================
# CONFIGURATION
# ============================================================================

DB_PATH = r"C:\Users\benfi\Ablage_System\Trainings_Data\_validation_system\training_data.db"
THUMBNAIL_DIR = r"C:\Users\benfi\Ablage_System\Trainings_Data\_validation_system\thumbnails"
HOST = "127.0.0.1"
PORT = 5000

app = Flask(__name__)
app.secret_key = 'ablage-system-validation-2024'

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def dict_from_row(row):
    return dict(zip(row.keys(), row)) if row else None


# ============================================================================
# HTML TEMPLATES
# ============================================================================

BASE_CSS = """
:root { --bg-dark: #0a0a0a; --bg-card: #141414; --bg-hover: #1a1a1a; --text-primary: #fff; --text-secondary: #888; --accent: #3b82f6; --success: #22c55e; --warning: #f59e0b; --error: #ef4444; --border: #2a2a2a; }
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Inter', -apple-system, sans-serif; background: var(--bg-dark); color: var(--text-primary); min-height: 100vh; }
.header { background: var(--bg-card); border-bottom: 1px solid var(--border); padding: 1rem 2rem; display: flex; align-items: center; justify-content: space-between; }
.header h1 { font-size: 1.5rem; font-weight: 600; }
.nav { display: flex; gap: 1rem; }
.nav a { color: var(--text-secondary); text-decoration: none; padding: 0.5rem 1rem; border-radius: 6px; transition: all 0.2s; }
.nav a:hover, .nav a.active { color: var(--text-primary); background: var(--bg-hover); }
.container { max-width: 1600px; margin: 0 auto; padding: 2rem; }
.stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; margin-bottom: 2rem; }
.stat-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 12px; padding: 1.5rem; }
.stat-card .label { color: var(--text-secondary); font-size: 0.875rem; margin-bottom: 0.5rem; }
.stat-card .value { font-size: 2rem; font-weight: 700; }
.stat-card .value.success { color: var(--success); }
.stat-card .value.warning { color: var(--warning); }
.doc-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 1.5rem; }
.doc-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 12px; overflow: hidden; transition: all 0.2s; cursor: pointer; }
.doc-card:hover { border-color: var(--accent); transform: translateY(-2px); }
.doc-card img { width: 100%; height: 200px; object-fit: contain; background: #1a1a1a; }
.doc-card .info { padding: 1rem; }
.doc-card .filename { font-weight: 600; margin-bottom: 0.5rem; word-break: break-all; }
.doc-card .meta { color: var(--text-secondary); font-size: 0.875rem; }
.status { display: inline-block; padding: 0.25rem 0.5rem; border-radius: 4px; font-size: 0.75rem; font-weight: 600; margin-top: 0.5rem; }
.status.pending { background: var(--warning); color: black; }
.status.completed { background: var(--success); color: black; }
.status.in_progress { background: var(--accent); color: white; }
.comparison-view { display: grid; grid-template-columns: 1fr 1fr; gap: 2rem; min-height: 600px; }
.panel { background: var(--bg-card); border: 1px solid var(--border); border-radius: 12px; overflow: hidden; display: flex; flex-direction: column; }
.panel-header { padding: 1rem; border-bottom: 1px solid var(--border); font-weight: 600; }
.panel-content { flex: 1; overflow: auto; padding: 1rem; }
.text-area { width: 100%; min-height: 400px; background: var(--bg-dark); border: 1px solid var(--border); border-radius: 8px; color: var(--text-primary); padding: 1rem; font-family: 'Consolas', monospace; font-size: 0.9rem; resize: vertical; }
.btn { display: inline-flex; align-items: center; gap: 0.5rem; padding: 0.75rem 1.5rem; border-radius: 8px; font-weight: 600; cursor: pointer; border: none; transition: all 0.2s; text-decoration: none; }
.btn-primary { background: var(--accent); color: white; }
.btn-primary:hover { background: #2563eb; }
.btn-success { background: var(--success); color: black; }
.btn-outline { background: transparent; border: 1px solid var(--border); color: var(--text-primary); }
.btn-outline:hover { background: var(--bg-hover); }
.actions { display: flex; gap: 1rem; margin-top: 1rem; }
.filter-bar { display: flex; gap: 1rem; margin-bottom: 2rem; flex-wrap: wrap; }
.filter-bar select, .filter-bar input { background: var(--bg-card); border: 1px solid var(--border); color: var(--text-primary); padding: 0.75rem 1rem; border-radius: 8px; min-width: 150px; }
.pagination { display: flex; justify-content: center; gap: 0.5rem; margin-top: 2rem; }
.pagination a, .pagination span { padding: 0.5rem 1rem; background: var(--bg-card); border: 1px solid var(--border); border-radius: 6px; color: var(--text-primary); text-decoration: none; }
.pagination a:hover, .pagination a.active { background: var(--accent); border-color: var(--accent); }
.input-field { width: 100%; padding: 0.5rem; background: var(--bg-dark); border: 1px solid var(--border); border-radius: 6px; color: white; margin-top: 0.25rem; }
.field-label { color: var(--text-secondary); font-size: 0.875rem; }
.meta-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 1rem; color: var(--text-secondary); margin-top: 1rem; padding: 1rem; background: var(--bg-card); border-radius: 12px; }
"""


BASE_TEMPLATE = '''<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Ablage-System: Training Validation</title>
    <style>''' + BASE_CSS + '''</style>
</head>
<body>
    <header class="header">
        <h1>📄 Ablage-System: Training Validation</h1>
        <nav class="nav">
            <a href="/" class="{dashboard_active}">Dashboard</a>
            <a href="/browse" class="{browse_active}">Browse</a>
            <a href="/sample" class="{sample_active}">Sample Set</a>
        </nav>
    </header>
    <main class="container">{content}</main>
</body>
</html>'''

def render_page(content, active='dashboard'):
    return BASE_TEMPLATE.format(
        content=content,
        dashboard_active='active' if active == 'dashboard' else '',
        browse_active='active' if active == 'browse' else '',
        sample_active='active' if active == 'sample' else ''
    )


# ============================================================================
# ROUTES
# ============================================================================

@app.route('/')
def dashboard():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM documents")
    total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM documents WHERE is_in_sample_set = TRUE")
    sample = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM documents WHERE is_in_sample_set = TRUE AND ground_truth_status = 'completed'")
    completed = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM documents WHERE is_in_sample_set = TRUE AND ground_truth_status = 'pending'")
    pending = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM documents WHERE file_format = 'TIF'")
    tif = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM documents WHERE file_format = 'PDF'")
    pdf = cur.fetchone()[0]
    cur.execute("SELECT folder_name, COUNT(*) as cnt FROM documents GROUP BY folder_name ORDER BY folder_name")
    folders = cur.fetchall()
    conn.close()
    
    folder_cards = ''.join([f'<div class="stat-card"><div class="label">{f[0]}</div><div class="value">{f[1]}</div></div>' for f in folders])
    
    content = f'''
    <h2 style="margin-bottom: 1.5rem;">📊 Inventar Übersicht</h2>
    <div class="stats-grid">
        <div class="stat-card"><div class="label">Dokumente Gesamt</div><div class="value">{total:,}</div></div>
        <div class="stat-card"><div class="label">Sample Set</div><div class="value" style="color: #3b82f6;">{sample}</div></div>
        <div class="stat-card"><div class="label">Ground Truth Fertig</div><div class="value success">{completed}</div></div>
        <div class="stat-card"><div class="label">Ausstehend</div><div class="value warning">{pending}</div></div>
        <div class="stat-card"><div class="label">TIF Dateien</div><div class="value">{tif:,}</div></div>
        <div class="stat-card"><div class="label">PDF Dateien</div><div class="value">{pdf}</div></div>
    </div>
    <h3 style="margin-bottom: 1rem;">📁 Nach Ordner</h3>
    <div class="stats-grid">{folder_cards}</div>
    <div class="actions" style="margin-top: 2rem;">
        <a href="/sample" class="btn btn-primary">→ Zum Sample Set</a>
        <a href="/browse" class="btn btn-outline">Alle durchsuchen</a>
    </div>
    '''
    return render_page(content, 'dashboard')


@app.route('/browse')
def browse():
    page = int(request.args.get('page', 1))
    per_page = 24
    folder = request.args.get('folder', '')
    format_filter = request.args.get('format', '')
    
    conn = get_db()
    cur = conn.cursor()
    
    query = "SELECT * FROM documents WHERE 1=1"
    params = []
    if folder:
        query += " AND folder_name = ?"
        params.append(folder)
    if format_filter:
        query += " AND file_format = ?"
        params.append(format_filter)
    
    count_query = query.replace("SELECT *", "SELECT COUNT(*)")
    cur.execute(count_query, params)
    total = cur.fetchone()[0]
    total_pages = max(1, (total + per_page - 1) // per_page)
    
    query += f" ORDER BY folder_name, file_name LIMIT {per_page} OFFSET {(page-1)*per_page}"
    cur.execute(query, params)
    documents = [dict_from_row(r) for r in cur.fetchall()]
    
    cur.execute("SELECT DISTINCT folder_name FROM documents ORDER BY folder_name")
    folders = [r[0] for r in cur.fetchall()]
    conn.close()
    
    folder_options = ''.join([f'<option value="{f}" {"selected" if f == folder else ""}>{f}</option>' for f in folders])
    
    doc_cards = ''
    for doc in documents:
        thumb = f'<img src="/thumbnail/{doc["id"]}" alt="{doc["file_name"]}">' if doc.get('thumbnail_path') else '<div style="height: 200px; display: flex; align-items: center; justify-content: center; background: #1a1a1a;"><span style="font-size: 3rem;">📄</span></div>'
        status_badge = f'<span class="status {doc["ground_truth_status"]}">{doc["ground_truth_status"]}</span>' if doc.get('is_in_sample_set') else ''
        doc_cards += f'''<div class="doc-card" onclick="window.location='/document/{doc["id"]}'">
            {thumb}
            <div class="info">
                <div class="filename">{doc["file_name"]}</div>
                <div class="meta">{doc["folder_name"]} · {doc["file_size_bytes"]/1024:.1f} KB</div>
                {status_badge}
            </div>
        </div>'''
    
    prev_link = f'<a href="?page={page-1}&folder={folder}&format={format_filter}">← Zurück</a>' if page > 1 else ''
    next_link = f'<a href="?page={page+1}&folder={folder}&format={format_filter}">Weiter →</a>' if page < total_pages else ''
    
    content = f'''
    <h2 style="margin-bottom: 1.5rem;">📁 Dokumente durchsuchen</h2>
    <div class="filter-bar">
        <select onchange="window.location=`/browse?folder=${{this.value}}&format={format_filter}`">
            <option value="">Alle Ordner</option>
            {folder_options}
        </select>
        <select onchange="window.location=`/browse?folder={folder}&format=${{this.value}}`">
            <option value="">Alle Formate</option>
            <option value="TIF" {"selected" if format_filter == "TIF" else ""}>TIF</option>
            <option value="PDF" {"selected" if format_filter == "PDF" else ""}>PDF</option>
        </select>
    </div>
    <div class="doc-grid">{doc_cards}</div>
    <div class="pagination">{prev_link}<span>Seite {page} von {total_pages}</span>{next_link}</div>
    '''
    return render_page(content, 'browse')


@app.route('/sample')
def sample_set():
    status = request.args.get('status', '')
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("SELECT COUNT(*) FROM documents WHERE is_in_sample_set = TRUE")
    total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM documents WHERE is_in_sample_set = TRUE AND ground_truth_status = 'completed'")
    completed = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM documents WHERE is_in_sample_set = TRUE AND ground_truth_status = 'in_progress'")
    in_progress = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM documents WHERE is_in_sample_set = TRUE AND ground_truth_status = 'pending'")
    pending = cur.fetchone()[0]
    
    query = "SELECT * FROM documents WHERE is_in_sample_set = TRUE"
    if status:
        query += f" AND ground_truth_status = '{status}'"
    query += " ORDER BY ground_truth_status DESC, folder_name, file_name"
    cur.execute(query)
    documents = [dict_from_row(r) for r in cur.fetchall()]
    conn.close()
    
    doc_cards = ''
    for doc in documents:
        thumb = f'<img src="/thumbnail/{doc["id"]}" alt="{doc["file_name"]}">' if doc.get('thumbnail_path') else '<div style="height: 200px; display: flex; align-items: center; justify-content: center; background: #1a1a1a;"><span style="font-size: 3rem;">📄</span></div>'
        doc_cards += f'''<div class="doc-card" onclick="window.location='/document/{doc["id"]}'">
            {thumb}
            <div class="info">
                <div class="filename">{doc["file_name"]}</div>
                <div class="meta">{doc["folder_name"]}</div>
                <span class="status {doc["ground_truth_status"]}">{doc["ground_truth_status"]}</span>
            </div>
        </div>'''
    
    content = f'''
    <h2 style="margin-bottom: 1.5rem;">🎯 Sample Set für Validation</h2>
    <div class="stats-grid" style="margin-bottom: 2rem;">
        <div class="stat-card"><div class="label">Im Sample Set</div><div class="value">{total}</div></div>
        <div class="stat-card"><div class="label">Fertig annotiert</div><div class="value success">{completed}</div></div>
        <div class="stat-card"><div class="label">In Bearbeitung</div><div class="value" style="color: #3b82f6;">{in_progress}</div></div>
        <div class="stat-card"><div class="label">Ausstehend</div><div class="value warning">{pending}</div></div>
    </div>
    <div class="filter-bar">
        <select onchange="window.location=`/sample?status=${{this.value}}`">
            <option value="">Alle Status</option>
            <option value="pending" {"selected" if status == "pending" else ""}>Ausstehend</option>
            <option value="in_progress" {"selected" if status == "in_progress" else ""}>In Bearbeitung</option>
            <option value="completed" {"selected" if status == "completed" else ""}>Fertig</option>
        </select>
    </div>
    <div class="doc-grid">{doc_cards}</div>
    '''
    return render_page(content, 'sample')


@app.route('/document/<int:doc_id>')
def document(doc_id):
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("SELECT * FROM documents WHERE id = ?", (doc_id,))
    doc = dict_from_row(cur.fetchone())
    if not doc:
        return "Document not found", 404
    
    cur.execute("SELECT * FROM ground_truth WHERE document_id = ?", (doc_id,))
    gt_row = cur.fetchone()
    gt = dict_from_row(gt_row) if gt_row else {}
    
    cur.execute("SELECT id FROM documents WHERE is_in_sample_set = TRUE AND id < ? ORDER BY id DESC LIMIT 1", (doc_id,))
    prev_row = cur.fetchone()
    prev_id = prev_row[0] if prev_row else None
    
    cur.execute("SELECT id FROM documents WHERE is_in_sample_set = TRUE AND id > ? ORDER BY id ASC LIMIT 1", (doc_id,))
    next_row = cur.fetchone()
    next_id = next_row[0] if next_row else None
    conn.close()
    
    prev_btn = f'<a href="/document/{prev_id}" class="btn btn-outline">← Vorheriges</a>' if prev_id else ''
    next_btn = f'<a href="/document/{next_id}" class="btn btn-outline">Nächstes →</a>' if next_id else ''
    status_badge = f'<span class="status {doc["ground_truth_status"]}" style="margin-left: 1rem;">{doc["ground_truth_status"]}</span>' if doc.get('is_in_sample_set') else ''
    
    content = f'''
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.5rem;">
        <h2>📄 {doc["file_name"]}</h2>
        <div>{prev_btn} {next_btn}</div>
    </div>
    <div class="comparison-view">
        <div class="panel">
            <div class="panel-header">Original Scan</div>
            <div class="panel-content" style="text-align: center; background: #1a1a1a;">
                <img src="/image/{doc["id"]}" alt="{doc["file_name"]}" style="max-width: 100%; max-height: 800px;">
            </div>
        </div>
        <div class="panel">
            <div class="panel-header">Ground Truth Annotation {status_badge}</div>
            <div class="panel-content">
                <form action="/save_ground_truth/{doc["id"]}" method="POST">
                    <textarea name="ground_truth" class="text-area" placeholder="Ground Truth Text hier eingeben...">{gt.get("full_text", "")}</textarea>
                    <div style="margin-top: 1rem; display: grid; grid-template-columns: 1fr 1fr; gap: 1rem;">
                        <div><label class="field-label">Rechnungsnummer</label><input type="text" name="invoice_number" value="{gt.get("extracted_invoice_number", "")}" class="input-field"></div>
                        <div><label class="field-label">Datum</label><input type="text" name="doc_date" value="{gt.get("extracted_date", "")}" class="input-field"></div>
                        <div><label class="field-label">Gesamtbetrag</label><input type="text" name="total_amount" value="{gt.get("extracted_total_amount", "")}" class="input-field"></div>
                        <div><label class="field-label">Absender</label><input type="text" name="sender_name" value="{gt.get("extracted_sender_name", "")}" class="input-field"></div>
                    </div>
                    <div class="actions">
                        <button type="submit" class="btn btn-success">💾 Speichern</button>
                        <button type="submit" name="status" value="completed" class="btn btn-primary">✓ Als fertig markieren</button>
                    </div>
                </form>
            </div>
        </div>
    </div>
    <div class="meta-grid">
        <div><strong>Ordner:</strong> {doc["folder_name"]}</div>
        <div><strong>Format:</strong> {doc["file_format"]}</div>
        <div><strong>Größe:</strong> {doc["file_size_bytes"]/1024:.1f} KB</div>
        <div><strong>Auflösung:</strong> {doc.get("width_px", "?")}x{doc.get("height_px", "?")} px</div>
        <div><strong>DPI:</strong> {doc.get("dpi") or "N/A"}</div>
        <div><strong>Farbmodus:</strong> {doc.get("color_mode", "?")}</div>
    </div>
    '''
    return render_page(content, 'document')


@app.route('/save_ground_truth/<int:doc_id>', methods=['POST'])
def save_ground_truth(doc_id):
    conn = get_db()
    cur = conn.cursor()
    
    full_text = request.form.get('ground_truth', '')
    invoice_number = request.form.get('invoice_number', '')
    doc_date = request.form.get('doc_date', '')
    total_amount = request.form.get('total_amount', '')
    sender_name = request.form.get('sender_name', '')
    status = request.form.get('status', 'in_progress')
    
    umlaut_chars = set('äöüÄÖÜß')
    contains_umlauts = any(c in umlaut_chars for c in full_text)
    
    cur.execute("""
        INSERT INTO ground_truth (document_id, full_text, extracted_invoice_number, 
                                  extracted_date, extracted_total_amount, extracted_sender_name,
                                  contains_umlauts, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(document_id) DO UPDATE SET
            full_text = excluded.full_text,
            extracted_invoice_number = excluded.extracted_invoice_number,
            extracted_date = excluded.extracted_date,
            extracted_total_amount = excluded.extracted_total_amount,
            extracted_sender_name = excluded.extracted_sender_name,
            contains_umlauts = excluded.contains_umlauts,
            updated_at = CURRENT_TIMESTAMP
    """, (doc_id, full_text, invoice_number, doc_date, total_amount, sender_name, contains_umlauts))
    
    cur.execute("UPDATE documents SET ground_truth_status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (status, doc_id))
    conn.commit()
    conn.close()
    
    return redirect(f'/document/{doc_id}')


@app.route('/thumbnail/<int:doc_id>')
def thumbnail(doc_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT thumbnail_path FROM documents WHERE id = ?", (doc_id,))
    row = cur.fetchone()
    conn.close()
    if row and row[0] and os.path.exists(row[0]):
        return send_file(row[0], mimetype='image/png')
    return "", 404


@app.route('/image/<int:doc_id>')
def image(doc_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT file_path, file_format FROM documents WHERE id = ?", (doc_id,))
    row = cur.fetchone()
    conn.close()
    if row and os.path.exists(row[0]):
        mime = 'image/tiff' if row[1] == 'TIF' else 'application/pdf'
        return send_file(row[0], mimetype=mime)
    return "", 404


@app.route('/api/stats')
def api_stats():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM documents")
    total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM documents WHERE is_in_sample_set = TRUE")
    sample = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM documents WHERE is_in_sample_set = TRUE AND ground_truth_status = 'completed'")
    completed = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM documents WHERE is_in_sample_set = TRUE AND ground_truth_status = 'pending'")
    pending = cur.fetchone()[0]
    conn.close()
    return jsonify({'total': total, 'sample': sample, 'completed': completed, 'pending': pending})


# ============================================================================
# MAIN
# ============================================================================

if __name__ == '__main__':
    print("=" * 60)
    print("ABLAGE-SYSTEM: Training Data Validation UI")
    print("=" * 60)
    print(f"Database: {DB_PATH}")
    print(f"Starting server at http://{HOST}:{PORT}")
    print("=" * 60)
    app.run(host=HOST, port=PORT, debug=True)
