/**
 * LinkingStatisticsPage - Seite fuer Verknuepfungs-Statistiken
 *
 * WICHTIG: Types muessen EXAKT mit Backend uebereinstimmen!
 * Backend verwendet snake_case und Response hat task_id (nicht taskId)
 * @see app/api/v1/lexware.py:EntityLinkingResponse
 *
 * Zeigt Uebersicht ueber Dokument-Entity-Verknuepfungen:
 * - Verknuepfungsrate
 * - Matching-Strategien
 * - Manuelles Verknuepfen triggern
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { RefreshCw, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useToast } from '@/components/ui/use-toast'
import { LinkingStatisticsCard } from './components/LinkingStatisticsCard'
import { fetchLinkingStatistics, triggerDocumentLinking } from './api/lexware-admin-api'

export function LinkingStatisticsPage() {
  const { toast } = useToast()
  const queryClient = useQueryClient()

  // Fetch statistics
  const {
    data: statistics,
    isLoading,
    refetch,
  } = useQuery({
    queryKey: ['lexware-linking-statistics'],
    queryFn: fetchLinkingStatistics,
  })

  // Trigger linking mutation
  const linkingMutation = useMutation({
    mutationFn: triggerDocumentLinking,
    onSuccess: (result) => {
      // Backend returns snake_case: task_id, linked_count, etc.
      toast({
        title: 'Verknuepfung gestartet',
        description: result.task_id
          ? `Task ${result.task_id} wurde erstellt. Die Verknuepfung laeuft im Hintergrund.`
          : `${result.linked_count} Dokumente wurden verknuepft.`,
      })
      // Refetch statistics after a delay
      setTimeout(() => {
        queryClient.invalidateQueries({ queryKey: ['lexware-linking-statistics'] })
      }, 5000)
    },
    onError: (error) => {
      toast({
        title: 'Verknuepfung fehlgeschlagen',
        description: error instanceof Error ? error.message : 'Ein unbekannter Fehler ist aufgetreten',
        variant: 'destructive',
      })
    },
  })

  return (
    <div className="space-y-6">
      {/* Actions */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold">Verknuepfungs-Statistiken</h2>
          <p className="text-sm text-muted-foreground">
            Uebersicht ueber Dokument-Entity-Verknuepfungen
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            onClick={() => refetch()}
            disabled={isLoading}
          >
            {isLoading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <RefreshCw className="h-4 w-4" />
            )}
            <span className="ml-2">Aktualisieren</span>
          </Button>
          <Button
            onClick={() => linkingMutation.mutate()}
            disabled={linkingMutation.isPending}
          >
            {linkingMutation.isPending ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin mr-2" />
                Wird gestartet...
              </>
            ) : (
              <>
                <RefreshCw className="h-4 w-4 mr-2" />
                Alle Dokumente verknuepfen
              </>
            )}
          </Button>
        </div>
      </div>

      {/* Statistics */}
      <LinkingStatisticsCard statistics={statistics} isLoading={isLoading} />
    </div>
  )
}
