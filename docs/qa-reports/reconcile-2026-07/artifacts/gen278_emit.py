#!/usr/bin/env python3
"""Emit-Phase fuer Migration 278 (liest Katalog-Artefakte, schreibt Migrationsdatei).

Regeln:
- Kette kanonisch, AUSSER 4 Model-Truth-Faelle (centroid/prompt_embedding/
  affected_months/wsd.payload), wo die Kette hinter dem Model ist -> beide
  Seiten konvergieren auf Model-Wahrheit (guarded Conditional-ALTER).
- Jedes Statement idempotent/no-op-faehig auf BEIDEN Seiten.
- 1 Statement = 1 op.execute (env.py-$$-Splitter).
"""
import collections
import re
import sys

ART = "docs/qa-reports/reconcile-2026-07/artifacts"
PLANNED = {"gdpr_deletion_status", "gobd_audit_summary", "feature_toggle_history"}

# Model-Truth-Overrides: (table, col) -> (zieltyp_ddl, using_expr oder None, zeilen_guard)
MODEL_TRUTH_TYPES = {
    ("document_clusters", "centroid"): ("vector(1024)", "NULL::vector(1024)", True),
    ("llm_cache", "prompt_embedding"): ("jsonb", "to_jsonb(prompt_embedding)", False),
    ("entity_seasonal_patterns", "affected_months"): ("jsonb", "affected_months::jsonb", False),
    ("webhook_subscription_deliveries", "payload"): ("jsonb", "payload::jsonb", False),
    ("webhook_deliveries", "event_id"): ("uuid", "event_id::uuid", False),
    ("webhook_deliveries", "payload"): ("jsonb", "payload::jsonb", False),
}
# Erwartete format_type-Werte fuer die Postcondition:
MODEL_TRUTH_EXPECT = {
    ("document_clusters", "centroid"): "vector(1024)",
    ("llm_cache", "prompt_embedding"): "jsonb",
    ("entity_seasonal_patterns", "affected_months"): "jsonb",
    ("webhook_subscription_deliveries", "payload"): "jsonb",
    ("webhook_deliveries", "event_id"): "uuid",
    ("webhook_deliveries", "payload"): "jsonb",
}

TYPE_DDL = {"integer": "integer", "jsonb": "jsonb", "uuid": "uuid", "text": "text"}


def load_columns(path):
    d = {}
    for line in open(path, encoding="utf-8"):
        p = line.rstrip("\n").split("|")
        if len(p) != 5:
            continue
        d[(p[0], p[1])] = {"type": p[2], "nullable": p[3], "default": p[4]}
    return d


def load_constraints(path):
    d = collections.defaultdict(list)
    for line in open(path, encoding="utf-8"):
        p = line.rstrip("\n").split("|", 2)
        if len(p) != 3:
            continue
        d[p[0]].append({"name": p[1], "def": p[2]})
    return d


def load_indexes(path):
    d = {}
    for line in open(path, encoding="utf-8"):
        p = line.rstrip("\n").split("|", 3)
        if len(p) != 4:
            continue
        d[(p[1], p[2])] = p[3]
    return d


def load_comments(path):
    d = {}
    for line in open(path, encoding="utf-8"):
        p = line.rstrip("\n").split("|", 3)
        if len(p) != 4:
            continue
        relkind, rel, col, txt = p
        d[(rel, col)] = (relkind, txt)
    return d


def fk_signature(condef):
    m = re.match(r"FOREIGN KEY \(([^)]+)\) REFERENCES ([^( ]+)", condef)
    return ("FK", m.group(1), m.group(2)) if m else None


def compute():
    fc = load_columns(f"{ART}/fresh_COLUMNS.txt")
    lc = load_columns(f"{ART}/live_COLUMNS_before.txt")
    fcon = load_constraints(f"{ART}/fresh_CONSTRAINTS.txt")
    lcon = load_constraints(f"{ART}/live_CONSTRAINTS_before.txt")
    fidx = load_indexes(f"{ART}/fresh_INDEXES.txt")
    lidx = load_indexes(f"{ART}/live_INDEXES_before.txt")
    fcom = load_comments(f"{ART}/fresh_COMMENTS.txt")
    lcom = load_comments(f"{ART}/live_COMMENTS_before.txt")

    o = {k: [] for k in [
        "add_columns", "drop_columns", "alter_type_plain", "alter_type_model",
        "set_default", "drop_default", "set_not_null", "drop_not_null",
        "con_rename", "con_replace", "con_add", "con_drop",
        "idx_drop", "idx_rename", "idx_create",
        "comment_set", "comment_clear",
    ]}

    for k in sorted(fc):
        t, c = k
        if t in PLANNED:
            continue
        if k not in lc:
            o["add_columns"].append((t, c, fc[k]))
    for k in sorted(lc):
        if k not in fc:
            o["drop_columns"].append(k)
    for k in sorted(fc):
        if k not in lc or fc[k] == lc[k]:
            continue
        t, c = k
        f, l = fc[k], lc[k]
        if f["type"] != l["type"]:
            if k in MODEL_TRUTH_TYPES:
                o["alter_type_model"].append((t, c) + MODEL_TRUTH_TYPES[k])
            else:
                assert f["type"] == "text" and l["type"] == "character varying", \
                    f"Unerwarteter Typ-Diff {k}: {l['type']} -> {f['type']}"
                o["alter_type_plain"].append((t, c))
        if f["default"] != l["default"]:
            if f["default"] == "-":
                o["drop_default"].append((t, c))
            else:
                o["set_default"].append((t, c, f["default"]))
        if f["nullable"] != l["nullable"]:
            (o["set_not_null"] if f["nullable"] == "NO" else o["drop_not_null"]).append((t, c))

    for t in sorted(set(fcon) | set(lcon)):
        if t in PLANNED:
            continue
        fl, ll = fcon.get(t, []), lcon.get(t, [])
        f_by_def = collections.defaultdict(list)
        l_by_def = collections.defaultdict(list)
        for c in fl:
            f_by_def[c["def"]].append(c["name"])
        for c in ll:
            l_by_def[c["def"]].append(c["name"])
        f_rest, l_rest = [], []
        for d in sorted(set(f_by_def) | set(l_by_def)):
            fn = sorted(f_by_def.get(d, []))
            lnames = sorted(l_by_def.get(d, []))
            common = set(fn) & set(lnames)
            fn = [x for x in fn if x not in common]
            lnames = [x for x in lnames if x not in common]
            while fn and lnames:
                o["con_rename"].append((t, lnames.pop(0), fn.pop(0)))
            f_rest += [{"name": n, "def": d} for n in fn]
            l_rest += [{"name": n, "def": d} for n in lnames]
        l_by_sig = collections.defaultdict(list)
        for c in l_rest:
            sig = fk_signature(c["def"])
            if sig:
                l_by_sig[sig].append(c)
        for c in list(f_rest):
            sig = fk_signature(c["def"])
            if sig and l_by_sig.get(sig):
                lm = l_by_sig[sig].pop(0)
                o["con_replace"].append((t, lm["name"], c["name"], c["def"]))
                f_rest.remove(c)
                l_rest.remove(lm)
        for c in f_rest:
            o["con_add"].append((t, c["name"], c["def"]))
        for c in l_rest:
            o["con_drop"].append((t, c["name"]))

    def norm_idx(d):
        return re.sub(r"INDEX \S+ ON", "INDEX ? ON", d)

    fresh_only = {k: v for k, v in fidx.items() if lidx.get(k) != v and k[0] not in PLANNED}
    live_only = {k: v for k, v in lidx.items() if fidx.get(k) != v}
    l_norm = collections.defaultdict(list)
    for (t, n), d in sorted(live_only.items()):
        l_norm[(t, norm_idx(d))].append(n)
    for (t, n), d in sorted(fresh_only.items()):
        key = (t, norm_idx(d))
        if l_norm.get(key):
            ln = l_norm[key].pop(0)
            o["idx_rename"].append((t, ln, n))
            del live_only[(t, ln)]
        else:
            o["idx_create"].append((t, n, d))
    for (t, n), d in sorted(live_only.items()):
        o["idx_drop"].append((t, n))

    for k in sorted(set(fcom) | set(lcom)):
        rel, col = k
        if rel in PLANNED:
            continue
        f, l = fcom.get(k), lcom.get(k)
        if f == l:
            continue
        if f is None:
            o["comment_clear"].append((lcom[k][0], rel, col))
        else:
            o["comment_set"].append((f[0], rel, col, f[1]))
    return o


def sql_str(s):
    return s.replace("'", "''")


def emit(o):
    S = []  # (kommentar, [statements])

    s1 = []
    for t, c, spec in o["add_columns"]:
        ddl = TYPE_DDL[spec["type"]]
        stmt = f"ALTER TABLE {t} ADD COLUMN IF NOT EXISTS {c} {ddl}"
        if spec["default"] != "-":
            stmt += f" DEFAULT {spec['default']}"
        if spec["nullable"] == "NO":
            stmt += " NOT NULL"
        s1.append(stmt)
    S.append(("G1: fehlende Spalten nachziehen (Kette kanonisch)", s1))

    guard_cols = ", ".join(c for _, c in o["drop_columns"])
    tset = {t for t, _ in o["drop_columns"]}
    assert tset == {"webhook_deliveries"}, tset
    s2 = ["""\
DO $$
BEGIN
    IF (SELECT count(*) FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'webhook_deliveries'
          AND column_name IN ('attempt_count', 'duration_ms', 'error_message',
                              'http_status_code', 'subscription_id')) > 0
       AND (SELECT count(*) FROM webhook_deliveries) > 0 THEN
        RAISE EXCEPTION 'Migration 278/G2: webhook_deliveries enthaelt Daten - Leichen-Spalten nicht verlustfrei droppbar';
    END IF;
END $$"""]
    for t, c in o["drop_columns"]:
        s2.append(f"ALTER TABLE {t} DROP COLUMN IF EXISTS {c}")
    S.append(("G2: Leichen-Spalten (alter Model-Stand, 0 Zeilen verifiziert 2026-07-14)", s2))

    s3 = [f"ALTER TABLE {t} ALTER COLUMN {c} TYPE text" for t, c in o["alter_type_plain"]]
    for t, c, target, using, row_guard in o["alter_type_model"]:
        guard = ""
        if row_guard:
            guard = f"""
        IF (SELECT count(*) FROM {t}) > 0 THEN
            RAISE EXCEPTION 'Migration 278/G3: {t}.{c} hat Daten - USING-Neuaufbau nicht verlustfrei';
        END IF;"""
        s3.append(f"""\
DO $$
BEGIN
    IF (SELECT format_type(a.atttypid, a.atttypmod) FROM pg_attribute a
        WHERE a.attrelid = 'public.{t}'::regclass AND a.attname = '{c}'
          AND NOT a.attisdropped) IS DISTINCT FROM '{MODEL_TRUTH_EXPECT[(t, c)]}' THEN{guard}
        EXECUTE 'ALTER TABLE {t} ALTER COLUMN {c} TYPE {target} USING {sql_str(using)}';
    END IF;
END $$""")
    S.append(("G3: Typ-Angleichung (10x varchar->text Kette-kanonisch; 6x Model-Wahrheit beidseitig)", s3))

    s4 = [f"ALTER TABLE {t} ALTER COLUMN {c} SET DEFAULT {d}" for t, c, d in o["set_default"]]
    s4 += [f"ALTER TABLE {t} ALTER COLUMN {c} DROP DEFAULT" for t, c in o["drop_default"]]
    S.append(("G4: Spalten-Defaults (Kette kanonisch; Live-Guards: alle Kandidaten 0 NULL-Zeilen)", s4))

    s5 = [f"ALTER TABLE {t} ALTER COLUMN {c} SET NOT NULL" for t, c in o["set_not_null"]]
    s5 += [f"ALTER TABLE {t} ALTER COLUMN {c} DROP NOT NULL" for t, c in o["drop_not_null"]]
    S.append(("G5: Nullability (SET NOT NULL validiert PG selbst -> Abbruch=Rollback; live 0 NULLs verifiziert)", s5))

    s6 = []
    for t, old, new in o["con_rename"]:
        s6.append(f"""\
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = '{old}' AND conrelid = 'public.{t}'::regclass)
       AND NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = '{new}' AND conrelid = 'public.{t}'::regclass) THEN
        EXECUTE 'ALTER TABLE {t} RENAME CONSTRAINT {old} TO {new}';
    END IF;
END $$""")
    for t, old, new, cdef in o["con_replace"]:
        # Auch bei old == new droppen: gleicher Name mit ANDERER Definition
        # (z.B. ON-DELETE-Aktion) wuerde sonst den guarded ADD ueberspringen
        # und die Live-Definition behalten (Fund der Klon-Generalprobe).
        s6.append(f"ALTER TABLE {t} DROP CONSTRAINT IF EXISTS {old}")
        s6.append(f"""\
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = '{new}' AND conrelid = 'public.{t}'::regclass) THEN
        EXECUTE 'ALTER TABLE {t} ADD CONSTRAINT {new} {sql_str(cdef)}';
    END IF;
END $$""")
    for t, n, cdef in o["con_add"]:
        s6.append(f"""\
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = '{n}' AND conrelid = 'public.{t}'::regclass) THEN
        EXECUTE 'ALTER TABLE {t} ADD CONSTRAINT {n} {sql_str(cdef)}';
    END IF;
END $$""")
    for t, n in o["con_drop"]:
        s6.append(f"ALTER TABLE {t} DROP CONSTRAINT IF EXISTS {n}")
    S.append(("G6: Constraints (FK-ON-DELETE-Paritaet, CHECK/UNIQUE nachziehen; alle Ziel-Tabellen 0 Zeilen bzw. FK-validierbar)", s6))

    # Fund der Klon-Generalprobe: der kpi_history-Unique-Index braucht diese
    # Funktion (Mig 084) - einzige fehlende Funktion lt. pg_proc-Vergleich;
    # der create_all-Bootstrap legte Migrations-Funktionen nie an.
    s7 = ["CREATE OR REPLACE FUNCTION kpi_history_utc_day(ts timestamptz) RETURNS date "
          "LANGUAGE sql IMMUTABLE AS $$ SELECT (ts AT TIME ZONE 'UTC')::date $$"]
    s7 += [f"DROP INDEX IF EXISTS {n}" for t, n in o["idx_drop"]]
    # Rename-Ziele, die G6 bereits als Constraint-Backing-Index anlegt, wuerden
    # den Rename-Guard nie feuern lassen -> Alt-Index stattdessen droppen
    # (der plain-Ersatz kommt aus idx_create).
    g6_names = {new for _, _, new, _ in o["con_replace"]} | {n for _, n, _ in o["con_add"]}
    for t, old, new in list(o["idx_rename"]):
        if new in g6_names:
            o["idx_rename"].remove((t, old, new))
            s7.append(f"DROP INDEX IF EXISTS {old}")
    for t, old, new in o["idx_rename"]:
        s7.append(f"""\
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_class WHERE relname = '{old}' AND relkind = 'i')
       AND NOT EXISTS (SELECT 1 FROM pg_class WHERE relname = '{new}' AND relkind = 'i') THEN
        EXECUTE 'ALTER INDEX {old} RENAME TO {new}';
    END IF;
END $$""")
    for t, n, d in o["idx_create"]:
        d2 = d.replace("CREATE UNIQUE INDEX ", "CREATE UNIQUE INDEX IF NOT EXISTS ", 1) \
             if d.startswith("CREATE UNIQUE INDEX ") else \
             d.replace("CREATE INDEX ", "CREATE INDEX IF NOT EXISTS ", 1)
        s7.append(d2)
    S.append(("G7: Indexe (Drop Live-only -> Rename def-gleicher -> Create fehlende, Namen = Kette)", s7))

    kind_kw = {"r": "TABLE", "p": "TABLE", "v": "VIEW", "m": "MATERIALIZED VIEW"}
    cmt_lines = []
    for relkind, rel, col, txt in o["comment_set"]:
        kw = kind_kw[relkind]
        if col:
            cmt_lines.append(
                f"    EXECUTE format('COMMENT ON COLUMN public.%I.%I IS %L', '{rel}', '{col}', '{sql_str(txt)}');")
        else:
            cmt_lines.append(
                f"    EXECUTE format('COMMENT ON {kw} public.%I IS %L', '{rel}', '{sql_str(txt)}');")
    for relkind, rel, col in o["comment_clear"]:
        kw = kind_kw[relkind]
        if col:
            cmt_lines.append(
                f"    EXECUTE format('COMMENT ON COLUMN public.%I.%I IS NULL', '{rel}', '{col}');")
        else:
            cmt_lines.append(
                f"    EXECUTE format('COMMENT ON {kw} public.%I IS NULL', '{rel}');")
    s8 = []
    BATCH = 40
    for i in range(0, len(cmt_lines), BATCH):
        body = "\n".join(cmt_lines[i:i + BATCH])
        s8.append(f"DO $$\nBEGIN\n{body}\nEND $$")
    S.append(("G8: Kommentar-Paritaet (Kette kanonisch; format(%I/%L) uebernimmt Quoting)", s8))

    # ---- Postconditions -------------------------------------------------
    posts = []
    addcols = ", ".join(f"('{t}','{c}')" for t, c, _ in o["add_columns"])
    dropcols = ", ".join(f"'{c}'" for _, c in o["drop_columns"])
    posts.append(f"""\
DO $$
DECLARE n INT;
BEGIN
    SELECT count(*) INTO n FROM information_schema.columns
    WHERE table_schema = 'public' AND (table_name, column_name) IN ({addcols});
    IF n <> {len(o["add_columns"])} THEN
        RAISE EXCEPTION 'Migration 278/P1: nachgezogene Spalten unvollstaendig (%/{len(o["add_columns"])})', n;
    END IF;
    SELECT count(*) INTO n FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'webhook_deliveries'
      AND column_name IN ({dropcols});
    IF n > 0 THEN
        RAISE EXCEPTION 'Migration 278/P1: % Leichen-Spalten ueberleben', n;
    END IF;
END $$""")
    nn = ", ".join(f"('{t}','{c}')" for t, c in o["set_not_null"])
    dn = ", ".join(f"('{t}','{c}')" for t, c in o["drop_not_null"])
    posts.append(f"""\
DO $$
DECLARE n INT;
BEGIN
    SELECT count(*) INTO n FROM information_schema.columns
    WHERE table_schema = 'public' AND (table_name, column_name) IN ({nn})
      AND is_nullable = 'YES';
    IF n > 0 THEN
        RAISE EXCEPTION 'Migration 278/P2: % SET-NOT-NULL-Spalten weiterhin nullable', n;
    END IF;
    SELECT count(*) INTO n FROM information_schema.columns
    WHERE table_schema = 'public' AND (table_name, column_name) IN ({dn})
      AND is_nullable = 'NO';
    IF n > 0 THEN
        RAISE EXCEPTION 'Migration 278/P2: % DROP-NOT-NULL-Spalten weiterhin NOT NULL', n;
    END IF;
END $$""")
    con_expected = sorted({(t, new) for t, _, new, _ in o["con_replace"]}
                          | {(t, n) for t, n, _ in o["con_add"]}
                          | {(t, new) for t, _, new in o["con_rename"]})
    con_list = ", ".join(f"('{t}','{n}')" for t, n in con_expected)
    fresh_con_names = {n for _, n in con_expected}
    gone = sorted({(t, old) for t, old, new, _ in o["con_replace"] if old != new and old not in fresh_con_names}
                  | {(t, n) for t, n in o["con_drop"] if n not in fresh_con_names}
                  | {(t, old) for t, old, new in o["con_rename"] if old not in fresh_con_names})
    gone_list = ", ".join(f"('{t}','{n}')" for t, n in gone)
    posts.append(f"""\
DO $$
DECLARE n INT;
BEGIN
    SELECT count(*) INTO n FROM pg_constraint c
    WHERE (c.conrelid::regclass::text, c.conname) IN ({con_list});
    IF n <> {len(con_expected)} THEN
        RAISE EXCEPTION 'Migration 278/P3: Ziel-Constraints unvollstaendig (%/{len(con_expected)})', n;
    END IF;
    SELECT count(*) INTO n FROM pg_constraint c
    WHERE (c.conrelid::regclass::text, c.conname) IN ({gone_list});
    IF n > 0 THEN
        RAISE EXCEPTION 'Migration 278/P3: % Alt-Constraints ueberleben', n;
    END IF;
END $$""")
    idx_expected = sorted({n for _, n, _ in o["idx_create"]} | {new for _, _, new in o["idx_rename"]})
    idx_list = ", ".join(f"'{n}'" for n in idx_expected)
    idx_gone = sorted({n for _, n in o["idx_drop"] if n not in idx_expected}
                      | {old for _, old, new in o["idx_rename"] if old not in idx_expected})
    idx_gone_list = ", ".join(f"'{n}'" for n in idx_gone)
    posts.append(f"""\
DO $$
DECLARE n INT;
BEGIN
    SELECT count(*) INTO n FROM pg_class WHERE relkind = 'i' AND relname IN ({idx_list});
    IF n <> {len(idx_expected)} THEN
        RAISE EXCEPTION 'Migration 278/P4: Ziel-Indexe unvollstaendig (%/{len(idx_expected)})', n;
    END IF;
    SELECT count(*) INTO n FROM pg_class WHERE relkind = 'i' AND relname IN ({idx_gone_list});
    IF n > 0 THEN
        RAISE EXCEPTION 'Migration 278/P4: % Alt-Indexe ueberleben', n;
    END IF;
END $$""")
    tm = ", ".join(f"('{t}','{c}','{MODEL_TRUTH_EXPECT[(t, c)]}')" for t, c, *_ in o["alter_type_model"])
    posts.append(f"""\
DO $$
DECLARE n INT;
BEGIN
    SELECT count(*) INTO n FROM (VALUES {tm}) v(t, c, want)
    JOIN pg_attribute a ON a.attrelid = ('public.'||v.t)::regclass AND a.attname = v.c
    WHERE format_type(a.atttypid, a.atttypmod) IS DISTINCT FROM v.want;
    IF n > 0 THEN
        RAISE EXCEPTION 'Migration 278/P5: % Model-Truth-Typen nicht erreicht', n;
    END IF;
END $$""")
    posts.append("""\
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
                   WHERE n.nspname = 'public' AND p.proname = 'kpi_history_utc_day') THEN
        RAISE EXCEPTION 'Migration 278/P6: kpi_history_utc_day() fehlt (Funktions-Paritaet)';
    END IF;
END $$""")
    S.append(("Postconditions P1-P6", posts))
    return S


HEADER = '''"""Drift-Reconcile E4 (Teil 3/3): Spalten-/Constraint-/Index-/Kommentar-Paritaet.

GENERIERT am 2026-07-14 aus dem Katalog-Diff Frisch(277+init.sql-Substrat) vs.
Live(275) durch scratchpad/gen278_emit.py; Quell-Artefakte unter
docs/qa-reports/reconcile-2026-07/artifacts/ (fresh_/live_-COLUMNS/CONSTRAINTS/
INDEXES/COMMENTS). Gate-1.5-Entscheidung Ben 2026-07-14: "Volle Paritaet jetzt".

Zweite Drift-Ebene desselben create_all-Bootstraps (siehe Migration 276):
Spalten-Attribute (Defaults/Nullability/Typen), FK-ON-DELETE-Semantik,
Indexe und Kommentare weichen zwischen Live und Kette ab.

Richtungsregel: Kette = kanonisch. AUSNAHME (Model-Wahrheit, 6 Spalten):
document_clusters.centroid (CrossDBVector(1024)), llm_cache.prompt_embedding,
entity_seasonal_patterns.affected_months, webhook_subscription_deliveries.payload
(alle CrossDBJSON->jsonb) sind auf LIVE model-treu und in der KETTE veraltet;
webhook_deliveries.event_id/payload umgekehrt. Diese 6 werden per guarded
Conditional-ALTER auf Model-Wahrheit gezogen - auf beiden Seiten no-op-faehig.

Datenguards (Live verifiziert 2026-07-14, werden zur Laufzeit erneut geprueft
bzw. von PostgreSQL selbst validiert -> Fehler = transaktionaler Rollback):
- alle 22 SET-NOT-NULL-Spalten: 0 NULL-Zeilen
- webhook_deliveries (5 Drop-Spalten): 0 Zeilen (Runtime-Guard in G2)
- event_log/llm_cache/integration_*/privat_kpi_history/entity_seasonal_patterns/
  webhook_*: 0 Zeilen -> CHECK/UNIQUE/Typ-Aenderungen verlustfrei

WICHTIG (alembic/env.py, asyncpg): 1 Statement = 1 op.execute; DO-$$-Bloecke
einzeln (Splitter-Falle, siehe Migration 275/276).

Nachtraege der Klon-Generalprobe (2026-07-14, drei Funde):
1. Funktions-Paritaet: kpi_history_utc_day (Mig 084) fehlte auf Live (einzige
   fehlende Funktion lt. pg_proc-Vergleich) - nachgezogen am Beginn von G7 (P6).
2. FK-Replace bei NAMENSGLEICHHEIT: DROP CONSTRAINT IF EXISTS laeuft jetzt
   immer vor dem guarded ADD (sonst behielte Live die alte ON-DELETE-Aktion).
3. Zwei Unique-Index-Altlasten (ix_event_log_event_id, ix_llm_cache_prompt_hash)
   werden gedroppt statt umbenannt - ihr Zielname entsteht in G6 als
   Constraint-Backing-Index; der plain-Ersatz kommt aus idx_create.

Downgrade ist bewusst ein No-op: Der Vorher-Zustand ist der inkonsistente
create_all-Bootstrap - ihn wiederherzustellen ist nie gewollt; der
Rollback-Anker fuer das Wartungsfenster ist der restic-Snapshot (Gate 2).

Revision ID: 278
Revises: 277
Create Date: 2026-07-14
"""
from alembic import op

revision = "278"
down_revision = "277"
branch_labels = None
depends_on = None

'''

FOOTER = '''

def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        # Katalog-Paritaet ist PostgreSQL-only (SQLite-Test-Runs skippen).
        return
    for _section, _stmts in _SECTIONS:
        for _stmt in _stmts:
            op.execute(_stmt)


def downgrade() -> None:
    # Bewusst No-op: siehe Docstring.
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
'''


def main():
    o = compute()
    sections = emit(o)
    parts = [HEADER, "_SECTIONS = [\n"]
    for title, stmts in sections:
        parts.append(f"    # --- {title} ({len(stmts)} Statements) ---\n")
        parts.append(f"    ({title.split(':')[0]!r}, [\n")
        for s in stmts:
            parts.append(f"        {s!r},\n")
        parts.append("    ]),\n")
    parts.append("]\n")
    parts.append(FOOTER)
    path = "alembic/versions/278_column_constraint_index_parity.py"
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("".join(parts))
    total = sum(len(s) for _, s in sections)
    print(f"geschrieben: {path} ({total} Statements)")
    for title, stmts in sections:
        print(f"   {title}: {len(stmts)}")


if __name__ == "__main__":
    main()
