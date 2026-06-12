/**
 * Cashflow-Prognose Report
 *
 * Zeigt Liquiditätsprognose mit offenen Forderungen und Verbindlichkeiten.
 * Unterstützt Zeitraum-Auswahl (30/60/90 Tage) und Export.
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
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  type TooltipProps,
} from 'recharts'
import type { ValueType, NameType } from 'recharts/types/component/DefaultTooltipContent'
import {
  FileDown,
  TrendingUp,
  TrendingDown,
  Wallet,
  AlertCircle,
} from 'lucide-react'
import { toast } from 'sonner'
import { EmptyState } from '@/components/ui/empty-state'
import { fetchReportData, exportReport, type CashflowForecastData } from '../api/report-data-api'

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

function formatDate(dateStr: string): string {
  const date = new Date(dateStr)
  return date.toLocaleDateString('de-DE', {
    day: '2-digit',
    month: '2-digit',
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
      <p className="font-medium mb-2">{formatDate(String(label))}</p>
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

export function CashflowForecastReport() {
  const [daysAhead, setDaysAhead] = useState<string>('30')

  const { data, isLoading, isError, refetch } = useQuery<CashflowForecastData>({
    queryKey: ['report', 'cashflow-forecast', daysAhead],
    queryFn: () => fetchReportData<CashflowForecastData>('cashflow-forecast', { period: daysAhead }),
  })

  const handleExport = async (format: 'pdf' | 'excel' | 'csv') => {
    try {
      const blob = await exportReport('cashflow-forecast', format, { period: daysAhead })
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `cashflow-prognose-${daysAhead}tage.${format === 'excel' ? 'xlsx' : format}`
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
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <Skeleton className="h-32" />
          <Skeleton className="h-32" />
          <Skeleton className="h-32" />
        </div>
        <Skeleton className="h-[400px]" />
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
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

  // Filter data based on selected period
  const filteredData = data?.projectedPosition.slice(0, parseInt(daysAhead)) || []

  return (
    <div className="container mx-auto p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Cashflow-Prognose</h1>
          <p className="text-muted-foreground mt-1">
            Liquiditätsentwicklung und Zahlungsströme im Überblick
          </p>
        </div>
      </div>

      {/* Filters */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex flex-wrap items-center gap-6">
            <div className="space-y-2">
              <label htmlFor="days" className="text-sm font-medium">
                Prognosezeitraum
              </label>
              <Select value={daysAhead} onValueChange={setDaysAhead}>
                <SelectTrigger id="days" className="w-[180px]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="30">30 Tage</SelectItem>
                  <SelectItem value="60">60 Tage</SelectItem>
                  <SelectItem value="90">90 Tage</SelectItem>
                </SelectContent>
              </Select>
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

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Forderungen
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-2">
              <TrendingUp className="w-5 h-5 text-green-600" />
              <span className="text-2xl font-bold text-green-600">
                {formatCurrency(data?.summary.forderungen || 0)}
              </span>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Verbindlichkeiten
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-2">
              <TrendingDown className="w-5 h-5 text-red-600" />
              <span className="text-2xl font-bold text-red-600">
                {formatCurrency(data?.summary.verbindlichkeiten || 0)}
              </span>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Netto-Position
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-2">
              <Wallet className="w-5 h-5" />
              <span className="text-2xl font-bold">
                {formatCurrency(data?.summary.nettoPosition || 0)}
              </span>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Projected Position Chart */}
      <Card>
        <CardHeader>
          <CardTitle>Cashflow-Entwicklung</CardTitle>
          <CardDescription>
            Prognostizierte Liquiditätsentwicklung für die nächsten {daysAhead} Tage
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="h-[400px]">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={filteredData}>
                <defs>
                  <linearGradient id="colorPosition" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="oklch(0.55 0.18 250)" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="oklch(0.55 0.18 250)" stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="colorForderungen" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="oklch(0.72 0.17 145)" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="oklch(0.72 0.17 145)" stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="colorVerbindlichkeiten" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="oklch(0.55 0.22 25)" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="oklch(0.55 0.22 25)" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                <XAxis
                  dataKey="date"
                  tickFormatter={formatDate}
                  tick={{ fontSize: 11 }}
                  tickMargin={8}
                />
                <YAxis
                  tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`}
                  tick={{ fontSize: 11 }}
                />
                <Tooltip content={<CustomTooltip />} />
                <Legend />
                <Area
                  type="monotone"
                  dataKey="position"
                  stroke="oklch(0.55 0.18 250)"
                  fill="url(#colorPosition)"
                  strokeWidth={2}
                  name="Position"
                />
                <Area
                  type="monotone"
                  dataKey="forderungen"
                  stroke="oklch(0.72 0.17 145)"
                  fill="url(#colorForderungen)"
                  strokeWidth={2}
                  name="Forderungen"
                />
                <Area
                  type="monotone"
                  dataKey="verbindlichkeiten"
                  stroke="oklch(0.55 0.22 25)"
                  fill="url(#colorVerbindlichkeiten)"
                  strokeWidth={2}
                  name="Verbindlichkeiten"
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </CardContent>
      </Card>

      {/* Forderungen und Verbindlichkeiten Tables */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Offene Forderungen */}
        <Card>
          <CardHeader>
            <CardTitle>Offene Forderungen</CardTitle>
            <CardDescription>Ausstehende Zahlungen von Kunden</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              <div className="grid grid-cols-4 gap-4 text-sm font-medium text-muted-foreground pb-2 border-b">
                <div>Beleg</div>
                <div>Kunde</div>
                <div className="text-right">Betrag</div>
                <div className="text-right">Fällig</div>
              </div>
              {data?.offeneForderungen.map((forderung, idx) => (
                <div key={idx} className="grid grid-cols-4 gap-4 text-sm py-2">
                  <div className="font-medium">{forderung.belegnummer}</div>
                  <div className="truncate">{forderung.kunde}</div>
                  <div className="text-right">{formatCurrency(forderung.betrag)}</div>
                  <div className="flex items-center justify-end gap-2">
                    {formatDate(forderung.fälligkeitsdatum)}
                    {forderung.überfällig && (
                      <Badge variant="destructive" className="text-xs">
                        <AlertCircle className="w-3 h-3 mr-1" />
                        {forderung.tageÜberfällig}d
                      </Badge>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* Offene Verbindlichkeiten */}
        <Card>
          <CardHeader>
            <CardTitle>Offene Verbindlichkeiten</CardTitle>
            <CardDescription>Zu zahlende Rechnungen an Lieferanten</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              <div className="grid grid-cols-4 gap-4 text-sm font-medium text-muted-foreground pb-2 border-b">
                <div>Beleg</div>
                <div>Lieferant</div>
                <div className="text-right">Betrag</div>
                <div className="text-right">Fällig</div>
              </div>
              {data?.offeneVerbindlichkeiten.map((verbindlichkeit, idx) => (
                <div key={idx} className="grid grid-cols-4 gap-4 text-sm py-2">
                  <div className="font-medium">{verbindlichkeit.belegnummer}</div>
                  <div className="truncate">{verbindlichkeit.lieferant}</div>
                  <div className="text-right">{formatCurrency(verbindlichkeit.betrag)}</div>
                  <div className="flex items-center justify-end gap-2">
                    {formatDate(verbindlichkeit.fälligkeitsdatum)}
                    {verbindlichkeit.überfällig && (
                      <Badge variant="destructive" className="text-xs">
                        <AlertCircle className="w-3 h-3 mr-1" />
                        {verbindlichkeit.tageÜberfällig}d
                      </Badge>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
