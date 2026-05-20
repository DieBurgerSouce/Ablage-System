/**
 * Theme Types and Configuration
 *
 * Definiert die Typen für das Theming System.
 */

import { z } from 'zod';

// ==================== Display Mode ====================

export const displayModeSchema = z.enum(['light', 'dark', 'whitescreen', 'blackscreen']);
export type DisplayMode = z.infer<typeof displayModeSchema>;

// ==================== Theme Customization ====================

/**
 * Verfügbare Radius-Werte für UI-Elemente
 */
export const radiusValues = ['0', '0.25', '0.5', '0.75', '1'] as const;
export type RadiusValue = typeof radiusValues[number];

/**
 * Verfügbare Density-Werte für UI-Elemente
 * cozy: Standard-Abstände (default)
 * compact: Reduzierte Abstände für Power-User mit 4K-Monitoren
 */
export const densityValues = ['cozy', 'compact'] as const;
export type DensityValue = typeof densityValues[number];

/**
 * Theme Konfiguration
 */
export const themeConfigSchema = z.object({
  /** Aktiver Display-Modus */
  displayMode: displayModeSchema,

  /**
   * Primaerfarbe Hue (0-360)
   * Standard: 250 (industrielles Blau)
   */
  primaryHue: z.number().min(0).max(360).default(250),

  /**
   * Akzentfarbe Hue (0-360)
   * Standard: 85 (Precision Yellow)
   */
  accentHue: z.number().min(0).max(360).default(85),

  /**
   * Border Radius für UI-Elemente
   * @default '0.5'
   */
  radius: z.enum(radiusValues).default('0.5'),

  /**
   * Sättigung der Farben
   * @default 'medium'
   */
  saturation: z.enum(['low', 'medium', 'high']).default('medium'),

  /**
   * UI Dichte / Spacing
   * cozy: Standard-Abstände
   * compact: Reduzierte Abstände für mehr Informationsdichte
   * @default 'cozy'
   */
  density: z.enum(densityValues).default('cozy'),
});

export type ThemeConfig = z.infer<typeof themeConfigSchema>;

// ==================== Default Values ====================

export const defaultThemeConfig: ThemeConfig = {
  displayMode: 'light',
  primaryHue: 250,
  accentHue: 85,
  radius: '0.5',
  saturation: 'medium',
  density: 'cozy',
};

// ==================== Preset Themes ====================

export interface ThemePreset {
  id: string;
  name: string;
  description: string;
  config: Partial<ThemeConfig>;
}

export const themePresets: ThemePreset[] = [
  {
    id: 'industrial',
    name: 'Industrial (Standard)',
    description: 'Professionelles Blau mit Gelb-Akzent',
    config: {
      primaryHue: 250,
      accentHue: 85,
      saturation: 'medium',
    },
  },
  {
    id: 'ocean',
    name: 'Ocean',
    description: 'Beruhigendes Meerblau mit Türkis-Akzent',
    config: {
      primaryHue: 200,
      accentHue: 175,
      saturation: 'medium',
    },
  },
  {
    id: 'forest',
    name: 'Forest',
    description: 'Natürliches Grün mit Amber-Akzent',
    config: {
      primaryHue: 145,
      accentHue: 40,
      saturation: 'medium',
    },
  },
  {
    id: 'sunset',
    name: 'Sunset',
    description: 'Warmes Orange mit Rosa-Akzent',
    config: {
      primaryHue: 25,
      accentHue: 330,
      saturation: 'high',
    },
  },
  {
    id: 'minimal',
    name: 'Minimal',
    description: 'Gedämpftes Grau mit subtilen Akzenten',
    config: {
      primaryHue: 220,
      accentHue: 220,
      saturation: 'low',
    },
  },
];

// ==================== Storage Keys ====================

export const THEME_STORAGE_KEY = 'ablage-display-mode';
export const THEME_CONFIG_STORAGE_KEY = 'ablage-theme-config';
