/**
 * useMediaQuery - Responsive Breakpoint Detection Hook
 *
 * Ermoeglicht Media-Query-basierte Responsive-Logik in Komponenten.
 *
 * Verwendung:
 * - const isMobile = useMediaQuery('(max-width: 640px)')
 * - const isTablet = useMediaQuery('(min-width: 641px) and (max-width: 1024px)')
 * - const { isMobile, isTablet, isDesktop } = useResponsiveBreakpoints()
 */

import { useState, useEffect, useCallback } from 'react'

/**
 * Hook fuer Media-Query-basierte Responsive-Logik
 *
 * @param query - CSS Media Query String
 * @returns boolean - true wenn Query zutrifft
 */
export function useMediaQuery(query: string): boolean {
  const getMatches = useCallback((mediaQuery: string): boolean => {
    // SSR-safe: window existiert nicht auf Server
    if (typeof window !== 'undefined') {
      return window.matchMedia(mediaQuery).matches
    }
    return false
  }, [])

  const [matches, setMatches] = useState<boolean>(() => getMatches(query))

  useEffect(() => {
    const mediaQueryList = window.matchMedia(query)

    // Handler fuer Media-Query-Aenderungen
    const handleChange = (event: MediaQueryListEvent) => {
      setMatches(event.matches)
    }

    // Initial setzen
    setMatches(mediaQueryList.matches)

    // Event Listener hinzufuegen (moderne API)
    if (mediaQueryList.addEventListener) {
      mediaQueryList.addEventListener('change', handleChange)
    } else {
      // Fallback fuer aeltere Browser
      mediaQueryList.addListener(handleChange)
    }

    // Cleanup
    return () => {
      if (mediaQueryList.removeEventListener) {
        mediaQueryList.removeEventListener('change', handleChange)
      } else {
        mediaQueryList.removeListener(handleChange)
      }
    }
  }, [query])

  return matches
}

/**
 * Vordefinierte Tailwind-kompatible Breakpoints
 */
export const BREAKPOINTS = {
  sm: '640px',
  md: '768px',
  lg: '1024px',
  xl: '1280px',
  '2xl': '1536px',
} as const

/**
 * Hook mit vordefinierten Responsive-Breakpoints
 *
 * Basiert auf Tailwind CSS Breakpoints:
 * - Mobile: < 640px
 * - Tablet: 640px - 1023px
 * - Desktop: >= 1024px
 *
 * @returns Object mit isMobile, isTablet, isDesktop booleans
 */
export function useResponsiveBreakpoints() {
  const isMobile = useMediaQuery(`(max-width: ${parseInt(BREAKPOINTS.sm) - 1}px)`)
  const isTablet = useMediaQuery(
    `(min-width: ${BREAKPOINTS.sm}) and (max-width: ${parseInt(BREAKPOINTS.lg) - 1}px)`
  )
  const isDesktop = useMediaQuery(`(min-width: ${BREAKPOINTS.lg})`)

  return {
    isMobile,
    isTablet,
    isDesktop,
    // Zusaetzliche Convenience-Props
    isMobileOrTablet: isMobile || isTablet,
    isTabletOrDesktop: isTablet || isDesktop,
  }
}

/**
 * Hook fuer Touch-Device-Erkennung
 *
 * @returns boolean - true wenn Touch-Device
 */
export function useIsTouchDevice(): boolean {
  const [isTouch, setIsTouch] = useState(false)

  useEffect(() => {
    const checkTouch = () => {
      setIsTouch(
        'ontouchstart' in window ||
          navigator.maxTouchPoints > 0 ||
          // @ts-expect-error - msMaxTouchPoints ist IE-spezifisch
          navigator.msMaxTouchPoints > 0
      )
    }

    checkTouch()
  }, [])

  return isTouch
}

export default useMediaQuery
