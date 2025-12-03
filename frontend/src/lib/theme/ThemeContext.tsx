import { createContext, useContext, useEffect, useState, ReactNode } from 'react'

/**
 * Display modes for the Ablage-System UI.
 * - light: Standard light theme (default)
 * - dark: Standard dark theme for low-light environments
 * - whitescreen: High contrast mode for maximum readability (WCAG AAA)
 * - blackscreen: Inverted high contrast for OLED displays and photosensitivity
 */
export type DisplayMode = 'light' | 'dark' | 'whitescreen' | 'blackscreen'

interface ThemeContextType {
    displayMode: DisplayMode
    setDisplayMode: (mode: DisplayMode) => void
}

const ThemeContext = createContext<ThemeContextType | undefined>(undefined)

const STORAGE_KEY = 'ablage-display-mode'

/**
 * Get initial display mode from localStorage or system preference
 */
function getInitialDisplayMode(): DisplayMode {
    // Check localStorage first
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored && ['light', 'dark', 'whitescreen', 'blackscreen'].includes(stored)) {
        return stored as DisplayMode
    }

    // Fall back to system preference
    if (window.matchMedia('(prefers-color-scheme: dark)').matches) {
        return 'dark'
    }

    return 'light'
}

/**
 * Apply display mode class to document element
 */
function applyDisplayMode(mode: DisplayMode) {
    const root = document.documentElement

    // Remove all mode classes
    root.classList.remove('light', 'dark', 'whitescreen', 'blackscreen')

    // Apply new mode class
    root.classList.add(mode)
}

interface ThemeProviderProps {
    children: ReactNode
}

export function ThemeProvider({ children }: ThemeProviderProps) {
    const [displayMode, setDisplayModeState] = useState<DisplayMode>(getInitialDisplayMode)

    // Apply display mode on mount and when changed
    useEffect(() => {
        applyDisplayMode(displayMode)
    }, [displayMode])

    // Listen for system preference changes
    useEffect(() => {
        const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')

        const handleChange = (e: MediaQueryListEvent) => {
            // Only auto-switch if user hasn't explicitly chosen a mode
            const stored = localStorage.getItem(STORAGE_KEY)
            if (!stored) {
                setDisplayModeState(e.matches ? 'dark' : 'light')
            }
        }

        mediaQuery.addEventListener('change', handleChange)
        return () => mediaQuery.removeEventListener('change', handleChange)
    }, [])

    const setDisplayMode = (mode: DisplayMode) => {
        localStorage.setItem(STORAGE_KEY, mode)
        setDisplayModeState(mode)
    }

    return (
        <ThemeContext.Provider value={{ displayMode, setDisplayMode }}>
            {children}
        </ThemeContext.Provider>
    )
}

/**
 * Hook to access the current display mode and setter
 */
export function useTheme() {
    const context = useContext(ThemeContext)
    if (context === undefined) {
        throw new Error('useTheme must be used within a ThemeProvider')
    }
    return context
}
