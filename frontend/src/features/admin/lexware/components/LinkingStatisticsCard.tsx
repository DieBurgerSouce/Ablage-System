/**
 * LinkingStatisticsCard - Statistiken fuer Dokumenten-Verknuepfung
 *
 * WICHTIG: Types muessen EXAKT mit Backend uebereinstimmen!
 * Backend verwendet snake_case: total_documents, linked_documents, etc.
 * @see app/api/v1/lexware.py:LinkingStatistics
 *
 * Zeigt:
 * - Verknuepfte vs Unverknuepfte Dokumente (%)
 * - Matching-Strategie-Verteilung
 * - Confidence-Level-Verteilung
 * - Entity-Type-Verteilung
 */

import { useMemo } from 'react'
import {
  Link2,
  Link2Off,
  PieChart,
  TrendingUp,
  Hash,
  Building,
  CreditCard,
  FileText,
  MapPin,
  Users,
  Package,
} from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import { Skeleton } from '@/components/ui/skeleton'
import type { LinkingStatistics } from '../api/lexware-admin-api'

interface LinkingStatisticsCardProps {
  statistics: LinkingStatistics | undefined
  isLoading: boolean
}

export function LinkingStatisticsCard({
  statistics,
  isLoading,
}: LinkingStatisticsCardProps) {
  // Transform by_match_type into displayable data
  const matchTypeData = useMemo(() => {
    if (!statistics?.by_match_type) return []

    const entries = Object.entries(statistics.by_match_type)
    const total = entries.reduce((sum, [, count]) => sum + count, 0)

    if (total === 0) return []

    // Map match type keys to display info
    const matchTypeInfo: Record<string, { label: string; icon: typeof Hash; color: string }> = {
      customer_number: { label: 'Kundennummer', icon: Hash, color: 'bg-green-500' },
      supplier_number: { label: 'Lieferantennummer', icon: Hash, color: 'bg-green-500' },
      matchcode: { label: 'Matchcode', icon: Building, color: 'bg-blue-500' },
      iban: { label: 'IBAN', icon: CreditCard, color: 'bg-purple-500' },
      vat_id: { label: 'USt-ID', icon: FileText, color: 'bg-orange-500' },
      fuzzy_name: { label: 'Fuzzy-Name', icon: Building, color: 'bg-yellow-500' },
      address: { label: 'Adresse', icon: MapPin, color: 'bg-pink-500' },
      manual: { label: 'Manuell', icon: Users, color: 'bg-gray-500' },
    }

    return entries
      .map(([key, count]) => {
        const info = matchTypeInfo[key] || { label: key, icon: FileText, color: 'bg-gray-500' }
        return {
          key,
          label: info.label,
          value: count,
          percent: (count / total) * 100,
          icon: info.icon,
          color: info.color,
        }
      })
      .filter((item) => item.value > 0)
      .sort((a, b) => b.value - a.value)
  }, [statistics])

  // Transform by_confidence into displayable data
  const confidenceData = useMemo(() => {
    if (!statistics?.by_confidence) return []

    const entries = Object.entries(statistics.by_confidence)
    const total = entries.reduce((sum, [, count]) => sum + count, 0)

    if (total === 0) return []

    return entries
      .map(([range, count]) => ({
        range,
        value: count,
        percent: (count / total) * 100,
      }))
      .sort((a, b) => b.range.localeCompare(a.range))
  }, [statistics])

  // Transform by_entity_type into displayable data
  const entityTypeData = useMemo(() => {
    if (!statistics?.by_entity_type) return []

    const entries = Object.entries(statistics.by_entity_type)
    const total = entries.reduce((sum, [, count]) => sum + count, 0)

    if (total === 0) return []

    const entityTypeInfo: Record<string, { label: string; icon: typeof Users }> = {
      customer: { label: 'Kunden', icon: Users },
      supplier: { label: 'Lieferanten', icon: Package },
    }

    return entries.map(([key, count]) => {
      const info = entityTypeInfo[key] || { label: key, icon: FileText }
      return {
        key,
        label: info.label,
        value: count,
        percent: (count / total) * 100,
        icon: info.icon,
      }
    })
  }, [statistics])

  if (isLoading) {
    return <LinkingStatisticsSkeleton />
  }

  if (!statistics) {
    return (
      <Card>
        <CardContent className="py-8">
          <div className="flex flex-col items-center gap-3 text-center">
            <Link2Off className="h-12 w-12 text-muted-foreground" />
            <p className="font-medium">Keine Statistiken verfuegbar</p>
            <p className="text-sm text-muted-foreground">
              Importieren Sie zuerst Kunden oder Lieferanten aus Lexware.
            </p>
          </div>
        </CardContent>
      </Card>
    )
  }

  return (
    <div className="space-y-6">
      {/* Overview Card */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <PieChart className="h-5 w-5" />
            Verknuepfungs-Uebersicht
          </CardTitle>
          <CardDescription>
            Dokumente mit zugeordneten Kunden/Lieferanten
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Linking Progress - using snake_case fields */}
          <div className="space-y-2">
            <div className="flex justify-between text-sm">
              <span>Verknuepfungsrate</span>
              <span className="font-medium">
                {statistics.linked_percentage.toFixed(1)}%
              </span>
            </div>
            <Progress
              value={statistics.linked_percentage}
              className="h-3"
            />
          </div>

          {/* Stats Grid - using snake_case fields */}
          <div className="grid grid-cols-3 gap-4">
            <div className="p-4 bg-muted/50 rounded-lg text-center">
              <p className="text-2xl font-bold">
                {statistics.total_documents.toLocaleString('de-DE')}
              </p>
              <p className="text-sm text-muted-foreground">Gesamt</p>
            </div>
            <div className="p-4 bg-green-50 dark:bg-green-950/30 rounded-lg text-center">
              <div className="flex items-center justify-center gap-1">
                <Link2 className="h-4 w-4 text-green-500" />
                <p className="text-2xl font-bold text-green-700 dark:text-green-300">
                  {statistics.linked_documents.toLocaleString('de-DE')}
                </p>
              </div>
              <p className="text-sm text-green-600 dark:text-green-400">Verknuepft</p>
            </div>
            <div className="p-4 bg-yellow-50 dark:bg-yellow-950/30 rounded-lg text-center">
              <div className="flex items-center justify-center gap-1">
                <Link2Off className="h-4 w-4 text-yellow-500" />
                <p className="text-2xl font-bold text-yellow-700 dark:text-yellow-300">
                  {statistics.unlinked_documents.toLocaleString('de-DE')}
                </p>
              </div>
              <p className="text-sm text-yellow-600 dark:text-yellow-400">Offen</p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Strategy Distribution Card */}
      {matchTypeData.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <TrendingUp className="h-5 w-5" />
              Matching-Strategien
            </CardTitle>
            <CardDescription>
              Wie wurden Dokumente zugeordnet?
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {matchTypeData.map((item) => (
                <div key={item.key} className="space-y-1">
                  <div className="flex items-center justify-between text-sm">
                    <div className="flex items-center gap-2">
                      <item.icon className="h-4 w-4 text-muted-foreground" />
                      <span>{item.label}</span>
                    </div>
                    <span className="text-muted-foreground">
                      {item.value.toLocaleString('de-DE')} ({item.percent.toFixed(1)}%)
                    </span>
                  </div>
                  <div className="h-2 bg-muted rounded-full overflow-hidden">
                    <div
                      className={`h-full ${item.color} transition-all`}
                      style={{ width: `${item.percent}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Confidence Distribution Card */}
      {confidenceData.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Confidence-Verteilung</CardTitle>
            <CardDescription>
              Wie sicher sind die Verknuepfungen?
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {confidenceData.map((item) => (
                <div key={item.range} className="space-y-1">
                  <div className="flex items-center justify-between text-sm">
                    <span>{item.range}</span>
                    <span className="text-muted-foreground">
                      {item.value.toLocaleString('de-DE')} ({item.percent.toFixed(1)}%)
                    </span>
                  </div>
                  <div className="h-2 bg-muted rounded-full overflow-hidden">
                    <div
                      className="h-full bg-primary transition-all"
                      style={{ width: `${item.percent}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Entity Type Distribution Card */}
      {entityTypeData.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Entity-Typen</CardTitle>
            <CardDescription>
              Verteilung nach Kunden vs Lieferanten
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 gap-4">
              {entityTypeData.map((item) => (
                <div
                  key={item.key}
                  className="p-4 bg-muted/50 rounded-lg text-center"
                >
                  <div className="flex items-center justify-center gap-2 mb-2">
                    <item.icon className="h-5 w-5 text-muted-foreground" />
                    <span className="font-medium">{item.label}</span>
                  </div>
                  <p className="text-2xl font-bold">
                    {item.value.toLocaleString('de-DE')}
                  </p>
                  <p className="text-sm text-muted-foreground">
                    {item.percent.toFixed(1)}%
                  </p>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

function LinkingStatisticsSkeleton() {
  return (
    <Card>
      <CardHeader>
        <Skeleton className="h-6 w-48" />
        <Skeleton className="h-4 w-64" />
      </CardHeader>
      <CardContent className="space-y-6">
        <div className="space-y-2">
          <div className="flex justify-between">
            <Skeleton className="h-4 w-32" />
            <Skeleton className="h-4 w-16" />
          </div>
          <Skeleton className="h-3 w-full" />
        </div>
        <div className="grid grid-cols-3 gap-4">
          <Skeleton className="h-20 rounded-lg" />
          <Skeleton className="h-20 rounded-lg" />
          <Skeleton className="h-20 rounded-lg" />
        </div>
      </CardContent>
    </Card>
  )
}
