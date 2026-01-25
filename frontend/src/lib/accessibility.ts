/**
 * Global Accessibility Utilities
 *
 * WCAG 2.1 AA Compliance Utilities:
 * - Focus Management
 * - Keyboard Navigation
 * - Screen Reader Support
 * - Color Contrast Helpers
 * - High Contrast Mode
 * - Reduced Motion Support
 *
 * Feinpoliert und durchdacht - Barrierefreie Benutzeroberfläche.
 */

import { useCallback, useEffect, useRef, useState } from 'react'

// =============================================================================
// Types
// =============================================================================

export interface FocusTrapOptions {
  /** Initial focus element selector */
  initialFocus?: string
  /** Return focus to element on deactivation */
  returnFocusOnDeactivate?: boolean
  /** Allow clicking outside to deactivate */
  clickOutsideDeactivates?: boolean
  /** Allow escape key to deactivate */
  escapeDeactivates?: boolean
  /** Callback when focus trap is deactivated */
  onDeactivate?: () => void
}

export interface KeyboardNavigationOptions {
  /** Enable/disable navigation */
  enabled?: boolean
  /** Loop around at boundaries */
  loop?: boolean
  /** Navigation orientation */
  orientation?: 'vertical' | 'horizontal' | 'both'
  /** Skip disabled items */
  skipDisabled?: boolean
}

export interface A11yButtonProps {
  /** Accessible label for screen readers */
  'aria-label'?: string
  /** ID of element describing this button */
  'aria-describedby'?: string
  /** Whether button is disabled */
  'aria-disabled'?: boolean
  /** Whether button is pressed (toggle) */
  'aria-pressed'?: boolean
  /** Whether button is expanded (dropdown) */
  'aria-expanded'?: boolean
  /** Whether button controls another element */
  'aria-controls'?: string
  /** Whether button has a popup */
  'aria-haspopup'?: boolean | 'menu' | 'listbox' | 'tree' | 'grid' | 'dialog'
}

// =============================================================================
// Focus Management
// =============================================================================

/**
 * Selectors for focusable elements
 */
export const FOCUSABLE_SELECTORS = [
  'a[href]:not([disabled]):not([aria-disabled="true"])',
  'button:not([disabled]):not([aria-disabled="true"])',
  'input:not([disabled]):not([type="hidden"]):not([aria-disabled="true"])',
  'select:not([disabled]):not([aria-disabled="true"])',
  'textarea:not([disabled]):not([aria-disabled="true"])',
  '[tabindex]:not([tabindex="-1"]):not([disabled]):not([aria-disabled="true"])',
  '[contenteditable="true"]',
].join(', ')

/**
 * Get all focusable elements within a container
 */
export function getFocusableElements(container: HTMLElement): HTMLElement[] {
  return Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTORS))
    .filter((el) => {
      // Check if element is visible
      const style = window.getComputedStyle(el)
      return style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0'
    })
}

/**
 * Focus the first focusable element in a container
 */
export function focusFirst(container: HTMLElement): boolean {
  const elements = getFocusableElements(container)
  if (elements.length > 0) {
    elements[0].focus()
    return true
  }
  return false
}

/**
 * Focus the last focusable element in a container
 */
export function focusLast(container: HTMLElement): boolean {
  const elements = getFocusableElements(container)
  if (elements.length > 0) {
    elements[elements.length - 1].focus()
    return true
  }
  return false
}

/**
 * Hook for managing focus trap in dialogs/modals
 */
export function useFocusTrap(isActive: boolean, options: FocusTrapOptions = {}) {
  const {
    initialFocus,
    returnFocusOnDeactivate = true,
    clickOutsideDeactivates = false,
    escapeDeactivates = true,
    onDeactivate,
  } = options

  const containerRef = useRef<HTMLDivElement>(null)
  const previousFocusRef = useRef<HTMLElement | null>(null)

  useEffect(() => {
    if (!isActive) return

    // Store previous focus
    previousFocusRef.current = document.activeElement as HTMLElement

    const container = containerRef.current
    if (!container) return

    // Focus initial element or first focusable
    if (initialFocus) {
      const initialElement = container.querySelector<HTMLElement>(initialFocus)
      initialElement?.focus()
    } else {
      focusFirst(container)
    }

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Tab') {
        const focusable = getFocusableElements(container)
        if (focusable.length === 0) return

        const first = focusable[0]
        const last = focusable[focusable.length - 1]

        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault()
          last.focus()
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault()
          first.focus()
        }
      }

      if (escapeDeactivates && e.key === 'Escape') {
        onDeactivate?.()
      }
    }

    const handleClickOutside = (e: MouseEvent) => {
      if (clickOutsideDeactivates && !container.contains(e.target as Node)) {
        onDeactivate?.()
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    if (clickOutsideDeactivates) {
      document.addEventListener('mousedown', handleClickOutside)
    }

    return () => {
      document.removeEventListener('keydown', handleKeyDown)
      if (clickOutsideDeactivates) {
        document.removeEventListener('mousedown', handleClickOutside)
      }

      // Return focus
      if (returnFocusOnDeactivate && previousFocusRef.current) {
        previousFocusRef.current.focus()
      }
    }
  }, [isActive, initialFocus, returnFocusOnDeactivate, clickOutsideDeactivates, escapeDeactivates, onDeactivate])

  return containerRef
}

// =============================================================================
// Keyboard Navigation
// =============================================================================

export const KEYS = {
  ENTER: 'Enter',
  SPACE: ' ',
  ESCAPE: 'Escape',
  TAB: 'Tab',
  ARROW_UP: 'ArrowUp',
  ARROW_DOWN: 'ArrowDown',
  ARROW_LEFT: 'ArrowLeft',
  ARROW_RIGHT: 'ArrowRight',
  HOME: 'Home',
  END: 'End',
  PAGE_UP: 'PageUp',
  PAGE_DOWN: 'PageDown',
  DELETE: 'Delete',
  BACKSPACE: 'Backspace',
} as const

/**
 * Hook for roving tabindex keyboard navigation
 */
export function useRovingTabIndex<T>(
  items: T[],
  options: KeyboardNavigationOptions & {
    onSelect?: (item: T, index: number) => void
    onFocusChange?: (index: number) => void
  } = {}
) {
  const {
    enabled = true,
    loop = true,
    orientation = 'vertical',
    skipDisabled = true,
    onSelect,
    onFocusChange,
  } = options

  const [focusedIndex, setFocusedIndex] = useState(0)
  const containerRef = useRef<HTMLElement>(null)
  const itemRefs = useRef<(HTMLElement | null)[]>([])

  const setItemRef = useCallback((index: number) => (el: HTMLElement | null) => {
    itemRefs.current[index] = el
  }, [])

  const moveFocus = useCallback(
    (delta: number) => {
      const newIndex = loop
        ? (focusedIndex + delta + items.length) % items.length
        : Math.max(0, Math.min(focusedIndex + delta, items.length - 1))

      // Skip disabled items if needed
      if (skipDisabled && itemRefs.current[newIndex]?.getAttribute('aria-disabled') === 'true') {
        const nextDelta = delta > 0 ? 1 : -1
        const nextIndex = newIndex + nextDelta
        if (nextIndex >= 0 && nextIndex < items.length) {
          setFocusedIndex(nextIndex)
          onFocusChange?.(nextIndex)
          itemRefs.current[nextIndex]?.focus()
          return
        }
      }

      setFocusedIndex(newIndex)
      onFocusChange?.(newIndex)
      itemRefs.current[newIndex]?.focus()
    },
    [focusedIndex, items.length, loop, skipDisabled, onFocusChange]
  )

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (!enabled) return

      const isVertical = orientation === 'vertical' || orientation === 'both'
      const isHorizontal = orientation === 'horizontal' || orientation === 'both'

      switch (e.key) {
        case KEYS.ARROW_DOWN:
          if (isVertical) {
            e.preventDefault()
            moveFocus(1)
          }
          break
        case KEYS.ARROW_UP:
          if (isVertical) {
            e.preventDefault()
            moveFocus(-1)
          }
          break
        case KEYS.ARROW_RIGHT:
          if (isHorizontal) {
            e.preventDefault()
            moveFocus(1)
          }
          break
        case KEYS.ARROW_LEFT:
          if (isHorizontal) {
            e.preventDefault()
            moveFocus(-1)
          }
          break
        case KEYS.HOME:
          e.preventDefault()
          setFocusedIndex(0)
          onFocusChange?.(0)
          itemRefs.current[0]?.focus()
          break
        case KEYS.END:
          e.preventDefault()
          const lastIndex = items.length - 1
          setFocusedIndex(lastIndex)
          onFocusChange?.(lastIndex)
          itemRefs.current[lastIndex]?.focus()
          break
        case KEYS.ENTER:
        case KEYS.SPACE:
          e.preventDefault()
          onSelect?.(items[focusedIndex], focusedIndex)
          break
      }
    },
    [enabled, orientation, moveFocus, items, focusedIndex, onSelect, onFocusChange]
  )

  const getItemProps = useCallback(
    (index: number) => ({
      ref: setItemRef(index),
      tabIndex: index === focusedIndex ? 0 : -1,
      onKeyDown: handleKeyDown,
      onFocus: () => {
        setFocusedIndex(index)
        onFocusChange?.(index)
      },
    }),
    [setItemRef, focusedIndex, handleKeyDown, onFocusChange]
  )

  return {
    containerRef,
    focusedIndex,
    setFocusedIndex,
    getItemProps,
    handleKeyDown,
  }
}

// =============================================================================
// Screen Reader Announcements
// =============================================================================

/**
 * Announce a message to screen readers via aria-live region
 */
export function announce(
  message: string,
  priority: 'polite' | 'assertive' = 'polite',
  timeoutMs: number = 1000
): void {
  // Check if live region already exists
  let liveRegion = document.getElementById('a11y-live-region')

  if (!liveRegion) {
    liveRegion = document.createElement('div')
    liveRegion.id = 'a11y-live-region'
    liveRegion.className = 'sr-only'
    liveRegion.setAttribute('aria-live', priority)
    liveRegion.setAttribute('aria-atomic', 'true')
    liveRegion.setAttribute('role', 'status')
    document.body.appendChild(liveRegion)
  }

  // Update priority if different
  if (liveRegion.getAttribute('aria-live') !== priority) {
    liveRegion.setAttribute('aria-live', priority)
  }

  // Clear and set new message
  liveRegion.textContent = ''
  // Use setTimeout to ensure screen reader picks up the change
  setTimeout(() => {
    if (liveRegion) {
      liveRegion.textContent = message
    }
  }, 100)

  // Clear message after timeout
  setTimeout(() => {
    if (liveRegion) {
      liveRegion.textContent = ''
    }
  }, timeoutMs)
}

/**
 * Hook for screen reader announcements
 */
export function useAnnounce() {
  const announceCallback = useCallback(
    (message: string, priority: 'polite' | 'assertive' = 'polite') => {
      announce(message, priority)
    },
    []
  )

  return announceCallback
}

// =============================================================================
// ID Generation
// =============================================================================

let idCounter = 0

/**
 * Generate unique ID for accessibility attributes
 */
export function generateId(prefix: string = 'a11y'): string {
  return `${prefix}-${++idCounter}`
}

/**
 * Hook for generating stable IDs
 */
export function useId(prefix: string = 'a11y'): string {
  const idRef = useRef<string | null>(null)
  if (idRef.current === null) {
    idRef.current = generateId(prefix)
  }
  return idRef.current
}

// =============================================================================
// High Contrast Mode
// =============================================================================

/**
 * Check if high contrast mode is enabled
 */
export function isHighContrastMode(): boolean {
  if (typeof window === 'undefined') return false

  // Check Windows High Contrast Mode
  const mediaQuery = window.matchMedia('(forced-colors: active)')
  if (mediaQuery.matches) return true

  // Check for prefers-contrast
  const contrastQuery = window.matchMedia('(prefers-contrast: more)')
  return contrastQuery.matches
}

/**
 * Hook for high contrast mode detection
 */
export function useHighContrastMode(): boolean {
  const [isHighContrast, setIsHighContrast] = useState(false)

  useEffect(() => {
    if (typeof window === 'undefined') return

    const checkHighContrast = () => {
      setIsHighContrast(isHighContrastMode())
    }

    checkHighContrast()

    const mediaQuery = window.matchMedia('(forced-colors: active)')
    const contrastQuery = window.matchMedia('(prefers-contrast: more)')

    const handler = () => checkHighContrast()

    mediaQuery.addEventListener?.('change', handler)
    contrastQuery.addEventListener?.('change', handler)

    return () => {
      mediaQuery.removeEventListener?.('change', handler)
      contrastQuery.removeEventListener?.('change', handler)
    }
  }, [])

  return isHighContrast
}

// =============================================================================
// Reduced Motion
// =============================================================================

/**
 * Check if reduced motion is preferred
 */
export function prefersReducedMotion(): boolean {
  if (typeof window === 'undefined') return false
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

/**
 * Hook for reduced motion preference
 */
export function useReducedMotion(): boolean {
  const [reducedMotion, setReducedMotion] = useState(false)

  useEffect(() => {
    if (typeof window === 'undefined') return

    const mediaQuery = window.matchMedia('(prefers-reduced-motion: reduce)')
    setReducedMotion(mediaQuery.matches)

    const handler = (e: MediaQueryListEvent) => setReducedMotion(e.matches)
    mediaQuery.addEventListener?.('change', handler)

    return () => {
      mediaQuery.removeEventListener?.('change', handler)
    }
  }, [])

  return reducedMotion
}

// =============================================================================
// Color Contrast
// =============================================================================

/**
 * Calculate relative luminance of a color
 */
export function getLuminance(r: number, g: number, b: number): number {
  const [rs, gs, bs] = [r, g, b].map((c) => {
    const s = c / 255
    return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4)
  })
  return 0.2126 * rs + 0.7152 * gs + 0.0722 * bs
}

/**
 * Calculate contrast ratio between two colors
 */
export function getContrastRatio(
  color1: { r: number; g: number; b: number },
  color2: { r: number; g: number; b: number }
): number {
  const l1 = getLuminance(color1.r, color1.g, color1.b)
  const l2 = getLuminance(color2.r, color2.g, color2.b)
  const lighter = Math.max(l1, l2)
  const darker = Math.min(l1, l2)
  return (lighter + 0.05) / (darker + 0.05)
}

/**
 * Check if contrast ratio meets WCAG AA standard
 */
export function meetsWCAGAA(ratio: number, isLargeText: boolean = false): boolean {
  return isLargeText ? ratio >= 3 : ratio >= 4.5
}

/**
 * Check if contrast ratio meets WCAG AAA standard
 */
export function meetsWCAGAAA(ratio: number, isLargeText: boolean = false): boolean {
  return isLargeText ? ratio >= 4.5 : ratio >= 7
}

// =============================================================================
// German ARIA Labels
// =============================================================================

export const ARIA_LABELS_DE = {
  // Navigation
  mainNavigation: 'Hauptnavigation',
  breadcrumb: 'Brotkrumen-Navigation',
  pagination: 'Seitennavigation',
  backToOverview: 'Zurück zur Übersicht',
  previousPage: 'Vorherige Seite',
  nextPage: 'Nächste Seite',
  firstPage: 'Erste Seite',
  lastPage: 'Letzte Seite',
  currentPage: 'Aktuelle Seite',
  goToPage: (page: number) => `Gehe zu Seite ${page}`,

  // Actions
  upload: 'Hochladen',
  download: 'Herunterladen',
  edit: 'Bearbeiten',
  delete: 'Löschen',
  save: 'Speichern',
  cancel: 'Abbrechen',
  confirm: 'Bestätigen',
  close: 'Schließen',
  open: 'Öffnen',
  expand: 'Erweitern',
  collapse: 'Reduzieren',
  search: 'Suchen',
  filter: 'Filtern',
  sort: 'Sortieren',
  refresh: 'Aktualisieren',
  copy: 'Kopieren',
  print: 'Drucken',
  share: 'Teilen',
  settings: 'Einstellungen',
  help: 'Hilfe',
  info: 'Information',
  menu: 'Menü',
  moreActions: 'Weitere Aktionen',

  // Selection
  selectAll: 'Alle auswählen',
  deselectAll: 'Auswahl aufheben',
  selectItem: (name: string) => `${name} auswählen`,
  selected: (count: number) => `${count} ausgewählt`,

  // Status
  loading: 'Wird geladen...',
  loadingData: 'Daten werden geladen...',
  processing: 'Wird verarbeitet...',
  saving: 'Wird gespeichert...',
  error: 'Fehler',
  success: 'Erfolgreich',
  warning: 'Warnung',
  required: 'Erforderlich',
  optional: 'Optional',
  empty: 'Keine Einträge',
  noResults: 'Keine Ergebnisse gefunden',

  // Forms
  showPassword: 'Passwort anzeigen',
  hidePassword: 'Passwort verbergen',
  clearInput: 'Eingabe löschen',
  characterCount: (current: number, max: number) => `${current} von ${max} Zeichen`,
  validationError: 'Validierungsfehler',

  // Dialogs
  dialog: 'Dialog',
  closeDialog: 'Dialog schließen',
  confirmDialog: 'Bestätigungsdialog',

  // Tables
  sortAscending: 'Aufsteigend sortieren',
  sortDescending: 'Absteigend sortieren',
  expandRow: 'Zeile erweitern',
  collapseRow: 'Zeile reduzieren',
  rowsPerPage: 'Zeilen pro Seite',

  // Dates
  selectDate: 'Datum auswählen',
  selectTime: 'Uhrzeit auswählen',
  today: 'Heute',

  // Files
  dragAndDrop: 'Dateien hierher ziehen oder klicken zum Auswählen',
  fileSize: (size: string) => `Dateigröße: ${size}`,
  fileType: (type: string) => `Dateityp: ${type}`,

  // Accessibility specific
  skipToContent: 'Zum Hauptinhalt springen',
  skipToNavigation: 'Zur Navigation springen',
  newWindow: 'Öffnet in neuem Fenster',
  externalLink: 'Externer Link',
} as const

export type AriaLabelKey = keyof typeof ARIA_LABELS_DE

// =============================================================================
// Utility Functions
// =============================================================================

/**
 * Build aria-describedby string from multiple IDs
 */
export function buildAriaDescribedBy(...ids: (string | undefined | null)[]): string | undefined {
  const validIds = ids.filter((id): id is string => Boolean(id))
  return validIds.length > 0 ? validIds.join(' ') : undefined
}

/**
 * Create accessible button props
 */
export function createButtonA11yProps(options: {
  label?: string
  describedBy?: string
  pressed?: boolean
  expanded?: boolean
  controls?: string
  hasPopup?: A11yButtonProps['aria-haspopup']
  disabled?: boolean
}): A11yButtonProps {
  const props: A11yButtonProps = {}

  if (options.label) props['aria-label'] = options.label
  if (options.describedBy) props['aria-describedby'] = options.describedBy
  if (options.pressed !== undefined) props['aria-pressed'] = options.pressed
  if (options.expanded !== undefined) props['aria-expanded'] = options.expanded
  if (options.controls) props['aria-controls'] = options.controls
  if (options.hasPopup) props['aria-haspopup'] = options.hasPopup
  if (options.disabled) props['aria-disabled'] = options.disabled

  return props
}

/**
 * Check if element is visible for accessibility
 */
export function isAccessiblyHidden(element: HTMLElement): boolean {
  // Check aria-hidden
  if (element.getAttribute('aria-hidden') === 'true') return true

  // Check CSS visibility
  const style = window.getComputedStyle(element)
  if (style.display === 'none' || style.visibility === 'hidden') return true

  // Check parent chain
  let parent = element.parentElement
  while (parent) {
    if (parent.getAttribute('aria-hidden') === 'true') return true
    const parentStyle = window.getComputedStyle(parent)
    if (parentStyle.display === 'none' || parentStyle.visibility === 'hidden') return true
    parent = parent.parentElement
  }

  return false
}
