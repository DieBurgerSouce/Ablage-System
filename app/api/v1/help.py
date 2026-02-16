"""Help System API endpoints.

Provides contextual help system for:
- Help articles by context/page
- Onboarding tutorial progress tracking
- Feature tooltips
- Video tutorials
- User help preferences
- Full-text search in articles
"""

from typing import Optional, List

from app.core.types import JSONDict
from datetime import datetime, timezone
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from app.db.models import User
from app.db.database import get_db
from app.api.dependencies import get_current_active_user

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/help", tags=["help"])


# ==================== Schemas ====================

class HelpArticle(BaseModel):
    """Hilfe-Artikel Schema."""
    id: str = Field(..., description="Artikel-ID")
    title: str = Field(..., description="Artikel-Titel")
    content: str = Field(..., description="Artikel-Inhalt (Markdown)")
    category: str = Field(..., description="Kategorie: getting-started, features, troubleshooting, faq")
    context: Optional[str] = Field(None, description="Kontext/Seite (z.B. 'documents', 'ocr-settings')")
    tags: List[str] = Field(default_factory=list, description="Tags für Suche")
    video_url: Optional[str] = Field(None, description="YouTube/Video-URL")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    order: int = Field(0, description="Sortierreihenfolge innerhalb Kategorie")

    class Config:
        from_attributes = True


class HelpArticleList(BaseModel):
    """Liste von Hilfe-Artikeln."""
    articles: List[HelpArticle]
    total: int
    category: Optional[str] = None


class Tooltip(BaseModel):
    """Feature-Tooltip Schema."""
    id: str = Field(..., description="Tooltip-ID")
    feature_id: str = Field(..., description="Feature-Identifier (z.B. 'upload-button')")
    title: str = Field(..., description="Tooltip-Titel")
    content: str = Field(..., description="Tooltip-Beschreibung")
    position: str = Field("bottom", description="Position: top, bottom, left, right")
    icon: Optional[str] = Field(None, description="Icon-Name (z.B. 'info', 'lightbulb')")

    class Config:
        from_attributes = True


class OnboardingStep(BaseModel):
    """Onboarding-Schritt Schema."""
    id: str = Field(..., description="Schritt-ID")
    title: str = Field(..., description="Schritt-Titel")
    description: str = Field(..., description="Schritt-Beschreibung")
    target_element: Optional[str] = Field(None, description="CSS-Selector für Highlight")
    position: str = Field("center", description="Position des Popups")
    order: int = Field(..., description="Reihenfolge")
    completed: bool = Field(False, description="Wurde erledigt")
    icon: Optional[str] = Field(None, description="Icon für Schritt")

    class Config:
        from_attributes = True


class OnboardingStatus(BaseModel):
    """Onboarding-Fortschritt Schema."""
    steps_completed: int = Field(..., description="Anzahl erledigte Schritte")
    total_steps: int = Field(..., description="Gesamt-Anzahl Schritte")
    current_step: Optional[str] = Field(None, description="Aktueller Schritt-ID")
    completed: bool = Field(False, description="Alle Schritte erledigt")
    skipped: bool = Field(False, description="Onboarding übersprungen")
    steps: List[OnboardingStep] = Field(default_factory=list)

    class Config:
        from_attributes = True


class VideoTutorial(BaseModel):
    """Video-Tutorial Schema."""
    id: str = Field(..., description="Video-ID")
    title: str = Field(..., description="Video-Titel")
    description: str = Field(..., description="Video-Beschreibung")
    url: str = Field(..., description="Video-URL (YouTube, Vimeo, etc.)")
    thumbnail_url: Optional[str] = Field(None, description="Vorschaubild-URL")
    duration: Optional[int] = Field(None, description="Dauer in Sekunden")
    category: str = Field(..., description="Kategorie")
    tags: List[str] = Field(default_factory=list)
    order: int = Field(0, description="Sortierreihenfolge")

    class Config:
        from_attributes = True


class UserHelpPreferences(BaseModel):
    """Benutzer-Hilfe-Präferenzen Schema."""
    show_hints: bool = Field(True, description="Tooltips anzeigen")
    show_onboarding: bool = Field(True, description="Onboarding-Tour anzeigen")
    onboarding_completed: bool = Field(False, description="Onboarding abgeschlossen")
    dismissed_tooltips: List[str] = Field(default_factory=list, description="Ausgeblendete Tooltip-IDs")
    completed_steps: List[str] = Field(default_factory=list, description="Erledigte Onboarding-Schritte")
    last_updated: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Config:
        from_attributes = True


class UpdatePreferencesRequest(BaseModel):
    """Request zum Aktualisieren der Hilfe-Präferenzen."""
    show_hints: Optional[bool] = None
    show_onboarding: Optional[bool] = None
    dismiss_tooltip: Optional[str] = None
    restore_tooltip: Optional[str] = None


class SearchResultItem(BaseModel):
    """Such-Ergebnis für Artikel."""
    article: HelpArticle
    score: float = Field(..., description="Relevanz-Score (0-1)")
    highlight: Optional[str] = Field(None, description="Hervorgehobener Text-Ausschnitt")


class SearchResults(BaseModel):
    """Such-Ergebnisse Liste."""
    results: List[SearchResultItem]
    total: int
    query: str


# ==================== Default Data ====================

# Default Onboarding Steps
DEFAULT_ONBOARDING_STEPS = [
    {
        "id": "welcome",
        "title": "Willkommen bei Ablage-System",
        "description": "Lernen Sie die Grundfunktionen in 5 Schritten kennen.",
        "target_element": None,
        "position": "center",
        "order": 1,
        "icon": "hand-wave"
    },
    {
        "id": "upload-document",
        "title": "Dokument hochladen",
        "description": "Klicken Sie hier, um Ihr erstes Dokument hochzuladen.",
        "target_element": "[data-tour='upload-button']",
        "position": "bottom",
        "order": 2,
        "icon": "upload"
    },
    {
        "id": "ocr-processing",
        "title": "OCR-Verarbeitung",
        "description": "Nach dem Upload wird das Dokument automatisch mit OCR verarbeitet.",
        "target_element": "[data-tour='ocr-status']",
        "position": "left",
        "order": 3,
        "icon": "scan"
    },
    {
        "id": "search-documents",
        "title": "Dokumente durchsuchen",
        "description": "Nutzen Sie die Suche, um Dokumente schnell zu finden.",
        "target_element": "[data-tour='search-bar']",
        "position": "bottom",
        "order": 4,
        "icon": "search"
    },
    {
        "id": "organize-tags",
        "title": "Mit Tags organisieren",
        "description": "Fügen Sie Tags hinzu, um Dokumente besser zu organisieren.",
        "target_element": "[data-tour='tags-section']",
        "position": "right",
        "order": 5,
        "icon": "tag"
    }
]

# Default Help Articles
DEFAULT_HELP_ARTICLES = [
    {
        "id": "getting-started-overview",
        "title": "Erste Schritte",
        "content": """# Erste Schritte mit Ablage-System

Willkommen! Diese Anleitung führt Sie durch die wichtigsten Funktionen.

## 1. Dokument hochladen
Klicken Sie auf "Hochladen" und wählen Sie eine Datei aus (PDF, JPG, PNG).

## 2. OCR-Verarbeitung
Das System extrahiert automatisch Text aus Ihren Dokumenten mit KI-gestützter OCR.

## 3. Dokumente organisieren
- **Tags**: Fügen Sie Tags hinzu für bessere Organisation
- **Ordner**: Sortieren Sie Dokumente in Ordner
- **Suche**: Finden Sie Dokumente über Volltext-Suche

## 4. Metadaten bearbeiten
Klicken Sie auf ein Dokument, um Details wie Datum, Betrag oder Kategorie zu bearbeiten.
""",
        "category": "getting-started",
        "context": "overview",
        "tags": ["einsteiger", "erste-schritte", "basics"],
        "video_url": None,
        "order": 1
    },
    {
        "id": "upload-documents",
        "title": "Dokumente hochladen",
        "content": """# Dokumente hochladen

## Unterstützte Formate
- PDF-Dateien (.pdf)
- Bilder (.jpg, .jpeg, .png)
- Multi-Page PDFs

## Upload-Methoden
1. **Drag & Drop**: Ziehen Sie Dateien direkt in den Browser
2. **Datei-Auswahl**: Klicken Sie auf "Hochladen" → Datei auswählen
3. **Mehrfach-Upload**: Wählen Sie mehrere Dateien gleichzeitig

## Was passiert nach dem Upload?
1. Datei wird hochgeladen und gespeichert
2. OCR-Verarbeitung startet automatisch (falls aktiviert)
3. Extrahierte Daten werden angezeigt
4. Sie können Metadaten bearbeiten
""",
        "category": "features",
        "context": "documents",
        "tags": ["upload", "dokumente", "hochladen"],
        "video_url": None,
        "order": 1
    },
    {
        "id": "ocr-backends",
        "title": "OCR-Backends verstehen",
        "content": """# OCR-Backends

Ablage-System bietet mehrere OCR-Engines für beste Ergebnisse.

## Verfügbare Backends

### Auto (Empfohlen)
Wählt automatisch das beste Backend basierend auf Dokumenttyp.

### DeepSeek-Janus-Pro
- **Stärken**: Deutsche Texte, Frakturschrift, Umlaute
- **VRAM**: 12GB
- **Geschwindigkeit**: Mittel

### GOT-OCR 2.0
- **Stärken**: Tabellen, Formeln, schnelle Verarbeitung
- **VRAM**: 10GB
- **Geschwindigkeit**: Schnell

### Surya + Docling
- **Stärken**: Layout-Analyse, CPU-Fallback
- **VRAM**: 0GB (läuft auf CPU)
- **Geschwindigkeit**: Langsam

## Backend wählen
1. Gehen Sie zu Einstellungen → OCR
2. Wählen Sie "Standard-Backend"
3. Bei "Auto" wählt das System automatisch
""",
        "category": "features",
        "context": "ocr-settings",
        "tags": ["ocr", "backend", "einstellungen"],
        "video_url": None,
        "order": 2
    },
    {
        "id": "search-tips",
        "title": "Such-Tipps",
        "content": """# Effektiv suchen

## Volltext-Suche
Die Suche durchsucht:
- Dokumentnamen
- OCR-Text
- Tags
- Metadaten (Lieferant, Kundennummer, etc.)

## Such-Operatoren
- **"exakter Text"**: Findet exakte Phrase
- **tag:rechnung**: Sucht nur in Tags
- **date:2024**: Sucht nach Datum

## Filter kombinieren
1. Nutzen Sie die Kategorie-Filter (links)
2. Kombinieren Sie mit Textsuche
3. Sortieren Sie Ergebnisse nach Datum/Relevanz

## Gespeicherte Suchen
Speichern Sie häufige Suchen als Favoriten.
""",
        "category": "features",
        "context": "search",
        "tags": ["suche", "filter", "tipps"],
        "video_url": None,
        "order": 3
    },
    {
        "id": "troubleshoot-ocr-failed",
        "title": "OCR-Verarbeitung fehlgeschlagen",
        "content": """# OCR-Fehler beheben

## Häufige Ursachen

### 1. GPU-Speicher voll
**Symptom**: Fehler "CUDA out of memory"
**Lösung**:
- Warten Sie, bis andere Verarbeitungen abgeschlossen sind
- Nutzen Sie CPU-Backend (Surya)

### 2. Dokument unleserlich
**Symptom**: Kein Text erkannt oder falsche Erkennung
**Lösung**:
- Verbessern Sie Scan-Qualität (mindestens 300 DPI)
- Probieren Sie anderes OCR-Backend

### 3. Großes Dokument
**Symptom**: Timeout oder sehr langsam
**Lösung**:
- Teilen Sie PDF in kleinere Teile
- Erhöhen Sie Timeout in Einstellungen

## Support kontaktieren
Bei anhaltenden Problemen erstellen Sie ein Support-Ticket mit:
- Dokument-ID
- Fehlermeldung
- Verwendetes Backend
""",
        "category": "troubleshooting",
        "context": "ocr-failed",
        "tags": ["fehler", "ocr", "probleme"],
        "video_url": None,
        "order": 1
    },
    {
        "id": "faq-german-umlauts",
        "title": "Werden deutsche Umlaute korrekt erkannt?",
        "content": """# Umlaut-Erkennung

Ja! Ablage-System ist speziell für deutsche Dokumente optimiert.

## 100% Umlaut-Genauigkeit
- DeepSeek-Janus-Pro hat 100% Genauigkeit bei ä, ö, ü, ß
- Auch ältere Frakturschrift wird korrekt erkannt

## Best Practices
1. Nutzen Sie "Auto" oder "DeepSeek" Backend für deutsche Texte
2. Scan-Qualität: Mindestens 300 DPI
3. Bei Problemen: OCR-Backend wechseln

## Beispiel-Erkennung
- Straße → ✅ korrekt
- Gebühren → wird zu "Gebühren" korrigiert
- Muenchen → wird zu "München" korrigiert
""",
        "category": "faq",
        "context": None,
        "tags": ["deutsch", "umlaute", "faq"],
        "video_url": None,
        "order": 1
    }
]

# Default Tooltips
DEFAULT_TOOLTIPS = [
    {
        "id": "upload-button-tooltip",
        "feature_id": "upload-button",
        "title": "Dokument hochladen",
        "content": "Laden Sie PDF- oder Bild-Dateien hoch. OCR-Verarbeitung startet automatisch.",
        "position": "bottom",
        "icon": "upload"
    },
    {
        "id": "ocr-backend-tooltip",
        "feature_id": "ocr-backend-select",
        "title": "OCR-Backend wählen",
        "content": "Auto wählt automatisch das beste Backend. DeepSeek ist optimal für deutsche Texte.",
        "position": "right",
        "icon": "info"
    },
    {
        "id": "display-mode-tooltip",
        "feature_id": "display-mode-select",
        "title": "Anzeigemodus",
        "content": "Wählen Sie zwischen Dark, Light, Whitescreen und Blackscreen.",
        "position": "bottom",
        "icon": "palette"
    },
    {
        "id": "tags-tooltip",
        "feature_id": "tags-input",
        "title": "Tags hinzufügen",
        "content": "Organisieren Sie Dokumente mit Tags. Drücken Sie Enter nach jedem Tag.",
        "position": "top",
        "icon": "tag"
    },
    {
        "id": "search-tooltip",
        "feature_id": "search-bar",
        "title": "Volltext-Suche",
        "content": "Durchsucht Namen, OCR-Text, Tags und Metadaten. Nutzen Sie Filter für präzisere Ergebnisse.",
        "position": "bottom",
        "icon": "search"
    }
]

# Default Video Tutorials
DEFAULT_VIDEO_TUTORIALS = [
    {
        "id": "intro-video",
        "title": "Ablage-System Einführung (5 Min)",
        "description": "Überblick über alle Hauptfunktionen und erste Schritte.",
        "url": "https://www.youtube.com/watch?v=example1",
        "thumbnail_url": None,
        "duration": 300,
        "category": "getting-started",
        "tags": ["einführung", "overview"],
        "order": 1
    },
    {
        "id": "ocr-tutorial",
        "title": "OCR-Backends verstehen (8 Min)",
        "description": "Vergleich der OCR-Engines und wann welches Backend zu nutzen ist.",
        "url": "https://www.youtube.com/watch?v=example2",
        "thumbnail_url": None,
        "duration": 480,
        "category": "features",
        "tags": ["ocr", "backends"],
        "order": 2
    },
    {
        "id": "advanced-search",
        "title": "Erweiterte Suche & Filter (6 Min)",
        "description": "Nutzen Sie Such-Operatoren und Filter für schnelleres Finden.",
        "url": "https://www.youtube.com/watch?v=example3",
        "thumbnail_url": None,
        "duration": 360,
        "category": "features",
        "tags": ["suche", "filter", "advanced"],
        "order": 3
    }
]


# ==================== Helper Functions ====================

def get_user_help_preferences(user: User) -> JSONDict:
    """Lädt Hilfe-Präferenzen aus User.preferences oder gibt Defaults zurück."""
    if user.preferences and "help" in user.preferences:
        help_prefs = user.preferences["help"]
        return {
            "show_hints": help_prefs.get("show_hints", True),
            "show_onboarding": help_prefs.get("show_onboarding", True),
            "onboarding_completed": help_prefs.get("onboarding_completed", False),
            "dismissed_tooltips": help_prefs.get("dismissed_tooltips", []),
            "completed_steps": help_prefs.get("completed_steps", []),
            "last_updated": help_prefs.get("last_updated", datetime.now(timezone.utc).isoformat())
        }

    return {
        "show_hints": True,
        "show_onboarding": True,
        "onboarding_completed": False,
        "dismissed_tooltips": [],
        "completed_steps": [],
        "last_updated": datetime.now(timezone.utc).isoformat()
    }


async def save_user_help_preferences(
    user: User,
    preferences: JSONDict,
    db: AsyncSession
) -> None:
    """Speichert Hilfe-Präferenzen in User.preferences."""
    if not user.preferences:
        user.preferences = {}

    user.preferences["help"] = preferences
    user.preferences["help"]["last_updated"] = datetime.now(timezone.utc).isoformat()

    await db.commit()
    await db.refresh(user)


def search_articles(query: str, articles: List[JSONDict]) -> List[JSONDict]:
    """Führt Volltext-Suche in Artikeln durch."""
    query_lower = query.lower()
    results = []

    for article in articles:
        score = 0.0
        highlight = None

        # Titel-Match (höchste Priorität)
        if query_lower in article["title"].lower():
            score += 1.0
            highlight = article["title"]

        # Content-Match
        if query_lower in article["content"].lower():
            score += 0.5
            # Extrahiere Kontext (50 Zeichen vor und nach Match)
            content_lower = article["content"].lower()
            idx = content_lower.find(query_lower)
            if idx != -1:
                start = max(0, idx - 50)
                end = min(len(article["content"]), idx + len(query) + 50)
                highlight = "..." + article["content"][start:end] + "..."

        # Tags-Match
        for tag in article.get("tags", []):
            if query_lower in tag.lower():
                score += 0.7

        # Context-Match
        if article.get("context") and query_lower in article["context"].lower():
            score += 0.3

        if score > 0:
            results.append({
                "article": article,
                "score": min(score, 1.0),  # Cap at 1.0
                "highlight": highlight
            })

    # Sortiere nach Score absteigend
    results.sort(key=lambda x: x["score"], reverse=True)
    return results


# ==================== Endpoints ====================

@router.get("/articles", response_model=HelpArticleList)
async def get_help_articles(
    category: Optional[str] = Query(None, description="Filter nach Kategorie"),
    context: Optional[str] = Query(None, description="Filter nach Kontext/Seite"),
    current_user: User = Depends(get_current_active_user)
):
    """Alle Hilfe-Artikel abrufen.

    Filter nach Kategorie:
    - `getting-started`: Erste Schritte
    - `features`: Feature-Erklärungen
    - `troubleshooting`: Problembehebung
    - `faq`: Häufige Fragen

    Filter nach Context/Seite:
    - `documents`: Dokumente-Seite
    - `ocr-settings`: OCR-Einstellungen
    - `search`: Suche
    - etc.
    """
    articles = list(DEFAULT_HELP_ARTICLES)

    # Filter nach Kategorie
    if category:
        articles = [a for a in articles if a["category"] == category]

    # Filter nach Context
    if context:
        articles = [a for a in articles if a.get("context") == context]

    # Sortiere nach order
    articles.sort(key=lambda x: x.get("order", 0))

    logger.info(
        "help_articles_fetched",
        user_id=str(current_user.id),
        category=category,
        context=context,
        total=len(articles)
    )

    return HelpArticleList(
        articles=[HelpArticle(**a) for a in articles],
        total=len(articles),
        category=category
    )


@router.get("/articles/{article_id}", response_model=HelpArticle)
async def get_help_article(
    article_id: str,
    current_user: User = Depends(get_current_active_user)
):
    """Einzelnen Hilfe-Artikel abrufen."""
    article = next(
        (a for a in DEFAULT_HELP_ARTICLES if a["id"] == article_id),
        None
    )

    if not article:
        raise HTTPException(
            status_code=404,
            detail=f"Hilfe-Artikel '{article_id}' nicht gefunden"
        )

    logger.info(
        "help_article_viewed",
        user_id=str(current_user.id),
        article_id=article_id
    )

    return HelpArticle(**article)


@router.get("/articles/context/{context}", response_model=HelpArticleList)
async def get_help_articles_by_context(
    context: str,
    current_user: User = Depends(get_current_active_user)
):
    """Hilfe-Artikel für spezifischen Kontext/Seite abrufen.

    Gibt kontextspezifische Hilfe-Artikel zurück, z.B.:
    - `context=documents` → Artikel über Dokumente-Verwaltung
    - `context=ocr-settings` → Artikel über OCR-Konfiguration
    """
    articles = [
        a for a in DEFAULT_HELP_ARTICLES
        if a.get("context") == context
    ]

    # Sortiere nach order
    articles.sort(key=lambda x: x.get("order", 0))

    logger.info(
        "contextual_help_fetched",
        user_id=str(current_user.id),
        context=context,
        total=len(articles)
    )

    return HelpArticleList(
        articles=[HelpArticle(**a) for a in articles],
        total=len(articles),
        category=None
    )


@router.get("/search", response_model=SearchResults)
async def search_help_articles(
    q: str = Query(..., min_length=2, description="Suchbegriff"),
    current_user: User = Depends(get_current_active_user)
):
    """Volltext-Suche in Hilfe-Artikeln.

    Durchsucht:
    - Titel (höchste Priorität)
    - Inhalt
    - Tags
    - Kontext

    Ergebnisse werden nach Relevanz sortiert.
    """
    results = search_articles(q, DEFAULT_HELP_ARTICLES)

    logger.info(
        "help_search_performed",
        user_id=str(current_user.id),
        query=q,
        results_count=len(results)
    )

    return SearchResults(
        results=[
            SearchResultItem(
                article=HelpArticle(**r["article"]),
                score=r["score"],
                highlight=r["highlight"]
            )
            for r in results
        ],
        total=len(results),
        query=q
    )


@router.get("/tooltips/{feature_id}", response_model=Tooltip)
async def get_feature_tooltip(
    feature_id: str,
    current_user: User = Depends(get_current_active_user)
):
    """Tooltip für spezifisches Feature abrufen.

    Feature-IDs:
    - `upload-button`: Upload-Button
    - `ocr-backend-select`: OCR-Backend Auswahl
    - `display-mode-select`: Display-Mode Auswahl
    - `tags-input`: Tags-Input
    - `search-bar`: Such-Leiste
    """
    # Prüfe ob Tooltip vom User ausgeblendet wurde
    prefs = get_user_help_preferences(current_user)
    if feature_id in prefs["dismissed_tooltips"]:
        raise HTTPException(
            status_code=404,
            detail=f"Tooltip für '{feature_id}' wurde ausgeblendet"
        )

    tooltip = next(
        (t for t in DEFAULT_TOOLTIPS if t["feature_id"] == feature_id),
        None
    )

    if not tooltip:
        raise HTTPException(
            status_code=404,
            detail=f"Tooltip für Feature '{feature_id}' nicht gefunden"
        )

    return Tooltip(**tooltip)


@router.get("/onboarding", response_model=OnboardingStatus)
async def get_onboarding_status(
    current_user: User = Depends(get_current_active_user)
):
    """Onboarding-Fortschritt abrufen.

    Gibt aktuellen Status und alle Schritte zurück.
    """
    prefs = get_user_help_preferences(current_user)
    completed_steps_ids = prefs["completed_steps"]

    # Füge completed-Status zu Steps hinzu
    steps = []
    for step_data in DEFAULT_ONBOARDING_STEPS:
        step = OnboardingStep(**step_data)
        step.completed = step.id in completed_steps_ids
        steps.append(step)

    # Finde aktuellen Schritt (erster nicht-erledigter)
    current_step = next(
        (s.id for s in steps if not s.completed),
        None
    )

    return OnboardingStatus(
        steps_completed=len(completed_steps_ids),
        total_steps=len(DEFAULT_ONBOARDING_STEPS),
        current_step=current_step,
        completed=len(completed_steps_ids) >= len(DEFAULT_ONBOARDING_STEPS),
        skipped=prefs["onboarding_completed"] and len(completed_steps_ids) < len(DEFAULT_ONBOARDING_STEPS),
        steps=steps
    )


@router.patch("/onboarding/step/{step_id}")
async def mark_onboarding_step_completed(
    step_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Onboarding-Schritt als erledigt markieren."""
    # Validiere step_id
    valid_steps = [s["id"] for s in DEFAULT_ONBOARDING_STEPS]
    if step_id not in valid_steps:
        raise HTTPException(
            status_code=404,
            detail=f"Onboarding-Schritt '{step_id}' nicht gefunden"
        )

    prefs = get_user_help_preferences(current_user)

    # Füge step_id hinzu falls nicht vorhanden
    if step_id not in prefs["completed_steps"]:
        prefs["completed_steps"].append(step_id)

    # Prüfe ob alle Schritte erledigt
    if len(prefs["completed_steps"]) >= len(DEFAULT_ONBOARDING_STEPS):
        prefs["onboarding_completed"] = True

    await save_user_help_preferences(current_user, prefs, db)

    logger.info(
        "onboarding_step_completed",
        user_id=str(current_user.id),
        step_id=step_id,
        total_completed=len(prefs["completed_steps"])
    )

    return {
        "message": f"Schritt '{step_id}' als erledigt markiert",
        "steps_completed": len(prefs["completed_steps"]),
        "total_steps": len(DEFAULT_ONBOARDING_STEPS)
    }


@router.post("/onboarding/skip")
async def skip_onboarding(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Onboarding-Tour überspringen.

    Markiert Onboarding als abgeschlossen ohne alle Schritte zu absolvieren.
    """
    prefs = get_user_help_preferences(current_user)
    prefs["onboarding_completed"] = True
    prefs["show_onboarding"] = False

    await save_user_help_preferences(current_user, prefs, db)

    logger.info(
        "onboarding_skipped",
        user_id=str(current_user.id)
    )

    return {
        "message": "Onboarding wurde übersprungen",
        "onboarding_completed": True
    }


@router.post("/onboarding/reset")
async def reset_onboarding(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Onboarding zurücksetzen.

    Setzt alle erledigten Schritte zurück und startet Tour neu.
    """
    prefs = get_user_help_preferences(current_user)
    prefs["onboarding_completed"] = False
    prefs["completed_steps"] = []
    prefs["show_onboarding"] = True

    await save_user_help_preferences(current_user, prefs, db)

    logger.info(
        "onboarding_reset",
        user_id=str(current_user.id)
    )

    return {
        "message": "Onboarding wurde zurückgesetzt",
        "onboarding_completed": False,
        "steps_completed": 0
    }


@router.get("/videos", response_model=List[VideoTutorial])
async def get_video_tutorials(
    category: Optional[str] = Query(None, description="Filter nach Kategorie"),
    current_user: User = Depends(get_current_active_user)
):
    """Video-Tutorial-Liste abrufen.

    Optional nach Kategorie filtern:
    - `getting-started`: Erste Schritte
    - `features`: Feature-Tutorials
    """
    videos = list(DEFAULT_VIDEO_TUTORIALS)

    # Filter nach Kategorie
    if category:
        videos = [v for v in videos if v["category"] == category]

    # Sortiere nach order
    videos.sort(key=lambda x: x.get("order", 0))

    logger.info(
        "video_tutorials_fetched",
        user_id=str(current_user.id),
        category=category,
        total=len(videos)
    )

    return [VideoTutorial(**v) for v in videos]


@router.get("/preferences", response_model=UserHelpPreferences)
async def get_help_preferences(
    current_user: User = Depends(get_current_active_user)
):
    """Hilfe-Präferenzen des Benutzers abrufen."""
    prefs = get_user_help_preferences(current_user)

    return UserHelpPreferences(
        show_hints=prefs["show_hints"],
        show_onboarding=prefs["show_onboarding"],
        onboarding_completed=prefs["onboarding_completed"],
        dismissed_tooltips=prefs["dismissed_tooltips"],
        completed_steps=prefs["completed_steps"],
        last_updated=datetime.fromisoformat(prefs["last_updated"])
    )


@router.patch("/preferences", response_model=UserHelpPreferences)
async def update_help_preferences(
    request: UpdatePreferencesRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Hilfe-Präferenzen aktualisieren.

    Unterstützte Aktionen:
    - `show_hints`: Tooltips ein/aus
    - `show_onboarding`: Onboarding-Tour ein/aus
    - `dismiss_tooltip`: Spezifischen Tooltip ausblenden
    - `restore_tooltip`: Tooltip wieder einblenden
    """
    prefs = get_user_help_preferences(current_user)

    # Update Flags
    if request.show_hints is not None:
        prefs["show_hints"] = request.show_hints

    if request.show_onboarding is not None:
        prefs["show_onboarding"] = request.show_onboarding

    # Tooltip ausblenden
    if request.dismiss_tooltip:
        if request.dismiss_tooltip not in prefs["dismissed_tooltips"]:
            prefs["dismissed_tooltips"].append(request.dismiss_tooltip)
            logger.info(
                "tooltip_dismissed",
                user_id=str(current_user.id),
                tooltip_id=request.dismiss_tooltip
            )

    # Tooltip wiederherstellen
    if request.restore_tooltip:
        if request.restore_tooltip in prefs["dismissed_tooltips"]:
            prefs["dismissed_tooltips"].remove(request.restore_tooltip)
            logger.info(
                "tooltip_restored",
                user_id=str(current_user.id),
                tooltip_id=request.restore_tooltip
            )

    await save_user_help_preferences(current_user, prefs, db)

    logger.info(
        "help_preferences_updated",
        user_id=str(current_user.id),
        show_hints=prefs["show_hints"],
        show_onboarding=prefs["show_onboarding"]
    )

    return UserHelpPreferences(
        show_hints=prefs["show_hints"],
        show_onboarding=prefs["show_onboarding"],
        onboarding_completed=prefs["onboarding_completed"],
        dismissed_tooltips=prefs["dismissed_tooltips"],
        completed_steps=prefs["completed_steps"],
        last_updated=datetime.fromisoformat(prefs["last_updated"])
    )
