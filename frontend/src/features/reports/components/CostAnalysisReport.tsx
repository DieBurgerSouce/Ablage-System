/**
 * Kostenauswertung Report
 *
 * Zeigt detaillierte Kostenanalyse mit Kategorien, Top-Lieferanten und Kostenstellen.
 * Unterstützt Vorjahresvergleich und Export in verschiedene Formate.
 */

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Switch } from '@/components/ui/switch'
import { Label } from '@/components/ui/label'
import {
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  type TooltipProps,
} from 'recharts'
import type { ValueType, NameType } from 'recharts/types/component/DefaultTooltipContent'
import { FileDown, TrendingDown, TrendingUp } from 'lucide-react'
import { toast } from 'sonner'
import { EmptyState } from '@/components/ui/empty-state'
import { fetchReportData, exportReport, type CostAnalysisData } from '../api/report-data-api'

// =============================================================================
// Constants
// =============================================================================

const CHART_COLORS = [
  'oklch(0.55 0.18 250)',   // blue
  'oklch(0.72 0.17 145)',   // green
  'oklch(0.55 0.22 25)',    // red
  'oklch(0.70 0.15 65)',    // orange
  'oklch(0.60 0.16 290)',   // purple
  'oklch(0.65 0.12 180)',   // teal
]

// =============================================================================
// Helper Functions
// =============================================================================

function formatCurrency(value: number): string {
  return value.toLocaleString('de-DE', {
    style: 'currency',
    currency: 'EUR',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  })
}

// =============================================================================
// Custom Tooltip
// =============================================================================

type RechartsTooltipProps = TooltipProps<ValueType, NameType> & {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  payload?: any[]
  label?: string
}

function CustomTooltip({ active, payload, label }: RechartsTooltipProps) {
  if (!active || !payload || !label) return null

  return (
    <div className="rounded-lg border bg-background p-3 shadow-md">
      <p className="font-medium mb-2">{String(label)}</p>
      {payload.map((entry, index) => (
        <div key={index} className="flex items-center gap-2 text-sm">
          <div
            className="w-3 h-3 rounded-full"
            style={{ backgroundColor: entry.color as string }}
          />
          <span className="text-muted-foreground">{entry.name}:</span>
          <span className="font-medium">{formatCurrency(Number(entry.value))}</span>
        </div>
      ))}
    </div>
  )
}

// =============================================================================
// Main Component
// =============================================================================

export function CostAnalysisReport() {
  const [period, setPeriod] = useState<string>('monat')
  const [comparison, setComparison] = useState(false)

  const { data, isLoading, isError, refetch } = useQuery<CostAnalysisData>({
    queryKey: ['report', 'cost-analysis', period, comparison],
    queryFn: () => fetchReportData<CostAnalysisData>('cost-analysis', { period, comparison }),
  })

  const handleExport = async (format: 'pdf' | 'excel' | 'csv') => {
    try {
      const blob = await exportReport('cost-analysis', format, { period, comparison })
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `kostenauswertung-${period}.${format === 'excel' ? 'xlsx' : format}`
      document.body.appendChild(a)
      a.click()
      window.URL.revokeObjectURL(url)
      document.body.removeChild(a)
      toast.success(`Export als ${format.toUpperCase()} erfolgreich`)
    } catch (error) {
      toast.error(`Export fehlgeschlagen: ${error}`)
    }
  }

  if (isLoading) {
    return (
      <div className="container mx-auto p-6 space-y-6">
        <Skeleton className="h-10 w-64" />
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Skeleton className="h-[400px]" />
          <Skeleton className="h-[400px]" />
          <Skeleton className="h-[400px]" />
          <Skeleton className="h-[400px]" />
        </div>
      </div>
    )
  }

  if (isError || !data) {
    return (
      <div className="container mx-auto p-6">
        <EmptyState
          variant="error"
          title="Berichtsdaten nicht verfügbar"
          description="Die Berichtsdaten sind derzeit nicht verfügbar. Bitte versuchen Sie es später erneut."
          action={{ label: 'Erneut versuchen', onClick: () => { void refetch(); } }}
        />
      </div>
    )
  }

  return (
    <div className="container mx-auto p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Kostenauswertung</h1>
          <p className="text-muted-foreground mt-1">
            Detaillierte Analyse Ihrer Ausgaben nach Kategorien und Lieferanten
          </p>
        </div>
      </div>

      {/* Filters */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex flex-wrap items-center gap-6">
            <div className="space-y-2">
              <Label htmlFor="period">Zeitraum</Label>
              <Select value={period} onValueChange={setPeriod}>
                <SelectTrigger id="period" className="w-[180px]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="monat">Aktueller Monat</SelectItem>
                  <SelectItem value="quartal">Aktuelles Quartal</SelectItem>
                  <SelectItem value="jahr">Aktuelles Jahr</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="flex items-center space-x-2">
              <Switch
                id="comparison"
                checked={comparison}
                onCheckedChange={setComparison}
              />
              <Label htmlFor="comparison">Vorjahresvergleich</Label>
            </div>

            <div className="ml-auto flex gap-2">
              <Button variant="outline" size="sm" onClick={() => handleExport('pdf')}>
                <FileDown className="w-4 h-4 mr-2" />
                PDF
              </Button>
              <Button variant="outline" size="sm" onClick={() => handleExport('excel')}>
                <FileDown className="w-4 h-4 mr-2" />
                Excel
              </Button>
              <Button variant="outline" size="sm" onClick={() => handleExport('csv')}>
                <FileDown className="w-4 h-4 mr-2" />
                CSV
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Vorjahresvergleich */}
      {comparison && data?.comparison && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              {data.comparison.change < 0 ? (
                <TrendingDown className="w-5 h-5 text-green-600" />
              ) : (
                <TrendingUp className="w-5 h-5 text-red-600" />
              )}
              Vorjahresvergleich
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-4">
              <div>
                <p className="text-sm text-muted-foreground">Veränderung</p>
                <p
                  className={`text-2xl font-bold ${
                    data.comparison.change < 0 ? 'text-green-600' : 'text-red-600'
                  }`}
                >
                  {formatCurrency(Math.abs(data.comparison.change))}
                </p>
              </div>
              <Badge variant={data.comparison.change < 0 ? 'success' : 'destructive'}>
                {data.comparison.changePercent > 0 ? '+' : ''}
                {data.comparison.changePercent.toFixed(1)}%
              </Badge>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Charts Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Kosten nach Kategorie */}
        <Card>
          <CardHeader>
            <CardTitle>Kosten nach Kategorie</CardTitle>
            <CardDescription>Ausgaben gruppiert nach Kostenkategorien</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="h-[350px]">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={data?.categories || []}>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                  <XAxis
                    dataKey="kategorie"
                    tick={{ fontSize: 11 }}
                    angle={-45}
                    textAnchor="end"
                    height={80}
                  />
                  <YAxis tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`} />
                  <Tooltip content={<CustomTooltip />} />
                  <Legend />
                  <Bar dataKey="betrag" fill={CHART_COLORS[0]} name="Betrag (EUR)" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>

        {/* Top Lieferanten */}
        <Card>
          <CardHeader>
            <CardTitle>Top-Lieferanten</CardTitle>
            <CardDescription>Ausgaben nach Lieferanten sortiert</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              {data?.topSuppliers.map((supplier, idx) => (
                <div key={idx} className="space-y-1">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium">{supplier.lieferant}</span>
                    <span className="text-sm font-bold">{formatCurrency(supplier.betrag)}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="flex-1 bg-secondary rounded-full h-2">
                      <div
                        className="bg-primary h-2 rounded-full transition-all"
                        style={{ width: `${supplier.anteil}%` }}
                      />
                    </div>
                    <span className="text-xs text-muted-foreground w-12 text-right">
                      {supplier.anteil.toFixed(1)}%
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* Kostenstellen */}
        <Card>
          <CardHeader>
            <CardTitle>Kostenstellen-Verteilung</CardTitle>
            <CardDescription>Ausgaben nach Kostenstellen</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="h-[350px]">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={data?.costCenters || []}
                    dataKey="betrag"
                    nameKey="kostenstelle"
                    cx="50%"
                    cy="50%"
                    outerRadius={120}
                    label={(props) => {
                      const { kostenstelle, anteil } = props.payload as {
                        kostenstelle: string
                        anteil: number
                      }
                      return `${kostenstelle} (${anteil.toFixed(1)}%)`
                    }}
                  >
                    {data?.costCenters.map((_entry, index) => (
                      <Cell key={`cell-${index}`} fill={CHART_COLORS[index % CHART_COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip content={<CustomTooltip />} />
                </PieChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>

        {/* Kategorie Tabelle */}
        <Card>
          <CardHeader>
            <CardTitle>Alle Kategorien</CardTitle>
            <CardDescription>Vollständige Übersicht der Kostenverteilung</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              <div className="grid grid-cols-3 gap-4 text-sm font-medium text-muted-foreground pb-2 border-b">
                <div>Kategorie</div>
                <div className="text-right">Betrag</div>
                <div className="text-right">Anteil</div>
              </div>
              {data?.categories.map((cat, idx) => (
                <div key={idx} className="grid grid-cols-3 gap-4 text-sm py-2">
                  <div className="font-medium">{cat.kategorie}</div>
                  <div className="text-right">{formatCurrency(cat.betrag)}</div>
                  <div className="text-right">{cat.anteil.toFixed(1)}%</div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
