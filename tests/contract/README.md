# Contract Tests - API-Kompatibilitaetstests

## Übersicht

Contract Tests pruefen die Stabilitaet und Rueckwaertskompatibilitaet der API-Schnittstellen. Sie erkennen Breaking Changes und stellen sicher, dass die API sich nicht unbeabsichtigt aendert.

## Test-Dateien

| Datei | Beschreibung |
|-------|--------------|
| `test_openapi_compatibility.py` | Haupttests fuer OpenAPI-Schema-Kompatibilitaet |
| `schema_diff.py` | Utility zum Vergleichen von OpenAPI-Schemas |
| `conftest.py` | Pytest-Fixtures fuer Contract-Tests |
| `baseline_openapi_schema.json` | Referenz-Schema fuer Kompatibilitaetstests |

## Tests Ausfuehren

```bash
# Alle Contract-Tests
pytest tests/contract/ -v -m contract

# Einzelne Test-Klasse
pytest tests/contract/test_openapi_compatibility.py::TestSchemaCompatibility -v

# Mit Coverage
pytest tests/contract/ --cov=app.main --cov-report=html
```

## Baseline Aktualisieren

Wenn bewusste API-Aenderungen durchgefuehrt wurden:

```bash
python scripts/update_openapi_baseline.py
```

Dies erstellt ein Backup der alten Baseline und speichert das neue Schema.

## Test-Kategorien

### 1. Schema-Validitaet
- `test_openapi_schema_is_valid()` - Schema entspricht OpenAPI 3.x Spec
- `test_openapi_schema_has_paths()` - Mindestens ein Endpoint definiert

### 2. Endpoint-Dokumentation
- `test_all_endpoints_have_descriptions()` - Alle Endpoints dokumentiert
- `test_all_endpoints_have_response_models()` - Response-Schemas definiert
- `test_all_error_responses_documented()` - Error-Responses (400/404/422/500)
- `test_german_descriptions()` - Beschreibungen auf Deutsch

### 3. Schema-Kompatibilitaet
- `test_no_breaking_changes()` - Keine Breaking Changes vs. Baseline
- `test_schema_change_report()` - Detaillierter Aenderungsbericht
- `test_endpoint_count_stability()` - Endpoint-Anzahl bleibt stabil

### 4. Schema-Komponenten
- `test_all_schemas_have_descriptions()` - Models dokumentiert
- `test_no_empty_schemas()` - Keine leeren Schema-Definitionen
- `test_all_responses_reference_schemas()` - Valide Schema-Referenzen

### 5. Performance
- `test_openapi_schema_generation_performance()` - Schema-Generierung <1s

## Breaking Changes Erkennung

Das `schema_diff.py` Modul identifiziert folgende Breaking Changes:

### Endpoints
- ❌ Endpoint entfernt
- ❌ HTTP-Methode entfernt
- ❌ Neuer required Parameter
- ❌ Required Parameter entfernt
- ❌ Success-Response entfernt

### Schemas
- ❌ Neues required Feld
- ❌ Required Feld entfernt
- ❌ Feld-Typ geaendert
- ❌ Enum-Werte entfernt

### Non-Breaking Changes
- ✅ Neuer Endpoint
- ✅ Neue HTTP-Methode
- ✅ Neuer optionaler Parameter
- ✅ Required -> Optional
- ✅ Neue Enum-Werte

## Workflow

### 1. Vor neuem Feature
```bash
# Baseline als Referenz speichern
python scripts/update_openapi_baseline.py
```

### 2. Feature entwickeln
- API-Aenderungen implementieren
- Neue Endpoints dokumentieren
- Response-Schemas definieren

### 3. Tests ausfuehren
```bash
pytest tests/contract/ -v
```

### 4. Breaking Changes?
Falls Breaking Changes gefunden werden:

**Option A**: Aenderungen sind unbeabsichtigt → Code korrigieren

**Option B**: Aenderungen sind beabsichtigt:
1. Versioning pruefen (z.B. /api/v2/)
2. Deprecation-Warnings hinzufuegen
3. Baseline aktualisieren: `python scripts/update_openapi_baseline.py`
4. CHANGELOG.md aktualisieren

## Integration mit CI/CD

Empfohlene Pipeline:

```yaml
# .github/workflows/tests.yml oder .gitlab-ci.yml
contract-tests:
  script:
    - pytest tests/contract/ -v -m contract
  rules:
    - if: $CI_COMMIT_BRANCH == "main"
    - if: $CI_MERGE_REQUEST_TARGET_BRANCH_NAME == "main"
```

Contract-Tests sollten bei jedem PR ausgefuehrt werden, der API-Code aendert.

## Best Practices

### 1. Versionierung
- Breaking Changes → neue API-Version (/api/v2/)
- Non-Breaking Changes → gleiche Version erweitern

### 2. Deprecation
```python
@router.get("/old-endpoint", deprecated=True)
async def old_endpoint():
    """DEPRECATED: Verwende /new-endpoint stattdessen."""
    ...
```

### 3. Dokumentation
- Jeder Endpoint braucht `summary` und `description`
- Response-Schemas fuer alle Success-Codes
- Error-Responses dokumentieren (422, 404, etc.)

### 4. Schema-Design
- Keine leeren Schemas
- Klare Feld-Namen (deutsch oder englisch konsistent)
- Required vs Optional explizit definieren

## Troubleshooting

### Test schlaegt fehl: "Keine Baseline vorhanden"
```bash
python scripts/update_openapi_baseline.py
```

### Test schlaegt fehl: "Breaking Changes gefunden"
1. Pruefen ob Aenderung beabsichtigt
2. Falls ja: Baseline aktualisieren
3. Falls nein: Code korrigieren

### Test schlaegt fehl: "Undefinierte Schema-Referenzen"
- FastAPI Response-Model pruefen
- Sicherstellen dass Schema in `components/schemas` definiert ist

### Schema-Generierung zu langsam
- Lazy imports verwenden
- Startup-Code optimieren
- Unnoetige Imports entfernen

## Weitere Informationen

- [OpenAPI 3.1 Specification](https://spec.openapis.org/oas/v3.1.0)
- [FastAPI OpenAPI](https://fastapi.tiangolo.com/advanced/extending-openapi/)
- [API Versioning Best Practices](https://www.rfc-editor.org/rfc/rfc9110.html)

---

**Erstellt**: 2026-02-07
**Version**: 1.0
**Maintainer**: Ablage-System Team
