/**
 * AccessibleDialog - Enterprise-grade barrierefreier Dialog Wrapper
 *
 * Features:
 * - Focus Trap (automatisch durch radix-ui)
 * - ESC zum Schließen
 * - Bestätigung bei ungespeicherten Änderungen
 * - Screen Reader Ankündigungen
 * - Keyboard Navigation
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { useAnnounce, ARIA_LABELS } from '../utils/accessibility'

// ==================== TYPES ====================

interface AccessibleDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  description?: string
  children: React.ReactNode
  footer?: React.ReactNode
  /**
   * Wenn true, wird beim Schließen mit ungespeicherten Änderungen
   * ein Bestätigungsdialog angezeigt
   */
  confirmOnClose?: boolean
  /**
   * Gibt an, ob es ungespeicherte Änderungen gibt
   */
  isDirty?: boolean
  /**
   * Callback wenn der Dialog erfolgreich geschlossen wird
   */
  onConfirmClose?: () => void
  /**
   * Größe des Dialogs
   */
  size?: 'sm' | 'md' | 'lg' | 'xl' | 'full'
  /**
   * Zusätzliche CSS-Klassen
   */
  className?: string
  /**
   * Aria Label ID für den Dialog
   */
  ariaLabelledBy?: string
  /**
   * Aria Described By ID für den Dialog
   */
  ariaDescribedBy?: string
}

// ==================== SIZE CLASSES ====================

const SIZE_CLASSES = {
  sm: 'max-w-sm',
  md: 'max-w-md',
  lg: 'max-w-lg',
  xl: 'max-w-xl',
  full: 'max-w-[90vw] max-h-[90vh]',
}

// ==================== COMPONENT ====================

export function AccessibleDialog({
  open,
  onOpenChange,
  title,
  description,
  children,
  footer,
  confirmOnClose = false,
  isDirty = false,
  onConfirmClose,
  size = 'md',
  className = '',
  ariaLabelledBy,
  ariaDescribedBy,
}: AccessibleDialogProps) {
  const announce = useAnnounce()
  const [showConfirmDialog, setShowConfirmDialog] = useState(false)
  const previousOpenRef = useRef(open)

  // Announce dialog state changes
  useEffect(() => {
    if (open && !previousOpenRef.current) {
      announce(`Dialog geöffnet: ${title}`, 'polite')
    } else if (!open && previousOpenRef.current) {
      announce('Dialog geschlossen', 'polite')
    }
    previousOpenRef.current = open
  }, [open, title, announce])

  // Handle close request
  const handleOpenChange = useCallback(
    (newOpen: boolean) => {
      if (!newOpen && confirmOnClose && isDirty) {
        setShowConfirmDialog(true)
        return
      }
      onOpenChange(newOpen)
    },
    [confirmOnClose, isDirty, onOpenChange]
  )

  // Handle confirm close
  const handleConfirmClose = useCallback(() => {
    setShowConfirmDialog(false)
    onConfirmClose?.()
    onOpenChange(false)
  }, [onConfirmClose, onOpenChange])

  // Handle cancel close
  const handleCancelClose = useCallback(() => {
    setShowConfirmDialog(false)
  }, [])

  return (
    <>
      <Dialog open={open} onOpenChange={handleOpenChange}>
        <DialogContent
          className={`${SIZE_CLASSES[size]} ${className}`}
          aria-labelledby={ariaLabelledBy || 'dialog-title'}
          aria-describedby={ariaDescribedBy || (description ? 'dialog-description' : undefined)}
        >
          <DialogHeader>
            <DialogTitle id="dialog-title">{title}</DialogTitle>
            {description && (
              <DialogDescription id="dialog-description">{description}</DialogDescription>
            )}
          </DialogHeader>

          <div role="region" aria-label={title}>
            {children}
          </div>

          {footer && <DialogFooter>{footer}</DialogFooter>}
        </DialogContent>
      </Dialog>

      {/* Confirmation Dialog for unsaved changes */}
      <AlertDialog open={showConfirmDialog} onOpenChange={setShowConfirmDialog}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Ungespeicherte Änderungen</AlertDialogTitle>
            <AlertDialogDescription>
              Sie haben ungespeicherte Änderungen. Möchten Sie den Dialog wirklich schließen?
              Alle Änderungen gehen verloren.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel onClick={handleCancelClose}>
              Abbrechen
            </AlertDialogCancel>
            <AlertDialogAction onClick={handleConfirmClose}>
              Schließen ohne Speichern
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}

// ==================== FORM FIELD WITH ARIA ====================

interface AccessibleFormFieldProps {
  id: string
  label: string
  error?: string
  hint?: string
  required?: boolean
  children: React.ReactNode
}

/**
 * Barrierefreies Formularfeld mit Label, Error und Hint
 */
export function AccessibleFormField({
  id,
  label,
  error,
  hint,
  required,
  children,
}: AccessibleFormFieldProps) {
  const errorId = error ? `${id}-error` : undefined
  const hintId = hint ? `${id}-hint` : undefined
  const describedBy = [errorId, hintId].filter(Boolean).join(' ') || undefined

  return (
    <div className="space-y-2">
      <label
        htmlFor={id}
        className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70"
      >
        {label}
        {required && (
          <span className="text-destructive ml-1" aria-hidden="true">
            *
          </span>
        )}
        {required && <span className="sr-only">(Pflichtfeld)</span>}
      </label>

      <div
        aria-describedby={describedBy}
        aria-invalid={error ? 'true' : undefined}
      >
        {children}
      </div>

      {hint && !error && (
        <p id={hintId} className="text-sm text-muted-foreground">
          {hint}
        </p>
      )}

      {error && (
        <p id={errorId} className="text-sm text-destructive" role="alert">
          {error}
        </p>
      )}
    </div>
  )
}

// ==================== LIVE REGION ====================

interface LiveRegionProps {
  message: string
  priority?: 'polite' | 'assertive'
}

/**
 * Live Region für Screen Reader Ankündigungen
 */
export function LiveRegion({ message, priority = 'polite' }: LiveRegionProps) {
  return (
    <div
      role="status"
      aria-live={priority}
      aria-atomic="true"
      className="sr-only"
    >
      {message}
    </div>
  )
}

// ==================== EXPORTS ====================

export { ARIA_LABELS }
