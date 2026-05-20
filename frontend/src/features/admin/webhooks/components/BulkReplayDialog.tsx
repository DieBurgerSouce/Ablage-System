/**
 * BulkReplayDialog
 *
 * Dialog fuer Bulk-Replay von Events nach Typ und Zeitraum.
 */

import { useState } from 'react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Loader2, RefreshCw } from 'lucide-react'
import { toast } from '@/components/ui/use-toast'
import { useBulkReplay } from '../api'

interface BulkReplayDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function BulkReplayDialog({ open, onOpenChange }: BulkReplayDialogProps) {
  const [eventType, setEventType] = useState('')
  const [fromDate, setFromDate] = useState('')
  const [toDate, setToDate] = useState('')
  const bulkReplayMutation = useBulkReplay()

  const handleReplay = async () => {
    if (!eventType.trim()) {
      toast({
        title: 'Fehler',
        description: 'Bitte geben Sie einen Event-Typ ein.',
        variant: 'destructive',
      })
      return
    }
    if (!fromDate || !toDate) {
      toast({
        title: 'Fehler',
        description: 'Bitte waehlen Sie einen Zeitraum.',
        variant: 'destructive',
      })
      return
    }

    try {
      const result = await bulkReplayMutation.mutateAsync({
        event_type: eventType.trim(),
        from_date: new Date(fromDate).toISOString(),
        to_date: new Date(toDate).toISOString(),
      })
      toast({
        title: 'Bulk-Replay gestartet',
        description: result.message,
      })
      onOpenChange(false)
    } catch {
      toast({
        title: 'Fehler',
        description: 'Bulk-Replay konnte nicht gestartet werden.',
        variant: 'destructive',
      })
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Bulk-Replay</DialogTitle>
          <DialogDescription>
            Replayed alle Events eines Typs in einem definierten Zeitraum.
            Alle passenden aktiven Endpoints erhalten erneut eine Zustellung.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          <div className="space-y-2">
            <Label htmlFor="bulk-event-type">Event-Typ *</Label>
            <Input
              id="bulk-event-type"
              value={eventType}
              onChange={(e) => setEventType(e.target.value)}
              placeholder="z.B. document.created"
              className="font-mono"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="bulk-from">Von *</Label>
              <Input
                id="bulk-from"
                type="datetime-local"
                value={fromDate}
                onChange={(e) => setFromDate(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="bulk-to">Bis *</Label>
              <Input
                id="bulk-to"
                type="datetime-local"
                value={toDate}
                onChange={(e) => setToDate(e.target.value)}
              />
            </div>
          </div>

          <div className="rounded-md bg-amber-50 dark:bg-amber-950/30 p-3 text-sm text-amber-800 dark:text-amber-200">
            <strong>Achtung:</strong> Alle Events des angegebenen Typs im
            Zeitraum werden erneut an alle passenden Endpoints zugestellt.
            Dies kann zu doppelten Zustellungen fuehren.
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Abbrechen
          </Button>
          <Button onClick={handleReplay} disabled={bulkReplayMutation.isPending}>
            {bulkReplayMutation.isPending ? (
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            ) : (
              <RefreshCw className="h-4 w-4 mr-2" />
            )}
            Replay starten
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
