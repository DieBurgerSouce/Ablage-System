/**
 * Accessibility Utilities fuer Finanzen-Modul
 *
 * WCAG 2.1 AA Compliance:
 * - Focus Management
 * - Keyboard Navigation
 * - Screen Reader Support
 * - Color Contrast Helpers
 */

import { useEffect, useRef, useCallback } from 'react'

// ==================== FOCUS TRAP HOOK ====================

/**
 * Hook fuer Focus Trap in Dialogen/Modals
 * Haelt den Fokus innerhalb eines Containers
 */
export function useFocusTrap(isActive: boolean) {
  const containerRef = useRef<HTMLDivElement>(null)
  const previousFocusRef = useRef<HTMLElement | null>(null)

  useEffect(() => {
    if (!isActive) return

    // Speichere vorherigen Fokus
    previousFocusRef.current = document.activeElement as HTMLElement

    const container = containerRef.current
    if (!container) return

    // Fokussiere erstes fokussierbares Element
    const focusableElements = getFocusableElements(container)
    if (focusableElements.length > 0) {
      focusableElements[0].focus()
    }

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key !== 'Tab') return

      const focusable = getFocusableElements(container)
      if (focusable.length === 0) return

      const firstElement = focusable[0]
      const lastElement = focusable[focusable.length - 1]

      // Shift+Tab am Anfang -> zum Ende
      if (e.shiftKey && document.activeElement === firstElement) {
        e.preventDefault()
        lastElement.focus()
      }
      // Tab am Ende -> zum Anfang
      else if (!e.shiftKey && document.activeElement === lastElement) {
        e.preventDefault()
        firstElement.focus()
      }
    }

    document.addEventListener('keydown', handleKeyDown)

    return () => {
      document.removeEventListener('keydown', handleKeyDown)
      // Stelle vorherigen Fokus wieder her
      previousFocusRef.current?.focus()
    }
  }, [isActive])

  return containerRef
}

/**
 * Findet alle fokussierbaren Elemente in einem Container
 */
function getFocusableElements(container: HTMLElement): HTMLElement[] {
  const selectors = [
    'a[href]',
    'button:not([disabled])',
    'input:not([disabled])',
    'select:not([disabled])',
    'textarea:not([disabled])',
    '[tabindex]:not([tabindex="-1"])',
  ].join(', ')

  return Array.from(container.querySelectorAll<HTMLElement>(selectors))
}

// ==================== KEYBOARD NAVIGATION HOOK ====================

/**
 * Hook fuer Keyboard-Navigation in Listen/Tabellen
 */
export function useKeyboardNavigation<T>(
  items: T[],
  onSelect: (item: T, index: number) => void,
  options: {
    enabled?: boolean
    loop?: boolean
    orientation?: 'vertical' | 'horizontal' | 'both'
  } = {}
) {
  const { enabled = true, loop = true, orientation = 'vertical' } = options
  const selectedIndexRef = useRef(0)
  const containerRef = useRef<HTMLDivElement>(null)

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (!enabled || items.length === 0) return

      const isVertical = orientation === 'vertical' || orientation === 'both'
      const isHorizontal = orientation === 'horizontal' || orientation === 'both'

      let newIndex = selectedIndexRef.current

      switch (e.key) {
        case 'ArrowDown':
          if (isVertical) {
            e.preventDefault()
            newIndex = loop
              ? (selectedIndexRef.current + 1) % items.length
              : Math.min(selectedIndexRef.current + 1, items.length - 1)
          }
          break
        case 'ArrowUp':
          if (isVertical) {
            e.preventDefault()
            newIndex = loop
              ? (selectedIndexRef.current - 1 + items.length) % items.length
              : Math.max(selectedIndexRef.current - 1, 0)
          }
          break
        case 'ArrowRight':
          if (isHorizontal) {
            e.preventDefault()
            newIndex = loop
              ? (selectedIndexRef.current + 1) % items.length
              : Math.min(selectedIndexRef.current + 1, items.length - 1)
          }
          break
        case 'ArrowLeft':
          if (isHorizontal) {
            e.preventDefault()
            newIndex = loop
              ? (selectedIndexRef.current - 1 + items.length) % items.length
              : Math.max(selectedIndexRef.current - 1, 0)
          }
          break
        case 'Home':
          e.preventDefault()
          newIndex = 0
          break
        case 'End':
          e.preventDefault()
          newIndex = items.length - 1
          break
        case 'Enter':
        case ' ':
          e.preventDefault()
          onSelect(items[selectedIndexRef.current], selectedIndexRef.current)
          return
        default:
          return
      }

      if (newIndex !== selectedIndexRef.current) {
        selectedIndexRef.current = newIndex
        onSelect(items[newIndex], newIndex)
      }
    },
    [enabled, items, loop, orientation, onSelect]
  )

  useEffect(() => {
    const container = containerRef.current
    if (!container || !enabled) return

    container.addEventListener('keydown', handleKeyDown as EventListener)
    return () => container.removeEventListener('keydown', handleKeyDown as EventListener)
  }, [handleKeyDown, enabled])

  return {
    containerRef,
    selectedIndex: selectedIndexRef.current,
    setSelectedIndex: (index: number) => {
      selectedIndexRef.current = index
    },
  }
}

// ==================== ANNOUNCE HOOK ====================

/**
 * Hook fuer Screen Reader Ankuendigungen (aria-live)
 */
export function useAnnounce() {
  const announce = useCallback((message: string, priority: 'polite' | 'assertive' = 'polite') => {
    const element = document.createElement('div')
    element.setAttribute('role', 'status')
    element.setAttribute('aria-live', priority)
    element.setAttribute('aria-atomic', 'true')
    element.className = 'sr-only'
    element.textContent = message

    document.body.appendChild(element)

    // Entferne nach kurzer Zeit
    setTimeout(() => {
      document.body.removeChild(element)
    }, 1000)
  }, [])

  return announce
}

// ==================== ARIA HELPERS ====================

/**
 * Generiert aria-describedby ID
 */
export function getAriaDescribedBy(prefix: string, ...ids: (string | undefined | null)[]): string | undefined {
  const validIds = ids.filter(Boolean)
  if (validIds.length === 0) return undefined
  return validIds.map((id) => `${prefix}-${id}`).join(' ')
}

/**
 * Erzeugt eindeutige ID fuer Accessibility
 */
let idCounter = 0
export function generateA11yId(prefix: string): string {
  return `${prefix}-${++idCounter}`
}

// ==================== SKIP LINK COMPONENT ====================

/**
 * Skip Link Props
 */
export interface SkipLinkProps {
  targetId: string
  children: React.ReactNode
}

/**
 * Skip Link fuer Keyboard-Navigation
 * Erlaubt es Usern, direkt zum Hauptinhalt zu springen
 */
export function SkipLink({ targetId, children }: SkipLinkProps) {
  const handleClick = (e: React.MouseEvent) => {
    e.preventDefault()
    const target = document.getElementById(targetId)
    if (target) {
      target.focus()
      target.scrollIntoView()
    }
  }

  return (
    <a
      href={`#${targetId}`}
      onClick={handleClick}
      className="sr-only focus:not-sr-only focus:absolute focus:top-4 focus:left-4 focus:z-50 focus:px-4 focus:py-2 focus:bg-primary focus:text-primary-foreground focus:rounded-md focus:outline-none focus:ring-2 focus:ring-offset-2"
    >
      {children}
    </a>
  )
}

// ==================== VISUALLY HIDDEN COMPONENT ====================

/**
 * Visuell versteckt aber fuer Screen Reader sichtbar
 */
export function VisuallyHidden({ children }: { children: React.ReactNode }) {
  return <span className="sr-only">{children}</span>
}

// ==================== CONSTANTS ====================

/**
 * Keyboard Key Codes fuer Navigation
 */
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
} as const

/**
 * ARIA Role Descriptions auf Deutsch
 */
export const ARIA_LABELS = {
  // Navigation
  backToOverview: 'Zurueck zur Uebersicht',
  backToYear: 'Zurueck zum Jahr',
  nextPage: 'Naechste Seite',
  previousPage: 'Vorherige Seite',

  // Actions
  uploadDocument: 'Dokument hochladen',
  editDocument: 'Dokument bearbeiten',
  deleteDocument: 'Dokument loeschen',
  filterDocuments: 'Dokumente filtern',
  searchDocuments: 'Dokumente durchsuchen',
  selectDocument: 'Dokument auswaehlen',
  selectAllDocuments: 'Alle Dokumente auswaehlen',

  // Status
  loading: 'Wird geladen...',
  loadingDocuments: 'Dokumente werden geladen...',
  error: 'Fehler aufgetreten',
  success: 'Erfolgreich',

  // Dialogs
  closeDialog: 'Dialog schliessen',
  confirmAction: 'Aktion bestaetigen',
  cancelAction: 'Aktion abbrechen',

  // Document States
  deadlinePending: 'Frist ausstehend',
  deadlineOverdue: 'Frist ueberschritten',
  documentProcessed: 'Dokument verarbeitet',
  documentPending: 'Dokument in Bearbeitung',
} as const

export type AriaLabelKey = keyof typeof ARIA_LABELS
