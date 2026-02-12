# Visual Regression Testing mit Storybook

Dieses Verzeichnis enthält alle Storybook Stories für Visual Regression Testing.

## Setup

### 1. Abhängigkeiten installieren

```bash
npm install --save-dev @storybook/react-vite @storybook/addon-essentials @storybook/addon-a11y @storybook/addon-interactions @storybook/addon-links @storybook/addon-coverage @storybook/test-runner @storybook/test @storybook/theming @storybook/manager-api @percy/storybook axe-playwright
```

### 2. Storybook starten

```bash
npm run storybook
```

Storybook ist dann erreichbar unter: http://localhost:6006

### 3. Tests ausführen

```bash
# Interaction + A11y Tests
npm run test:storybook

# Visual Regression Tests mit Percy
npm run test:visual
```

## Verzeichnisstruktur

```
src/stories/
+-- README.md              # Diese Datei
+-- Button.stories.tsx     # Button-Varianten
+-- Card.stories.tsx       # Card-Komponenten
+-- Alert.stories.tsx      # Alert/Notification
+-- DataTable.stories.tsx  # EnterpriseDataTable
+-- Form.stories.tsx       # Formular-Elemente
+-- Modal.stories.tsx      # Dialog/Sheet/AlertDialog
+-- Navigation.stories.tsx # Tabs/Breadcrumbs/Pagination
+-- Charts.stories.tsx     # Recharts-basierte Charts
```

## Story-Struktur

Jede Story-Datei folgt diesem Muster:

```tsx
import type { Meta, StoryObj } from '@storybook/react';
import { MyComponent } from '@/components/ui/my-component';

const meta: Meta<typeof MyComponent> = {
    title: 'UI/MyComponent',
    component: MyComponent,
    parameters: {
        layout: 'centered',
    },
    tags: ['autodocs'],
};

export default meta;
type Story = StoryObj<typeof meta>;

// Basis-Story
export const Default: Story = {
    args: {
        children: 'Default',
    },
};

// Dark Mode Story
export const DarkMode: Story = {
    parameters: {
        backgrounds: { default: 'dark' },
    },
    decorators: [
        (Story) => (
            <div className="dark">
                <Story />
            </div>
        ),
    ],
};
```

## Viewports

Vordefinierte Viewports für responsive Testing:

| Name | Breite | Höhe |
|------|--------|-------|
| Mobile | 375px | 667px |
| Tablet | 768px | 1024px |
| Desktop | 1280px | 800px |
| Widescreen | 1920px | 1080px |

## A11y Testing

Jede Story wird automatisch auf Barrierefreiheit getestet:

- WCAG 2.0 Level A
- WCAG 2.0 Level AA
- WCAG 2.1 Level A
- WCAG 2.1 Level AA
- Best Practices

Probleme werden im Storybook A11y Panel angezeigt.

## Percy Visual Testing

### Setup

1. Percy Token setzen:
```bash
export PERCY_TOKEN=<your-token>
```

2. Storybook bauen und Percy ausführen:
```bash
npm run test:visual
```

### Breakpoints

Percy macht Snapshots bei:
- 375px (Mobile)
- 768px (Tablet)
- 1280px (Desktop)
- 1920px (Widescreen)

### Ausgeschlossene Stories

Folgende Patterns werden von Percy ausgeschlossen:
- `**/DarkMode` - Separat getestet
- `**/*Loading*` - Animationen
- `**/*Controlled*` - Braucht Interaktion

## Best Practices

1. **Jede Variante testen**: Erstelle separate Stories für jede visuelle Variante
2. **Dark Mode**: Inkludiere immer eine Dark Mode Story
3. **Responsive**: Nutze die Viewports um responsive Verhalten zu testen
4. **Interaction Tests**: Nutze `play` Functions für Interaktionen
5. **A11y**: Behebe alle A11y-Fehler bevor du Visual Tests machst

## Neue Story hinzufügen

1. Erstelle `ComponentName.stories.tsx` in `src/stories/`
2. Importiere die Komponente
3. Definiere Meta-Objekt mit `title`, `component`, `parameters`
4. Exportiere Stories für jede Variante
5. Füge Dark Mode Story hinzu
6. Teste lokal mit `npm run storybook`
7. Committe und erstelle PR - Percy läuft automatisch in CI
