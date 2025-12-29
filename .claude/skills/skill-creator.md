---
name: skill-creator
description: Erstelle effektive Skills fuer das Ablage-System Projekt. Nutze diesen Skill wenn du neue Skills erstellen, bestehende erweitern oder Skills fuer spezifische Workflows bauen willst. Skills werden in .claude/skills/ abgelegt.
---

# Skill Creator (Ablage-System)

Guide zum Erstellen von Skills die Claude's Faehigkeiten erweitern.

## Was sind Skills?

Modulare, eigenstaendige Pakete die Claude erweitern:
1. **Spezialisierte Workflows** - Multi-Step Prozeduren
2. **Tool-Integrationen** - Datei-Formate, APIs
3. **Domain-Wissen** - Projekt-spezifisches Know-how
4. **Bundled Resources** - Scripts, References, Assets

## Core Principles

### 1. Concise is Key
- Context Window ist begrenzt
- Claude ist bereits sehr schlau
- Nur hinzufuegen was Claude NICHT weiss
- Knappe Beispiele > ausfuehrliche Erklaerungen

### 2. Degrees of Freedom

| Level | Use Case | Beispiel |
|-------|----------|----------|
| Hoch (Text) | Multiple Ansaetze moeglich | Design-Guidance |
| Mittel (Pseudocode) | Preferred Patterns | Konfiguration |
| Niedrig (Scripts) | Fragile Operationen | File-Manipulationen |

## Skill-Anatomie

```
skill-name/
├── SKILL.md (required)
│   ├── YAML frontmatter (name, description)
│   └── Markdown instructions
└── Bundled Resources (optional)
    ├── scripts/      # Ausfuehrbarer Code
    ├── references/   # Dokumentation
    └── assets/       # Templates, Icons
```

## SKILL.md Struktur

```yaml
---
name: mein-skill
description: Was der Skill macht UND wann er genutzt werden soll.
             WICHTIG: Alle Trigger-Infos gehoeren HIER, nicht im Body!
---

# Skill Title

## Quick Start
[Kurze Anleitung]

## Detailed Usage
[Ausfuehrliche Infos]

## References
- [REFERENCE.md](REFERENCE.md) fuer Details
```

## Ablage-System Skill-Pfad

Skills werden abgelegt in:
```
C:\Users\benfi\Ablage_System\.claude\skills\
```

Aufruf dann via:
```
/skill-name
```

## Skill erstellen: Schritt-fuer-Schritt

### 1. Zweck definieren
- Was soll der Skill erreichen?
- Wann wird er getriggert?
- Welche Beispiel-Aufrufe gibt es?

### 2. Inhalte planen
- Welche Scripts werden gebraucht?
- Welche References?
- Welche Assets?

### 3. SKILL.md schreiben

```markdown
---
name: mein-neuer-skill
description: Kurze Beschreibung + Trigger-Woerter. Nutze wenn X, Y, Z.
---

# Mein Neuer Skill

## Wann nutzen
- Situation A
- Situation B

## Anleitung
1. Schritt eins
2. Schritt zwei

## Beispiele
[Code-Beispiele]
```

### 4. Testen
- Skill aufrufen
- Verschiedene Szenarien testen
- Iterieren

## Best Practices

1. **Description ist KRITISCH** - Enthaelt alle Trigger-Infos
2. **Body unter 500 Zeilen** - Sonst in References auslagern
3. **Keine Duplikation** - Info ist ENTWEDER in SKILL.md ODER in References
4. **Deutsche Sprache** - Fuer Ablage-System Kontext

## Beispiel: OCR-Skill

```yaml
---
name: ocr-debug
description: Diagnostiziere OCR-Probleme im Ablage-System.
             Nutze wenn GPU-Fehler, schlechte Erkennung,
             Umlaut-Probleme oder Performance-Issues auftreten.
---

# OCR Debugging

## Quick Check
nvidia-smi  # GPU Status

## Backends
- DeepSeek: Beste Umlaut-Genauigkeit
- GOT-OCR: Schnell, Tabellen
- Surya: CPU-Fallback
```

## Progressive Disclosure

| Level | Content | Groesse | Geladen |
|-------|---------|---------|---------|
| 1 | Metadata (name + description) | ~100 Woerter | Immer |
| 2 | SKILL.md Body | <5k Woerter | Bei Trigger |
| 3 | Bundled Resources | Unbegrenzt | Bei Bedarf |
