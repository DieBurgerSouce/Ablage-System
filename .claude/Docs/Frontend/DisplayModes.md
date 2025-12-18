# Display Modes - Adaptive Darstellung

## Übersicht

Das Ablage-System unterstützt 4 Display-Modi für optimale Lesbarkeit unter verschiedenen Bedingungen.

---

## Die 4 Display-Modi

### 1. Dark Mode (Standard)

**Anwendungsfall**: Normale Nutzung, dunkle Umgebung, Nachtarbeit

| Eigenschaft | Wert |
|-------------|------|
| Hintergrund | `#1a1a1a` |
| Text | `#e0e0e0` |
| Akzent | `#4a9eff` |
| Contrast Ratio | 12.5:1 |

```css
:root[data-theme="dark"] {
  --background: 0 0% 10%;
  --foreground: 0 0% 88%;
  --primary: 213 94% 65%;
  --muted: 0 0% 15%;
  --border: 0 0% 20%;
}
```

### 2. Light Mode

**Anwendungsfall**: Gut beleuchtete Räume, Tageslicht

| Eigenschaft | Wert |
|-------------|------|
| Hintergrund | `#ffffff` |
| Text | `#1a1a1a` |
| Akzent | `#0066cc` |
| Contrast Ratio | 12.5:1 |

```css
:root[data-theme="light"] {
  --background: 0 0% 100%;
  --foreground: 0 0% 10%;
  --primary: 213 94% 40%;
  --muted: 0 0% 96%;
  --border: 0 0% 90%;
}
```

### 3. Whitescreen Mode (High Contrast)

**Anwendungsfall**: Sehbehinderungen, maximale Lesbarkeit, WCAG AAA

| Eigenschaft | Wert |
|-------------|------|
| Hintergrund | `#ffffff` |
| Text | `#000000` (reines Schwarz) |
| Akzent | `#0000ff` (reines Blau) |
| Contrast Ratio | 21:1 (Maximum) |

```css
:root[data-theme="whitescreen"] {
  --background: 0 0% 100%;
  --foreground: 0 0% 0%;
  --primary: 240 100% 50%;
  --muted: 0 0% 98%;
  --border: 0 0% 0%;
}
```

### 4. Blackscreen Mode (Inverted High Contrast)

**Anwendungsfall**: OLED-Displays, extreme Dunkelheit, Energiesparen

| Eigenschaft | Wert |
|-------------|------|
| Hintergrund | `#000000` (reines Schwarz) |
| Text | `#ffffff` (reines Weiß) |
| Akzent | `#00ff00` (helles Grün) |
| Contrast Ratio | 21:1 (Maximum) |

```css
:root[data-theme="blackscreen"] {
  --background: 0 0% 0%;
  --foreground: 0 0% 100%;
  --primary: 120 100% 50%;
  --muted: 0 0% 5%;
  --border: 0 0% 100%;
}
```

---

## Architektur

### ThemeContext

```tsx
// lib/theme/ThemeContext.tsx

import { createContext, useContext, useState, useEffect } from "react";

type Theme = "dark" | "light" | "whitescreen" | "blackscreen";

interface ThemeContextType {
  theme: Theme;
  setTheme: (theme: Theme) => void;
}

const ThemeContext = createContext<ThemeContextType | undefined>(undefined);

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setTheme] = useState<Theme>(() => {
    // 1. localStorage
    const stored = localStorage.getItem("theme") as Theme;
    if (stored) return stored;

    // 2. System Preference
    if (window.matchMedia("(prefers-color-scheme: dark)").matches) {
      return "dark";
    }

    return "light";
  });

  useEffect(() => {
    // Theme auf <html> setzen
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("theme", theme);
  }, [theme]);

  return (
    <ThemeContext.Provider value={{ theme, setTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error("useTheme must be used within ThemeProvider");
  }
  return context;
}
```

### ThemeToggle Komponente

```tsx
// components/layout/ThemeToggle.tsx

import { useTheme } from "@/lib/theme/ThemeContext";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Sun, Moon, Monitor, Contrast } from "lucide-react";

const themes = [
  { id: "dark", label: "Dunkel", icon: Moon },
  { id: "light", label: "Hell", icon: Sun },
  { id: "whitescreen", label: "Hoher Kontrast (Hell)", icon: Monitor },
  { id: "blackscreen", label: "Hoher Kontrast (Dunkel)", icon: Contrast },
] as const;

export function ThemeToggle() {
  const { theme, setTheme } = useTheme();

  const currentTheme = themes.find((t) => t.id === theme);
  const Icon = currentTheme?.icon || Moon;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" aria-label="Theme wechseln">
          <Icon className="h-5 w-5" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {themes.map(({ id, label, icon: ItemIcon }) => (
          <DropdownMenuItem
            key={id}
            onClick={() => setTheme(id)}
            className={theme === id ? "bg-accent" : ""}
          >
            <ItemIcon className="mr-2 h-4 w-4" />
            {label}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
```

---

## CSS-Variablen

### Vollständige Theme-Definition

```css
/* globals.css */

:root {
  /* Basis (Dark als Default) */
  --background: 0 0% 10%;
  --foreground: 0 0% 88%;
  --card: 0 0% 12%;
  --card-foreground: 0 0% 88%;
  --popover: 0 0% 12%;
  --popover-foreground: 0 0% 88%;
  --primary: 213 94% 65%;
  --primary-foreground: 0 0% 100%;
  --secondary: 0 0% 18%;
  --secondary-foreground: 0 0% 88%;
  --muted: 0 0% 15%;
  --muted-foreground: 0 0% 60%;
  --accent: 0 0% 18%;
  --accent-foreground: 0 0% 88%;
  --destructive: 0 72% 51%;
  --destructive-foreground: 0 0% 100%;
  --border: 0 0% 20%;
  --input: 0 0% 20%;
  --ring: 213 94% 65%;
  --radius: 0.5rem;
}

[data-theme="light"] {
  --background: 0 0% 100%;
  --foreground: 0 0% 10%;
  --card: 0 0% 100%;
  --card-foreground: 0 0% 10%;
  --primary: 213 94% 40%;
  --secondary: 0 0% 96%;
  --muted: 0 0% 96%;
  --muted-foreground: 0 0% 45%;
  --border: 0 0% 90%;
}

[data-theme="whitescreen"] {
  --background: 0 0% 100%;
  --foreground: 0 0% 0%;
  --card: 0 0% 100%;
  --card-foreground: 0 0% 0%;
  --primary: 240 100% 50%;
  --secondary: 0 0% 98%;
  --muted: 0 0% 98%;
  --border: 0 0% 0%;
  --ring: 240 100% 50%;
}

[data-theme="blackscreen"] {
  --background: 0 0% 0%;
  --foreground: 0 0% 100%;
  --card: 0 0% 0%;
  --card-foreground: 0 0% 100%;
  --primary: 120 100% 50%;
  --secondary: 0 0% 5%;
  --muted: 0 0% 5%;
  --border: 0 0% 100%;
  --ring: 120 100% 50%;
}
```

---

## Komponenten-Anpassung

### Bedingte Styles

```tsx
// Komponente mit theme-spezifischen Styles
function DocumentCard() {
  const { theme } = useTheme();

  return (
    <Card
      className={cn(
        "transition-colors",
        // High Contrast Modes: dickere Borders
        (theme === "whitescreen" || theme === "blackscreen") && "border-2",
        // Blackscreen: spezielle Hover-Farbe
        theme === "blackscreen" && "hover:bg-gray-900"
      )}
    >
      {/* Content */}
    </Card>
  );
}
```

### Tailwind-Klassen für Themes

```tsx
// Tailwind mit CSS-Variablen
<div className="bg-background text-foreground">
  <h1 className="text-primary">Überschrift</h1>
  <p className="text-muted-foreground">Beschreibung</p>
  <button className="bg-primary text-primary-foreground">
    Aktion
  </button>
</div>
```

---

## Accessibility (WCAG 2.1)

### Contrast Ratios

| Mode | Text/Background | WCAG Level |
|------|-----------------|------------|
| Dark | 12.5:1 | AAA |
| Light | 12.5:1 | AAA |
| Whitescreen | 21:1 | AAA |
| Blackscreen | 21:1 | AAA |

### Keyboard Navigation

```tsx
// Theme-Wechsel per Tastatur
useEffect(() => {
  function handleKeyDown(e: KeyboardEvent) {
    // Alt + T = Theme Toggle
    if (e.altKey && e.key === "t") {
      const themes = ["dark", "light", "whitescreen", "blackscreen"];
      const currentIndex = themes.indexOf(theme);
      const nextIndex = (currentIndex + 1) % themes.length;
      setTheme(themes[nextIndex]);
    }
  }

  document.addEventListener("keydown", handleKeyDown);
  return () => document.removeEventListener("keydown", handleKeyDown);
}, [theme, setTheme]);
```

### Reduced Motion

```css
@media (prefers-reduced-motion: reduce) {
  * {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
}
```

---

## System-Preference Detection

```tsx
// Automatische Erkennung der System-Einstellung
useEffect(() => {
  const mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");

  function handleChange(e: MediaQueryListEvent) {
    // Nur ändern, wenn kein explizites Theme gesetzt
    if (!localStorage.getItem("theme")) {
      setTheme(e.matches ? "dark" : "light");
    }
  }

  mediaQuery.addEventListener("change", handleChange);
  return () => mediaQuery.removeEventListener("change", handleChange);
}, [setTheme]);
```

---

## Testing

### Visual Regression Tests

```tsx
// Playwright Test für alle Themes
const themes = ["dark", "light", "whitescreen", "blackscreen"];

for (const theme of themes) {
  test(`DocumentCard renders correctly in ${theme} mode`, async ({ page }) => {
    await page.goto("/documents");
    await page.evaluate((t) => {
      document.documentElement.setAttribute("data-theme", t);
    }, theme);

    await expect(page.locator(".document-card").first()).toHaveScreenshot(
      `document-card-${theme}.png`
    );
  });
}
```

---

## Best Practices

### 1. Keine hardcodierten Farben

```tsx
// ❌ Schlecht
<div className="bg-gray-900 text-white">

// ✓ Gut
<div className="bg-background text-foreground">
```

### 2. Semantische Farbvariablen

```tsx
// ❌ Schlecht
<span className="text-red-500">Fehler</span>

// ✓ Gut
<span className="text-destructive">Fehler</span>
```

### 3. Icon-Kontrast sicherstellen

```tsx
// In High Contrast Modes
<Icon
  className={cn(
    "h-5 w-5",
    theme === "blackscreen" && "stroke-[2.5px]"
  )}
/>
```

---

## Änderungshistorie

| Datum | Version | Änderung |
|-------|---------|----------|
| 2024-12-18 | 1.0 | Initial Release |
