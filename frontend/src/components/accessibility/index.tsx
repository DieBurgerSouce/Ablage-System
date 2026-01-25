/**
 * Accessibility Components
 *
 * WCAG 2.1 AA Compliant Components:
 * - Skip Links
 * - Live Regions
 * - Visually Hidden
 * - Focus Indicators
 * - High Contrast Mode Toggle
 *
 * Feinpoliert und durchdacht - Barrierefreie Komponenten.
 */

import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { cn } from '@/lib/utils'
import {
  useHighContrastMode,
  useReducedMotion,
  ARIA_LABELS_DE,
} from '@/lib/accessibility'

// =============================================================================
// Context
// =============================================================================

interface AccessibilityContextValue {
  /** High contrast mode enabled */
  highContrast: boolean
  /** Set high contrast mode */
  setHighContrast: (enabled: boolean) => void
  /** Reduced motion preferred */
  reducedMotion: boolean
  /** Screen reader mode enabled */
  screenReaderMode: boolean
  /** Set screen reader mode */
  setScreenReaderMode: (enabled: boolean) => void
}

const AccessibilityContext = createContext<AccessibilityContextValue | null>(null)

/**
 * Hook for accessibility context
 */
export function useAccessibility(): AccessibilityContextValue {
  const context = useContext(AccessibilityContext)
  if (!context) {
    throw new Error('useAccessibility must be used within AccessibilityProvider')
  }
  return context
}

// =============================================================================
// Provider
// =============================================================================

interface AccessibilityProviderProps {
  children: ReactNode
}

/**
 * Accessibility Provider
 *
 * Provides accessibility settings and preferences to the app.
 */
export function AccessibilityProvider({ children }: AccessibilityProviderProps) {
  const systemHighContrast = useHighContrastMode()
  const systemReducedMotion = useReducedMotion()

  const [highContrast, setHighContrastState] = useState(false)
  const [screenReaderMode, setScreenReaderMode] = useState(false)

  // Sync with system preference
  useEffect(() => {
    setHighContrastState(systemHighContrast)
  }, [systemHighContrast])

  // Apply high contrast class to document
  useEffect(() => {
    if (highContrast) {
      document.documentElement.classList.add('high-contrast')
    } else {
      document.documentElement.classList.remove('high-contrast')
    }
  }, [highContrast])

  // Apply reduced motion class
  useEffect(() => {
    if (systemReducedMotion) {
      document.documentElement.classList.add('reduced-motion')
    } else {
      document.documentElement.classList.remove('reduced-motion')
    }
  }, [systemReducedMotion])

  const setHighContrast = (enabled: boolean) => {
    setHighContrastState(enabled)
    // Persist preference
    localStorage.setItem('a11y-high-contrast', String(enabled))
  }

  // Load persisted preferences
  useEffect(() => {
    const stored = localStorage.getItem('a11y-high-contrast')
    if (stored !== null) {
      setHighContrastState(stored === 'true')
    }

    const storedScreenReader = localStorage.getItem('a11y-screen-reader')
    if (storedScreenReader !== null) {
      setScreenReaderMode(storedScreenReader === 'true')
    }
  }, [])

  const setScreenReaderModeWithPersist = (enabled: boolean) => {
    setScreenReaderMode(enabled)
    localStorage.setItem('a11y-screen-reader', String(enabled))
  }

  return (
    <AccessibilityContext.Provider
      value={{
        highContrast,
        setHighContrast,
        reducedMotion: systemReducedMotion,
        screenReaderMode,
        setScreenReaderMode: setScreenReaderModeWithPersist,
      }}
    >
      {children}
    </AccessibilityContext.Provider>
  )
}

// =============================================================================
// Skip Link
// =============================================================================

interface SkipLinkProps {
  /** Target element ID */
  targetId: string
  /** Link text */
  children?: ReactNode
}

/**
 * Skip Link Component
 *
 * Allows keyboard users to skip directly to main content.
 * Shows on focus only.
 */
export function SkipLink({ targetId, children = ARIA_LABELS_DE.skipToContent }: SkipLinkProps) {
  const handleClick = (e: React.MouseEvent<HTMLAnchorElement>) => {
    e.preventDefault()
    const target = document.getElementById(targetId)
    if (target) {
      target.setAttribute('tabindex', '-1')
      target.focus()
      target.scrollIntoView({ behavior: 'smooth' })
    }
  }

  return (
    <a
      href={`#${targetId}`}
      onClick={handleClick}
      className={cn(
        'sr-only focus:not-sr-only',
        'focus:fixed focus:top-4 focus:left-4 focus:z-[9999]',
        'focus:px-4 focus:py-2 focus:rounded-md',
        'focus:bg-primary focus:text-primary-foreground',
        'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2',
        'focus:font-medium focus:shadow-lg'
      )}
    >
      {children}
    </a>
  )
}

// =============================================================================
// Skip Links Group
// =============================================================================

interface SkipLinksProps {
  /** Skip links configuration */
  links?: Array<{
    targetId: string
    label: string
  }>
}

/**
 * Skip Links Group
 *
 * Multiple skip links for complex layouts.
 */
export function SkipLinks({ links }: SkipLinksProps) {
  const defaultLinks = [
    { targetId: 'main-content', label: ARIA_LABELS_DE.skipToContent },
    { targetId: 'main-navigation', label: ARIA_LABELS_DE.skipToNavigation },
  ]

  const linksToRender = links || defaultLinks

  return (
    <nav aria-label="Sprunglinks" className="sr-only focus-within:not-sr-only">
      <ul className="focus-within:fixed focus-within:top-4 focus-within:left-4 focus-within:z-[9999] focus-within:flex focus-within:flex-col focus-within:gap-2">
        {linksToRender.map(({ targetId, label }) => (
          <li key={targetId}>
            <SkipLink targetId={targetId}>{label}</SkipLink>
          </li>
        ))}
      </ul>
    </nav>
  )
}

// =============================================================================
// Visually Hidden
// =============================================================================

interface VisuallyHiddenProps {
  children: ReactNode
  /** Element to render as */
  as?: 'span' | 'div' | 'p' | 'label'
}

/**
 * Visually Hidden Component
 *
 * Hides content visually but keeps it accessible to screen readers.
 */
export function VisuallyHidden({ children, as: Tag = 'span' }: VisuallyHiddenProps) {
  return <Tag className="sr-only">{children}</Tag>
}

// =============================================================================
// Live Region
// =============================================================================

interface LiveRegionProps {
  /** Region ID */
  id?: string
  /** Live region politeness */
  politeness?: 'polite' | 'assertive' | 'off'
  /** Atomic updates */
  atomic?: boolean
  /** Relevant changes */
  relevant?: 'additions' | 'removals' | 'text' | 'all'
  /** Content */
  children?: ReactNode
}

/**
 * Live Region Component
 *
 * Announces dynamic content changes to screen readers.
 */
export function LiveRegion({
  id = 'live-region',
  politeness = 'polite',
  atomic = true,
  relevant = 'all',
  children,
}: LiveRegionProps) {
  return (
    <div
      id={id}
      role="status"
      aria-live={politeness}
      aria-atomic={atomic}
      aria-relevant={relevant}
      className="sr-only"
    >
      {children}
    </div>
  )
}

// =============================================================================
// Focus Indicator
// =============================================================================

interface FocusIndicatorProps {
  /** Show focus ring */
  visible: boolean
  /** Position relative to element */
  position?: 'inside' | 'outside'
  /** Ring color */
  color?: 'primary' | 'destructive' | 'warning'
}

/**
 * Custom Focus Indicator
 *
 * For elements that need custom focus styling.
 */
export function FocusIndicator({
  visible,
  position = 'outside',
  color = 'primary',
}: FocusIndicatorProps) {
  if (!visible) return null

  const colorClasses = {
    primary: 'ring-primary',
    destructive: 'ring-destructive',
    warning: 'ring-yellow-500',
  }

  return (
    <span
      className={cn(
        'pointer-events-none absolute inset-0 rounded-md ring-2',
        position === 'inside' ? 'ring-inset' : 'ring-offset-2',
        colorClasses[color]
      )}
      aria-hidden="true"
    />
  )
}

// =============================================================================
// High Contrast Toggle
// =============================================================================

interface HighContrastToggleProps {
  /** Optional label */
  label?: string
  /** Optional className */
  className?: string
}

/**
 * High Contrast Mode Toggle
 *
 * Allows users to toggle high contrast mode.
 */
export function HighContrastToggle({ label = 'Hoher Kontrast', className }: HighContrastToggleProps) {
  const { highContrast, setHighContrast } = useAccessibility()

  return (
    <button
      type="button"
      role="switch"
      aria-checked={highContrast}
      aria-label={label}
      onClick={() => setHighContrast(!highContrast)}
      className={cn(
        'inline-flex items-center gap-2 px-3 py-2 rounded-md',
        'text-sm font-medium transition-colors',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
        highContrast
          ? 'bg-primary text-primary-foreground'
          : 'bg-secondary text-secondary-foreground hover:bg-secondary/80',
        className
      )}
    >
      <span aria-hidden="true" className="text-lg">
        {highContrast ? '◉' : '○'}
      </span>
      {label}
    </button>
  )
}

// =============================================================================
// Accessible Icon Button
// =============================================================================

interface IconButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  /** Accessible label (required for icon-only buttons) */
  'aria-label': string
  /** Icon to display */
  icon: ReactNode
  /** Button size */
  size?: 'sm' | 'md' | 'lg'
  /** Button variant */
  variant?: 'default' | 'ghost' | 'outline' | 'destructive'
}

/**
 * Accessible Icon Button
 *
 * Icon-only button with required aria-label.
 */
export function IconButton({
  'aria-label': ariaLabel,
  icon,
  size = 'md',
  variant = 'ghost',
  className,
  ...props
}: IconButtonProps) {
  const sizeClasses = {
    sm: 'h-8 w-8',
    md: 'h-10 w-10',
    lg: 'h-12 w-12',
  }

  const variantClasses = {
    default: 'bg-primary text-primary-foreground hover:bg-primary/90',
    ghost: 'hover:bg-accent hover:text-accent-foreground',
    outline: 'border border-input bg-background hover:bg-accent hover:text-accent-foreground',
    destructive: 'bg-destructive text-destructive-foreground hover:bg-destructive/90',
  }

  return (
    <button
      type="button"
      aria-label={ariaLabel}
      className={cn(
        'inline-flex items-center justify-center rounded-md transition-colors',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
        'disabled:pointer-events-none disabled:opacity-50',
        sizeClasses[size],
        variantClasses[variant],
        className
      )}
      {...props}
    >
      {icon}
    </button>
  )
}

// =============================================================================
// Accessible Loading State
// =============================================================================

interface LoadingProps {
  /** Loading message for screen readers */
  message?: string
  /** Show visual spinner */
  showSpinner?: boolean
  /** Size */
  size?: 'sm' | 'md' | 'lg'
}

/**
 * Accessible Loading Indicator
 *
 * Provides visual and screen reader feedback for loading states.
 */
export function Loading({
  message = ARIA_LABELS_DE.loading,
  showSpinner = true,
  size = 'md',
}: LoadingProps) {
  const sizeClasses = {
    sm: 'h-4 w-4 border-2',
    md: 'h-8 w-8 border-3',
    lg: 'h-12 w-12 border-4',
  }

  return (
    <div
      role="status"
      aria-live="polite"
      aria-busy="true"
      className="flex items-center gap-3"
    >
      {showSpinner && (
        <div
          className={cn(
            'animate-spin rounded-full border-primary border-t-transparent',
            sizeClasses[size]
          )}
          aria-hidden="true"
        />
      )}
      <span className="sr-only">{message}</span>
    </div>
  )
}

// =============================================================================
// Accessible Error Message
// =============================================================================

interface ErrorMessageProps {
  /** Error ID for aria-describedby */
  id: string
  /** Error message */
  message: string
  /** Additional className */
  className?: string
}

/**
 * Accessible Error Message
 *
 * Error message component with proper ARIA attributes.
 */
export function ErrorMessage({ id, message, className }: ErrorMessageProps) {
  return (
    <p
      id={id}
      role="alert"
      aria-live="assertive"
      className={cn('text-sm text-destructive mt-1', className)}
    >
      {message}
    </p>
  )
}

// =============================================================================
// Exports
// =============================================================================

export {
  AccessibilityContext,
  type AccessibilityContextValue,
}
