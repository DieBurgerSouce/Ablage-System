import { FileText, TrendingUp, TrendingDown, AlertTriangle, Calendar, Clock } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import type { FinanceAggregations } from '../types'
import { formatCurrency } from '../mockData'

interface FinanzenAggregationsProps {
  aggregations: FinanceAggregations | null
  isLoading?: boolean
  showDeadlines?: boolean
  showPeriod?: boolean
  earliestDate?: string | null
  latestDate?: string | null
}

/**
 * FinanzenAggregations - Zeigt Finanz-spezifische Aggregations-Karten
 *
 * Varianten:
 * - Dokumente: Anzahl der Dokumente
 * - Nachzahlung: Summe der Nachzahlungen (rot)
 * - Erstattung: Summe der Erstattungen (gruen)
 * - Offene Fristen: Anzahl offener Fristen (warning wenn > 0)
 * - Optional: Zeitraum
 */
export function FinanzenAggregations({
  aggregations,
  isLoading = false,
  showDeadlines = true,
  showPeriod = false,
  earliestDate,
  latestDate,
}: FinanzenAggregationsProps) {
  if (isLoading) {
    return <FinanzenAggregationsSkeleton />
  }

  if (!aggregations) {
    return null
  }

  const formatDateShort = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString('de-DE', {
      month: 'short',
      year: 'numeric',
    })
  }

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
      {/* Dokumente */}
      <Card>
        <CardContent className="p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-slate-100 dark:bg-slate-800">
              <FileText className="w-5 h-5 text-slate-600 dark:text-slate-400" />
            </div>
            <div>
              <p className="text-2xl font-bold">
                {aggregations.totalDocuments.toLocaleString('de-DE')}
              </p>
              <p className="text-sm text-muted-foreground">Dokumente</p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Nachzahlung */}
      <Card>
        <CardContent className="p-4">
          <div className="flex items-center gap-3">
            <div className={`p-2 rounded-lg ${aggregations.totalNachzahlung > 0 ? 'bg-red-100 dark:bg-red-950' : 'bg-slate-100 dark:bg-slate-800'}`}>
              <TrendingDown className={`w-5 h-5 ${aggregations.totalNachzahlung > 0 ? 'text-red-600 dark:text-red-400' : 'text-slate-600 dark:text-slate-400'}`} />
            </div>
            <div>
              <p className={`text-2xl font-bold ${aggregations.totalNachzahlung > 0 ? 'text-red-600 dark:text-red-400' : ''}`}>
                {formatCurrency(aggregations.totalNachzahlung)}
              </p>
              <p className="text-sm text-muted-foreground">Nachzahlung</p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Erstattung */}
      <Card>
        <CardContent className="p-4">
          <div className="flex items-center gap-3">
            <div className={`p-2 rounded-lg ${aggregations.totalErstattung > 0 ? 'bg-green-100 dark:bg-green-950' : 'bg-slate-100 dark:bg-slate-800'}`}>
              <TrendingUp className={`w-5 h-5 ${aggregations.totalErstattung > 0 ? 'text-green-600 dark:text-green-400' : 'text-slate-600 dark:text-slate-400'}`} />
            </div>
            <div>
              <p className={`text-2xl font-bold ${aggregations.totalErstattung > 0 ? 'text-green-600 dark:text-green-400' : ''}`}>
                {formatCurrency(aggregations.totalErstattung)}
              </p>
              <p className="text-sm text-muted-foreground">Erstattung</p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Offene Fristen oder Zeitraum */}
      {showDeadlines ? (
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center gap-3">
              <div className={`p-2 rounded-lg ${aggregations.pendingDeadlines > 0 ? 'bg-amber-100 dark:bg-amber-950' : 'bg-slate-100 dark:bg-slate-800'}`}>
                <AlertTriangle className={`w-5 h-5 ${aggregations.pendingDeadlines > 0 ? 'text-amber-600 dark:text-amber-400' : 'text-slate-600 dark:text-slate-400'}`} />
              </div>
              <div>
                <p className={`text-2xl font-bold ${aggregations.pendingDeadlines > 0 ? 'text-amber-600 dark:text-amber-400' : ''}`}>
                  {aggregations.pendingDeadlines}
                </p>
                <p className="text-sm text-muted-foreground">Offene Fristen</p>
              </div>
            </div>
          </CardContent>
        </Card>
      ) : showPeriod && earliestDate && latestDate ? (
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg bg-slate-100 dark:bg-slate-800">
                <Calendar className="w-5 h-5 text-slate-600 dark:text-slate-400" />
              </div>
              <div>
                <p className="text-lg font-bold">
                  {formatDateShort(earliestDate)} - {formatDateShort(latestDate)}
                </p>
                <p className="text-sm text-muted-foreground">Zeitraum</p>
              </div>
            </div>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg bg-slate-100 dark:bg-slate-800">
                <Clock className="w-5 h-5 text-slate-600 dark:text-slate-400" />
              </div>
              <div>
                <p className={`text-2xl font-bold ${aggregations.saldo >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
                  {aggregations.saldo >= 0 ? '+' : ''}{formatCurrency(aggregations.saldo)}
                </p>
                <p className="text-sm text-muted-foreground">Saldo</p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

/**
 * Skeleton für Ladeindikator
 */
function FinanzenAggregationsSkeleton() {
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4" role="status" aria-label="Lade Statistiken">
      {[1, 2, 3, 4].map((i) => (
        <Card key={i}>
          <CardContent className="p-4">
            <div className="flex items-center gap-3">
              <Skeleton className="w-9 h-9 rounded-lg" />
              <div className="space-y-2">
                <Skeleton className="h-7 w-20" />
                <Skeleton className="h-4 w-16" />
              </div>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  )
}
