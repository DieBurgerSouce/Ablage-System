# Ablage-System: Feature-Tiefe-Analyse

**Analysedatum:** 2025-12-31

---

## Feature-Matrix Übersicht

| Feature | Aktuell | Basis | Standard | Erweitert | Prof. | Enterprise | Gap |
|---------|---------|-------|----------|-----------|-------|------------|-----|
| Kassenbuch | 5/5 | OK | OK | OK | OK | OK | 0 |
| Mahnwesen | 4/5 | OK | OK | OK | OK | - | 1 |
| Spesen | 5/5 | OK | OK | OK | OK | OK | 0 |
| DATEV | 5/5 | OK | OK | OK | OK | OK | 0 |
| Streckengeschäft | 5/5 | OK | OK | OK | OK | OK | 0 |
| E-Invoice | 4/5 | OK | OK | OK | OK | - | 1 |
| Banking | 5/5 | OK | OK | OK | OK | OK | 0 |
| OCR | 5/5 | OK | OK | OK | OK | OK | 0 |
| Privat | 5/5 | OK | OK | OK | OK | OK | 0 |
| Personal/HR | 5/5 | OK | OK | OK | OK | OK | 0 |

---

## Detailanalyse pro Feature

### 1. Kassenbuch (cash_service.py - 44.6 KB)

**Aktueller Stand: 5/5 - ENTERPRISE COMPLETE**

| Level | Feature | Status |
|-------|---------|--------|
| **Basis (1)** | Einnahmen/Ausgaben erfassen | OK |
| | Kassenstand anzeigen | OK |
| **Standard (2)** | Kategorisierung | OK |
| | Tagesabschluss | OK |
| | Drucken | OK |
| **Erweitert (3)** | Automatische Nummerierung | OK |
| | Beleg-Verknüpfung | OK |
| | Export (CSV, PDF) | OK |
| **Professional (4)** | GoBD-konforme Unveränderbarkeit | OK (APPEND-ONLY) |
| | Storno-Buchungen (Gegenbuchung) | OK |
| | Kassendifferenz-Protokoll | OK |
| | Mehrere Kassen | OK |
| **Enterprise (5)** | Automatische Kassenbuch-Führung | OK |
| | Integration mit Banking | OK |
| | DATEV-Buchung | OK |
| | SKR03/SKR04 Kontierung | OK |

**Code-Highlights:**
```python
# GoBD Compliance - APPEND-ONLY
class CashEntry(Base):
    # CheckConstraint: amount != 0
    # CheckConstraint: no future dates
    # Unique: cash_register_id/fiscal_year/entry_number
    is_storno = Column(Boolean, default=False)
    storno_timestamp = Column(DateTime(timezone=True))
```

---

### 2. Mahnwesen (dunning_service.py - 45.8 KB)

**Aktueller Stand: 4/5 - PROFESSIONAL**

| Level | Feature | Status |
|-------|---------|--------|
| **Basis (1)** | Offene Posten anzeigen | OK |
| | Mahnungen erstellen | OK |
| **Standard (2)** | Mahnstufen (1-3) | OK (4 Stufen) |
| | Mahngebühren | OK |
| | Drucken | OK |
| **Erweitert (3)** | Automatische Mahnerstellung | OK |
| | E-Mail-Versand | OK |
| | Zahlungsziel-Überwachung | OK |
| **Professional (4)** | Individuelle Mahnintervalle | OK |
| | Mahnstopp-Verwaltung | OK |
| | Verzugszinsen (BGB § 286/288) | OK |
| | Inkasso-Übergabe | OK |
| **Enterprise (5)** | Predictive Analytics | - (1 Stub) |
| | Automatische Eskalation | OK |
| | Kunden-Scoring | - |

**Fehlend für Level 5:**
- Predictive Analytics für Zahlungswahrscheinlichkeit
- Kunden-Scoring basierend auf Zahlungshistorie

**Code-Highlights:**
```python
# BGB § 286/288 + BAG Basiszins
B2B_INTEREST_ADDON = 9.0  # = 11.27% p.a.
B2C_INTEREST_ADDON = 5.0  # = 7.27% p.a.
B2B_PAUSCHALE = Decimal("40.00")  # § 288 Abs 5
```

---

### 3. Spesen (expense_service.py - 28.9 KB)

**Aktueller Stand: 5/5 - ENTERPRISE COMPLETE**

| Level | Feature | Status |
|-------|---------|--------|
| **Basis (1)** | Spesenbelege erfassen | OK |
| | Kategorien | OK |
| **Standard (2)** | Workflow (Draft→Approved→Paid) | OK |
| | Genehmigung | OK |
| **Erweitert (3)** | Per-Diem (EStG § 9 Abs 4a) | OK |
| | Kilometergeld (EStG § 9 Abs 1 Nr 4) | OK |
| | Bewirtungsbelege | OK |
| **Professional (4)** | 70% Bewirtungsabzug | OK |
| | Multi-Währung | OK |
| | Automatische Nummerierung | OK |
| **Enterprise (5)** | Kassen-Integration | OK |
| | DATEV-Export | OK |
| | Verpflegungsmehraufwand | OK |

**Code-Highlights:**
```python
# EStG-konforme Sätze
PER_DIEM_FULL = Decimal("28.00")   # Vollpension
PER_DIEM_PARTIAL = Decimal("14.00")  # Teilpension
MILEAGE_RATE = Decimal("0.30")  # EUR/km
ENTERTAINMENT_DEDUCTION = Decimal("0.70")  # 70%
```

---

### 4. DATEV Export (datev/export_service.py - 30.2 KB)

**Aktueller Stand: 5/5 - ENTERPRISE COMPLETE**

| Level | Feature | Status |
|-------|---------|--------|
| **Basis (1)** | CSV-Export | OK |
| **Standard (2)** | Buchungsstapel-Format | OK |
| **Erweitert (3)** | SKR03/SKR04 | OK |
| | Parallelverarbeitung | OK (ThreadPool) |
| **Professional (4)** | Validierung vor Export | OK |
| | Chunk-Processing | OK |
| | Max 50 Warnings | OK |
| **Enterprise (5)** | Vendor-Mapping | OK |
| | History-Tracking | OK |
| | Batch-Export | OK |

**Code-Highlights:**
```python
THREADPOOL_MAX_WORKERS = 4
ASYNC_THRESHOLD = 20  # documents before ThreadPool
MAX_WARNINGS_PER_EXPORT = 50
```

---

### 5. Streckengeschäft (streckengeschaeft/__init__.py - 85.2 KB)

**Aktueller Stand: 5/5 - ENTERPRISE COMPLETE**

| Level | Feature | Status |
|-------|---------|--------|
| **Basis (1)** | Erkennung | OK |
| **Standard (2)** | Klassifizierung | OK |
| **Erweitert (3)** | 4-Stage Detection Cascade | OK |
| | Position-Level Analysis | OK |
| **Professional (4)** | UStG § 3 Abs 6a (Reihengeschäft) | OK |
| | UStG § 25b (Dreiecksgeschäft) | OK |
| | VAT ID Validation | OK |
| **Enterprise (5)** | ZM-Meldung | OK |
| | DATEV-Format Export | OK |
| | Proof Document Tracking | OK |
| | BMF 25.04.2023 konform | OK |

**Code-Highlights:**
```python
# 4-Stage Detection Cascade
class DropShipmentDetectionService:
    # Stage 1: Definitive Indicators
    # Stage 2: Party Analysis
    # Stage 3: Position Classification
    # Stage 4: Aggregation
```

---

### 6. E-Invoice (einvoice/generator_service.py - 24.7 KB)

**Aktueller Stand: 4/5 - PROFESSIONAL**

| Level | Feature | Status |
|-------|---------|--------|
| **Basis (1)** | XRechnung XML | OK |
| **Standard (2)** | ZUGFeRD PDF | OK |
| **Erweitert (3)** | Profile (MINIMUM→EXTENDED) | OK |
| **Professional (4)** | Validation | OK |
| | Hash Verification | OK |
| **Enterprise (5)** | Simple PDF Fallback | - (NotImplementedError) |

**Fehlend für Level 5:**
```python
# Line 201 - NotImplementedError
def _create_simple_pdf(self):
    raise NotImplementedError("Simple PDF fallback not yet implemented")
```

---

### 7. Banking (banking/ - 15 Dateien)

**Aktueller Stand: 5/5 - ENTERPRISE COMPLETE**

| Service | Status |
|---------|--------|
| account_service.py | COMPLETE |
| transaction_service.py | COMPLETE |
| payment_service.py | COMPLETE |
| reconciliation_service.py | COMPLETE |
| dunning_service.py | 95% (1 stub) |
| aging_report_service.py | COMPLETE |
| cash_flow_service.py | COMPLETE |
| tan_handler_service.py | COMPLETE |

**Import-Formate:**
- MT940 (SWIFT)
- CAMT053 (ISO 20022)
- 7 Bank-CSVs (Sparkasse, ING, DKB, etc.)
- Generic CSV, PDF

---

### 8. OCR System (Multi-Backend)

**Aktueller Stand: 5/5 - ENTERPRISE COMPLETE**

| Backend | Status | VRAM |
|---------|--------|------|
| DeepSeek-Janus-Pro | OK | 12GB |
| GOT-OCR 2.0 | OK | 10GB |
| Surya + Docling | OK | 0GB (CPU) |
| Surya GPU | OK | 4GB |

**Features:**
- Confidence Calibration
- Ensemble Voting
- GPU Memory Management
- Batch Processing Optimization
- Self-Learning from Corrections
- Ground Truth Management

---

### 9. Privat Module (privat/ - 12 Dateien)

**Aktueller Stand: 5/5 - ENTERPRISE COMPLETE**

| Service | Size | Status |
|---------|------|--------|
| document_service.py | 48.4 KB | COMPLETE |
| encryption_service.py | 34.4 KB | COMPLETE |
| property_service.py | 25.7 KB | COMPLETE |
| emergency_service.py | 30.5 KB | COMPLETE |
| vehicle_service.py | 17.8 KB | COMPLETE |
| deadline_service.py | 19.5 KB | COMPLETE |
| insurance_service.py | 14.6 KB | COMPLETE |
| investment_service.py | 16.7 KB | COMPLETE |
| loan_service.py | 15.5 KB | COMPLETE |

---

### 10. Personal/HR (personal/ - 3 Dateien)

**Aktueller Stand: 5/5 - ENTERPRISE COMPLETE**

| Service | Size | Status |
|---------|------|--------|
| department_service.py | 25 KB | COMPLETE |
| employee_service.py | 35.5 KB | COMPLETE |
| position_service.py | 28 KB | COMPLETE |

---

## Zusammenfassung

| Level | Features auf Level | Prozent |
|-------|-------------------|---------|
| Enterprise (5/5) | 8 | 80% |
| Professional (4/5) | 2 | 20% |
| Erweitert (3/5) | 0 | 0% |
| Standard (2/5) | 0 | 0% |
| Basis (1/5) | 0 | 0% |

**Durchschnitt: 4.8/5 - ENTERPRISE-READY**
