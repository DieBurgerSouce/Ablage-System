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
import { AlertTriangle } from 'lucide-react'

interface UnsavedChangesDialogProps {
    /** Whether the dialog is open */
    open: boolean
    /** Called when user confirms navigation (discards changes) */
    onConfirm: () => void
    /** Called when user cancels navigation (stays on page) */
    onCancel: () => void
    /** Custom title (German) */
    title?: string
    /** Custom description (German) */
    description?: string
}

/**
 * Dialog to warn users about unsaved changes.
 * All text is in German.
 *
 * @example
 * ```tsx
 * <UnsavedChangesDialog
 *   open={showWarning}
 *   onConfirm={confirmNavigation}
 *   onCancel={cancelNavigation}
 * />
 * ```
 */
export function UnsavedChangesDialog({
    open,
    onConfirm,
    onCancel,
    title = 'Ungespeicherte Änderungen',
    description = 'Sie haben ungespeicherte Änderungen. Wenn Sie die Seite verlassen, gehen diese verloren.',
}: UnsavedChangesDialogProps) {
    return (
        <AlertDialog open={open} onOpenChange={(isOpen) => !isOpen && onCancel()}>
            <AlertDialogContent>
                <AlertDialogHeader>
                    <AlertDialogTitle className="flex items-center gap-2">
                        <AlertTriangle className="w-5 h-5 text-amber-500" />
                        {title}
                    </AlertDialogTitle>
                    <AlertDialogDescription>
                        {description}
                    </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                    <AlertDialogCancel onClick={onCancel}>
                        Auf Seite bleiben
                    </AlertDialogCancel>
                    <AlertDialogAction
                        onClick={onConfirm}
                        className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                    >
                        Änderungen verwerfen
                    </AlertDialogAction>
                </AlertDialogFooter>
            </AlertDialogContent>
        </AlertDialog>
    )
}
