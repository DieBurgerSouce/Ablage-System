---
name: frontend-design
description: Erstelle hochwertige, produktionsreife Frontend-Interfaces fuer das Ablage-System. Nutze diesen Skill wenn du UI-Komponenten, Pages, Dashboards oder React-Components baust. Unterstuetzt die 4 Display-Modi (Dark, Light, Whitescreen, Blackscreen) und shadcn/ui + Tailwind CSS.
---

# Frontend Design (Ablage-System)

Erstelle distinctive, produktionsreife Frontend-Interfaces die generische "AI-Aesthetik" vermeiden.

## Projekt-Stack

- **Framework**: React 18 + TypeScript 5.x
- **Routing**: TanStack Router
- **UI Library**: shadcn/ui + Tailwind CSS
- **State**: TanStack Query
- **Icons**: Lucide React

## 4 Display-Modi (PFLICHT)

Alle Komponenten MUESSEN diese Modi unterstuetzen:

| Modus | Background | Text | Accent | Use Case |
|-------|------------|------|--------|----------|
| Dark (default) | `#1a1a1a` | `#e0e0e0` | `#4a9eff` | Low-light |
| Light | `#ffffff` | `#1a1a1a` | `#0066cc` | Daylight |
| Whitescreen | `#ffffff` | `#000000` | `#0000ff` | High contrast (WCAG AAA) |
| Blackscreen | `#000000` | `#ffffff` | `#00ff00` | OLED, Accessibility |

## Design-Denken VOR dem Code

Bevor du codest, klaere:

1. **Zweck**: Welches Problem loest die Komponente?
2. **Ton**: Minimalistisch, professionell, technisch?
3. **Constraints**: Display-Modi, Accessibility, Mobile?
4. **Differenzierung**: Was macht sie einzigartig?

## Aesthetische Prinzipien

### Typografie
- **VERMEIDE**: Arial, Inter, generische Fonts
- **NUTZE**: Distinctive Display-Fonts + refined Body-Fonts
- Im Ablage-System: System-Fonts fuer Performance

### Farben & Themes
- CSS Variables fuer Theme-Support
- Dominante Farben mit scharfen Akzenten
- Keine zaghaften Paletten

### Motion
- CSS-Loesungen bevorzugen
- Staggered Reveals bei Page Load
- Hover States mit Scroll-Trigger

### Spatial Composition
- Unerwartete Layouts
- Asymmetrie und Overlap
- Grosszuegiger Negative Space

## Code-Pattern: Theme-aware Component

```tsx
import { cn } from "@/lib/utils"

interface CardProps {
  children: React.ReactNode
  className?: string
}

export function Card({ children, className }: CardProps) {
  return (
    <div className={cn(
      // Base styles
      "rounded-lg border p-6 shadow-sm",
      // Theme-aware (funktioniert mit allen 4 Modi)
      "bg-card text-card-foreground border-border",
      // Hover/Focus states
      "transition-all hover:shadow-md focus-within:ring-2",
      className
    )}>
      {children}
    </div>
  )
}
```

## Vermeide "AI Slop"

NICHT:
- Uebermaessige Gradients
- Generische Icons ohne Kontext
- Cookie-cutter Card-Layouts
- Predictable Grid-Systeme

STATTDESSEN:
- Kontext-spezifisches Design
- Intentionale Asymmetrie
- Charaktervolle Details
- Deutsche UX-Texte

## Accessibility (WCAG 2.1 AA)

```tsx
// Immer aria-labels fuer Icons
<Button aria-label="Dokument hochladen">
  <Upload className="h-4 w-4" />
</Button>

// Focus-visible fuer Keyboard-Navigation
<input className="focus-visible:ring-2 focus-visible:ring-primary" />

// Kontrast-Ratios beachten (besonders Whitescreen/Blackscreen)
```

## Deutsche UX-Texte

### KRITISCH: Echte Umlaute verwenden!

```tsx
// ✅ RICHTIG - Echte Umlaute
<Button>Löschen</Button>
<Label>Größe</Label>
<span>Übertragung läuft...</span>
<Alert>Datei erfolgreich geändert</Alert>

// ❌ FALSCH - Keine Ersatzschreibung!
<Button>Loeschen</Button>  // NIEMALS!
<Label>Groesse</Label>     // NIEMALS!
<span>Uebertragung</span>  // NIEMALS!
```

**Regel**: IMMER ä, ö, ü, ß verwenden - NIEMALS ae, oe, ue, ss!

### Beispiele

```tsx
// Buttons
<Button>Speichern</Button>
<Button variant="destructive">Löschen</Button>

// Feedback
<Toast>Dokument erfolgreich verarbeitet</Toast>
<Alert>Fehler bei der OCR-Verarbeitung</Alert>

// Formulare
<Label>Datei auswählen</Label>
<Input placeholder="Suchbegriff eingeben..." />

// Navigation
<NavItem>Übersicht</NavItem>
<NavItem>Größenänderung</NavItem>

// Status
<Badge>Geändert</Badge>
<Status>Verfügbar</Status>
```

## Komponenten-Bibliothek

Nutze shadcn/ui Komponenten:
```bash
npx shadcn-ui@latest add button card dialog input
```

Dann anpassen fuer Ablage-System:
- Deutsche Labels
- 4 Display-Modi Support
- Projekt-spezifische Varianten
