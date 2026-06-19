# 04 — Phantom-Spalten (Spec)

## IST (belegt)
- **12x** `Document.metadata` / `document.metadata[...]` in `app/api/v1/ocr.py` (Z.1762,1763,1847,2105,2108,2125,...).
  `Document` hat KEINE `metadata`-Spalte; korrekt ist `document_metadata` (CrossDBJSON). `metadata` trifft die
  SQLAlchemy-reservierte `MetaData`-Registry -> AttributeError/falsches Verhalten zur Laufzeit.
- `User.company_id` ist ein Phantom (kein Feld am User-Modell; Tenancy via UserCompany). Residuen: siehe 03
  (sso.py:1060). **PortalUser.company_id** ist legitim (siehe 03, NICHT anfassen).

## ZIEL
- `Document.metadata` -> `Document.document_metadata`. Bei JSONB-Operatoren zusaetzlich `cast(..., JSONB)`
  (Muster bereits etabliert, siehe CrossDBJSON-Fixes B1).

### Pseudocode
```
# vorher
val = document.metadata.get("handwriting_analysis")          # Phantom -> MetaData-Objekt
flag = Document.metadata["is_temporary"].astext               # falsche Spalte + JSONB-Op auf JSON
# nachher
val = document.document_metadata.get("handwriting_analysis")
flag = cast(Document.document_metadata, JSONB)["is_temporary"].astext
```

## TDD-Anker
- `test_ocr_consistency_statistics_uses_document_metadata` (Endpunkt, der `metadata` las, liefert 200).
- Statische Pruefung: kein `Document.metadata` / `\.metadata\[` / `\.metadata\.get` mehr in app/api/v1/ocr.py.

## Verifikation / DoD
- [ ] `grep -n "document.metadata\|Document\.metadata\|\.metadata\[" app/api/v1/ocr.py` -> 0.
- [ ] betroffene OCR-Endpunkte Live 200 (mit Bearer).
- [ ] keine Regression in CrossDBJSON (B1 bleibt sauber).