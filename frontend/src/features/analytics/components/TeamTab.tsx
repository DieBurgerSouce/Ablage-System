// Team Tab Component
// Displays per-user productivity table with documents, approval time, corrections, quality

import { Skeleton } from '@/components/ui/skeleton';
import { Badge } from '@/components/ui/badge';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { StatCard } from './StatCard';
import { WorkloadHeatmap } from './WorkloadHeatmap';
import { useTeamStats } from '../hooks/use-analytics-queries';
import {
  type AnalyticsPeriod,
  UI_LABELS,
  formatNumber,
  formatHours,
} from '../types/analytics-types';

interface TeamTabProps {
  period: AnalyticsPeriod;
}

function getQualityBadge(score: number) {
  if (score >= 90) return <Badge variant="default">{score}</Badge>;
  if (score >= 70) return <Badge variant="secondary">{score}</Badge>;
  return <Badge variant="destructive">{score}</Badge>;
}

export function TeamTab({ period }: TeamTabProps) {
  const { data, isLoading, isError } = useTeamStats(period);

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-32 w-48" />
        <Skeleton className="h-64" />
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

  return (
    <div className="space-y-6">
      {/* Summary */}
      <div className="grid gap-4 grid-cols-2 md:grid-cols-3">
        <StatCard
          stat={{
            label: UI_LABELS.TOTAL_DOCUMENTS,
            value: formatNumber(data.totalDocuments),
          }}
        />
        <StatCard
          stat={{
            label: UI_LABELS.TEAM_OVERVIEW,
            value: `${data.userStats.length} Mitarbeiter`,
          }}
        />
      </div>

      {/* User Table */}
      {data.userStats.length > 0 ? (
        <div className="rounded-lg border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{UI_LABELS.USERNAME}</TableHead>
                <TableHead className="text-right">{UI_LABELS.DOCS_COUNT}</TableHead>
                <TableHead className="text-right">{UI_LABELS.AVG_APPROVAL_TIME}</TableHead>
                <TableHead className="text-right">{UI_LABELS.OCR_CORRECTIONS}</TableHead>
                <TableHead className="text-right">{UI_LABELS.QUALITY_SCORE}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.userStats.map((user) => (
                <TableRow key={user.userId}>
                  <TableCell className="font-medium">{user.username}</TableCell>
                  <TableCell className="text-right">
                    {formatNumber(user.documentsProcessed)}
                  </TableCell>
                  <TableCell className="text-right">
                    {formatHours(user.avgApprovalTimeHours)}
                  </TableCell>
                  <TableCell className="text-right">
                    {formatNumber(user.ocrCorrections)}
                  </TableCell>
                  <TableCell className="text-right">
                    {getQualityBadge(user.qualityScore)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      ) : (
        <div className="text-center py-12 text-muted-foreground">
          {UI_LABELS.NO_DATA}
        </div>
      )}

      {/* Workload Heatmap */}
      <WorkloadHeatmap period={period} />
    </div>
  );
}
