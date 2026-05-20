/**
 * AnalyticsDashboard
 *
 * Umfassendes Analytics-Dashboard für die Validierungs-Queue.
 * Visualisiert Trends, Editor-Performance und Konfidenz-Verteilung mit Recharts.
 */

import { useState, useMemo } from 'react';
import {
  BarChart3,
  TrendingUp,
  Users,
  Calendar,
  Clock,
  CheckCircle,
  XCircle,
  RefreshCw,
  Download,
  Filter,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  LineChart,
  Line,
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
  AreaChart,
  Area,
} from 'recharts';
import {
  useAnalyticsOverview,
  useEditorStats,
  useTrends,
  useDocumentTypeStats,
  useConfidenceDistribution,
} from '../hooks/use-validation-queue';

// Farben für Charts
const CHART_COLORS = {
  primary: 'hsl(var(--primary))',
  secondary: 'hsl(var(--secondary))',
  success: '#22c55e',
  warning: '#f59e0b',
  danger: '#ef4444',
  info: '#3b82f6',
};

const PIE_COLORS = ['#3b82f6', '#22c55e', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899'];

interface TimeRange {
  days: number;
  groupBy: 'day' | 'week' | 'month';
  label: string;
}

const TIME_RANGES: TimeRange[] = [
  { days: 7, groupBy: 'day', label: 'Letzte 7 Tage' },
  { days: 30, groupBy: 'day', label: 'Letzte 30 Tage' },
  { days: 90, groupBy: 'week', label: 'Letzte 90 Tage' },
  { days: 365, groupBy: 'month', label: 'Letztes Jahr' },
];

export function AnalyticsDashboard() {
  const [timeRange, setTimeRange] = useState<TimeRange>(TIME_RANGES[1]);

  // Queries
  const { data: overview, isLoading: isLoadingOverview, refetch: refetchOverview } = useAnalyticsOverview();
  const { data: editorStats, isLoading: isLoadingEditors } = useEditorStats();
  const { data: trends, isLoading: isLoadingTrends } = useTrends(timeRange.days, timeRange.groupBy);
  const { data: docTypeStats, isLoading: isLoadingDocTypes } = useDocumentTypeStats();
  const { data: confidenceDist, isLoading: isLoadingConfidence } = useConfidenceDistribution();

  // Chart data transformations
  const trendData = useMemo(() => {
    if (!trends?.data_points) return [];
    return trends.data_points.map((point) => ({
      date: new Date(point.date).toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit' }),
      validiert: point.validated_count,
      genehmigt: point.approved_count,
      abgelehnt: point.rejected_count,
      zeitProItem: point.avg_time_seconds ? Math.round(point.avg_time_seconds / 60) : 0,
    }));
  }, [trends]);

  const editorChartData = useMemo(() => {
    if (!editorStats?.editors) return [];
    return editorStats.editors
      .slice(0, 10) // Top 10
      .map((editor) => ({
        name: editor.editor_name.split(' ')[0], // Vorname
        validiert: editor.items_validated,
        genehmigt: editor.items_approved,
        abgelehnt: editor.items_rejected,
        genauigkeit: editor.accuracy_rate ? Math.round(editor.accuracy_rate * 100) : 0,
      }));
  }, [editorStats]);

  const docTypeChartData = useMemo(() => {
    if (!docTypeStats?.document_types) return [];
    return docTypeStats.document_types.map((dt) => ({
      name: dt.document_type,
      value: dt.total_count,
      pending: dt.pending_count,
      genehmigt: dt.approved_count,
      abgelehnt: dt.rejected_count,
    }));
  }, [docTypeStats]);

  const confidenceChartData = useMemo(() => {
    if (!confidenceDist?.buckets) return [];
    return confidenceDist.buckets.map((bucket) => ({
      range: `${Math.round(bucket.range_start * 100)}-${Math.round(bucket.range_end * 100)}%`,
      count: bucket.count,
      percentage: bucket.percentage,
    }));
  }, [confidenceDist]);

  const handleRefreshAll = () => {
    refetchOverview();
    // Andere queries werden automatisch durch staleTime invalidiert
  };

  const isLoading = isLoadingOverview || isLoadingEditors || isLoadingTrends || isLoadingDocTypes || isLoadingConfidence;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">Validierungs-Statistiken</h2>
          <p className="text-sm text-muted-foreground">
            Detaillierte Analysen und Trends zur Dokumentvalidierung
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Select
            value={`${timeRange.days}`}
            onValueChange={(value) => {
              const range = TIME_RANGES.find((r) => r.days === parseInt(value));
              if (range) setTimeRange(range);
            }}
          >
            <SelectTrigger className="w-[160px]">
              <Calendar className="w-4 h-4 mr-2" />
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {TIME_RANGES.map((range) => (
                <SelectItem key={range.days} value={`${range.days}`}>
                  {range.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button
            variant="outline"
            size="icon"
            onClick={handleRefreshAll}
            disabled={isLoading}
          >
            <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
          </Button>
        </div>
      </div>

      {/* Overview Stats Cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Gesamt validiert</CardTitle>
            <CheckCircle className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            {isLoadingOverview ? (
              <Skeleton className="h-8 w-24" />
            ) : (
              <>
                <div className="text-2xl font-bold">
                  {overview?.approved_items?.toLocaleString('de-DE') || 0}
                </div>
                <p className="text-xs text-muted-foreground">
                  {overview?.approval_rate
                    ? `${Math.round(overview.approval_rate * 100)}% Genehmigungsrate`
                    : 'Keine Daten'}
                </p>
              </>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Durchschn. Zeit</CardTitle>
            <Clock className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            {isLoadingOverview ? (
              <Skeleton className="h-8 w-24" />
            ) : (
              <>
                <div className="text-2xl font-bold">
                  {overview?.avg_time_to_validate_seconds
                    ? `${Math.round(overview.avg_time_to_validate_seconds / 60)} Min`
                    : '-'}
                </div>
                <p className="text-xs text-muted-foreground">Pro Dokument</p>
              </>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Diese Woche</CardTitle>
            <TrendingUp className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            {isLoadingOverview ? (
              <Skeleton className="h-8 w-24" />
            ) : (
              <>
                <div className="text-2xl font-bold">
                  {overview?.items_validated_this_week?.toLocaleString('de-DE') || 0}
                </div>
                <p className="text-xs text-muted-foreground">Dokumente validiert</p>
              </>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Korrekturen/Dok.</CardTitle>
            <BarChart3 className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            {isLoadingOverview ? (
              <Skeleton className="h-8 w-24" />
            ) : (
              <>
                <div className="text-2xl font-bold">
                  {overview?.avg_corrections_per_item
                    ? overview.avg_corrections_per_item.toFixed(1)
                    : '-'}
                </div>
                <p className="text-xs text-muted-foreground">Durchschnittliche Korrekturen</p>
              </>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Charts Row 1: Trend + Editor Performance */}
      <div className="grid gap-4 lg:grid-cols-2">
        {/* Trend Chart */}
        <Card>
          <CardHeader>
            <CardTitle>Validierungstrend</CardTitle>
            <CardDescription>Validierte Dokumente über Zeit</CardDescription>
          </CardHeader>
          <CardContent>
            {isLoadingTrends ? (
              <Skeleton className="h-[300px] w-full" />
            ) : trendData.length > 0 ? (
              <ResponsiveContainer width="100%" height={300}>
                <AreaChart data={trendData}>
                  <defs>
                    <linearGradient id="colorValidiert" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor={CHART_COLORS.info} stopOpacity={0.8} />
                      <stop offset="95%" stopColor={CHART_COLORS.info} stopOpacity={0} />
                    </linearGradient>
                    <linearGradient id="colorGenehmigt" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor={CHART_COLORS.success} stopOpacity={0.8} />
                      <stop offset="95%" stopColor={CHART_COLORS.success} stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                  <XAxis dataKey="date" className="text-xs" />
                  <YAxis className="text-xs" />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: 'hsl(var(--background))',
                      border: '1px solid hsl(var(--border))',
                      borderRadius: '8px',
                    }}
                  />
                  <Legend />
                  <Area
                    type="monotone"
                    dataKey="genehmigt"
                    name="Genehmigt"
                    stroke={CHART_COLORS.success}
                    fillOpacity={1}
                    fill="url(#colorGenehmigt)"
                  />
                  <Area
                    type="monotone"
                    dataKey="abgelehnt"
                    name="Abgelehnt"
                    stroke={CHART_COLORS.danger}
                    fillOpacity={0.5}
                    fill={CHART_COLORS.danger}
                  />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-[300px] flex items-center justify-center text-muted-foreground">
                Keine Trend-Daten verfügbar
              </div>
            )}
          </CardContent>
        </Card>

        {/* Editor Performance */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Users className="w-4 h-4" />
              Editor-Performance
            </CardTitle>
            <CardDescription>Top 10 Editoren nach Validierungen</CardDescription>
          </CardHeader>
          <CardContent>
            {isLoadingEditors ? (
              <Skeleton className="h-[300px] w-full" />
            ) : editorChartData.length > 0 ? (
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={editorChartData} layout="vertical">
                  <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                  <XAxis type="number" className="text-xs" />
                  <YAxis type="category" dataKey="name" width={80} className="text-xs" />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: 'hsl(var(--background))',
                      border: '1px solid hsl(var(--border))',
                      borderRadius: '8px',
                    }}
                  />
                  <Legend />
                  <Bar dataKey="genehmigt" name="Genehmigt" fill={CHART_COLORS.success} stackId="stack" />
                  <Bar dataKey="abgelehnt" name="Abgelehnt" fill={CHART_COLORS.danger} stackId="stack" />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-[300px] flex items-center justify-center text-muted-foreground">
                Keine Editor-Daten verfügbar
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Charts Row 2: Document Types + Confidence Distribution */}
      <div className="grid gap-4 lg:grid-cols-2">
        {/* Document Types */}
        <Card>
          <CardHeader>
            <CardTitle>Dokumenttypen</CardTitle>
            <CardDescription>Verteilung nach Dokumenttyp</CardDescription>
          </CardHeader>
          <CardContent>
            {isLoadingDocTypes ? (
              <Skeleton className="h-[300px] w-full" />
            ) : docTypeChartData.length > 0 ? (
              <ResponsiveContainer width="100%" height={300}>
                <PieChart>
                  <Pie
                    data={docTypeChartData}
                    cx="50%"
                    cy="50%"
                    labelLine={false}
                    label={({ name, percent }) => `${name} (${(percent * 100).toFixed(0)}%)`}
                    outerRadius={100}
                    fill="#8884d8"
                    dataKey="value"
                  >
                    {docTypeChartData.map((_, index) => (
                      <Cell key={`cell-${index}`} fill={PIE_COLORS[index % PIE_COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{
                      backgroundColor: 'hsl(var(--background))',
                      border: '1px solid hsl(var(--border))',
                      borderRadius: '8px',
                    }}
                  />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-[300px] flex items-center justify-center text-muted-foreground">
                Keine Dokumenttyp-Daten verfügbar
              </div>
            )}
          </CardContent>
        </Card>

        {/* Confidence Distribution */}
        <Card>
          <CardHeader>
            <CardTitle>Konfidenz-Verteilung</CardTitle>
            <CardDescription>
              Verteilung der OCR-Konfidenzwerte
              {confidenceDist?.avg_confidence && (
                <span className="ml-2 text-foreground">
                  (Durchschnitt: {Math.round(confidenceDist.avg_confidence * 100)}%)
                </span>
              )}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {isLoadingConfidence ? (
              <Skeleton className="h-[300px] w-full" />
            ) : confidenceChartData.length > 0 ? (
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={confidenceChartData}>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                  <XAxis dataKey="range" className="text-xs" />
                  <YAxis className="text-xs" />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: 'hsl(var(--background))',
                      border: '1px solid hsl(var(--border))',
                      borderRadius: '8px',
                    }}
                    formatter={(value: number) => [`${value} Dokumente`, 'Anzahl']}
                  />
                  <Bar dataKey="count" name="Dokumente" fill={CHART_COLORS.info}>
                    {confidenceChartData.map((entry, index) => {
                      // Farbe basierend auf Konfidenzbereich
                      const rangeStart = parseInt(entry.range.split('-')[0]);
                      let color = CHART_COLORS.danger;
                      if (rangeStart >= 70) color = CHART_COLORS.warning;
                      if (rangeStart >= 90) color = CHART_COLORS.success;
                      return <Cell key={`cell-${index}`} fill={color} />;
                    })}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-[300px] flex items-center justify-center text-muted-foreground">
                Keine Konfidenz-Daten verfügbar
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Editor Leaderboard */}
      {editorStats?.editors && editorStats.editors.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Editor-Leaderboard</CardTitle>
            <CardDescription>Detaillierte Statistiken pro Editor</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b">
                    <th className="text-left py-2 px-2">Editor</th>
                    <th className="text-right py-2 px-2">Validiert</th>
                    <th className="text-right py-2 px-2">Genehmigt</th>
                    <th className="text-right py-2 px-2">Abgelehnt</th>
                    <th className="text-right py-2 px-2">Genauigkeit</th>
                    <th className="text-right py-2 px-2">Durchschn. Zeit</th>
                    <th className="text-right py-2 px-2">Korrekturen</th>
                  </tr>
                </thead>
                <tbody>
                  {editorStats.editors.map((editor, index) => (
                    <tr key={editor.editor_id} className="border-b hover:bg-muted/50">
                      <td className="py-2 px-2">
                        <div className="flex items-center gap-2">
                          <span
                            className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold ${
                              index === 0
                                ? 'bg-yellow-100 text-yellow-800'
                                : index === 1
                                  ? 'bg-gray-100 text-gray-800'
                                  : index === 2
                                    ? 'bg-orange-100 text-orange-800'
                                    : 'bg-muted text-muted-foreground'
                            }`}
                          >
                            {index + 1}
                          </span>
                          <span className="font-medium">{editor.editor_name}</span>
                        </div>
                      </td>
                      <td className="text-right py-2 px-2">{editor.items_validated}</td>
                      <td className="text-right py-2 px-2 text-green-600">{editor.items_approved}</td>
                      <td className="text-right py-2 px-2 text-red-600">{editor.items_rejected}</td>
                      <td className="text-right py-2 px-2">
                        {editor.accuracy_rate ? `${Math.round(editor.accuracy_rate * 100)}%` : '-'}
                      </td>
                      <td className="text-right py-2 px-2">
                        {editor.avg_time_per_item_seconds
                          ? `${Math.round(editor.avg_time_per_item_seconds / 60)} Min`
                          : '-'}
                      </td>
                      <td className="text-right py-2 px-2">{editor.total_corrections_made}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

export default AnalyticsDashboard;
