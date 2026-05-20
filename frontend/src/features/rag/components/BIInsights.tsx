/**
 * Business Intelligence Insights Component
 *
 * Displays structured BI query results with visualizations.
 * Supports multiple query types with specialized rendering.
 */

import * as React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  TrendingUp,
  TrendingDown,
  Minus,
  FileText,
  Receipt,
  Building2,
  Clock,
  AlertTriangle,
  CheckCircle2,
  BarChart3,
  PieChart,
  ArrowRight,
  Sparkles,
  Lightbulb,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { Separator } from '@/components/ui/separator';
import { cn } from '@/lib/utils';
import type {
  BIQueryResponse,
  BIQueryType,
  BIInvoiceAnalysis,
  BIEntityStatistics,
  BIPaymentPrediction,
  BITrendAnalysis,
} from '../api/bi-api';

interface BIInsightsProps {
  insights: BIQueryResponse;
  onSuggestionClick?: (suggestion: string) => void;
  className?: string;
}

/**
 * Format currency in German locale.
 */
function formatCurrency(value: number): string {
  return new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency: 'EUR',
  }).format(value);
}

/**
 * Format percentage.
 */
function formatPercent(value: number): string {
  return new Intl.NumberFormat('de-DE', {
    style: 'percent',
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  }).format(value / 100);
}

/**
 * Get trend icon and color.
 */
function getTrendIndicator(direction: string) {
  switch (direction) {
    case 'up':
    case 'improving':
      return { icon: TrendingUp, color: 'text-green-500', bg: 'bg-green-500/10' };
    case 'down':
    case 'worsening':
      return { icon: TrendingDown, color: 'text-red-500', bg: 'bg-red-500/10' };
    default:
      return { icon: Minus, color: 'text-gray-500', bg: 'bg-gray-500/10' };
  }
}

/**
 * Invoice Analysis Visualization
 */
function InvoiceAnalysisView({ data }: { data: BIInvoiceAnalysis }) {
  const openPercent = data.total_count > 0
    ? (data.open_count / data.total_count) * 100
    : 0;
  const overduePercent = data.total_count > 0
    ? (data.overdue_count / data.total_count) * 100
    : 0;

  return (
    <div className="space-y-4">
      {/* Summary Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Card className="p-3">
          <div className="text-xs text-muted-foreground">Gesamt</div>
          <div className="text-lg font-bold">{formatCurrency(data.total_amount)}</div>
          <div className="text-xs text-muted-foreground">{data.total_count} Rechnungen</div>
        </Card>
        <Card className="p-3 bg-green-500/5 border-green-500/20">
          <div className="flex items-center gap-1 text-xs text-green-600">
            <CheckCircle2 className="h-3 w-3" />
            Bezahlt
          </div>
          <div className="text-lg font-bold text-green-700">{formatCurrency(data.paid_amount)}</div>
          <div className="text-xs text-muted-foreground">{data.paid_count} Rechnungen</div>
        </Card>
        <Card className="p-3 bg-yellow-500/5 border-yellow-500/20">
          <div className="flex items-center gap-1 text-xs text-yellow-600">
            <Clock className="h-3 w-3" />
            Offen
          </div>
          <div className="text-lg font-bold text-yellow-700">{formatCurrency(data.open_amount)}</div>
          <div className="text-xs text-muted-foreground">{data.open_count} Rechnungen</div>
        </Card>
        <Card className="p-3 bg-red-500/5 border-red-500/20">
          <div className="flex items-center gap-1 text-xs text-red-600">
            <AlertTriangle className="h-3 w-3" />
            Überfällig
          </div>
          <div className="text-lg font-bold text-red-700">{formatCurrency(data.overdue_amount)}</div>
          <div className="text-xs text-muted-foreground">{data.overdue_count} Rechnungen</div>
        </Card>
      </div>

      {/* Progress Bars */}
      <div className="space-y-2">
        <div className="flex justify-between text-xs">
          <span>Offene Rechnungen</span>
          <span>{openPercent.toFixed(1)}%</span>
        </div>
        <Progress value={openPercent} className="h-2" />

        <div className="flex justify-between text-xs mt-3">
          <span className="text-red-600">Überfällig</span>
          <span className="text-red-600">{overduePercent.toFixed(1)}%</span>
        </div>
        <Progress
          value={overduePercent}
          className="h-2 [&>div]:bg-red-500"
        />
      </div>

      {/* Monthly Breakdown */}
      {data.by_month.length > 0 && (
        <div className="mt-4">
          <div className="flex items-center gap-2 mb-2">
            <BarChart3 className="h-4 w-4 text-muted-foreground" />
            <span className="text-sm font-medium">Nach Monat</span>
          </div>
          <div className="flex gap-1 items-end h-20">
            {data.by_month.slice(-12).map((month, i) => {
              const maxAmount = Math.max(...data.by_month.map(m => m.amount));
              const height = maxAmount > 0 ? (month.amount / maxAmount) * 100 : 0;
              return (
                <div
                  key={month.month}
                  className="flex-1 flex flex-col items-center"
                >
                  <div
                    className="w-full bg-primary/80 rounded-t"
                    style={{ height: `${height}%`, minHeight: height > 0 ? '4px' : '0' }}
                  />
                  <span className="text-[8px] text-muted-foreground mt-1 rotate-45 origin-left">
                    {month.month.slice(-2)}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * Entity Statistics View
 */
function EntityStatisticsView({ data }: { data: BIEntityStatistics | BIEntityStatistics[] }) {
  const entities = Array.isArray(data) ? data : [data];

  return (
    <div className="space-y-3">
      {entities.map((entity) => (
        <Card key={entity.entity_id} className="p-3">
          <div className="flex items-start justify-between">
            <div>
              <div className="flex items-center gap-2">
                <Building2 className="h-4 w-4 text-muted-foreground" />
                <span className="font-medium">{entity.entity_name}</span>
                <Badge variant="outline" className="text-xs">
                  {entity.entity_type}
                </Badge>
              </div>
              <div className="grid grid-cols-2 gap-x-4 gap-y-1 mt-2 text-sm">
                <div className="text-muted-foreground">Dokumente:</div>
                <div>{entity.document_count}</div>
                <div className="text-muted-foreground">Rechnungen:</div>
                <div>{entity.invoice_count}</div>
                <div className="text-muted-foreground">Umsatz:</div>
                <div className="font-medium">{formatCurrency(entity.total_revenue)}</div>
                <div className="text-muted-foreground">Offen:</div>
                <div className={entity.total_open > 0 ? 'text-yellow-600 font-medium' : ''}>
                  {formatCurrency(entity.total_open)}
                </div>
              </div>
            </div>
            {entity.risk_score !== null && (
              <div className={cn(
                'flex flex-col items-center p-2 rounded-lg',
                entity.risk_score >= 75 ? 'bg-red-500/10' :
                entity.risk_score >= 50 ? 'bg-yellow-500/10' : 'bg-green-500/10'
              )}>
                <span className="text-xs text-muted-foreground">Risiko</span>
                <span className={cn(
                  'text-xl font-bold',
                  entity.risk_score >= 75 ? 'text-red-600' :
                  entity.risk_score >= 50 ? 'text-yellow-600' : 'text-green-600'
                )}>
                  {entity.risk_score}
                </span>
              </div>
            )}
          </div>
        </Card>
      ))}
    </div>
  );
}

/**
 * Payment Prediction View
 */
function PaymentPredictionView({ data }: { data: BIPaymentPrediction }) {
  const trend = getTrendIndicator(data.recent_trend);
  const TrendIcon = trend.icon;

  return (
    <Card className="p-4">
      <div className="flex items-start gap-4">
        <div className={cn('p-3 rounded-lg', trend.bg)}>
          <TrendIcon className={cn('h-6 w-6', trend.color)} />
        </div>
        <div className="flex-1">
          <div className="text-lg font-bold">
            Erwartete Zahlung in {data.predicted_days} Tagen
          </div>
          <div className="flex items-center gap-2 mt-1">
            <Badge variant="outline">
              Konfidenz: {(data.confidence * 100).toFixed(0)}%
            </Badge>
            <Badge variant="secondary">
              Historisch: {data.historical_avg_days.toFixed(1)} Tage
            </Badge>
          </div>
          <div className="mt-3 space-y-1">
            {data.factors.map((factor, i) => (
              <div key={i} className="flex items-center gap-2 text-sm text-muted-foreground">
                <ArrowRight className="h-3 w-3" />
                {factor}
              </div>
            ))}
          </div>
        </div>
      </div>
    </Card>
  );
}

/**
 * Trend Analysis View
 */
function TrendAnalysisView({ data }: { data: BITrendAnalysis }) {
  const trend = getTrendIndicator(data.trend_direction);
  const TrendIcon = trend.icon;

  return (
    <div className="space-y-4">
      {/* Summary */}
      <div className="flex items-center justify-between">
        <div>
          <div className="text-sm text-muted-foreground">{data.metric}</div>
          <div className="text-2xl font-bold">{formatCurrency(data.total)}</div>
          <div className="text-sm text-muted-foreground">
            Durchschnitt: {formatCurrency(data.average)}
          </div>
        </div>
        <div className={cn('flex items-center gap-2 px-3 py-2 rounded-lg', trend.bg)}>
          <TrendIcon className={cn('h-5 w-5', trend.color)} />
          <span className={cn('font-medium', trend.color)}>
            {data.change_percent >= 0 ? '+' : ''}{data.change_percent.toFixed(1)}%
          </span>
        </div>
      </div>

      {/* Chart */}
      {data.data_points.length > 0 && (
        <div className="mt-4">
          <div className="flex gap-1 items-end h-24">
            {data.data_points.map((point, i) => {
              const maxValue = Math.max(...data.data_points.map(p => p.value));
              const height = maxValue > 0 ? (point.value / maxValue) * 100 : 0;
              return (
                <div
                  key={point.period}
                  className="flex-1 group relative"
                >
                  <div
                    className="w-full bg-primary/80 hover:bg-primary rounded-t transition-colors"
                    style={{ height: `${height}%`, minHeight: height > 0 ? '4px' : '0' }}
                  />
                  {/* Tooltip on hover */}
                  <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none">
                    <Card className="p-2 text-xs whitespace-nowrap">
                      <div className="font-medium">{point.period}</div>
                      <div>{formatCurrency(point.value)}</div>
                      {point.change_percent !== null && (
                        <div className={point.change_percent >= 0 ? 'text-green-600' : 'text-red-600'}>
                          {point.change_percent >= 0 ? '+' : ''}{point.change_percent.toFixed(1)}%
                        </div>
                      )}
                    </Card>
                  </div>
                  <span className="text-[8px] text-muted-foreground mt-1 block text-center">
                    {point.period.slice(-2)}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * Main BI Insights Component
 */
export function BIInsights({ insights, onSuggestionClick, className }: BIInsightsProps) {
  const queryTypeLabels: Record<BIQueryType, string> = {
    document_search: 'Dokumenten-Suche',
    invoice_analysis: 'Rechnungsanalyse',
    entity_statistics: 'Kunden-Statistik',
    payment_prediction: 'Zahlungsprognose',
    trend_analysis: 'Trend-Analyse',
    summary: 'Zusammenfassung',
  };

  const queryTypeIcons: Record<BIQueryType, React.ReactNode> = {
    document_search: <FileText className="h-4 w-4" />,
    invoice_analysis: <Receipt className="h-4 w-4" />,
    entity_statistics: <Building2 className="h-4 w-4" />,
    payment_prediction: <Clock className="h-4 w-4" />,
    trend_analysis: <BarChart3 className="h-4 w-4" />,
    summary: <PieChart className="h-4 w-4" />,
  };

  const renderContent = () => {
    if (!insights.data) return null;

    switch (insights.query_type) {
      case 'invoice_analysis':
        return <InvoiceAnalysisView data={insights.data as BIInvoiceAnalysis} />;
      case 'entity_statistics':
        return <EntityStatisticsView data={insights.data as BIEntityStatistics | BIEntityStatistics[]} />;
      case 'payment_prediction':
        return <PaymentPredictionView data={insights.data as BIPaymentPrediction} />;
      case 'trend_analysis':
        return <TrendAnalysisView data={insights.data as BITrendAnalysis} />;
      default:
        return (
          <pre className="text-xs bg-muted p-2 rounded overflow-x-auto">
            {JSON.stringify(insights.data, null, 2)}
          </pre>
        );
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className={cn('space-y-4', className)}
    >
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <div className="p-1.5 rounded-lg bg-primary/10">
                {queryTypeIcons[insights.query_type]}
              </div>
              <div>
                <CardTitle className="text-base">
                  {queryTypeLabels[insights.query_type]}
                </CardTitle>
                <CardDescription className="text-xs">
                  Analysiert in {insights.query_time_ms}ms
                </CardDescription>
              </div>
            </div>
            <Badge variant="secondary" className="flex items-center gap-1">
              <Sparkles className="h-3 w-3" />
              KI-Analyse
            </Badge>
          </div>
        </CardHeader>
        <CardContent>
          {/* Summary */}
          <p className="text-sm mb-4">{insights.summary}</p>

          <Separator className="my-4" />

          {/* Visualization */}
          {renderContent()}
        </CardContent>
      </Card>

      {/* Suggestions */}
      {insights.suggestions.length > 0 && (
        <Card className="p-3">
          <div className="flex items-center gap-2 mb-2">
            <Lightbulb className="h-4 w-4 text-yellow-500" />
            <span className="text-sm font-medium">Weiter erkunden</span>
          </div>
          <div className="flex flex-wrap gap-2">
            {insights.suggestions.map((suggestion, i) => (
              <Button
                key={i}
                variant="outline"
                size="sm"
                className="text-xs"
                onClick={() => onSuggestionClick?.(suggestion)}
              >
                {suggestion}
              </Button>
            ))}
          </div>
        </Card>
      )}
    </motion.div>
  );
}

export default BIInsights;
