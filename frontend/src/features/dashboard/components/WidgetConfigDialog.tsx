import { useState, useEffect } from 'react'
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select'
import { useDashboardStore } from '../stores/useDashboardStore'
import { getWidgetLabel } from '../registry'
import { toast } from 'sonner'

interface WidgetConfigDialogProps {
    open: boolean
    onOpenChange: (open: boolean) => void
    widgetId: string | null
}

export function WidgetConfigDialog({ open, onOpenChange, widgetId }: WidgetConfigDialogProps) {
    const { widgets, updateWidgetSize } = useDashboardStore()
    const widget = widgetId ? widgets.find(w => w.id === widgetId) : null

    const [width, setWidth] = useState(4)
    const [height, setHeight] = useState(3)

    useEffect(() => {
        if (widget) {
            setWidth(widget.w)
            setHeight(widget.h)
        }
    }, [widget])

    if (!widget) return null

    const handleSave = () => {
        updateWidgetSize(widget.id, width, height)
        toast.success('Widget aktualisiert', {
            description: `${getWidgetLabel(widget.type)} wurde konfiguriert.`,
        })
        onOpenChange(false)
    }

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="sm:max-w-[425px]">
                <DialogHeader>
                    <DialogTitle>Widget konfigurieren</DialogTitle>
                    <DialogDescription>
                        Einstellungen fuer {getWidgetLabel(widget.type)}
                    </DialogDescription>
                </DialogHeader>
                <div className="grid gap-4 py-4">
                    <div className="grid grid-cols-4 items-center gap-4">
                        <Label htmlFor="widget-type" className="text-right">Typ</Label>
                        <div className="col-span-3 text-sm text-muted-foreground">
                            {getWidgetLabel(widget.type)}
                        </div>
                    </div>
                    <div className="grid grid-cols-4 items-center gap-4">
                        <Label htmlFor="widget-width" className="text-right">Breite</Label>
                        <Select value={String(width)} onValueChange={(v) => setWidth(Number(v))}>
                            <SelectTrigger className="col-span-3">
                                <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value="2">2 Spalten</SelectItem>
                                <SelectItem value="3">3 Spalten</SelectItem>
                                <SelectItem value="4">4 Spalten (Standard)</SelectItem>
                                <SelectItem value="6">6 Spalten</SelectItem>
                                <SelectItem value="8">8 Spalten</SelectItem>
                                <SelectItem value="12">12 Spalten (Volle Breite)</SelectItem>
                            </SelectContent>
                        </Select>
                    </div>
                    <div className="grid grid-cols-4 items-center gap-4">
                        <Label htmlFor="widget-height" className="text-right">Hoehe</Label>
                        <Select value={String(height)} onValueChange={(v) => setHeight(Number(v))}>
                            <SelectTrigger className="col-span-3">
                                <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value="1">1 Zeile</SelectItem>
                                <SelectItem value="2">2 Zeilen</SelectItem>
                                <SelectItem value="3">3 Zeilen (Standard)</SelectItem>
                                <SelectItem value="4">4 Zeilen</SelectItem>
                                <SelectItem value="5">5 Zeilen</SelectItem>
                                <SelectItem value="6">6 Zeilen</SelectItem>
                            </SelectContent>
                        </Select>
                    </div>
                </div>
                <DialogFooter>
                    <Button variant="outline" onClick={() => onOpenChange(false)}>
                        Abbrechen
                    </Button>
                    <Button onClick={handleSave}>
                        Speichern
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    )
}
