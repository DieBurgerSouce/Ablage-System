# Recent Changes

<!-- AUTO-MANAGED: recent-changes -->
## 2026-01-10

### Features
- **Entity API Enhancement**: Added new endpoints for customer/supplier frontend display
  - `GET /api/v1/entities/customers/for-frontend` - Customer list with folder stats
  - `GET /api/v1/entities/suppliers/for-frontend` - Supplier list with folder stats
- **Frontend Ablage Navigation**: Complete Kunden/Lieferanten overview pages
  - KundenPage.tsx: Customer cards with document counts, folder stats
  - LieferantenPage.tsx: Supplier cards with document counts, folder stats
  - Display format: Customer number + matchcode for customers, matchcode-only for suppliers

### API Changes
- Entity API (`entities.py`): Added frontend-optimized list endpoints
- Response includes: displayName, fullName, folderStats, companyPresence
- Stats per folder: totalDocs, openInvoices aggregated

### Bug Fixes
- **BUG-001 FIXED**: Tunes & Kontext Edit function restored
- **BUG-002 FIXED**: OCR Training Ground Truth tab loading corrected
- **BUG-003 FIXED**: OCR Review permissions bug resolved (admin access working)

### Status Changes
- Project status changed from "NOT Production-Ready" to "Production-Ready"
- E2E Test coverage: 22 modules tested, 73% working

### Documentation
- CLAUDE.md restructured for auto-memory plugin compatibility
- Created `.claude/memory/` directory for modular documentation

## 2026-01-09

### Features
- **Lexware Integration**: Complete customer/supplier import from Excel exports
- **Entity Search Service**: Search by customer number, IBAN, VAT-ID, matchcode
- **Document Entity Linker**: Automatic document-to-entity linking after OCR

### Database
- Migration 089: Added lexware_ids, company_presence fields to BusinessEntity
- Migration 090: Merge migration for lexware and streckengeschaeft

## 2026-01-08

### Features
- **Enterprise Orchestration PHASE 1**: Cross-module orchestrator implemented
- **Decision Engine**: Intelligent prioritization and conflict resolution
- **Financial Health Service**: Health score calculation (0-100)
- **PrivatTask Model**: Orchestrator-generated task tracking

### API
- New endpoints: `/api/v1/orchestration/*`
- Decision approval/rejection workflow

## 2026-01-04

### OCR
- A/B Testing experiments for DeepSeek vs GOT-OCR
- Multiple benchmark runs completed

## December 2024

### Major Features
- Privat-Modul: Enterprise Vermoegensverwaltung (Production-Ready)
- Backup & Disaster Recovery System
- OCR Training & Validation System

<!-- /AUTO-MANAGED: recent-changes -->

## Change Log Format

Aenderungen werden dokumentiert mit:
- Datum (neueste zuerst)
- Kategorie: Features, Bug Fixes, Database, API, Documentation
- Kurze Beschreibung der Aenderung
