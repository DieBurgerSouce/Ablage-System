/**
 * Toast Hook - Sonner Wrapper für Rückwärtskompatibilität
 *
 * Diese Datei wrapped die Sonner Toast Library um das alte API beizubehalten.
 * Neue Komponenten sollten direkt `import { toast } from 'sonner'` verwenden.
 *
 * Migration Guide:
 * - Alt: const { toast } = useToast(); toast({ title, description, variant })
 * - Neu: import { toast } from 'sonner'; toast.success(title, { description })
 */

import { toast as sonnerToast, type ExternalToast } from 'sonner'
import { logger } from '@/lib/logger';

// ==================== Types (für Rückwärtskompatibilität) ====================

type ToastVariant = 'default' | 'destructive' | 'success'

type Toast = {
  title?: string
  description?: string
  variant?: ToastVariant
  action?: React.ReactElement
  duration?: number
}

type ToasterToast = Toast & {
  id: string
  open?: boolean
  onOpenChange?: (open: boolean) => void
}

// ==================== Sonner Wrapper ====================

/**
 * Wrapped toast function die das alte API auf Sonner mapped.
 *
 * @deprecated Nutze direkt `import { toast } from 'sonner'` für neue Komponenten
 */
function toast(props: Toast) {
  const { title, description, variant, action, duration } = props

  // Map action element to Sonner action format
  const sonnerOptions: ExternalToast = {
    description,
    duration: duration ?? 5000,
  }

  // If there's an action button, try to convert it
  if (action) {
    // Sonner expects { label: string, onClick: () => void }
    // We can't perfectly convert React elements, so we log a warning
    logger.warn(
      '[useToast] Aktions-Elemente werden nicht vollständig unterstützt. ' +
        'Verwenden Sie sonner direkt mit action: { label, onClick }'
    )
  }

  // Map variants to Sonner toast methods
  switch (variant) {
    case 'destructive':
      return sonnerToast.error(title ?? 'Fehler', sonnerOptions)
    case 'success':
      return sonnerToast.success(title ?? 'Erfolg', sonnerOptions)
    default:
      return sonnerToast(title ?? '', sonnerOptions)
  }
}

// Convenience methods for new code
toast.success = (title: string, options?: ExternalToast) => {
  return sonnerToast.success(title, options)
}

toast.error = (title: string, options?: ExternalToast) => {
  return sonnerToast.error(title, options)
}

toast.warning = (title: string, options?: ExternalToast) => {
  return sonnerToast.warning(title, options)
}

toast.info = (title: string, options?: ExternalToast) => {
  return sonnerToast.info(title, options)
}

toast.loading = (title: string, options?: ExternalToast) => {
  return sonnerToast.loading(title, options)
}

toast.promise = sonnerToast.promise

toast.dismiss = (toastId?: string | number) => {
  if (toastId !== undefined) {
    sonnerToast.dismiss(toastId)
  } else {
    sonnerToast.dismiss()
  }
}

// ==================== Hook (für Rückwärtskompatibilität) ====================

/**
 * Toast Hook für Rückwärtskompatibilität.
 *
 * @deprecated Nutze direkt `import { toast } from 'sonner'` für neue Komponenten
 *
 * @example
 * // Alter Stil (deprecated)
 * const { toast } = useToast()
 * toast({ title: 'Gespeichert', variant: 'success' })
 *
 * // Neuer Stil (bevorzugt)
 * import { toast } from 'sonner'
 * toast.success('Gespeichert')
 */
function useToast() {
  return {
    toast,
    dismiss: toast.dismiss,
    // Legacy: Leeres Array da Sonner den State intern verwaltet
    toasts: [] as ToasterToast[],
  }
}

// ==================== Exports ====================

export { useToast, toast }
export type { Toast, ToasterToast, ToastVariant }

// Re-export Sonner for direct usage
export { toast as sonnerToast } from 'sonner'
