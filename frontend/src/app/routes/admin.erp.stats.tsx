/**
 * ERP Statistics Route
 *
 * Detaillierte Statistiken zur ERP-Integration.
 */

import { createFileRoute } from '@tanstack/react-router'
import { useQuery } from '@tanstack/react-query'
import {
  BarChart,
  LineChart,
  PieChart,
  TrendingUp,
  TrendingDown,
  Loader2,
  Activity,
} from 'lucide-react'

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Progress } from '@/components/ui/progress'

import { useERPConnections, useERPStats } from '@/features/erp'
import { getSyncHistory, erpKeys } from '@/features/erp/api'
import type { ERPSyncHistory } from '@/features/erp/types'
import { useState } from 'react'

export const Route = createFileRoute('/admin/erp/stats')({
  component: ERPStatsPage,
})

function ERPStatsPage() {
  const [selectedConnection, setSelectedConnection] = useState<string>('')
  const [timeRange, setTimeRange] = useState<'24h' | '7d' | '30d'>('7d')

  const { data: connections } = useERPConnections()
  const { data: stats, isLoading: statsLoading } = useERPStats()

  const { data: syncHistory, isLoading: historyLoading } = useQuery({
    queryKey: [...erpKeys.syncHistory(selectedConnection || 'all'), timeRange],
    queryFn: () => {
      if (selectedConnection) {
        return getSyncHistory(selectedConnection, 200)
      }
      return [] as ERPSyncHistory[]
    },
    enabled: !!selectedConnection,
  })

  // Calculate stats from history
  const calculateStats = (history: ERPSyncHistory[]) => {
    if (!history?.length) return null

    const now = new Date()
    const rangeHours = timeRange === '24h' ? 24 : timeRange === '7d' ? 168 : 720
    const cutoff = new Date(now.getTime() - rangeHours * 60 * 60 * 1000)

    const filteredHistory = history.filter((h) => new Date(h.started_at) >= cutoff)

    if (!filteredHistory.length) return null

    const successCount = filteredHistory.filter((h) => h.status === 'success').length
    const failedCount = filteredHistory.filter((h) => h.status === 'failed').length
    const totalRecords = filteredHistory.reduce((sum, h) => sum + h.records_synced, 0)
    const totalConflicts = filteredHistory.reduce((sum, h) => sum + h.conflicts_detected, 0)
    const avgDuration =
      filteredHistory.reduce((sum, h) => sum + (h.duration_seconds || 0), 0) /
      filteredHistory.length

    // Entity breakdown
    const entityStats: Record<string, { synced: number; conflicts: number }> = {}
    filteredHistory.forEach((h) => {
      if (!entityStats[h.entity]) {
        entityStats[h.entity] = { synced: 0, conflicts: 0 }
      }
      entityStats[h.entity].synced += h.records_synced
      entityStats[h.entity].conflicts += h.conflicts_detected
    })

    return {
      successRate: (successCount / filteredHistory.length) * 100,
      successCount,
      failedCount,
      totalRecords,
      totalConflicts,
      avgDuration,
      totalSyncs: filteredHistory.length,
      entityStats,
    }
  }

  const calculatedStats = syncHistory ? calculateStats(syncHistory) : null

  const entityLabels: Record<string, string> = {
    customer: 'Kunden',
    supplier: 'Lieferanten',
    invoice: 'Rechnungen',
    payment: 'Zahlungen',
    product: 'Produkte',
    document: 'Dokumente',
    order: 'Bestellungen',
  }

  const timeRangeLabels: Record<string, string> = {
    '24h': 'Letzte 24 Stunden',
    '7d': 'Letzte 7 Tage',
    '30d': 'Letzte 30 Tage',
  }

  return (
    <div className="space-y-6">
      {/* Filters */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold">ERP-Statistiken</h2>
          <p className="text-muted-foreground">
            Detaillierte Sync-Metriken und Trends
          </p>
        </div>
        <div className="flex items-center gap-4">
          <Select value={selectedConnection} onValueChange={setSelectedConnection}>
            <SelectTrigger className="w-[200px]">
              <SelectValue placeholder="Verbindung waehlen" />
            </SelectTrigger>
            <SelectContent>
              {connections?.map((conn) => (
                <SelectItem key={conn.id} value={conn.id}>
                  {conn.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          <Select value={timeRange} onValueChange={(v) => setTimeRange(v as typeof timeRange)}>
            <SelectTrigger className="w-[180px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="24h">Letzte 24 Stunden</SelectItem>
              <SelectItem value="7d">Letzte 7 Tage</SelectItem>
              <SelectItem value="30d">Letzte 30 Tage</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* Global Stats Cards */}
      {statsLoading ? (
        <div className="flex items-center justify-center py-8">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      ) : stats && (
        <div className="grid gap-4 md:grid-cols-4">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium">Verbindungen</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stats.total_connections}</div>
              <p className="text-xs text-muted-foreground">
                {stats.active_connections} aktiv
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium">Syncs (24h)</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stats.syncs_last_24h}</div>
              <p className="text-xs text-muted-foreground">
                Synchronisierungen durchgefuehrt
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium">Offene Konflikte</CardTitle>
            </CardHeader>
            <CardContent>
              <div className={`text-2xl font-bold ${stats.pending_conflicts > 0 ? 'text-yellow-600' : 'text-green-600'}`}>
                {stats.pending_conflicts}
              </div>
              <p className="text-xs text-muted-foreground">
                Warten auf Aufloesung
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium">Verbindungsrate</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">
                {stats.total_connections > 0
                  ? Math.round((stats.active_connections / stats.total_connections) * 100)
                  : 0}%
              </div>
              <Progress
                value={stats.total_connections > 0 ? (stats.active_connections / stats.total_connections) * 100 : 0}
                className="mt-2"
              />
            </CardContent>
          </Card>
        </div>
      )}

      {/* Connection-specific Stats */}
      {!selectedConnection ? (
        <Card>
          <CardContent className="py-12 text-center text-muted-foreground">
            <Activity className="h-12 w-12 mx-auto mb-4 opacity-50" />
            <p>Waehlen Sie eine Verbindung aus, um detaillierte Statistiken anzuzeigen</p>
          </CardContent>
        </Card>
      ) : historyLoading ? (
        <div className="flex items-center justify-center py-8">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      ) : calculatedStats ? (
        <>
          {/* Performance Overview */}
          <div className="grid gap-4 md:grid-cols-3">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium flex items-center gap-2">
                  <BarChart className="h-4 w-4" />
                  Erfolgsrate
                </CardTitle>
                <CardDescription>{timeRangeLabels[timeRange]}</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="flex items-center gap-2">
                  <div className={`text-3xl font-bold ${calculatedStats.successRate >= 95 ? 'text-green-600' : calculatedStats.successRate >= 80 ? 'text-yellow-600' : 'text-red-600'}`}>
                    {calculatedStats.successRate.toFixed(1)}%
                  </div>
                  {calculatedStats.successRate >= 95 ? (
                    <TrendingUp className="h-5 w-5 text-green-600" />
                  ) : (
                    <TrendingDown className="h-5 w-5 text-red-600" />
                  )}
                </div>
                <Progress value={calculatedStats.successRate} className="mt-2" />
                <p className="text-xs text-muted-foreground mt-2">
                  {calculatedStats.successCount} erfolgreich, {calculatedStats.failedCount} fehlgeschlagen
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium flex items-center gap-2">
                  <LineChart className="h-4 w-4" />
                  Durchsatz
                </CardTitle>
                <CardDescription>{timeRangeLabels[timeRange]}</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="text-3xl font-bold">
                  {calculatedStats.totalRecords.toLocaleString('de-DE')}
                </div>
                <p className="text-xs text-muted-foreground mt-2">
                  Datensaetze synchronisiert
                </p>
                <div className="flex items-center gap-4 mt-2 text-sm">
                  <span>{calculatedStats.totalSyncs} Syncs</span>
                  <span className="text-muted-foreground">|</span>
                  <span>{Math.round(calculatedStats.totalRecords / calculatedStats.totalSyncs)} pro Sync</span>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium flex items-center gap-2">
                  <PieChart className="h-4 w-4" />
                  Durchschnittl. Dauer
                </CardTitle>
                <CardDescription>{timeRangeLabels[timeRange]}</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="text-3xl font-bold">
                  {calculatedStats.avgDuration < 60
                    ? `${calculatedStats.avgDuration.toFixed(1)}s`
                    : `${(calculatedStats.avgDuration / 60).toFixed(1)}m`}
                </div>
                <p className="text-xs text-muted-foreground mt-2">
                  Pro Synchronisation
                </p>
                <div className="flex items-center gap-4 mt-2 text-sm">
                  <Badge variant={calculatedStats.totalConflicts > 0 ? 'destructive' : 'secondary'}>
                    {calculatedStats.totalConflicts} Konflikte
                  </Badge>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Entity Breakdown */}
          <Card>
            <CardHeader>
              <CardTitle>Entitaeten-Aufschluesselung</CardTitle>
              <CardDescription>
                Synchronisierte Datensaetze nach Entitaetstyp
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                {Object.entries(calculatedStats.entityStats).map(([entity, stats]) => (
                  <div key={entity} className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div className="w-24 font-medium">
                        {entityLabels[entity] || entity}
                      </div>
                      <Progress
                        value={(stats.synced / calculatedStats.totalRecords) * 100}
                        className="w-48"
                      />
                    </div>
                    <div className="flex items-center gap-4 text-sm">
                      <span className="font-medium">
                        {stats.synced.toLocaleString('de-DE')}
                      </span>
                      {stats.conflicts > 0 && (
                        <Badge variant="outline" className="text-yellow-600">
                          {stats.conflicts} Konflikte
                        </Badge>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </>
      ) : (
        <Card>
          <CardContent className="py-12 text-center text-muted-foreground">
            <BarChart className="h-12 w-12 mx-auto mb-4 opacity-50" />
            <p>Keine Sync-Daten fuer den ausgewaehlten Zeitraum</p>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
