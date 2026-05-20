// Operations Tab Component
// Displays operational metrics: documents, OCR accuracy, approvals, errors, processing time

import { Skeleton } from '@/components/ui/skeleton';
import { StatCard } from './StatCard';
import { useOperationsData } from '../hooks/use-analytics-queries';
import {
  type AnalyticsPeriod,
  type StatCardData,
  UI_LABELS,
  formatNumber,
  formatPercent,
  formatMs,
} from '../types/analytics-types';

interface OperationsTabProps {
  period: AnalyticsPeriod;
}

export function OperationsTab({ period }: OperationsTabProps) {
  const { data, isLoading, isError } = useOperationsData(period);

  if (isLoading) {
    return (
      <div className="grid gap-4 grid-cols-2 md:grid-cols-3">
        {[...Array(6)].map((_, i) => (
          <Skeleton key={i} className="h-32" />
        ))}
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        {UI_LABELS.ERROR}
      </div>
    );
  }

  const stats: StatCardData[] = [
    {
      label: UI_LABELS.DOCS_PROCESSED,
      value: formatNumber(data.documentsProcessed.month),
      unit: `${UI_LABELS.DOCS_TODAY}: ${data.documentsProcessed.today} | ${UI_LABELS.DOCS_WEEK}: ${data.documentsProcessed.week}`,
    },
    {
      label: UI_LABELS.OCR_ACCURACY,
      value: formatPercent(data.ocrAccuracyPercent),
      trend: data.ocrAccuracyTrend,
      color: data.ocrAccuracyPercent >= 95 ? 'green' : data.ocrAccuracyPercent >= 85 ? 'yellow' : 'red',
    },
    {
      label: UI_LABELS.PENDING_APPROVALS,
      value: formatNumber(data.pendingApprovals),
      unit: data.oldestApprovalDays > 0
        ? `${UI_LABELS.OLDEST_APPROVAL}: ${data.oldestApprovalDays} ${UI_LABELS.DAYS}`
        : undefined,
      color: data.pendingApprovals > 10 ? 'red' : data.pendingApprovals > 5 ? 'yellow' : 'green',
    },
    {
      label: UI_LABELS.ERROR_RATE,
      value: formatPercent(data.errorRatePercent),
      trend: data.errorRatePercent > 5 ? 'down' : data.errorRatePercent < 2 ? 'up' : 'neutral',
      color: data.errorRatePercent > 5 ? 'red' : data.errorRatePercent > 2 ? 'yellow' : 'green',
    },
    {
      label: UI_LABELS.AVG_PROCESSING_TIME,
      value: formatMs(data.avgProcessingTimeMs),
      unit: `P95: ${formatMs(data.p95ProcessingTimeMs)}`,
    },
    {
      label: UI_LABELS.AUTO_PROCESS_RATE,
      value: formatPercent(data.autoProcessRate),
      trend: data.autoProcessRate >= 50 ? 'up' : 'neutral',
      color: data.autoProcessRate >= 70 ? 'green' : data.autoProcessRate >= 40 ? 'yellow' : 'red',
    },
  ];

  return (
    <div className="space-y-6">
      <div className="grid gap-4 grid-cols-2 md:grid-cols-3">
        {stats.map((stat) => (
          <StatCard key={stat.label} stat={stat} />
        ))}
      </div>

      {/* Top Errors */}
      {data.topErrors.length > 0 && (
        <div className="rounded-lg border p-4">
          <h3 className="text-sm font-medium mb-3">{UI_LABELS.TOP_ERRORS}</h3>
          <div className="space-y-2">
            {data.topErrors.slice(0, 3).map((error) => (
              <div
                key={error.errorType}
                className="flex items-center justify-between text-sm"
              >
                <span className="text-muted-foreground">{error.errorType}</span>
                <span className="font-medium">{error.count}x</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
