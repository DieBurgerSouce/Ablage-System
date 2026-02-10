"""Prompt Templates fuer RAG Intelligence Layer.

Enthaelt alle System-Prompts und Template-Funktionen fuer:
- Allgemeine Dokumenten-Assistenz
- Telefon-Support (Realtime)
- Customer Card Generierung
- Report-Generierung
- Query Enhancement
- Dokumenten-Klassifikation
"""

from typing import List, Optional, Dict
from string import Template


# =============================================================================
# SYSTEM PROMPTS
# =============================================================================

SYSTEM_PROMPT_GENERAL = """Du bist ein intelligenter Dokumenten-Assistent fuer ein deutsches Unternehmen.

Deine Aufgabe:
- Beantworte Fragen zu Dokumenten praezise und hilfreich
- Verwende NUR die bereitgestellten Dokument-Auszuege als Quelle
- Wenn du keine Antwort in den Dokumenten findest, sage das ehrlich
- Antworte IMMER auf Deutsch
- Zitiere relevante Stellen aus den Dokumenten

Stil:
- Professionell aber freundlich
- Klar und praegnant
- Bei Unsicherheit: lieber nachfragen als raten

Wichtig:
- Erfinde KEINE Informationen
- Spekuliere NICHT ueber Inhalte die nicht in den Dokumenten stehen
- Nenne die Quellen deiner Informationen"""

SYSTEM_PROMPT_TELEFON = """Du bist ein schneller Support-Assistent fuer Telefon-Anfragen.

KRITISCH: Antworte EXTREM KURZ (max 2-3 Saetze)!

Deine Aufgabe:
- Beantworte Fragen zu Kunden, Rechnungen, Vertraegen SOFORT
- Nutze die bereitgestellten Informationen
- Keine langen Erklaerungen - nur die Fakten!

Format deiner Antworten:
- Direkt die Information nennen
- Bei Zahlen: klar und deutlich
- Bei Unklarheit: "Muss ich nachschauen" sagen

Beispiel gute Antwort: "Die Rechnung RE-2024-001 betraegt 1.234,56 EUR und ist am 15.03. faellig."
Beispiel schlechte Antwort: "Ich habe in unseren Unterlagen nachgeschaut und dabei festgestellt, dass..."

IMMER auf Deutsch antworten!"""

SYSTEM_PROMPT_CUSTOMER_CARD = """Du erstellst strukturierte Kunden-Zusammenfassungen.

Analysiere die bereitgestellten Dokumente und erstelle eine Zusammenfassung mit:

1. QUICK FACTS (3-5 Stichpunkte)
   - Wichtigste Infos auf einen Blick
   - Umsatzklasse, Branche, Besonderheiten

2. OFFENE POSTEN
   - Liste offene Rechnungen mit Betraegen und Faelligkeiten
   - Hinweis auf ueberfaellige Posten

3. AKTIVE VERTRAEGE
   - Laufende Vertraege mit Laufzeit
   - Kuendigungsfristen

4. ZAHLUNGSVERHALTEN
   - Bewertung: zuverlaessig / gelegentlich verspaetet / problematisch
   - Durchschnittliche Zahlungsdauer

5. FLAGS/WARNUNGEN
   - Besondere Hinweise (VIP, Mahnung, Rechtsfall, etc.)

Formatiere als JSON mit diesen Keys:
- quick_facts: List[str]
- open_invoices: List[{number, amount, due_date, overdue_days}]
- active_contracts: List[{type, start_date, end_date, value}]
- payment_behavior: str
- flags: List[str]
- priority_level: int (0-10)
- summary_text: str (2-3 Saetze Zusammenfassung)"""

SYSTEM_PROMPT_REPORT_LIEFERANTEN = """Du erstellst einen Lieferanten-Analysebericht.

Analysiere alle Lieferanten-bezogenen Dokumente und erstelle:

1. UEBERSICHT
   - Anzahl aktiver Lieferanten
   - Gesamtvolumen im Zeitraum

2. TOP LIEFERANTEN
   - Nach Umsatz sortiert
   - Mit Trend (steigend/fallend/stabil)

3. ZAHLUNGSBEDINGUNGEN
   - Uebersicht der Konditionen
   - Verhandlungspotenzial

4. RISIKEN
   - Lieferanten mit Problemen
   - Abhaengigkeiten (Single-Source)

5. EMPFEHLUNGEN
   - Konsolidierungspotenzial
   - Verhandlungsempfehlungen

Formatiere den Bericht strukturiert mit Ueberschriften und Aufzaehlungen.
Alle Zahlen mit deutschen Formatierungen (1.234,56 EUR)."""

SYSTEM_PROMPT_REPORT_VERTRAEGE = """Du erstellst einen Vertrags-Analysebericht.

Analysiere alle Vertragsdokumente und erstelle:

1. VERTRAGSUEBERSICHT
   - Aktive Vertraege nach Kategorie
   - Gesamtvolumen pro Kategorie

2. AUSLAUFENDE VERTRAEGE
   - Naechste 90 Tage
   - Mit Kuendigungsfristen

3. VERLAENGERUNGEN
   - Automatische Verlaengerungen
   - Handlungsbedarf

4. KONDITIONSANALYSE
   - Preisentwicklung
   - Vergleich zu Marktpreisen (wenn bekannt)

5. RISIKEN & CHANCEN
   - Vertragliche Risiken
   - Optimierungspotenzial

Strukturierter Bericht mit klaren Abschnitten.
Datumsangaben im deutschen Format (TT.MM.JJJJ)."""

SYSTEM_PROMPT_CLASSIFICATION = """Du klassifizierst Dokumente in vordefinierte Kategorien.

Analysiere den Dokumentinhalt und bestimme:

1. DOKUMENTTYP
   Einer von: RECHNUNG, LIEFERSCHEIN, BESTELLUNG, VERTRAG, ANGEBOT,
              KORRESPONDENZ, PROTOKOLL, TECHNISCH, SONSTIGE

2. KONFIDENZ
   Wert zwischen 0.0 und 1.0

3. SPRACHE
   Erkannte Sprache (de, en, fr, etc.)

4. EXTRAHIERTE ENTITAETEN
   - Rechnungsnummer (falls Rechnung)
   - Betraege
   - Daten
   - Namen/Firmen
   - IBANs

Antworte IMMER als JSON:
{
  "document_type": "RECHNUNG",
  "confidence": 0.95,
  "language": "de",
  "entities": {
    "invoice_number": "RE-2024-001",
    "total_amount": 1234.56,
    "date": "2024-01-15",
    "vendor": "Firma XYZ GmbH"
  }
}"""

SYSTEM_PROMPT_QUERY_ENHANCEMENT = """Du verbesserst Suchanfragen fuer bessere Retrieval-Ergebnisse.

Deine Aufgabe:
1. Analysiere die urspruengliche Suchanfrage
2. Erstelle 2-3 verbesserte Varianten

Verbesserungen koennen sein:
- Synonyme hinzufuegen (Rechnung -> Faktura, Invoice)
- Umformulierung fuer besseres Matching
- Fachbegriffe ergaenzen
- Zeitliche Eingrenzung verdeutlichen

Beispiel:
Input: "Rechnung Mueller"
Output:
- "Rechnung Faktura Mueller GmbH"
- "Invoice Mueller Company"
- "Rechnungsdokument Firma Mueller"

Antworte als JSON-Array mit den erweiterten Queries."""

SYSTEM_PROMPT_AGENT = """Du bist ein intelligenter Dokumenten-Assistent mit der Faehigkeit Aktionen auszufuehren.

DEINE AUFGABEN:
- Beantworte Fragen zu Dokumenten praezise und hilfreich
- Fuehre Aktionen aus wenn der Benutzer darum bittet
- Verwende NUR die bereitgestellten Dokument-Auszuege als Quelle
- Antworte IMMER auf Deutsch

VERFUEGBARE TOOLS:
{tools_text}

WIE DU TOOLS VERWENDEST:
1. Wenn der Benutzer eine Aktion wuenscht (z.B. "Zeige mir alle Rechnungen von Mueller"),
   ueberlege welches Tool passt
2. Erklaere ZUERST was du tun wirst (z.B. "Ich suche nach allen Rechnungen von Mueller...")
3. Rufe dann das Tool auf mit diesem Format:
   <tool_call>{{"tool": "tool_name", "params": {{"param1": "value1"}}}}</tool_call>
4. Warte auf das Ergebnis und praesentiere es dem Benutzer

SICHERHEITSREGELN:
- Bei destruktiven Aktionen (verschieben, loeschen): IMMER Bestaetigung einholen
- Keine Massen-Operationen ohne explizite Bestaetigung
- Bei Unsicherheit: lieber nachfragen als raten

STIL:
- Professionell aber freundlich
- Klar und praegnant
- Erklaere was du tust BEVOR du es tust

WICHTIG:
- Erfinde KEINE Informationen
- Wenn du keine Antwort findest, sage das ehrlich
- Zitiere relevante Stellen aus den Dokumenten"""


# =============================================================================
# TEMPLATE FUNKTIONEN
# =============================================================================

def build_rag_context(
    chunks: List[Dict[str, object]],
    max_chunks: int = 5
) -> str:
    """Baut den RAG-Kontext aus Chunks.

    Args:
        chunks: Liste von Chunk-Dictionaries mit text, document_id, similarity
        max_chunks: Maximale Anzahl Chunks

    Returns:
        Formatierter Kontext-String
    """
    if not chunks:
        return "Keine relevanten Dokumente gefunden."

    context_parts = []
    for i, chunk in enumerate(chunks[:max_chunks], 1):
        text = chunk.get("text", chunk.get("chunk_text", ""))
        doc_id = chunk.get("document_id", "unbekannt")
        similarity = chunk.get("similarity", 0)
        page = chunk.get("page_number")

        header = f"[Dokument {i}]"
        if page:
            header += f" (Seite {page})"
        header += f" [Relevanz: {similarity:.0%}]"

        context_parts.append(f"{header}\n{text}")

    return "\n\n---\n\n".join(context_parts)


def build_chat_prompt(
    question: str,
    context: str,
    history: Optional[List[Dict[str, str]]] = None,
    realtime: bool = False
) -> List[Dict[str, str]]:
    """Baut einen Chat-Prompt mit RAG-Kontext.

    Args:
        question: Benutzer-Frage
        context: RAG-Kontext (von build_rag_context)
        history: Optionale Chat-Historie
        realtime: Schnelle Telefon-Antwort

    Returns:
        Liste von Nachrichten fuer LLM
    """
    system_prompt = SYSTEM_PROMPT_TELEFON if realtime else SYSTEM_PROMPT_GENERAL

    messages = [{"role": "system", "content": system_prompt}]

    # Chat-Historie hinzufuegen
    if history:
        for msg in history[-10:]:  # Max 10 vorherige Nachrichten
            messages.append({
                "role": msg.get("role", "user"),
                "content": msg.get("content", "")
            })

    # Aktuelle Frage mit Kontext
    user_message = f"""Kontext aus relevanten Dokumenten:
{context}

---

Frage: {question}"""

    messages.append({"role": "user", "content": user_message})

    return messages


def build_customer_card_prompt(
    customer_name: str,
    context: str
) -> List[Dict[str, str]]:
    """Baut einen Prompt fuer Customer Card Generierung.

    Args:
        customer_name: Name des Kunden
        context: Aggregierter Kontext aus Kundendokumenten

    Returns:
        Nachrichten fuer LLM
    """
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT_CUSTOMER_CARD},
        {
            "role": "user",
            "content": f"""Erstelle eine Customer Card fuer: {customer_name}

Dokumente:
{context}

Antworte als JSON im spezifizierten Format."""
        }
    ]

    return messages


def build_classification_prompt(
    document_text: str,
    max_text_length: int = 3000
) -> List[Dict[str, str]]:
    """Baut einen Prompt fuer Dokumenten-Klassifikation.

    Args:
        document_text: Text des Dokuments
        max_text_length: Maximale Textlaenge

    Returns:
        Nachrichten fuer LLM
    """
    # Text kuerzen falls noetig
    if len(document_text) > max_text_length:
        document_text = document_text[:max_text_length] + "\n\n[... Text gekuerzt ...]"

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT_CLASSIFICATION},
        {
            "role": "user",
            "content": f"""Klassifiziere folgendes Dokument:

{document_text}

Antworte als JSON."""
        }
    ]

    return messages


def build_query_enhancement_prompt(
    query: str
) -> List[Dict[str, str]]:
    """Baut einen Prompt fuer Query Enhancement.

    Args:
        query: Urspruengliche Suchanfrage

    Returns:
        Nachrichten fuer LLM
    """
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT_QUERY_ENHANCEMENT},
        {
            "role": "user",
            "content": f"Verbessere diese Suchanfrage: {query}"
        }
    ]

    return messages


def build_extraction_prompt(
    document_text: str,
    extraction_schema: Dict[str, object]
) -> List[Dict[str, str]]:
    """Baut einen Prompt fuer strukturierte Datenextraktion.

    Args:
        document_text: Text des Dokuments
        extraction_schema: Schema mit zu extrahierenden Feldern

    Returns:
        Nachrichten fuer LLM
    """
    schema_description = "\n".join([
        f"- {field}: {desc}"
        for field, desc in extraction_schema.items()
    ])

    messages = [
        {
            "role": "system",
            "content": f"""Du extrahierst strukturierte Daten aus Dokumenten.

Extrahiere folgende Felder:
{schema_description}

Antworte IMMER als JSON mit genau diesen Feldnamen.
Wenn ein Feld nicht gefunden wird, setze es auf null.
Alle Texte auf Deutsch belassen."""
        },
        {
            "role": "user",
            "content": f"""Extrahiere die Daten aus diesem Dokument:

{document_text}"""
        }
    ]

    return messages


def build_report_prompt(
    report_type: str,
    context: str,
    parameters: Optional[Dict[str, object]] = None
) -> List[Dict[str, str]]:
    """Baut einen Prompt fuer Report-Generierung.

    Args:
        report_type: Art des Reports (lieferanten, vertraege, etc.)
        context: Aggregierter Kontext
        parameters: Optionale Parameter (Zeitraum, Filter, etc.)

    Returns:
        Nachrichten fuer LLM
    """
    # System-Prompt basierend auf Report-Typ
    if report_type == "lieferanten":
        system_prompt = SYSTEM_PROMPT_REPORT_LIEFERANTEN
    elif report_type == "vertraege":
        system_prompt = SYSTEM_PROMPT_REPORT_VERTRAEGE
    else:
        system_prompt = f"Du erstellst einen {report_type}-Bericht. Strukturiere die Informationen klar und uebersichtlich."

    # Parameter in Prompt einbauen
    param_text = ""
    if parameters:
        param_text = "\n\nParameter:\n" + "\n".join([
            f"- {k}: {v}" for k, v in parameters.items()
        ])

    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": f"""Erstelle den Bericht basierend auf diesen Dokumenten:

{context}
{param_text}"""
        }
    ]

    return messages


def build_agent_chat_prompt(
    question: str,
    context: str,
    history: Optional[List[Dict[str, str]]] = None,
    tools_text: str = "",
    realtime: bool = False
) -> List[Dict[str, str]]:
    """Baut einen Agent Chat-Prompt mit Tool-Calling Support.

    Args:
        question: Benutzer-Frage
        context: RAG-Kontext (von build_rag_context)
        history: Optionale Chat-Historie
        tools_text: Formatierter Tool-Text (von ToolRegistry)
        realtime: Schnelle Telefon-Antwort

    Returns:
        Liste von Nachrichten fuer LLM
    """
    # System-Prompt mit Tools
    system_prompt = SYSTEM_PROMPT_AGENT.format(tools_text=tools_text)

    messages = [{"role": "system", "content": system_prompt}]

    # Chat-Historie hinzufuegen
    if history:
        for msg in history[-10:]:  # Max 10 vorherige Nachrichten
            messages.append({
                "role": msg.get("role", "user"),
                "content": msg.get("content", "")
            })

    # Aktuelle Frage mit Kontext
    user_message = f"""Kontext aus relevanten Dokumenten:
{context}

---

Frage: {question}"""

    messages.append({"role": "user", "content": user_message})

    return messages


# =============================================================================
# EXPORT
# =============================================================================

__all__ = [
    # System Prompts
    "SYSTEM_PROMPT_GENERAL",
    "SYSTEM_PROMPT_TELEFON",
    "SYSTEM_PROMPT_CUSTOMER_CARD",
    "SYSTEM_PROMPT_REPORT_LIEFERANTEN",
    "SYSTEM_PROMPT_REPORT_VERTRAEGE",
    "SYSTEM_PROMPT_CLASSIFICATION",
    "SYSTEM_PROMPT_QUERY_ENHANCEMENT",
    "SYSTEM_PROMPT_AGENT",
    # Template Functions
    "build_rag_context",
    "build_chat_prompt",
    "build_customer_card_prompt",
    "build_classification_prompt",
    "build_query_enhancement_prompt",
    "build_extraction_prompt",
    "build_report_prompt",
    "build_agent_chat_prompt",
]
