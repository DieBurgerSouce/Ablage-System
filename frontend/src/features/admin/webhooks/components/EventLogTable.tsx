/**
 * EventLogTable
 *
 * Event-Protokoll mit Filter nach Typ und Zeitraum.
 */

import { useState } from 'react'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { RefreshCw, Loader2, ScrollText } from 'lucide-react'
import { toast } from '@/components/ui/use-toast'
import { useEventLog, useReplayEvent } from '../api'
import type { WebhookEventLogResponse } from '../types'

interface EventLogTableProps {
  onBulkReplay: () => void
}

export function EventLogTable({ onBulkReplay }: EventLogTableProps) {
  const [page, setPage] = useState(1)
  const [eventTypeFilter, setEventTypeFilter] = useState('')
  const [fromDate, setFromDate] = useState('')
  const [toDate, setToDate] = useState('')

  const { data, isLoading } = useEventLog({
    page,
    per_page: 20,
    event_type: eventTypeFilter || undefined,
    from_date: fromDate || undefined,
    to_date: toDate || undefined,
  })

  const replayMutation = useReplayEvent()

  const handleReplay = async (event: WebhookEventLogResponse) => {
    try {
      const result = await replayMutation.mutateAsync(event.id)
      toast({
        title: 'Replay gestartet',
        description: result.message,
      })
    } catch {
      toast({
        title: 'Fehler',
        description: 'Event-Replay konnte nicht gestartet werden.',
        variant: 'destructive',
      })
    }
  }

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString('de-DE', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  }

  const events = data?.items ?? []

  return (
    <div className="space-y-4">
      {/* Filter */}
      <div className="flex flex-col md:flex-row gap-4 items-end">
        <div className="space-y-1 flex-1">
          <Label className="text-xs">Event-Typ</Label>
          <Input
            value={eventTypeFilter}
            onChange={(e) => {
              setEventTypeFilter(e.target.value)
              setPage(1)
            }}
            placeholder="z.B. document.created"
            className="font-mono"
          />
        </div>
        <div className="space-y-1">
          <Label className="text-xs">Von</Label>
          <Input
            type="datetime-local"
            value={fromDate}
            onChange={(e) => {
              setFromDate(e.target.value)
              setPage(1)
            }}
          />
        </div>
        <div className="space-y-1">
          <Label className="text-xs">Bis</Label>
          <Input
            type="datetime-local"
            value={toDate}
            onChange={(e) => {
              setToDate(e.target.value)
              setPage(1)
            }}
          />
        </div>
        <Button variant="outline" onClick={onBulkReplay}>
          Bulk-Replay
        </Button>
      </div>

      {/* Table */}
      {isLoading ? (
        <div className="space-y-2">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-12 w-full" />
          ))}
        </div>
      ) : events.length === 0 ? (
        <div className="text-center py-12 text-muted-foreground">
          <ScrollText className="h-12 w-12 mx-auto mb-4 opacity-30" />
          <p className="text-lg font-medium">Keine Events vorhanden</p>
          <p className="text-sm mt-1">
            Es wurden noch keine Webhook-Events publiziert.
          </p>
        </div>
      ) : (
        <>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Event-Typ</TableHead>
                <TableHead>Quelle</TableHead>
                <TableHead>Quell-ID</TableHead>
                <TableHead>Zeitpunkt</TableHead>
                <TableHead className="text-right">Aktion</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {events.map((event) => (
                <TableRow key={event.id}>
                  <TableCell>
                    <Badge variant="outline" className="font-mono text-xs">
                      {event.event_type}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-sm">
                    {event.source_table}
                  </TableCell>
                  <TableCell className="font-mono text-xs text-muted-foreground">
                    {event.source_id.slice(0, 8)}...
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {formatDate(event.created_at)}
                  </TableCell>
                  <TableCell className="text-right">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleReplay(event)}
                      disabled={replayMutation.isPending}
                    >
                      {replayMutation.isPending ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <RefreshCw className="h-4 w-4" />
                      )}
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>

          {/* Pagination */}
          <div className="flex justify-between items-center pt-4">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page <= 1}
            >
              Zurueck
            </Button>
            <span className="text-sm text-muted-foreground">Seite {page}</span>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage((p) => p + 1)}
              disabled={!data?.has_more}
            >
              Weiter
            </Button>
          </div>
        </>
      )}
    </div>
  )
}
