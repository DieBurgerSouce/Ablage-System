/**
 * EndpointTable
 *
 * Tabelle zur Anzeige registrierter Webhook-Endpoints mit Aktionen.
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
import { Switch } from '@/components/ui/switch'
import { Skeleton } from '@/components/ui/skeleton'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
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
import { MoreHorizontal, Pencil, Trash2, Send, History, Webhook } from 'lucide-react'
import { toast } from '@/components/ui/use-toast'
import { useDeleteEndpoint, useUpdateEndpoint } from '../api'
import type { WebhookEndpointResponse } from '../types'

interface EndpointTableProps {
  endpoints: WebhookEndpointResponse[]
  isLoading: boolean
  onEdit: (endpoint: WebhookEndpointResponse) => void
  onTest: (endpoint: WebhookEndpointResponse) => void
  onViewDeliveries: (endpoint: WebhookEndpointResponse) => void
}

export function EndpointTable({
  endpoints,
  isLoading,
  onEdit,
  onTest,
  onViewDeliveries,
}: EndpointTableProps) {
  const [deleteId, setDeleteId] = useState<string | null>(null)
  const deleteMutation = useDeleteEndpoint()
  const updateMutation = useUpdateEndpoint()

  const handleDelete = async () => {
    if (!deleteId) return
    try {
      await deleteMutation.mutateAsync(deleteId)
      toast({
        title: 'Endpoint deaktiviert',
        description: 'Der Webhook-Endpoint wurde deaktiviert.',
      })
    } catch {
      toast({
        title: 'Fehler',
        description: 'Der Endpoint konnte nicht deaktiviert werden.',
        variant: 'destructive',
      })
    }
    setDeleteId(null)
  }

  const handleToggleActive = async (
    endpoint: WebhookEndpointResponse,
    isActive: boolean
  ) => {
    try {
      await updateMutation.mutateAsync({
        id: endpoint.id,
        data: { is_active: isActive },
      })
      toast({
        title: isActive ? 'Endpoint aktiviert' : 'Endpoint deaktiviert',
        description: `"${endpoint.url}" wurde ${isActive ? 'aktiviert' : 'deaktiviert'}.`,
      })
    } catch {
      toast({
        title: 'Fehler',
        description: 'Status konnte nicht geaendert werden.',
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

  if (isLoading) {
    return (
      <div className="space-y-2">
        {[1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-12 w-full" />
        ))}
      </div>
    )
  }

  if (endpoints.length === 0) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        <Webhook className="h-12 w-12 mx-auto mb-4 opacity-30" />
        <p className="text-lg font-medium">Keine Webhook-Endpoints vorhanden</p>
        <p className="text-sm mt-1">
          Registrieren Sie Ihren ersten Outbound-Webhook.
        </p>
      </div>
    )
  }

  return (
    <>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-[300px]">URL</TableHead>
            <TableHead>Event-Typen</TableHead>
            <TableHead className="text-center">Aktiv</TableHead>
            <TableHead>Erstellt</TableHead>
            <TableHead className="text-right">Aktionen</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {endpoints.map((endpoint) => (
            <TableRow key={endpoint.id}>
              <TableCell>
                <div>
                  <div className="font-mono text-sm truncate max-w-[280px]">
                    {endpoint.url}
                  </div>
                  {endpoint.description && (
                    <div className="text-xs text-muted-foreground truncate max-w-[280px]">
                      {endpoint.description}
                    </div>
                  )}
                </div>
              </TableCell>
              <TableCell>
                <div className="flex flex-wrap gap-1">
                  {endpoint.event_types.length === 0 ? (
                    <Badge variant="secondary">Alle Events</Badge>
                  ) : (
                    endpoint.event_types.slice(0, 3).map((et) => (
                      <Badge key={et} variant="outline" className="text-xs">
                        {et}
                      </Badge>
                    ))
                  )}
                  {endpoint.event_types.length > 3 && (
                    <Badge variant="secondary" className="text-xs">
                      +{endpoint.event_types.length - 3}
                    </Badge>
                  )}
                </div>
              </TableCell>
              <TableCell className="text-center">
                <Switch
                  checked={endpoint.is_active}
                  onCheckedChange={(checked) =>
                    handleToggleActive(endpoint, checked)
                  }
                />
              </TableCell>
              <TableCell className="text-sm text-muted-foreground">
                {formatDate(endpoint.created_at)}
              </TableCell>
              <TableCell className="text-right">
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="ghost" className="h-8 w-8 p-0">
                      <MoreHorizontal className="h-4 w-4" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    <DropdownMenuItem onClick={() => onEdit(endpoint)}>
                      <Pencil className="h-4 w-4 mr-2" />
                      Bearbeiten
                    </DropdownMenuItem>
                    <DropdownMenuItem onClick={() => onTest(endpoint)}>
                      <Send className="h-4 w-4 mr-2" />
                      Testen
                    </DropdownMenuItem>
                    <DropdownMenuItem onClick={() => onViewDeliveries(endpoint)}>
                      <History className="h-4 w-4 mr-2" />
                      Zustellungen
                    </DropdownMenuItem>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem
                      onClick={() => setDeleteId(endpoint.id)}
                      className="text-destructive"
                    >
                      <Trash2 className="h-4 w-4 mr-2" />
                      Deaktivieren
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>

      <AlertDialog
        open={!!deleteId}
        onOpenChange={(open) => !open && setDeleteId(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Webhook-Endpoint deaktivieren?</AlertDialogTitle>
            <AlertDialogDescription>
              Der Endpoint wird deaktiviert und erhaelt keine weiteren Zustellungen.
              Historische Daten bleiben fuer Auditzwecke erhalten.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Abbrechen</AlertDialogCancel>
            <AlertDialogAction onClick={handleDelete}>
              Deaktivieren
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}
