# Help System API - Dokumentation

**Status**: ✅ Production-Ready
**Version**: 1.0
**Erstellt**: 2026-01-19

## Übersicht

Die Help System API bietet ein umfassendes kontextuelles Hilfe-System mit:
- Hilfe-Artikeln nach Kontext/Seite
- Interaktivem Onboarding-Tutorial
- Feature-Tooltips
- Video-Tutorials
- Benutzer-Präferenzen
- Volltext-Suche

## Architektur

### Datenspeicherung

Alle Daten werden im `User.preferences` JSONB-Feld gespeichert unter dem Schlüssel `"help"`:

```json
{
  "help": {
    "show_hints": true,
    "show_onboarding": true,
    "onboarding_completed": false,
    "dismissed_tooltips": ["upload-button-tooltip"],
    "completed_steps": ["welcome", "upload-document"],
    "last_updated": "2026-01-19T12:00:00Z"
  }
}
```

### Default-Daten

Hilfe-Inhalte sind als Python-Konstanten in `app/api/v1/help.py` definiert:
- `DEFAULT_HELP_ARTICLES` - Hilfe-Artikel
- `DEFAULT_ONBOARDING_STEPS` - Onboarding-Schritte
- `DEFAULT_TOOLTIPS` - Feature-Tooltips
- `DEFAULT_VIDEO_TUTORIALS` - Video-Tutorials

## API Endpoints

### Hilfe-Artikel

#### GET /api/v1/help/articles
Alle Hilfe-Artikel abrufen.

**Query-Parameter**:
- `category` (optional): Filter nach Kategorie
  - `getting-started` - Erste Schritte
  - `features` - Feature-Erklärungen
  - `troubleshooting` - Problembehebung
  - `faq` - Häufige Fragen
- `context` (optional): Filter nach Kontext/Seite (z.B. `documents`, `ocr-settings`)

**Response**:
```json
{
  "articles": [
    {
      "id": "getting-started-overview",
      "title": "Erste Schritte",
      "content": "# Erste Schritte mit Ablage-System\n\n...",
      "category": "getting-started",
      "context": "overview",
      "tags": ["einsteiger", "erste-schritte", "basics"],
      "video_url": null,
      "created_at": "2026-01-19T12:00:00Z",
      "updated_at": "2026-01-19T12:00:00Z",
      "order": 1
    }
  ],
  "total": 6,
  "category": "getting-started"
}
```

---

#### GET /api/v1/help/articles/{article_id}
Einzelnen Hilfe-Artikel abrufen.

**Path-Parameter**:
- `article_id` - Artikel-ID

**Response**: `HelpArticle`-Objekt

**Fehler**:
- `404` - Artikel nicht gefunden

---

#### GET /api/v1/help/articles/context/{context}
Hilfe-Artikel für spezifischen Kontext abrufen.

**Path-Parameter**:
- `context` - Kontext/Seite (z.B. `documents`, `ocr-settings`)

**Response**: `HelpArticleList` mit kontextspezifischen Artikeln

**Anwendungsfall**: Zeige relevante Hilfe-Artikel auf spezifischen Seiten.

---

#### GET /api/v1/help/search
Volltext-Suche in Hilfe-Artikeln.

**Query-Parameter**:
- `q` (required, min 2 Zeichen) - Suchbegriff

**Durchsucht**:
- Titel (höchste Priorität)
- Inhalt
- Tags
- Kontext

**Response**:
```json
{
  "results": [
    {
      "article": { /* HelpArticle */ },
      "score": 1.0,
      "highlight": "...extrahiert Text aus Ihren Dokumenten mit KI-gestützter OCR..."
    }
  ],
  "total": 3,
  "query": "ocr"
}
```

**Score-Berechnung**:
- Titel-Match: 1.0
- Content-Match: 0.5
- Tags-Match: 0.7
- Context-Match: 0.3

Ergebnisse werden nach Score absteigend sortiert.

---

### Tooltips

#### GET /api/v1/help/tooltips/{feature_id}
Tooltip für spezifisches Feature abrufen.

**Path-Parameter**:
- `feature_id` - Feature-Identifier

**Verfügbare Feature-IDs**:
- `upload-button` - Upload-Button
- `ocr-backend-select` - OCR-Backend Auswahl
- `display-mode-select` - Display-Mode Auswahl
- `tags-input` - Tags-Input
- `search-bar` - Such-Leiste

**Response**:
```json
{
  "id": "upload-button-tooltip",
  "feature_id": "upload-button",
  "title": "Dokument hochladen",
  "content": "Laden Sie PDF- oder Bild-Dateien hoch. OCR-Verarbeitung startet automatisch.",
  "position": "bottom",
  "icon": "upload"
}
```

**Fehler**:
- `404` - Tooltip nicht gefunden ODER vom User ausgeblendet

**Frontend-Integration**:
```tsx
// Tooltip wird nicht angezeigt wenn dismissed
try {
  const tooltip = await api.get(`/help/tooltips/${featureId}`);
  showTooltip(tooltip);
} catch (error) {
  // 404 = tooltip dismissed oder nicht gefunden
}
```

---

### Onboarding

#### GET /api/v1/help/onboarding
Onboarding-Fortschritt abrufen.

**Response**:
```json
{
  "steps_completed": 2,
  "total_steps": 5,
  "current_step": "ocr-processing",
  "completed": false,
  "skipped": false,
  "steps": [
    {
      "id": "welcome",
      "title": "Willkommen bei Ablage-System",
      "description": "Lernen Sie die Grundfunktionen in 5 Schritten kennen.",
      "target_element": null,
      "position": "center",
      "order": 1,
      "completed": true,
      "icon": "hand-wave"
    },
    {
      "id": "upload-document",
      "title": "Dokument hochladen",
      "description": "Klicken Sie hier, um Ihr erstes Dokument hochzuladen.",
      "target_element": "[data-tour='upload-button']",
      "position": "bottom",
      "order": 2,
      "completed": true,
      "icon": "upload"
    },
    {
      "id": "ocr-processing",
      "title": "OCR-Verarbeitung",
      "description": "Nach dem Upload wird das Dokument automatisch mit OCR verarbeitet.",
      "target_element": "[data-tour='ocr-status']",
      "position": "left",
      "order": 3,
      "completed": false,
      "icon": "scan"
    }
  ]
}
```

**Default-Schritte**:
1. `welcome` - Begrüßung
2. `upload-document` - Dokument hochladen
3. `ocr-processing` - OCR-Verarbeitung
4. `search-documents` - Suche nutzen
5. `organize-tags` - Tags organisieren

---

#### PATCH /api/v1/help/onboarding/step/{step_id}
Onboarding-Schritt als erledigt markieren.

**Path-Parameter**:
- `step_id` - Schritt-ID

**Response**:
```json
{
  "message": "Schritt 'upload-document' als erledigt markiert",
  "steps_completed": 2,
  "total_steps": 5
}
```

**Fehler**:
- `404` - Schritt-ID ungültig

**Verhalten**:
- Fügt `step_id` zu `completed_steps` hinzu
- Setzt `onboarding_completed=true` wenn alle Schritte erledigt

---

#### POST /api/v1/help/onboarding/skip
Onboarding-Tour überspringen.

**Response**:
```json
{
  "message": "Onboarding wurde übersprungen",
  "onboarding_completed": true
}
```

**Verhalten**:
- Setzt `onboarding_completed=true`
- Setzt `show_onboarding=false`
- Schritte bleiben unverändert

---

#### POST /api/v1/help/onboarding/reset
Onboarding zurücksetzen.

**Response**:
```json
{
  "message": "Onboarding wurde zurückgesetzt",
  "onboarding_completed": false,
  "steps_completed": 0
}
```

**Verhalten**:
- Setzt `onboarding_completed=false`
- Leert `completed_steps`
- Setzt `show_onboarding=true`

---

### Video-Tutorials

#### GET /api/v1/help/videos
Video-Tutorial-Liste abrufen.

**Query-Parameter**:
- `category` (optional): Filter nach Kategorie

**Response**:
```json
[
  {
    "id": "intro-video",
    "title": "Ablage-System Einführung (5 Min)",
    "description": "Überblick über alle Hauptfunktionen und erste Schritte.",
    "url": "https://www.youtube.com/watch?v=example1",
    "thumbnail_url": null,
    "duration": 300,
    "category": "getting-started",
    "tags": ["einführung", "overview"],
    "order": 1
  }
]
```

---

### Präferenzen

#### GET /api/v1/help/preferences
Hilfe-Präferenzen des Benutzers abrufen.

**Response**:
```json
{
  "show_hints": true,
  "show_onboarding": true,
  "onboarding_completed": false,
  "dismissed_tooltips": ["upload-button-tooltip"],
  "completed_steps": ["welcome", "upload-document"],
  "last_updated": "2026-01-19T12:00:00Z"
}
```

---

#### PATCH /api/v1/help/preferences
Hilfe-Präferenzen aktualisieren.

**Request**:
```json
{
  "show_hints": false,
  "show_onboarding": true,
  "dismiss_tooltip": "upload-button-tooltip",
  "restore_tooltip": "search-bar-tooltip"
}
```

**Felder** (alle optional):
- `show_hints` - Tooltips ein/aus
- `show_onboarding` - Onboarding-Tour ein/aus
- `dismiss_tooltip` - Spezifischen Tooltip ausblenden
- `restore_tooltip` - Tooltip wieder einblenden

**Response**: Aktualisierte `UserHelpPreferences`

**Verhalten**:
- `dismiss_tooltip`: Fügt zu `dismissed_tooltips` hinzu
- `restore_tooltip`: Entfernt aus `dismissed_tooltips`

---

## Schemas

### HelpArticle
```typescript
interface HelpArticle {
  id: string;
  title: string;
  content: string;              // Markdown
  category: "getting-started" | "features" | "troubleshooting" | "faq";
  context: string | null;       // Seite/Kontext (z.B. "documents")
  tags: string[];
  video_url: string | null;
  created_at: string;
  updated_at: string;
  order: number;
}
```

### Tooltip
```typescript
interface Tooltip {
  id: string;
  feature_id: string;
  title: string;
  content: string;
  position: "top" | "bottom" | "left" | "right";
  icon: string | null;
}
```

### OnboardingStep
```typescript
interface OnboardingStep {
  id: string;
  title: string;
  description: string;
  target_element: string | null;  // CSS-Selector
  position: string;
  order: number;
  completed: boolean;
  icon: string | null;
}
```

### OnboardingStatus
```typescript
interface OnboardingStatus {
  steps_completed: number;
  total_steps: number;
  current_step: string | null;
  completed: boolean;
  skipped: boolean;
  steps: OnboardingStep[];
}
```

### VideoTutorial
```typescript
interface VideoTutorial {
  id: string;
  title: string;
  description: string;
  url: string;
  thumbnail_url: string | null;
  duration: number | null;      // Sekunden
  category: string;
  tags: string[];
  order: number;
}
```

### UserHelpPreferences
```typescript
interface UserHelpPreferences {
  show_hints: boolean;
  show_onboarding: boolean;
  onboarding_completed: boolean;
  dismissed_tooltips: string[];
  completed_steps: string[];
  last_updated: string;
}
```

---

## Frontend-Integration

### React Hook Beispiel

```typescript
// useHelp.ts
import { useQuery, useMutation } from '@tanstack/react-query';
import { api } from '@/lib/api';

export function useHelpArticles(category?: string, context?: string) {
  return useQuery({
    queryKey: ['help-articles', category, context],
    queryFn: async () => {
      const params = new URLSearchParams();
      if (category) params.set('category', category);
      if (context) params.set('context', context);
      return api.get(`/api/v1/help/articles?${params}`);
    }
  });
}

export function useOnboardingStatus() {
  return useQuery({
    queryKey: ['onboarding-status'],
    queryFn: () => api.get('/api/v1/help/onboarding')
  });
}

export function useCompleteStep() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (stepId: string) =>
      api.patch(`/api/v1/help/onboarding/step/${stepId}`),
    onSuccess: () => {
      queryClient.invalidateQueries(['onboarding-status']);
    }
  });
}

export function useDismissTooltip() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (tooltipId: string) =>
      api.patch('/api/v1/help/preferences', {
        dismiss_tooltip: tooltipId
      }),
    onSuccess: () => {
      queryClient.invalidateQueries(['help-preferences']);
    }
  });
}
```

### Onboarding-Tour Integration

```tsx
// OnboardingTour.tsx
import { useOnboardingStatus, useCompleteStep } from '@/hooks/useHelp';

export function OnboardingTour() {
  const { data: status } = useOnboardingStatus();
  const completeStep = useCompleteStep();

  if (!status || status.completed || status.skipped) {
    return null;
  }

  const currentStep = status.steps.find(
    s => s.id === status.current_step
  );

  if (!currentStep) return null;

  return (
    <div className="onboarding-overlay">
      {currentStep.target_element && (
        <Spotlight selector={currentStep.target_element} />
      )}

      <Card position={currentStep.position}>
        <CardHeader>
          <Icon name={currentStep.icon} />
          <h3>{currentStep.title}</h3>
        </CardHeader>

        <CardContent>
          <p>{currentStep.description}</p>
        </CardContent>

        <CardFooter>
          <Button onClick={() => skipOnboarding()}>
            Überspringen
          </Button>
          <Button onClick={() => completeStep.mutate(currentStep.id)}>
            Weiter ({status.steps_completed + 1}/{status.total_steps})
          </Button>
        </CardFooter>
      </Card>
    </div>
  );
}
```

### Contextual Help Button

```tsx
// ContextualHelp.tsx
import { useHelpArticles } from '@/hooks/useHelp';

interface Props {
  context: string;
}

export function ContextualHelp({ context }: Props) {
  const { data } = useHelpArticles(undefined, context);

  if (!data?.articles.length) {
    return null;
  }

  return (
    <Popover>
      <PopoverTrigger>
        <Button variant="ghost" size="sm">
          <HelpCircle className="h-4 w-4" />
        </Button>
      </PopoverTrigger>

      <PopoverContent>
        <h4>Hilfe zu dieser Seite</h4>
        <ul>
          {data.articles.map(article => (
            <li key={article.id}>
              <a href={`/help/${article.id}`}>
                {article.title}
              </a>
            </li>
          ))}
        </ul>
      </PopoverContent>
    </Popover>
  );
}
```

### Smart Tooltip

```tsx
// SmartTooltip.tsx
import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { useDismissTooltip } from '@/hooks/useHelp';

interface Props {
  featureId: string;
  children: React.ReactNode;
}

export function SmartTooltip({ featureId, children }: Props) {
  const { data: tooltip } = useQuery({
    queryKey: ['tooltip', featureId],
    queryFn: () => api.get(`/api/v1/help/tooltips/${featureId}`),
    retry: false  // 404 wenn dismissed
  });

  const dismiss = useDismissTooltip();

  if (!tooltip) {
    return <>{children}</>;
  }

  return (
    <Tooltip>
      <TooltipTrigger>{children}</TooltipTrigger>

      <TooltipContent side={tooltip.position}>
        <div className="flex items-start gap-2">
          <Icon name={tooltip.icon} />
          <div>
            <h5 className="font-semibold">{tooltip.title}</h5>
            <p className="text-sm">{tooltip.content}</p>
          </div>
          <Button
            size="xs"
            variant="ghost"
            onClick={() => dismiss.mutate(tooltip.id)}
          >
            <X className="h-3 w-3" />
          </Button>
        </div>
      </TooltipContent>
    </Tooltip>
  );
}
```

---

## Best Practices

### 1. Kontext-Spezifische Hilfe
Zeige immer relevante Hilfe für die aktuelle Seite:
```tsx
<ContextualHelp context="documents" />
```

### 2. Progressive Onboarding
Zeige Onboarding nur neuen Benutzern:
```tsx
useEffect(() => {
  if (isNewUser && !onboardingCompleted) {
    showOnboarding();
  }
}, [isNewUser, onboardingCompleted]);
```

### 3. Tooltip-Management
Respektiere ausgeblendete Tooltips:
```tsx
// Tooltip wird automatisch nicht angezeigt wenn dismissed
<SmartTooltip featureId="upload-button">
  <Button>Hochladen</Button>
</SmartTooltip>
```

### 4. Such-Integration
Biete globale Hilfe-Suche:
```tsx
<Command>
  <CommandInput placeholder="Hilfe durchsuchen..." />
  <CommandList>
    {searchResults.map(result => (
      <CommandItem key={result.article.id}>
        <span className="font-medium">{result.article.title}</span>
        <span className="text-xs text-muted">{result.highlight}</span>
      </CommandItem>
    ))}
  </CommandList>
</Command>
```

---

## Erweiterung

### Neue Hilfe-Artikel hinzufügen

In `app/api/v1/help.py`:

```python
DEFAULT_HELP_ARTICLES.append({
    "id": "my-new-article",
    "title": "Neue Funktion XYZ",
    "content": """# Neue Funktion XYZ

Beschreibung...
""",
    "category": "features",
    "context": "my-feature",
    "tags": ["xyz", "neu"],
    "video_url": None,
    "order": 10
})
```

### Neue Onboarding-Schritte

```python
DEFAULT_ONBOARDING_STEPS.append({
    "id": "new-step",
    "title": "Neuer Schritt",
    "description": "Beschreibung des Schritts",
    "target_element": "[data-tour='new-feature']",
    "position": "bottom",
    "order": 6,
    "icon": "sparkles"
})
```

### Neue Tooltips

```python
DEFAULT_TOOLTIPS.append({
    "id": "new-tooltip",
    "feature_id": "new-feature-button",
    "title": "Neue Funktion",
    "content": "Beschreibung der neuen Funktion",
    "position": "right",
    "icon": "info"
})
```

---

## Logging

Alle wichtigen Aktionen werden geloggt:

```python
logger.info(
    "help_article_viewed",
    user_id=str(current_user.id),
    article_id=article_id
)

logger.info(
    "onboarding_step_completed",
    user_id=str(current_user.id),
    step_id=step_id,
    total_completed=len(prefs["completed_steps"])
)

logger.info(
    "tooltip_dismissed",
    user_id=str(current_user.id),
    tooltip_id=request.dismiss_tooltip
)
```

---

## Security

### Multi-Tenant Isolation
- Präferenzen sind user-spezifisch (via `current_user`)
- Keine Cross-User Zugriffe möglich

### Input-Validierung
- `article_id`, `step_id`, `feature_id` werden gegen bekannte Listen validiert
- `search?q=` hat Mindestlänge 2

### PII-Compliance
- Keine sensiblen Daten in Logs
- User-IDs werden als UUID geloggt

---

## Testing

### Unit-Tests

```python
# test_help_api.py
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_get_help_articles(client: AsyncClient, auth_headers):
    response = await client.get(
        "/api/v1/help/articles?category=getting-started",
        headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] > 0
    assert all(a["category"] == "getting-started" for a in data["articles"])

@pytest.mark.asyncio
async def test_complete_onboarding_step(client: AsyncClient, auth_headers):
    response = await client.patch(
        "/api/v1/help/onboarding/step/welcome",
        headers=auth_headers
    )
    assert response.status_code == 200
    assert "Schritt 'welcome' als erledigt markiert" in response.json()["message"]

@pytest.mark.asyncio
async def test_dismiss_tooltip(client: AsyncClient, auth_headers):
    response = await client.patch(
        "/api/v1/help/preferences",
        json={"dismiss_tooltip": "upload-button-tooltip"},
        headers=auth_headers
    )
    assert response.status_code == 200

    # Tooltip sollte jetzt 404 geben
    response = await client.get(
        "/api/v1/help/tooltips/upload-button",
        headers=auth_headers
    )
    assert response.status_code == 404
```

### Integration-Tests

```python
@pytest.mark.asyncio
async def test_onboarding_flow(client: AsyncClient, auth_headers):
    # 1. Status abrufen
    response = await client.get("/api/v1/help/onboarding", headers=auth_headers)
    assert response.status_code == 200
    status = response.json()
    assert status["steps_completed"] == 0

    # 2. Ersten Schritt erledigen
    await client.patch(
        "/api/v1/help/onboarding/step/welcome",
        headers=auth_headers
    )

    # 3. Status prüfen
    response = await client.get("/api/v1/help/onboarding", headers=auth_headers)
    status = response.json()
    assert status["steps_completed"] == 1
    assert status["current_step"] == "upload-document"
```

---

## Performance

### Caching-Strategie

Frontend sollte Hilfe-Daten cachen:

```typescript
// TanStack Query mit staleTime
const { data } = useHelpArticles(category, context, {
  staleTime: 5 * 60 * 1000,  // 5 Minuten
  cacheTime: 30 * 60 * 1000  // 30 Minuten
});
```

### Lazy-Loading

Lade Hilfe-Daten nur wenn benötigt:

```tsx
const [showHelp, setShowHelp] = useState(false);
const { data } = useHelpArticles(category, context, {
  enabled: showHelp  // Query nur wenn showHelp=true
});
```

---

## Roadmap

### Future Enhancements

1. **Persistent Help Content**
   - Migriere zu DB-Tabellen statt Python-Konstanten
   - Admin-UI für Hilfe-Content-Management

2. **Analytics**
   - Track welche Artikel am häufigsten gelesen werden
   - A/B Testing für Onboarding-Flows

3. **Multilingual Support**
   - Englische Übersetzungen
   - Automatische Spracherkennung

4. **Interactive Tutorials**
   - Step-by-Step Guided Walkthroughs
   - Code-Playgrounds für API-Endpoints

5. **AI-Powered Help**
   - Chatbot für kontextuelle Fragen
   - Auto-Suggest basierend auf User-Verhalten

---

**Version**: 1.0
**Letzte Aktualisierung**: 2026-01-19
