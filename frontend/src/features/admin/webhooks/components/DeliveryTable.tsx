/**
 * DeliveryTable
 *
 * Tabelle fuer Zustellungshistorie und Dead Letter Queue.
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
import { Skeleton } from '@/components/ui/skeleton'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { RefreshCw, Eye, Inbox } from 'lucide-react'
import { toast } from '@/components/ui/use-toast'
import { useRetryDLQ } from '../api'
import type { WebhookDeliveryResponse, DeliveryStatus } from '../types'
import { DELIVERY_STATUS_LABELS, DELIVERY_STATUS_COLORS } from '../types'

interface DeliveryTableProps {
  deliveries: WebhookDeliveryResponse[]
  isLoading: boolean
  showRetry?: boolean
  page: number
  hasMore: boolean
  onPageChange: (page: number) => void
}

export function DeliveryTable({
  deliveries,
  isLoading,
  showRetry = false,
  page,
  hasMore,
  onPageChange,
}: DeliveryTableProps) {
  const [detailDelivery, setDetailDelivery] = useState<WebhookDeliveryResponse | null>(null)
  const retryMutation = useRetryDLQ()

  const handleRetry = async (deliveryId: string) => {
    try {
      await retryMutation.mutateAsync(deliveryId)
      toast({
        title: 'Wiederholung gestartet',
        description: 'Die Zustellung wird erneut versucht.',
      })
    } catch {
      toast({
        title: 'Fehler',
        description: 'Wiederholung konnte nicht gestartet werden.',
        variant: 'destructive',
      })
    }
  }

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return '-'
    return new Date(dateStr).toLocaleDateString('de-DE', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  }

  if (isLoading) {
    return (
      <div className="space-y-2">
        {[1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-12 w-full" />
        ))}
      </div>
    )
  }

  if (deliveries.length === 0) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        <Inbox className="h-12 w-12 mx-auto mb-4 opacity-30" />
        <p className="text-lg font-medium">Keine Eintraege vorhanden</p>
        <p className="text-sm mt-1">
          {showRetry
            ? 'Die Dead Letter Queue ist leer.'
            : 'Es wurden noch keine Zustellungen durchgefuehrt.'}
        </p>
      </div>
    )
  }

  return (
    <>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Event-Typ</TableHead>
            <TableHead>Status</TableHead>
            <TableHead className="text-center">Versuche</TableHead>
            <TableHead>HTTP-Code</TableHead>
            <TableHead>Letzter Versuch</TableHead>
            <TableHead className="text-right">Aktionen</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {deliveries.map((delivery) => (
            <TableRow key={delivery.id}>
              <TableCell>
                <Badge variant="outline" className="font-mono text-xs">
                  {delivery.event_type}
                </Badge>
              </TableCell>
              <TableCell>
                <Badge
                  variant="secondary"
                  className={DELIVERY_STATUS_COLORS[delivery.status as DeliveryStatus]}
                >
                  {DELIVERY_STATUS_LABELS[delivery.status as DeliveryStatus] ?? delivery.status}
                </Badge>
              </TableCell>
              <TableCell className="text-center">
                {delivery.attempts}/{delivery.max_attempts}
              </TableCell>
              <TableCell>
                {delivery.response_status_code ? (
                  <span
                    className={
                      delivery.response_status_code >= 200 && delivery.response_status_code < 300
                        ? 'text-green-600'
                        : 'text-red-600'
                    }
                  >
                    {delivery.response_status_code}
                  </span>
                ) : (
                  <span className="text-muted-foreground">-</span>
                )}
              </TableCell>
              <TableCell className="text-sm text-muted-foreground">
                {formatDate(delivery.last_attempt_at)}
              </TableCell>
              <TableCell className="text-right">
                <div className="flex justify-end gap-1">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setDetailDelivery(delivery)}
                  >
                    <Eye className="h-4 w-4" />
                  </Button>
                  {showRetry && delivery.status === 'dlq' && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleRetry(delivery.id)}
                      disabled={retryMutation.isPending}
                    >
                      <RefreshCw className="h-4 w-4" />
                    </Button>
                  )}
                </div>
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
          onClick={() => onPageChange(page - 1)}
          disabled={page <= 1}
        >
          Zurueck
        </Button>
        <span className="text-sm text-muted-foreground">Seite {page}</span>
        <Button
          variant="outline"
          size="sm"
          onClick={() => onPageChange(page + 1)}
          disabled={!hasMore}
        >
          Weiter
        </Button>
      </div>

      {/* Detail-Dialog */}
      <Dialog
        open={!!detailDelivery}
        onOpenChange={(open) => !open && setDetailDelivery(null)}
      >
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Zustellungs-Details</DialogTitle>
          </DialogHeader>
          {detailDelivery && (
            <div className="space-y-3 text-sm">
              <div className="grid grid-cols-2 gap-2">
                <div className="text-muted-foreground">ID</div>
                <div className="font-mono text-xs">{detailDelivery.id}</div>

                <div className="text-muted-foreground">Event-Typ</div>
                <div className="font-mono">{detailDelivery.event_type}</div>

                <div className="text-muted-foreground">Status</div>
                <div>
                  <Badge
                    variant="secondary"
                    className={DELIVERY_STATUS_COLORS[detailDelivery.status as DeliveryStatus]}
                  >
                    {DELIVERY_STATUS_LABELS[detailDelivery.status as DeliveryStatus]}
                  </Badge>
                </div>

                <div className="text-muted-foreground">Versuche</div>
                <div>{detailDelivery.attempts}/{detailDelivery.max_attempts}</div>

                <div className="text-muted-foreground">HTTP-Code</div>
                <div>{detailDelivery.response_status_code ?? '-'}</div>

                <div className="text-muted-foreground">Erstellt</div>
                <div>{formatDate(detailDelivery.created_at)}</div>

                <div className="text-muted-foreground">Zugestellt</div>
                <div>{formatDate(detailDelivery.delivered_at)}</div>

                <div className="text-muted-foreground">Naechster Retry</div>
                <div>{formatDate(detailDelivery.next_retry_at)}</div>
              </div>

              {detailDelivery.response_body && (
                <div>
                  <div className="text-muted-foreground mb-1">Antwort-Body</div>
                  <pre className="text-xs bg-muted p-2 rounded overflow-x-auto max-h-32">
                    {detailDelivery.response_body}
                  </pre>
                </div>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </>
  )
}
