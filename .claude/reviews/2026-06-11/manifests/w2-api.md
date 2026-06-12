# Manifest w2-api (Branch fix/w2-api)

## TABU-Wunsch: Migration fuer `invoice_tracking.invoice_type`

**Befund (beim Fixen von W1-004 #9 entdeckt, adversarial via Pre-Fix-Testlauf verifiziert):**
`InvoiceTracking` (app/db/models_entity_business.py) hat KEINE Spalte
`invoice_type` — weder im Modell noch in irgendeiner Alembic-Migration
(grep ueber alembic/versions/ ohne Treffer). Trotzdem filtern mehrere
Services darauf:

- `app/services/ai/cashflow_prediction_service.py:762` (`== "outgoing"`, _get_open_receivables)
- `app/services/ai/cashflow_prediction_service.py:812` (`== "incoming"`, _get_open_payables)
- `app/services/ai/finance_assistant_service.py:1290/1674/1680` (dort zusaetzlich
  `InvoiceTracking.total_amount` — Modell hat nur `amount`!)
- `app/services/ai/insight_generator_service.py:182/235/296/311/331`

**Wirkung:** Jede dieser Queries wirft zur Laufzeit `AttributeError` -> 500.
Der von w2-api umgesetzte 404-Guard im Scenario-Endpoint fixt nur den
Schemathesis-Repro (nicht existente entity_id); valide Anfragen auf echten
Daten laufen weiterhin in den Service-500.

**Gewuenschte Entscheidung/Aktion (ausserhalb w2-api-Zone, braucht Migration = TABU):**
1. Richtungs-Semantik festlegen: neue Spalte `invoice_type` (varchar,
   'incoming'/'outgoing', Migration 269+) ODER Richtung aus verknuepftem
   Document/Entity ableiten und die Service-Queries umschreiben.
2. `finance_assistant_service`-Drift `total_amount` -> `amount` gleich mitziehen.
3. Befuellung der neuen Spalte fuer Bestandsdaten klaeren (Backfill).

## Kein TABU, aber Cross-Zone-Hinweis

- `app/db/database.py:117`: `create_async_engine(..., poolclass=QueuePool)` ist
  mit SQLAlchemy >= 2.0.31 ein harter `ArgumentError` (Host-Python betroffen;
  Container laeuft nur dank aelterem Pin). Korrekt: `AsyncAdaptedQueuePool`
  oder poolclass weglassen. Einzeiler, aber app/db/** ausserhalb w2-api-Zone.
- `app/api/v1/entities.py` `get_folder_documents`: `normalized_folder` wird
  berechnet, aber NIE als Filter angewandt — der Ordner-Parameter wird
  effektiv ignoriert (Dokumente aller Firmen-Ordner der Entity erscheinen).
  Fix braucht Mapping short_name -> Company.id-Filter auf Document.company_id
  (Semantik-/Frontend-Abstimmung empfohlen).
