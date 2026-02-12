/**
 * ThemeContext - Enhanced Theme Management
 *
 * Verwaltet Display-Modus und Theme-Anpassungen mit:
 * - 4 Display-Modi (light, dark, whitescreen, blackscreen)
 * - Anpassbare Primaer- und Akzentfarben
 * - Border Radius Anpassung
 * - Sättigung
 * - LocalStorage Persistenz
 * - System Preference Detection
 */

import { createContext, useContext, useEffect, useState, useCallback, useMemo, useRef } from 'react';
import type { ReactNode } from 'react';
import {
    type DisplayMode,
    type ThemeConfig,
    type RadiusValue,
    type DensityValue,
    defaultThemeConfig,
    themeConfigSchema,
    THEME_STORAGE_KEY,
    THEME_CONFIG_STORAGE_KEY,
} from './types';
import {
    generateCSSVariables,
    applyCSSVariables,
    removeCSSVariables,
} from './theme-utils';
import { logger } from '@/lib/logger';

// ==================== Context Type ====================

interface ThemeContextType {
    // Display Mode
    displayMode: DisplayMode;
    setDisplayMode: (mode: DisplayMode) => void;

    // Theme Customization
    primaryHue: number;
    setPrimaryHue: (hue: number) => void;
    accentHue: number;
    setAccentHue: (hue: number) => void;
    radius: RadiusValue;
    setRadius: (radius: RadiusValue) => void;
    saturation: 'low' | 'medium' | 'high';
    setSaturation: (saturation: 'low' | 'medium' | 'high') => void;
    density: DensityValue;
    setDensity: (density: DensityValue) => void;

    // Full config access
    themeConfig: ThemeConfig;
    setThemeConfig: (config: Partial<ThemeConfig>) => void;

    // Utilities
    resetToDefaults: () => void;
    isCustomized: boolean;
}

const ThemeContext = createContext<ThemeContextType | undefined>(undefined);

// ==================== Storage Functions ====================

function getStoredConfig(): ThemeConfig {
    try {
        // Try to load full config
        const configStr = localStorage.getItem(THEME_CONFIG_STORAGE_KEY);
        if (configStr) {
            const parsed = JSON.parse(configStr);
            const result = themeConfigSchema.safeParse(parsed);
            if (result.success) {
                return result.data;
            }
        }

        // Fall back to legacy display mode storage
        const legacyMode = localStorage.getItem(THEME_STORAGE_KEY);
        if (legacyMode && ['light', 'dark', 'whitescreen', 'blackscreen'].includes(legacyMode)) {
            return { ...defaultThemeConfig, displayMode: legacyMode as DisplayMode };
        }

        // Fall back to system preference
        if (window.matchMedia('(prefers-color-scheme: dark)').matches) {
            return { ...defaultThemeConfig, displayMode: 'dark' };
        }

        return defaultThemeConfig;
    } catch (e) {
        logger.error('Theme-Konfiguration konnte nicht geladen werden', e);
        return defaultThemeConfig;
    }
}

function saveConfig(config: ThemeConfig): void {
    try {
        localStorage.setItem(THEME_CONFIG_STORAGE_KEY, JSON.stringify(config));
        // Also save display mode separately for backwards compatibility
        localStorage.setItem(THEME_STORAGE_KEY, config.displayMode);
    } catch (e) {
        logger.error('Theme-Konfiguration konnte nicht gespeichert werden', e);
    }
}

// ==================== Display Mode Application ====================

function applyDisplayMode(mode: DisplayMode): void {
    const root = document.documentElement;
    root.classList.remove('light', 'dark', 'whitescreen', 'blackscreen');
    root.classList.add(mode);
}

// ==================== Provider ====================

interface ThemeProviderProps {
    children: ReactNode;
}

export function ThemeProvider({ children }: ThemeProviderProps) {
    const [config, setConfigState] = useState<ThemeConfig>(getStoredConfig);

    // Check if config is customized from defaults
    // WICHTIG: Memoized um unnötige Re-Renders zu verhindern
    const isCustomized = useMemo(
        () =>
            config.primaryHue !== defaultThemeConfig.primaryHue ||
            config.accentHue !== defaultThemeConfig.accentHue ||
            config.radius !== defaultThemeConfig.radius ||
            config.saturation !== defaultThemeConfig.saturation ||
            config.density !== defaultThemeConfig.density,
        [config.primaryHue, config.accentHue, config.radius, config.saturation, config.density]
    );

    // Apply display mode
    useEffect(() => {
        applyDisplayMode(config.displayMode);
    }, [config.displayMode]);

    // Apply CSS variables when config changes
    useEffect(() => {
        // Don't apply custom colors in high contrast modes
        if (config.displayMode === 'whitescreen' || config.displayMode === 'blackscreen') {
            removeCSSVariables(['--primary', '--primary-foreground', '--accent', '--accent-foreground']);
            // Only apply radius
            applyCSSVariables({ '--radius': `${config.radius}rem` });
            return;
        }

        const variables = generateCSSVariables(config);
        applyCSSVariables(variables);
    }, [config]);

    // Save to storage when config changes
    useEffect(() => {
        saveConfig(config);
    }, [config]);

    // Use ref to avoid stale closure in media query listener
    const configRef = useRef(config);
    configRef.current = config;

    // Listen for system preference changes
    useEffect(() => {
        const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');

        const handleChange = (e: MediaQueryListEvent) => {
            // Access current config via ref to avoid stale closure
            const currentMode = configRef.current.displayMode;

            // ENTERPRISE FIX: Nutze nur configRef statt localStorage für den Check
            // localStorage.getItem während setConfigState erzeugt Race Condition
            // mit dem Save-Effect (Storage write vs read)
            //
            // Logik: Nur auto-switch wenn User auf light/dark ist (nicht high contrast)
            // Der Ref-Wert ist die "Source of Truth" - localStorage wird asynchron
            // vom Save-Effect aktualisiert und könnte veraltet sein.
            if (currentMode === 'light' || currentMode === 'dark') {
                // ENTERPRISE FIX: Atomare Operation - speichere UND update zusammen
                // Dies verhindert Race Condition zwischen mediaQuery-Event und Save-Effect
                const newMode = e.matches ? 'dark' : 'light';
                const newConfig: ThemeConfig = {
                    ...configRef.current,
                    displayMode: newMode,
                };

                // Speichere SYNCHRON vor setState um Konsistenz zu garantieren
                saveConfig(newConfig);
                setConfigState(newConfig);
            }
            // Wenn User explizit whitescreen/blackscreen gewählt hat,
            // wird NICHT auto-switched (currentMode ist weder light noch dark)
        };

        mediaQuery.addEventListener('change', handleChange);
        return () => mediaQuery.removeEventListener('change', handleChange);
    }, []); // Empty deps - handler uses ref for current value

    // ==================== Setters ====================

    const setDisplayMode = useCallback((mode: DisplayMode) => {
        setConfigState((prev) => ({ ...prev, displayMode: mode }));
    }, []);

    const setPrimaryHue = useCallback((hue: number) => {
        setConfigState((prev) => ({ ...prev, primaryHue: Math.max(0, Math.min(360, hue)) }));
    }, []);

    const setAccentHue = useCallback((hue: number) => {
        setConfigState((prev) => ({ ...prev, accentHue: Math.max(0, Math.min(360, hue)) }));
    }, []);

    const setRadius = useCallback((radius: RadiusValue) => {
        setConfigState((prev) => ({ ...prev, radius }));
    }, []);

    const setSaturation = useCallback((saturation: 'low' | 'medium' | 'high') => {
        setConfigState((prev) => ({ ...prev, saturation }));
    }, []);

    const setDensity = useCallback((density: DensityValue) => {
        setConfigState((prev) => ({ ...prev, density }));
    }, []);

    const setThemeConfig = useCallback((updates: Partial<ThemeConfig>) => {
        setConfigState((prev) => ({ ...prev, ...updates }));
    }, []);

    const resetToDefaults = useCallback(() => {
        const newConfig = {
            ...defaultThemeConfig,
            displayMode: config.displayMode, // Keep current display mode
        };
        setConfigState(newConfig);
    }, [config.displayMode]);

    // ==================== Context Value ====================
    // Memoized to prevent unnecessary re-renders of all consumers

    const value = useMemo<ThemeContextType>(
        () => ({
            displayMode: config.displayMode,
            setDisplayMode,
            primaryHue: config.primaryHue,
            setPrimaryHue,
            accentHue: config.accentHue,
            setAccentHue,
            radius: config.radius,
            setRadius,
            saturation: config.saturation,
            setSaturation,
            density: config.density,
            setDensity,
            themeConfig: config,
            setThemeConfig,
            resetToDefaults,
            isCustomized,
        }),
        [
            config,
            setDisplayMode,
            setPrimaryHue,
            setAccentHue,
            setRadius,
            setSaturation,
            setDensity,
            setThemeConfig,
            resetToDefaults,
            isCustomized,
        ]
    );

    return (
        <ThemeContext.Provider value={value}>
            {children}
        </ThemeContext.Provider>
    );
}

// ==================== Hook ====================

/**
 * Hook to access theme context
 */
export function useTheme(): ThemeContextType {
    const context = useContext(ThemeContext);
    if (context === undefined) {
        throw new Error('useTheme must be used within a ThemeProvider');
    }
    return context;
}

// ==================== Re-exports ====================

export type { DisplayMode, ThemeConfig, RadiusValue, DensityValue };
