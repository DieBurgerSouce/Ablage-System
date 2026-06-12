/**
 * Action Approval Queue Page
 * Admin-Seite für Genehmigung autonomer Aktionen
 */

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, XCircle, Filter, RefreshCw, Loader2, ListChecks } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { useToast } from '@/hooks/use-toast'
import { getActionQueue, approveAction, rejectAction } from './api/automation-config-api'

// German labels for action types
const ACTION_TYPE_LABELS: Record<string, string> = {
  APPROVE_PAYMENT: 'Zahlungsfreigabe',
  SEND_DUNNING: 'Mahnung',
  FILE_DOCUMENT: 'Ablage',
  UPDATE_MASTER_DATA: 'Stammdaten-Update',
  ASSIGN_ENTITY: 'Entität zuweisen',
  CLASSIFY_DOCUMENT: 'Klassifizierung',
}

// Status badges
const STATUS_VARIANTS: Record<string, 'default' | 'secondary' | 'destructive' | 'outline'> = {
  pending: 'default',
  approved: 'secondary',
  rejected: 'destructive',
  executed: 'outline',
}

// Confidence color helper
const getConfidenceColor = (confidence: number): string => {
  if (confidence >= 0.9) return 'text-green-600 dark:text-green-400'
  if (confidence >= 0.7) return 'text-yellow-600 dark:text-yellow-400'
  return 'text-red-600 dark:text-red-400'
}

export function ActionApprovalQueue() {
  const { toast } = useToast()
  const queryClient = useQueryClient()
  const [statusFilter, setStatusFilter] = useState('pending')
  const [selectedIds, setSelectedIds] = useState<string[]>([])

  // Load queue with auto-refresh
  const {
    data: queueData,
    isLoading,
    refetch,
  } = useQuery({
    queryKey: ['action-queue', statusFilter],
    queryFn: () => getActionQueue(statusFilter),
    refetchInterval: 30000, // Auto-refresh every 30s
  })

  const actions = queueData?.actions || []

  // Approve mutation
  const approveMutation = useMutation({
    mutationFn: approveAction,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['action-queue'] })
      toast({
        title: 'Genehmigt',
        description: 'Aktion wurde genehmigt und wird ausgeführt',
      })
    },
    onError: () => {
      toast({
        title: 'Fehler',
        description: 'Aktion konnte nicht genehmigt werden',
        variant: 'destructive',
      })
    },
  })

  // Reject mutation
  const rejectMutation = useMutation({
    mutationFn: ({ actionId, reason }: { actionId: string; reason?: string }) => rejectAction(actionId, reason),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['action-queue'] })
      toast({
        title: 'Abgelehnt',
        description: 'Aktion wurde abgelehnt',
      })
    },
    onError: () => {
      toast({
        title: 'Fehler',
        description: 'Aktion konnte nicht abgelehnt werden',
        variant: 'destructive',
      })
    },
  })

  const handleApprove = (actionId: string) => {
    approveMutation.mutate(actionId)
  }

  const handleReject = (actionId: string) => {
    rejectMutation.mutate({ actionId })
  }

  const handleBulkApprove = () => {
    if (selectedIds.length === 0) return
    Promise.all(selectedIds.map((id) => approveMutation.mutateAsync(id))).then(() => {
      setSelectedIds([])
    })
  }

  const handleBulkReject = () => {
    if (selectedIds.length === 0) return
    Promise.all(selectedIds.map((id) => rejectMutation.mutateAsync({ actionId: id }))).then(() => {
      setSelectedIds([])
    })
  }

  const handleSelectAll = (checked: boolean) => {
    if (checked) {
      setSelectedIds(actions.map((action) => action.id))
    } else {
      setSelectedIds([])
    }
  }

  const handleSelectOne = (actionId: string, checked: boolean) => {
    if (checked) {
      setSelectedIds([...selectedIds, actionId])
    } else {
      setSelectedIds(selectedIds.filter((id) => id !== actionId))
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

  const truncateText = (text: string, maxLength: number = 50) => {
    if (text.length <= maxLength) return text
    return text.substring(0, maxLength) + '...'
  }

  return (
    <div className="container mx-auto py-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <ListChecks className="h-6 w-6" />
            Aktions-Warteschlange
          </h1>
          <p className="text-muted-foreground">
            Ausstehende autonome Aktionen prüfen und genehmigen
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Select value={statusFilter} onValueChange={setStatusFilter}>
            <SelectTrigger className="w-[180px]">
              <Filter className="h-4 w-4 mr-2" />
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="pending">Ausstehend</SelectItem>
              <SelectItem value="approved">Genehmigt</SelectItem>
              <SelectItem value="rejected">Abgelehnt</SelectItem>
              <SelectItem value="executed">Ausgeführt</SelectItem>
            </SelectContent>
          </Select>
          <Button variant="outline" size="icon" onClick={() => refetch()}>
            <RefreshCw className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {/* Bulk Actions Bar */}
      {selectedIds.length > 0 && (
        <Card className="bg-muted/50">
          <CardContent className="py-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Badge variant="secondary">{selectedIds.length} ausgewählt</Badge>
              </div>
              <div className="flex items-center gap-2">
                <Button variant="outline" size="sm" onClick={handleBulkReject}>
                  <XCircle className="h-4 w-4 mr-2" />
                  Alle ablehnen
                </Button>
                <Button variant="default" size="sm" onClick={handleBulkApprove}>
                  <CheckCircle2 className="h-4 w-4 mr-2" />
                  Alle genehmigen
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Actions Table */}
      <Card>
        <CardHeader>
          <CardTitle>Aktionen ({queueData?.total || 0})</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
          ) : actions.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-center">
              <CheckCircle2 className="h-12 w-12 text-green-500 mb-4" />
              <h3 className="text-lg font-medium">Keine ausstehenden Aktionen</h3>
              <p className="text-sm text-muted-foreground mt-1">
                Alle autonomen Aktionen wurden verarbeitet
              </p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[50px]">
                    <Checkbox
                      checked={selectedIds.length === actions.length && actions.length > 0}
                      onCheckedChange={handleSelectAll}
                      aria-label="Alle auswählen"
                    />
                  </TableHead>
                  <TableHead>Typ</TableHead>
                  <TableHead>Entität</TableHead>
                  <TableHead>Konfidenz</TableHead>
                  <TableHead>Grund</TableHead>
                  <TableHead>Erstellt</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Aktionen</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {actions.map((action) => (
                  <TableRow key={action.id}>
                    <TableCell>
                      <Checkbox
                        checked={selectedIds.includes(action.id)}
                        onCheckedChange={(checked) => handleSelectOne(action.id, checked as boolean)}
                        aria-label={`Aktion ${action.id} auswählen`}
                      />
                    </TableCell>
                    <TableCell>
                      <div className="font-medium">
                        {ACTION_TYPE_LABELS[action.action_type] || action.action_type}
                      </div>
                    </TableCell>
                    <TableCell>
                      <div className="max-w-[150px]">
                        {action.entity_name ? (
                          <span className="font-medium">{action.entity_name}</span>
                        ) : (
                          <span className="text-muted-foreground">-</span>
                        )}
                        {action.entity_type && (
                          <div className="text-xs text-muted-foreground">{action.entity_type}</div>
                        )}
                      </div>
                    </TableCell>
                    <TableCell>
                      <div className={`font-medium ${getConfidenceColor(action.confidence)}`}>
                        {(action.confidence * 100).toFixed(1)}%
                      </div>
                    </TableCell>
                    <TableCell>
                      <div className="max-w-[200px]" title={action.reason}>
                        {truncateText(action.reason, 50)}
                      </div>
                    </TableCell>
                    <TableCell>
                      <div className="text-sm">{formatDate(action.created_at)}</div>
                      {action.will_execute_at && (
                        <div className="text-xs text-muted-foreground">
                          Ausführung: {formatDate(action.will_execute_at)}
                        </div>
                      )}
                    </TableCell>
                    <TableCell>
                      <Badge variant={STATUS_VARIANTS[action.status] || 'outline'}>{action.status}</Badge>
                    </TableCell>
                    <TableCell className="text-right">
                      {action.status === 'pending' && (
                        <div className="flex items-center justify-end gap-1">
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => handleReject(action.id)}
                            disabled={rejectMutation.isPending}
                            title="Ablehnen"
                          >
                            <XCircle className="h-4 w-4 text-red-500" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => handleApprove(action.id)}
                            disabled={approveMutation.isPending}
                            title="Genehmigen"
                          >
                            <CheckCircle2 className="h-4 w-4 text-green-500" />
                          </Button>
                        </div>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
