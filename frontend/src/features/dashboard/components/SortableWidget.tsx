import { useState, useCallback } from 'react'
import { useSortable } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { GripVertical, X } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
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
import { getWidgetLabel } from '../registry'

interface SortableWidgetProps {
    id: string
    type: string
    children: React.ReactNode
    isEditMode: boolean
    onRemove?: (id: string) => void
}

export function SortableWidget({ id, type, children, isEditMode, onRemove }: SortableWidgetProps) {
    const [showRemoveDialog, setShowRemoveDialog] = useState(false)

    const {
        attributes,
        listeners,
        setNodeRef,
        transform,
        transition,
        isDragging
    } = useSortable({ id })

    const style = {
        transform: CSS.Transform.toString(transform),
        transition,
        opacity: isDragging ? 0.5 : 1,
        touchAction: 'none' // Prevent scrolling while dragging
    }

    const handleRemove = useCallback(() => {
        setShowRemoveDialog(false)
        onRemove?.(id)
    }, [id, onRemove])

    const widgetLabel = getWidgetLabel(type)

    return (
        <>
            <div ref={setNodeRef} style={style} className="relative group min-h-[100px] mb-6">
                {isEditMode && (
                    <>
                        {/* Drag Handle */}
                        <div
                            {...attributes}
                            {...listeners}
                            className="absolute -left-8 top-0 p-2 cursor-grab active:cursor-grabbing hover:bg-muted rounded-md z-50 md:opacity-0 md:group-hover:opacity-100 transition-opacity"
                        >
                            <GripVertical className="w-5 h-5 text-muted-foreground" />
                        </div>

                        {/* Remove Button */}
                        <Button
                            variant="destructive"
                            size="icon"
                            className="absolute -top-2 -right-2 h-6 w-6 rounded-full z-50 opacity-0 group-hover:opacity-100 transition-opacity"
                            onClick={() => setShowRemoveDialog(true)}
                            title="Widget entfernen"
                        >
                            <X className="h-3.5 w-3.5" />
                        </Button>
                    </>
                )}
                {children}
                {isEditMode && (
                    <div className="absolute inset-0 border-2 border-dashed border-primary/20 pointer-events-none rounded-xl" />
                )}
            </div>

            {/* Remove Confirmation Dialog */}
            <AlertDialog open={showRemoveDialog} onOpenChange={setShowRemoveDialog}>
                <AlertDialogContent>
                    <AlertDialogHeader>
                        <AlertDialogTitle>Widget entfernen?</AlertDialogTitle>
                        <AlertDialogDescription>
                            Moechten Sie das Widget "{widgetLabel}" wirklich vom Dashboard entfernen?
                            Sie koennen es jederzeit ueber den Widget-Katalog wieder hinzufuegen.
                        </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                        <AlertDialogCancel>Abbrechen</AlertDialogCancel>
                        <AlertDialogAction
                            onClick={handleRemove}
                            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                        >
                            Entfernen
                        </AlertDialogAction>
                    </AlertDialogFooter>
                </AlertDialogContent>
            </AlertDialog>
        </>
    )
}
