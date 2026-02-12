/**
 * LineageStatsCards Component
 *
 * Zeigt aggregierte Statistiken zur Dokumenten-Lineage.
 * Wird oberhalb des Flowcharts für schnelle Übersicht angezeigt.
 */

import { memo } from 'react';
import { cn } from '@/lib/utils';
import { formatNumberDE, formatPercentDE, formatDateTimeDE } from '@/lib/format';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import {
  FileUp,
  ScanSearch,
  Tag,
  Link2,
  Edit3,
  Download,
  Clock,
  Gauge,
  ThumbsUp,
  ThumbsDown,
} from 'lucide-react';
import type { LineageStats, LineageSummary } from '@/lib/api/services/lineage';

// =============================================================================
// Types
// =============================================================================

export interface LineageStatsCardsProps {
  stats?: LineageStats;
  summary?: LineageSummary;
  isLoading?: boolean;
  className?: string;
}

// =============================================================================
// Helper Components
// =============================================================================

interface StatCardProps {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: React.ReactNode;
  subValue?: string;
  colorClass?: string;
}

function StatCard({ icon: Icon, label, value, subValue, colorClass }: StatCardProps) {
  return (
    <Card className="flex-1 min-w-[140px]">
      <CardContent className="p-4">
        <div className="flex items-start gap-3">
          <div
            className={cn(
              'flex items-center justify-center w-10 h-10 rounded-lg',
              colorClass || 'bg-muted'
            )}
          >
            <Icon className="w-5 h-5" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm text-muted-foreground truncate">{label}</p>
            <div className="text-lg font-semibold">{value}</div>
            {subValue && (
              <p className="text-xs text-muted-foreground truncate">{subValue}</p>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

// =============================================================================
// Component
// =============================================================================

export const LineageStatsCards = memo(function LineageStatsCards({
  stats,
  summary,
  isLoading,
  className,
}: LineageStatsCardsProps) {
  if (isLoading) {
    return (
      <div className={cn('grid grid-cols-2 md:grid-cols-4 xl:grid-cols-6 gap-3', className)}>
        {Array.from({ length: 6 }).map((_, i) => (
          <Card key={i} className="animate-pulse">
            <CardContent className="p-4">
              <div className="flex items-start gap-3">
                <div className="w-10 h-10 rounded-lg bg-muted" />
                <div className="flex-1 space-y-2">
                  <div className="h-3 w-20 rounded bg-muted" />
                  <div className="h-6 w-16 rounded bg-muted" />
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    );
  }

  if (!stats) {
    return null;
  }

  return (
    <div className={cn('grid grid-cols-2 md:grid-cols-4 xl:grid-cols-6 gap-3', className)}>
      {/* Import */}
      <StatCard
        icon={FileUp}
        label="Import"
        value={
          stats.importInfo.sourceType ? (
            <Badge variant="outline" className="text-xs">
              {stats.importInfo.sourceType.replace(/_/g, ' ')}
            </Badge>
          ) : (
            '-'
          )
        }
        subValue={
          stats.importInfo.importedAt
            ? formatDateTimeDE(stats.importInfo.importedAt)
            : undefined
        }
        colorClass="bg-blue-100 text-blue-600 dark:bg-blue-900 dark:text-blue-400"
      />

      {/* OCR */}
      <StatCard
        icon={ScanSearch}
        label="OCR-Konfidenz"
        value={
          stats.ocr.confidence !== null ? (
            <Badge
              variant={stats.ocr.confidence >= 0.8 ? 'default' : 'secondary'}
            >
              {formatPercentDE(stats.ocr.confidence, 0, false)}
            </Badge>
          ) : (
            '-'
          )
        }
        subValue={
          stats.ocr.durationMs !== null
            ? `${formatNumberDE(stats.ocr.durationMs / 1000, 1)}s`
            : undefined
        }
        colorClass="bg-amber-100 text-amber-600 dark:bg-amber-900 dark:text-amber-400"
      />

      {/* Klassifikation */}
      <StatCard
        icon={Tag}
        label="Klassifikation"
        value={
          stats.classification.confidence !== null ? (
            <Badge
              variant={
                stats.classification.confidence >= 0.8 ? 'default' : 'secondary'
              }
            >
              {formatPercentDE(stats.classification.confidence, 0, false)}
            </Badge>
          ) : (
            '-'
          )
        }
        colorClass="bg-purple-100 text-purple-600 dark:bg-purple-900 dark:text-purple-400"
      />

      {/* Entity Linking */}
      <StatCard
        icon={Link2}
        label="Partner-Verknüpfung"
        value={
          stats.entityLinking.confidence !== null ? (
            <Badge
              variant={
                stats.entityLinking.confidence >= 0.8 ? 'default' : 'secondary'
              }
            >
              {formatPercentDE(stats.entityLinking.confidence, 0, false)}
            </Badge>
          ) : (
            '-'
          )
        }
        subValue={
          summary?.entityLinking.linkCount
            ? `${summary.entityLinking.linkCount} Verknüpfung(en)`
            : undefined
        }
        colorClass="bg-cyan-100 text-cyan-600 dark:bg-cyan-900 dark:text-cyan-400"
      />

      {/* Bearbeitungen */}
      <StatCard
        icon={Edit3}
        label="Bearbeitungen"
        value={stats.modifications.count}
        subValue={
          stats.modifications.lastModifiedAt
            ? `Zuletzt: ${formatDateTimeDE(stats.modifications.lastModifiedAt)}`
            : undefined
        }
        colorClass="bg-orange-100 text-orange-600 dark:bg-orange-900 dark:text-orange-400"
      />

      {/* Verarbeitungsdauer */}
      <StatCard
        icon={Clock}
        label="Verarbeitungsdauer"
        value={
          stats.totalProcessingDurationMs > 0 ? (
            <span>
              {stats.totalProcessingDurationMs < 1000
                ? `${stats.totalProcessingDurationMs}ms`
                : `${formatNumberDE(stats.totalProcessingDurationMs / 1000, 1)}s`}
            </span>
          ) : (
            '-'
          )
        }
        subValue={`${stats.totalEvents} Events`}
        colorClass="bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400"
      />
    </div>
  );
});
