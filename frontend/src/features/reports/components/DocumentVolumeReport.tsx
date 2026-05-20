/**
 * Dokumenten-Volumen Report
 *
 * Zeigt Dokumentenverarbeitung-Statistiken mit Volumen-Trend, SLA-Einhaltung
 * und Verarbeitungszeiten nach Kategorie.
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
  LineChart,
  Line,
  BarChart,
  Bar,
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
  FileText,
  Clock,
  CheckCircle2,
  TrendingUp,
} from 'lucide-react'
import { toast } from 'sonner'
import { fetchReportData, exportReport, type DocumentVolumeData } from '../api/report-data-api'

// =============================================================================
// Helper Functions
// =============================================================================

function formatNumber(value: number): string {
  return value.toLocaleString('de-DE')
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
          <span className="font-medium">{formatNumber(Number(entry.value))}</span>
        </div>
      ))}
    </div>
  )
}

// =============================================================================
// Main Component
// =============================================================================

export function DocumentVolumeReport() {
  const [period, setPeriod] = useState<string>('jahr')

  const { data, isLoading } = useQuery<DocumentVolumeData>({
    queryKey: ['report', 'document-volume', period],
    queryFn: () => fetchReportData('document-volume', { period }),
  })

  const handleExport = async (format: 'pdf' | 'excel' | 'csv') => {
    try {
      const blob = await exportReport('document-volume', format, { period })
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `dokumenten-volumen-${period}.${format === 'excel' ? 'xlsx' : format}`
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
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
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

  return (
    <div className="container mx-auto p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Dokumenten-Volumen</h1>
          <p className="text-muted-foreground mt-1">
            Statistiken zur Dokumentenverarbeitung und Performance
          </p>
        </div>
      </div>

      {/* Filters */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex flex-wrap items-center gap-6">
            <div className="space-y-2">
              <label htmlFor="period" className="text-sm font-medium">
                Zeitraum
              </label>
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

      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-2">
              <Clock className="w-4 h-4" />
              Ø Verarbeitungszeit
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {data?.kpis.avgVerarbeitungszeit.toFixed(1)}h
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              Durchschnittliche Bearbeitungsdauer
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4" />
              SLA-Einhaltung
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-2">
              <span className="text-2xl font-bold text-green-600">
                {data?.kpis.slaEinhaltung.toFixed(1)}%
              </span>
              {(data?.kpis.slaEinhaltung || 0) >= 95 && (
                <Badge variant="success">Exzellent</Badge>
              )}
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              Innerhalb der Service Level Agreements
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-2">
              <FileText className="w-4 h-4" />
              Dokumente diesen Monat
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-2">
              <span className="text-2xl font-bold">
                {formatNumber(data?.kpis.dokumenteDiesenMonat || 0)}
              </span>
              <TrendingUp className="w-5 h-5 text-green-600" />
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              Verarbeitete Dokumente
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Volume Trend Chart */}
      <Card>
        <CardHeader>
          <CardTitle>Volumen-Entwicklung</CardTitle>
          <CardDescription>
            Anzahl verarbeiteter Dokumente pro Monat
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="h-[400px]">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={data?.volumeTrend || []}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                <XAxis
                  dataKey="monat"
                  tick={{ fontSize: 11 }}
                  tickMargin={8}
                />
                <YAxis
                  tickFormatter={(v) => formatNumber(v)}
                  tick={{ fontSize: 11 }}
                />
                <Tooltip content={<CustomTooltip />} />
                <Legend />
                <Line
                  type="monotone"
                  dataKey="anzahl"
                  stroke="oklch(0.55 0.18 250)"
                  strokeWidth={3}
                  name="Dokumente"
                  dot={{ fill: 'oklch(0.55 0.18 250)', r: 4 }}
                  activeDot={{ r: 6 }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </CardContent>
      </Card>

      {/* Category Breakdown and Processing Times */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Category Breakdown */}
        <Card>
          <CardHeader>
            <CardTitle>Verteilung nach Kategorie</CardTitle>
            <CardDescription>Dokumententypen im Überblick</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="h-[350px]">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={data?.categoryBreakdown || []}>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                  <XAxis
                    dataKey="kategorie"
                    tick={{ fontSize: 10 }}
                    angle={-45}
                    textAnchor="end"
                    height={100}
                  />
                  <YAxis tickFormatter={(v) => formatNumber(v)} />
                  <Tooltip content={<CustomTooltip />} />
                  <Legend />
                  <Bar
                    dataKey="anzahl"
                    fill="oklch(0.72 0.17 145)"
                    name="Anzahl"
                    radius={[4, 4, 0, 0]}
                  />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>

        {/* Processing Times */}
        <Card>
          <CardHeader>
            <CardTitle>Verarbeitungszeiten</CardTitle>
            <CardDescription>
              Durchschnittliche Bearbeitungsdauer vs. SLA
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              <div className="grid grid-cols-4 gap-4 text-sm font-medium text-muted-foreground pb-2 border-b">
                <div>Kategorie</div>
                <div className="text-right">Ø Zeit</div>
                <div className="text-right">SLA</div>
                <div className="text-right">Status</div>
              </div>
              {data?.processingTimes.map((item, idx) => (
                <div key={idx} className="grid grid-cols-4 gap-4 text-sm py-2 items-center">
                  <div className="font-medium truncate">{item.kategorie}</div>
                  <div className="text-right">{item.avgZeit.toFixed(1)}h</div>
                  <div className="text-right text-muted-foreground">
                    {item.slaZeit.toFixed(1)}h
                  </div>
                  <div className="flex justify-end">
                    {item.slaEingehalten ? (
                      <Badge variant="success" className="text-xs">
                        OK
                      </Badge>
                    ) : (
                      <Badge variant="destructive" className="text-xs">
                        Überschritten
                      </Badge>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Category Table */}
      <Card>
        <CardHeader>
          <CardTitle>Alle Kategorien</CardTitle>
          <CardDescription>Vollständige Übersicht nach Dokumententyp</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            <div className="grid grid-cols-2 gap-4 text-sm font-medium text-muted-foreground pb-2 border-b">
              <div>Kategorie</div>
              <div className="text-right">Anzahl</div>
            </div>
            {data?.categoryBreakdown.map((cat, idx) => (
              <div key={idx} className="grid grid-cols-2 gap-4 text-sm py-2">
                <div className="font-medium">{cat.kategorie}</div>
                <div className="text-right">{formatNumber(cat.anzahl)}</div>
              </div>
            ))}
            <div className="grid grid-cols-2 gap-4 text-sm py-2 border-t font-bold">
              <div>Gesamt</div>
              <div className="text-right">
                {formatNumber(
                  data?.categoryBreakdown.reduce((sum, cat) => sum + cat.anzahl, 0) || 0
                )}
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
