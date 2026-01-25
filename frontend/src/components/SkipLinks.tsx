/**
 * SkipLinks Component
 *
 * WCAG 2.1 AA Skip Navigation Links
 * Ermoeglicht Tastaturnutzern schnellen Zugriff auf Hauptbereiche.
 */

import { useCallback, useState } from 'react'
import { cn } from '@/lib/utils'

interface SkipLinkTarget {
  id: string
  label: string
}

const DEFAULT_TARGETS: SkipLinkTarget[] = [
  { id: 'main-content', label: 'Zum Hauptinhalt' },
  { id: 'main-navigation', label: 'Zur Navigation' },
  { id: 'search-input', label: 'Zur Suche' },
]

interface SkipLinksProps {
  /** Custom skip link targets. If not provided, uses defaults. */
  targets?: SkipLinkTarget[]
  /** Additional CSS classes */
  className?: string
}

export function SkipLinks({ targets = DEFAULT_TARGETS, className }: SkipLinksProps) {
  const [focusedIndex, setFocusedIndex] = useState<number | null>(null)

  const handleClick = useCallback((targetId: string) => {
    const element = document.getElementById(targetId)
    if (element) {
      element.focus()
      element.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }, [])

  const handleKeyDown = useCallback(
    (event: React.KeyboardEvent, targetId: string, index: number) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault()
        handleClick(targetId)
      } else if (event.key === 'ArrowDown' || event.key === 'ArrowRight') {
        event.preventDefault()
        const nextIndex = (index + 1) % targets.length
        setFocusedIndex(nextIndex)
        const nextLink = document.querySelector(`[data-skip-link-index="${nextIndex}"]`) as HTMLElement
        nextLink?.focus()
      } else if (event.key === 'ArrowUp' || event.key === 'ArrowLeft') {
        event.preventDefault()
        const prevIndex = (index - 1 + targets.length) % targets.length
        setFocusedIndex(prevIndex)
        const prevLink = document.querySelector(`[data-skip-link-index="${prevIndex}"]`) as HTMLElement
        prevLink?.focus()
      }
    },
    [handleClick, targets.length]
  )

  return (
    <nav
      aria-label="Schnellnavigation"
      className={cn(
        // Visually hidden until focused
        'fixed top-0 left-0 z-[9999] p-2',
        // Container styling when any link is focused
        'focus-within:bg-background focus-within:border focus-within:border-border focus-within:rounded-md focus-within:shadow-lg',
        className
      )}
    >
      <ul className="flex flex-col gap-1" role="list">
        {targets.map((target, index) => (
          <li key={target.id}>
            <a
              href={`#${target.id}`}
              data-skip-link-index={index}
              onClick={(e) => {
                e.preventDefault()
                handleClick(target.id)
              }}
              onKeyDown={(e) => handleKeyDown(e, target.id, index)}
              onFocus={() => setFocusedIndex(index)}
              onBlur={() => setFocusedIndex(null)}
              className={cn(
                // Visually hidden by default
                'sr-only',
                // Visible when focused
                'focus:not-sr-only',
                'focus:block',
                'focus:px-4 focus:py-2',
                'focus:bg-primary focus:text-primary-foreground',
                'focus:rounded-md',
                'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2',
                'focus:transition-colors',
                // Text styling
                'text-sm font-medium',
                'whitespace-nowrap'
              )}
              tabIndex={focusedIndex === null || focusedIndex === index ? 0 : -1}
            >
              {target.label}
            </a>
          </li>
        ))}
      </ul>
    </nav>
  )
}

/**
 * SkipToMain - Simplified single skip link
 * Use when only main content skip is needed.
 */
export function SkipToMain() {
  const handleClick = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    const main = document.getElementById('main-content')
    if (main) {
      main.focus()
      main.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }, [])

  return (
    <a
      href="#main-content"
      onClick={handleClick}
      className={cn(
        'sr-only',
        'focus:not-sr-only',
        'focus:fixed focus:top-4 focus:left-4 focus:z-[9999]',
        'focus:px-4 focus:py-2',
        'focus:bg-primary focus:text-primary-foreground',
        'focus:rounded-md focus:shadow-lg',
        'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2',
        'text-sm font-medium'
      )}
    >
      Zum Hauptinhalt springen
    </a>
  )
}
