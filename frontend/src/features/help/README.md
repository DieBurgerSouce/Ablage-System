# Help System Frontend

Kontextuelles Hilfe-System mit Onboarding-Tour, Tooltips, Video-Tutorials und Hilfe-Artikeln.

## Features

- **Hilfe-Panel**: Ausfahrendes Panel mit Artikeln, Videos und Einstellungen
- **Onboarding-Tour**: Schrittweise Einführung für neue Benutzer
- **Kontextuelle Tooltips**: Feature-spezifische Hilfe-Hinweise
- **Feature Hints**: Inline-Hinweise mit Expand/Collapse
- **Video-Tutorials**: Eingebettete Videos (YouTube/Vimeo)
- **Volltextsuche**: Durchsuchbare Hilfe-Artikel
- **User-Präferenzen**: Personalisierte Hilfe-Einstellungen

## Installation

### 1. Provider einbinden

Füge den `HelpProvider` in deiner App hinzu:

```tsx
import { HelpProvider } from '@/features/help';

function App() {
  return (
    <HelpProvider>
      {/* Deine App-Komponenten */}
    </HelpProvider>
  );
}
```

### 2. Help Button einbinden

Füge den `HelpButton` zu deinem Layout hinzu:

```tsx
import { HelpButton } from '@/features/help';

function Layout() {
  return (
    <div>
      {/* Layout-Content */}
      <HelpButton />
    </div>
  );
}
```

### 3. Onboarding-Tour einbinden

Zeige die Onboarding-Tour beim ersten Login:

```tsx
import { OnboardingTour } from '@/features/help';

function Dashboard() {
  return (
    <div>
      <OnboardingTour autoStart={true} />
      {/* Dashboard-Content */}
    </div>
  );
}
```

## Nutzungsbeispiele

### Kontextuelle Tooltips

Füge Tooltips zu Formularfeldern hinzu:

```tsx
import { ContextualTooltip } from '@/features/help';

function DocumentForm() {
  return (
    <div className="flex items-center gap-2">
      <Label>OCR-Backend</Label>
      <ContextualTooltip featureId="ocr-backend-selection" />
    </div>
  );
}
```

Inline-Tooltips in Texten:

```tsx
import { InlineTooltipTrigger } from '@/features/help';

function InfoText() {
  return (
    <p>
      Die Konfidenz-Schwelle{' '}
      <InlineTooltipTrigger featureId="confidence-threshold" />{' '}
      bestimmt, wie sicher die OCR-Erkennung sein muss.
    </p>
  );
}
```

### Feature Hints

Zeige expandierbare Hinweise:

```tsx
import { FeatureHint } from '@/features/help';

function UploadSection() {
  return (
    <div>
      <FeatureHint
        id="upload-drag-drop"
        title="Tipp: Drag & Drop"
        defaultOpen={false}
        dismissible={true}
      >
        Sie können Dokumente auch direkt per Drag & Drop in diesen Bereich
        ziehen. Das System erkennt automatisch den Dokumenttyp.
      </FeatureHint>
    </div>
  );
}
```

Kompakte Quick-Hints:

```tsx
import { QuickHint } from '@/features/help';

function SettingsPage() {
  return (
    <div>
      <QuickHint id="auto-ocr-hint">
        Aktivieren Sie Auto-OCR, um Dokumente automatisch nach dem Upload zu
        verarbeiten.
      </QuickHint>
    </div>
  );
}
```

### Hilfe-Suche

Einbindung der Volltextsuche:

```tsx
import { HelpSearch } from '@/features/help';

function Sidebar() {
  const handleArticleSelect = (articleId: string) => {
    // Navigiere zum Artikel oder öffne Help Panel
    console.log('Selected article:', articleId);
  };

  return (
    <div className="p-4">
      <HelpSearch onSelectArticle={handleArticleSelect} />
    </div>
  );
}
```

Kompakte Variante:

```tsx
import { CompactHelpSearch } from '@/features/help';

function MobileSidebar() {
  return (
    <div className="p-2">
      <CompactHelpSearch onSelectArticle={(id) => console.log(id)} />
    </div>
  );
}
```

### Onboarding-Progress

Zeige den Fortschritt der Onboarding-Tour:

```tsx
import { OnboardingProgress } from '@/features/help';

function DashboardWelcome() {
  const handleContinueTour = () => {
    // Tour fortsetzen
  };

  return (
    <div>
      <OnboardingProgress onContinue={handleContinueTour} />
    </div>
  );
}
```

Kompakte Variante:

```tsx
import { OnboardingProgress } from '@/features/help';

function Sidebar() {
  return (
    <div>
      <OnboardingProgress compact={true} />
    </div>
  );
}
```

### React Query Hooks

Verwende die Hooks für direkte Daten-Zugriffe:

```tsx
import {
  useHelpArticles,
  useContextHelp,
  useOnboardingStatus,
} from '@/features/help';

function CustomHelpComponent() {
  // Alle Artikel einer Kategorie
  const { data: articles } = useHelpArticles('documents');

  // Kontextuelle Artikel für aktuelle Seite
  const { data: contextArticles } = useContextHelp('/dashboard');

  // Onboarding-Status
  const { data: onboarding } = useOnboardingStatus();

  return <div>{/* Custom UI */}</div>;
}
```

## Data Tour Attribute

Füge `data-tour` Attribute zu Elementen hinzu, die in der Onboarding-Tour hervorgehoben werden sollen:

```tsx
function UploadButton() {
  return (
    <Button data-tour="upload-button">
      Dokument hochladen
    </Button>
  );
}

function SearchBar() {
  return (
    <Input
      data-tour="search-bar"
      placeholder="Dokumente durchsuchen..."
    />
  );
}
```

## Styling

Das System nutzt shadcn/ui Komponenten und ist vollständig Theme-kompatibel.

### Spotlight-Effekt

Die Onboarding-Tour nutzt einen CSS Spotlight-Effekt. Elemente mit der Klasse `tour-spotlight` werden hervorgehoben.

### Dark Mode

Alle Komponenten unterstützen automatisch Dark Mode über Tailwind CSS.

## API-Abhängigkeiten

Das Frontend erwartet folgende Backend-Endpoints:

- `GET /api/v1/help/articles` - Hilfe-Artikel abrufen
- `GET /api/v1/help/articles/:id` - Einzelnen Artikel abrufen
- `GET /api/v1/help/articles/context/:context` - Kontextuelle Artikel
- `GET /api/v1/help/search?q=query` - Volltextsuche
- `GET /api/v1/help/tooltips/:featureId` - Tooltip abrufen
- `GET /api/v1/help/onboarding/status` - Onboarding-Status
- `POST /api/v1/help/onboarding/steps/:id/complete` - Schritt abschließen
- `POST /api/v1/help/onboarding/skip` - Onboarding überspringen
- `GET /api/v1/help/videos` - Video-Tutorials
- `GET /api/v1/help/preferences` - User-Präferenzen
- `PATCH /api/v1/help/preferences` - Präferenzen aktualisieren
- `POST /api/v1/help/tooltips/:id/dismiss` - Tooltip ausblenden

## TypeScript

Alle Komponenten sind vollständig typisiert. Importiere Types direkt:

```tsx
import type {
  HelpArticle,
  HelpCategory,
  Tooltip,
  OnboardingStatus,
  VideoTutorial,
} from '@/features/help';
```

## Best Practices

1. **Feature-IDs**: Nutze konsistente, beschreibende IDs für Tooltips und Hints
2. **Dismissible**: Wichtige Hinweise sollten `dismissible={true}` haben
3. **Context**: Setze sinnvolle Context-Werte für kontextuelle Hilfe
4. **Tour-Attribute**: Füge `data-tour` zu allen wichtigen UI-Elementen hinzu
5. **Kategorien**: Nutze die vordefinierten `HelpCategory` Enums

## Performance

- Alle API-Calls werden via TanStack Query gecacht
- Suche ist debounced (300ms)
- Videos werden lazy-loaded
- Tooltips werden nur bei Bedarf geladen
