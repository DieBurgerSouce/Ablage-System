/**
 * FinanceReportPanel - Finanz-Reports & Statistiken
 *
 * Zeigt aggregierte Finanz-Daten und ermoeglicht Report-Downloads.
 *
 * Features:
 * - KPI-Karten (Gesamt, Nachzahlung, Erstattung, Saldo)
 * - Kategorien-Verteilung
 * - Jahres-Vergleich
 * - Export-Optionen
 * - Accessibility-konform (WCAG 2.1 AA)
 */

import { memo, useMemo, useState } from 'react'
import {
  BarChart3,
  TrendingUp,
  TrendingDown,
  Minus,
  Download,
  FileSpreadsheet,
  Calendar,
  Euro,
  FileText,
  AlertTriangle,
  Clock,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import {
  useFinanceOverallAggregations,
  useFinanceYears,
  useFinanceDeadlines,
} from '../hooks/use-finanzen-queries'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Badge } from '@/components/ui/badge'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { FinanceExportDialog } from './FinanceExportDialog'

// ==================== TYPES ====================

interface FinanceReportPanelProps {
  className?: string
  year?: string
}

// ==================== HELPER FUNCTIONS ====================

function formatCurrency(amount: number): string {
  return new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency: 'EUR',
  }).format(amount)
}

function formatNumber(num: number): string {
  return new Intl.NumberFormat('de-DE').format(num)
}

// ==================== KPI CARD ====================

interface KPICardProps {
  title: string
  value: string | number
  subtitle?: string
  icon: typeof Euro
  trend?: 'up' | 'down' | 'neutral'
  trendValue?: string
  className?: string
}

const KPICard = memo(function KPICard({
  title,
  value,
  subtitle,
  icon: Icon,
  trend,
  trendValue,
  className,
}: KPICardProps) {
  return (
    <Card className={className}>
      <CardContent className="p-4">
        <div className="flex items-start justify-between">
          <div className="space-y-1">
            <p className="text-sm text-muted-foreground">{title}</p>
            <p className="text-2xl font-bold">{value}</p>
            {subtitle && (
              <p className="text-xs text-muted-foreground">{subtitle}</p>
            )}
          </div>
          <div className="flex flex-col items-end gap-1">
            <div className="p-2 bg-muted rounded-md">
              <Icon className="h-4 w-4" aria-hidden="true" />
            </div>
            {trend && trendValue && (
              <div className={cn(
                'flex items-center gap-1 text-xs',
                trend === 'up' && 'text-green-600',
                trend === 'down' && 'text-red-600',
                trend === 'neutral' && 'text-muted-foreground'
              )}>
                {trend === 'up' && <TrendingUp className="h-3 w-3" />}
                {trend === 'down' && <TrendingDown className="h-3 w-3" />}
                {trend === 'neutral' && <Minus className="h-3 w-3" />}
                {trendValue}
              </div>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  )
})

// ==================== CATEGORY CHART ====================

interface CategoryBarProps {
  category: string
  count: number
  maxCount: number
  color: string
}

const CategoryBar = memo(function CategoryBar({
  category,
  count,
  maxCount,
  color,
}: CategoryBarProps) {
  const percentage = maxCount > 0 ? (count / maxCount) * 100 : 0

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-sm">
        <span className="font-medium capitalize">{category.replace(/_/g, ' ')}</span>
        <span className="text-muted-foreground">{formatNumber(count)}</span>
      </div>
      <div className="h-2 bg-muted rounded-full overflow-hidden">
        <div
          className={cn('h-full rounded-full transition-all', color)}
          style={{ width: `${percentage}%` }}
          role="progressbar"
          aria-valuenow={count}
          aria-valuemax={maxCount}
          aria-label={`${category}: ${count} Dokumente`}
        />
      </div>
    </div>
  )
})

// ==================== DEADLINE SUMMARY ====================

interface DeadlineSummaryProps {
  overdueCount: number
  urgentCount: number
  upcomingCount: number
}

const DeadlineSummary = memo(function DeadlineSummary({
  overdueCount,
  urgentCount,
  upcomingCount,
}: DeadlineSummaryProps) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base flex items-center gap-2">
          <Clock className="h-4 w-4" aria-hidden="true" />
          Fristen-Uebersicht
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {overdueCount > 0 && (
          <div className="flex items-center justify-between p-2 bg-red-50 dark:bg-red-950/30 rounded-md">
            <div className="flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 text-red-600" aria-hidden="true" />
              <span className="text-sm font-medium text-red-700 dark:text-red-400">
                Ueberfaellig
              </span>
            </div>
            <Badge variant="destructive">{overdueCount}</Badge>
          </div>
        )}

        {urgentCount > 0 && (
          <div className="flex items-center justify-between p-2 bg-amber-50 dark:bg-amber-950/30 rounded-md">
            <div className="flex items-center gap-2">
              <Clock className="h-4 w-4 text-amber-600" aria-hidden="true" />
              <span className="text-sm font-medium text-amber-700 dark:text-amber-400">
                Dringend (7 Tage)
              </span>
            </div>
            <Badge className="bg-amber-500">{urgentCount}</Badge>
          </div>
        )}

        <div className="flex items-center justify-between p-2 bg-blue-50 dark:bg-blue-950/30 rounded-md">
          <div className="flex items-center gap-2">
            <Calendar className="h-4 w-4 text-blue-600" aria-hidden="true" />
            <span className="text-sm font-medium text-blue-700 dark:text-blue-400">
              Kommend (30 Tage)
            </span>
          </div>
          <Badge variant="secondary">{upcomingCount}</Badge>
        </div>

        {overdueCount === 0 && urgentCount === 0 && upcomingCount === 0 && (
          <p className="text-sm text-muted-foreground text-center py-2">
            Keine anstehenden Fristen
          </p>
        )}
      </CardContent>
    </Card>
  )
})

// ==================== LOADING SKELETON ====================

function ReportSkeleton() {
  return (
    <div className="space-y-6">
      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {[1, 2, 3, 4].map((i) => (
          <Card key={i}>
            <CardContent className="p-4">
              <Skeleton className="h-4 w-20 mb-2" />
              <Skeleton className="h-8 w-32 mb-1" />
              <Skeleton className="h-3 w-24" />
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <Skeleton className="h-5 w-32" />
          </CardHeader>
          <CardContent className="space-y-3">
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="space-y-1">
                <div className="flex justify-between">
                  <Skeleton className="h-4 w-24" />
                  <Skeleton className="h-4 w-12" />
                </div>
                <Skeleton className="h-2 w-full" />
              </div>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <Skeleton className="h-5 w-24" />
          </CardHeader>
          <CardContent className="space-y-3">
            {[1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-10 w-full" />
            ))}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

// ==================== MAIN COMPONENT ====================

export const FinanceReportPanel = memo(function FinanceReportPanel({
  className,
  year,
}: FinanceReportPanelProps) {
  const [exportDialogOpen, setExportDialogOpen] = useState(false)
  const [selectedYear, setSelectedYear] = useState<string | undefined>(year)

  const { data: aggregations, isLoading: isLoadingAgg } = useFinanceOverallAggregations()
  const { data: years, isLoading: isLoadingYears } = useFinanceYears()
  const { data: deadlines, isLoading: isLoadingDeadlines } = useFinanceDeadlines({
    year: selectedYear,
    includePast: false,
    daysAhead: 30,
  })

  const isLoading = isLoadingAgg || isLoadingYears || isLoadingDeadlines

  // Calculate saldo trend
  const saldoTrend = useMemo(() => {
    if (!aggregations) return { trend: 'neutral' as const, value: '' }

    const saldo = aggregations.saldo
    if (saldo > 0) return { trend: 'up' as const, value: `+${formatCurrency(saldo)}` }
    if (saldo < 0) return { trend: 'down' as const, value: formatCurrency(saldo) }
    return { trend: 'neutral' as const, value: 'Ausgeglichen' }
  }, [aggregations])

  // Category distribution
  const categoryDistribution = useMemo(() => {
    if (!aggregations?.documentsByPackage) return []

    const entries = Object.entries(aggregations.documentsByPackage)
    const maxCount = Math.max(...entries.map(([, count]) => count))
    const colors = [
      'bg-blue-500',
      'bg-green-500',
      'bg-amber-500',
      'bg-purple-500',
      'bg-pink-500',
      'bg-teal-500',
    ]

    return entries.map(([category, count], index) => ({
      category,
      count,
      maxCount,
      color: colors[index % colors.length],
    }))
  }, [aggregations])

  // All document IDs for export (simplified - would need API call in production)
  const allDocumentIds = useMemo(() => {
    // This would normally come from an API call to get all document IDs
    // For now, we'll pass an empty array and let the export dialog handle it
    return []
  }, [])

  if (isLoading) {
    return (
      <div className={cn('p-4', className)} aria-label="Berichte werden geladen...">
        <ReportSkeleton />
      </div>
    )
  }

  return (
    <div className={cn('space-y-6', className)}>
      {/* Header with export button */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <BarChart3 className="h-5 w-5" aria-hidden="true" />
            Finanz-Reports
          </h2>
          <p className="text-sm text-muted-foreground">
            Aggregierte Statistiken und Berichte
          </p>
        </div>

        <div className="flex items-center gap-2">
          {/* Year filter */}
          <Select value={selectedYear || 'all'} onValueChange={(v) => setSelectedYear(v === 'all' ? undefined : v)}>
            <SelectTrigger className="w-32">
              <SelectValue placeholder="Jahr" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Alle Jahre</SelectItem>
              {years?.map((y) => (
                <SelectItem key={y.id} value={String(y.year)}>
                  {y.year}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          <Button variant="outline" onClick={() => setExportDialogOpen(true)}>
            <Download className="h-4 w-4 mr-2" aria-hidden="true" />
            Export
          </Button>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <KPICard
          title="Dokumente"
          value={formatNumber(aggregations?.totalDocuments || 0)}
          subtitle={`${years?.length || 0} Jahre`}
          icon={FileText}
        />

        <KPICard
          title="Nachzahlungen"
          value={formatCurrency(aggregations?.totalNachzahlung || 0)}
          icon={TrendingDown}
          className="border-red-200 dark:border-red-900"
        />

        <KPICard
          title="Erstattungen"
          value={formatCurrency(aggregations?.totalErstattung || 0)}
          icon={TrendingUp}
          className="border-green-200 dark:border-green-900"
        />

        <KPICard
          title="Saldo"
          value={formatCurrency(aggregations?.saldo || 0)}
          icon={Euro}
          trend={saldoTrend.trend}
          trendValue={saldoTrend.value}
          className={cn(
            (aggregations?.saldo || 0) >= 0
              ? 'border-green-200 dark:border-green-900'
              : 'border-red-200 dark:border-red-900'
          )}
        />
      </div>

      {/* Charts and summaries */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Category distribution */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <FileSpreadsheet className="h-4 w-4" aria-hidden="true" />
              Pakete-Verteilung
            </CardTitle>
            <CardDescription>
              Dokumente nach Finanz-Paket
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {categoryDistribution.length > 0 ? (
              categoryDistribution.map((item) => (
                <CategoryBar
                  key={item.category}
                  category={item.category}
                  count={item.count}
                  maxCount={item.maxCount}
                  color={item.color}
                />
              ))
            ) : (
              <p className="text-sm text-muted-foreground text-center py-4">
                Keine Daten vorhanden
              </p>
            )}
          </CardContent>
        </Card>

        {/* Deadline summary */}
        <DeadlineSummary
          overdueCount={deadlines?.overdueCount || 0}
          urgentCount={deadlines?.urgentCount || 0}
          upcomingCount={deadlines?.upcomingCount || 0}
        />
      </div>

      {/* Years overview */}
      {years && years.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Calendar className="h-4 w-4" aria-hidden="true" />
              Jahre-Uebersicht
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
              {years.map((y) => (
                <div
                  key={y.id}
                  className={cn(
                    'p-3 rounded-lg border text-center transition-colors',
                    y.isActive
                      ? 'border-primary bg-primary/5'
                      : 'hover:border-muted-foreground/50'
                  )}
                >
                  <p className="font-semibold">{y.year}</p>
                  <p className="text-xs text-muted-foreground">
                    {formatNumber(y.totalDocuments)} Dok.
                  </p>
                  {y.pendingDeadlines > 0 && (
                    <Badge variant="secondary" className="mt-1 text-xs">
                      {y.pendingDeadlines} Fristen
                    </Badge>
                  )}
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Export dialog */}
      <FinanceExportDialog
        isOpen={exportDialogOpen}
        onClose={() => setExportDialogOpen(false)}
        documentIds={allDocumentIds}
        year={selectedYear}
      />
    </div>
  )
})

export default FinanceReportPanel
