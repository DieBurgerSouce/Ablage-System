/**
 * Theme Utilities - OKLCH Color Generation
 *
 * Utilities für die dynamische Generierung von OKLCH-basierten Farbpaletten.
 * OKLCH bietet perceptuell einheitliche Farben für bessere Accessibility.
 */

import type { ThemeConfig } from './types';

// ==================== OKLCH Utilities ====================

/**
 * Generiert einen OKLCH Farbwert
 */
export function oklch(l: number, c: number, h: number): string {
  return `oklch(${l} ${c} ${h})`;
}

/**
 * Konvertiert einen HSL-Hue zu OKLCH
 * OKLCH verwendet den gleichen Hue-Kreis wie HSL
 */
export function hueToOklch(hue: number): number {
  return hue;
}

// ==================== Saturation Multipliers ====================

const saturationMultipliers = {
  low: 0.6,
  medium: 1.0,
  high: 1.3,
};

// ==================== Density Spacing ====================

/**
 * CSS-Variablen für unterschiedliche UI-Dichte
 * cozy: Standard-Abstände für komfortables Arbeiten
 * compact: Reduzierte Abstände für Power-User
 */
const densityVariables = {
  cozy: {
    '--density-spacing-xs': '0.25rem',  // 4px
    '--density-spacing-sm': '0.5rem',   // 8px
    '--density-spacing-md': '0.75rem',  // 12px
    '--density-spacing-lg': '1rem',     // 16px
    '--density-spacing-xl': '1.5rem',   // 24px
    '--density-padding-cell': '0.75rem', // Table cell padding
    '--density-row-height': '3rem',      // 48px - Table row height
    '--density-card-padding': '1.5rem',  // Card padding
    '--density-gap': '1rem',             // Grid/flex gap
    '--density-button-height': '2.5rem', // 40px
    '--density-input-height': '2.5rem',  // 40px
  },
  compact: {
    '--density-spacing-xs': '0.125rem', // 2px
    '--density-spacing-sm': '0.25rem',  // 4px
    '--density-spacing-md': '0.5rem',   // 8px
    '--density-spacing-lg': '0.75rem',  // 12px
    '--density-spacing-xl': '1rem',     // 16px
    '--density-padding-cell': '0.5rem', // Table cell padding
    '--density-row-height': '2.25rem',   // 36px - Table row height
    '--density-card-padding': '1rem',   // Card padding
    '--density-gap': '0.5rem',          // Grid/flex gap
    '--density-button-height': '2rem',  // 32px
    '--density-input-height': '2rem',   // 32px
  },
} as const;

// ==================== Color Generation ====================

interface ColorSet {
  base: string;
  foreground: string;
  muted: string;
}

/**
 * Generiert eine Farbpalette basierend auf Hue und Modus
 */
export function generatePrimaryColors(
  hue: number,
  saturation: 'low' | 'medium' | 'high',
  isDark: boolean
): ColorSet {
  const mult = saturationMultipliers[saturation];
  const chroma = 0.08 * mult;

  if (isDark) {
    return {
      base: oklch(0.88, 0.16 * mult, hue), // Bright for dark mode
      foreground: oklch(0.15, 0.02, hue),
      muted: oklch(0.3, chroma, hue),
    };
  }

  return {
    base: oklch(0.35, chroma, hue),
    foreground: oklch(0.98, 0.01, hue),
    muted: oklch(0.95, chroma * 0.5, hue),
  };
}

/**
 * Generiert Akzentfarben
 */
export function generateAccentColors(
  hue: number,
  saturation: 'low' | 'medium' | 'high',
  isDark: boolean
): ColorSet {
  const mult = saturationMultipliers[saturation];
  const chroma = 0.16 * mult;

  if (isDark) {
    return {
      base: oklch(0.82, chroma, hue),
      foreground: oklch(0.2, 0.02, hue),
      muted: oklch(0.25, chroma * 0.5, hue),
    };
  }

  return {
    base: oklch(0.88, chroma, hue),
    foreground: oklch(0.2, 0.02, hue),
    muted: oklch(0.96, chroma * 0.3, hue),
  };
}

// ==================== CSS Variable Generation ====================

/**
 * Generiert CSS Custom Properties für die Theme-Konfiguration
 */
export function generateCSSVariables(config: ThemeConfig): Record<string, string> {
  const isDark = config.displayMode === 'dark';
  const isHighContrast =
    config.displayMode === 'whitescreen' || config.displayMode === 'blackscreen';

  // Density-Variablen sind immer verfügbar
  const density = config.density || 'cozy';
  const densityVars = densityVariables[density];

  // High contrast modes haben feste Farben, aber density wird angewendet
  if (isHighContrast) {
    return {
      ...densityVars,
    };
  }

  const primary = generatePrimaryColors(
    config.primaryHue,
    config.saturation,
    isDark
  );
  const accent = generateAccentColors(config.accentHue, config.saturation, isDark);

  return {
    '--primary': primary.base,
    '--primary-foreground': primary.foreground,
    '--accent': accent.base,
    '--accent-foreground': accent.foreground,
    '--radius': `${config.radius}rem`,
    ...densityVars,
  };
}

/**
 * Gibt die Density-Variablen für eine bestimmte Dichte zurück
 */
export function getDensityVariables(density: 'cozy' | 'compact'): Record<string, string> {
  return densityVariables[density];
}

/**
 * Wendet CSS-Variablen auf das Document an
 */
export function applyCSSVariables(variables: Record<string, string>): void {
  const root = document.documentElement;

  Object.entries(variables).forEach(([key, value]) => {
    root.style.setProperty(key, value);
  });
}

/**
 * Entfernt custom CSS-Variablen (reset zu CSS defaults)
 */
export function removeCSSVariables(keys: string[]): void {
  const root = document.documentElement;

  keys.forEach((key) => {
    root.style.removeProperty(key);
  });
}

// ==================== Color Preview ====================

/**
 * Generiert Preview-Farben für die Theme-Vorschau
 */
export function generatePreviewColors(hue: number): {
  light: string;
  dark: string;
  accent: string;
} {
  return {
    light: oklch(0.35, 0.08, hue),
    dark: oklch(0.88, 0.16, hue),
    accent: oklch(0.82, 0.16, hue),
  };
}

// ==================== Hue Labels ====================

/**
 * Beschreibende Namen für Hue-Werte
 */
export function getHueLabel(hue: number): string {
  const hueRanges: [number, number, string][] = [
    [0, 15, 'Rot'],
    [15, 45, 'Orange'],
    [45, 75, 'Gelb'],
    [75, 105, 'Lime'],
    [105, 135, 'Grün'],
    [135, 165, 'Tuerkis'],
    [165, 195, 'Cyan'],
    [195, 225, 'Himmelblau'],
    [225, 255, 'Blau'],
    [255, 285, 'Indigo'],
    [285, 315, 'Violett'],
    [315, 345, 'Magenta'],
    [345, 360, 'Rot'],
  ];

  const match = hueRanges.find(([min, max]) => hue >= min && hue < max);
  return match ? match[2] : 'Unbekannt';
}

// ==================== Export ====================

export default {
  oklch,
  generatePrimaryColors,
  generateAccentColors,
  generateCSSVariables,
  getDensityVariables,
  applyCSSVariables,
  removeCSSVariables,
  generatePreviewColors,
  getHueLabel,
};
