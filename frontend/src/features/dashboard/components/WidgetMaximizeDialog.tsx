import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogDescription,
} from '@/components/ui/dialog'
import { useDashboardStore } from '../stores/useDashboardStore'
import { getWidgetComponent, getWidgetLabel } from '../registry'

interface WidgetMaximizeDialogProps {
    open: boolean
    onOpenChange: (open: boolean) => void
    widgetId: string | null
}

export function WidgetMaximizeDialog({ open, onOpenChange, widgetId }: WidgetMaximizeDialogProps) {
    const { widgets } = useDashboardStore()
    const widget = widgetId ? widgets.find(w => w.id === widgetId) : null

    if (!widget) return null

    const Component = getWidgetComponent(widget.type)

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="max-w-[95vw] w-[95vw] max-h-[90vh] h-[90vh] flex flex-col">
                <DialogHeader className="flex-shrink-0">
                    <DialogTitle>{getWidgetLabel(widget.type)}</DialogTitle>
                    <DialogDescription>
                        Maximierte Ansicht
                    </DialogDescription>
                </DialogHeader>
                <div className="flex-1 overflow-auto min-h-0">
                    <Component />
                </div>
            </DialogContent>
        </Dialog>
    )
}
