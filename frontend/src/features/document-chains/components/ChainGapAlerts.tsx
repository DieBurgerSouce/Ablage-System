/**
 * ChainGapAlerts - Luecken-Warnungen fuer Auftragsketten
 *
 * Zeigt erkannte Luecken in Dokumentenketten mit Severity-Badges
 * und Vorschlaegen zum Verknuepfen fehlender Dokumente.
 */

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  AlertTriangle,
  AlertCircle,
  Info,
  Link2,
  Loader2,
  RefreshCw,
  FileSearch,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { useChainGaps } from '../hooks/use-chain-queries';
import type { ChainGap, GapSeverity } from '../api/chain-intelligence-api';

interface ChainGapAlertsProps {
  onChainClick?: (chainId: string) => void;
  className?: string;
  maxGaps?: number;
}

const SEVERITY_CONFIG: Record<GapSeverity, {
  label: string;
  icon: typeof AlertTriangle;
  badgeClass: string;
  borderClass: string;
}> = {
  critical: {
    label: 'Kritisch',
    icon: AlertCircle,
    badgeClass: 'bg-red-50 text-red-700 border-red-200',
    borderClass: 'border-l-red-500',
  },
  warning: {
    label: 'Warnung',
    icon: AlertTriangle,
    badgeClass: 'bg-yellow-50 text-yellow-700 border-yellow-200',
    borderClass: 'border-l-yellow-500',
  },
  info: {
    label: 'Info',
    icon: Info,
    badgeClass: 'bg-blue-50 text-blue-700 border-blue-200',
    borderClass: 'border-l-blue-500',
  },
};

export function ChainGapAlerts({
  onChainClick,
  className,
  maxGaps = 10,
}: ChainGapAlertsProps) {
  const gapsQuery = useChainGaps();
  const report = gapsQuery.data;
  const gaps = report?.gaps ?? [];
  const displayGaps = gaps.slice(0, maxGaps);

  if (gapsQuery.isLoading) {
    return (
      <Card className={className}>
        <CardContent className="py-8">
          <div className="flex items-center justify-center text-muted-foreground">
            <Loader2 className="w-5 h-5 animate-spin mr-2" />
            <span>Kettenanalyse wird durchgefuehrt...</span>
          </div>
        </CardContent>
      </Card>
    );
  }

  if (gapsQuery.isError) {
    return (
      <Card className={className}>
        <CardContent className="py-8">
          <div className="text-center text-muted-foreground">
            <AlertTriangle className="w-8 h-8 mx-auto mb-2 opacity-50" />
            <p className="text-sm">Fehler beim Laden der Kettenanalyse</p>
            <Button
              variant="outline"
              size="sm"
              className="mt-2"
              onClick={() => gapsQuery.refetch()}
            >
              <RefreshCw className="w-4 h-4 mr-1" />
              Erneut versuchen
            </Button>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className={className}>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base font-semibold flex items-center gap-2">
            <FileSearch className="w-5 h-5" />
            Ketten-Intelligenz
          </CardTitle>
          <div className="flex items-center gap-2">
            {report && (
              <span className="text-xs text-muted-foreground">
                {report.totalChains} Ketten, {report.averageCompletion.toFixed(0)}% Durchschnitt
              </span>
            )}
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7"
              onClick={() => gapsQuery.refetch()}
              disabled={gapsQuery.isFetching}
            >
              <RefreshCw
                className={cn('w-3.5 h-3.5', gapsQuery.isFetching && 'animate-spin')}
              />
            </Button>
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-2">
        {/* Summary Stats */}
        {report && report.chainsWithGaps > 0 && (
          <div className="flex items-center gap-4 text-sm mb-3 p-2 bg-muted/50 rounded-md">
            <div>
              <span className="font-medium text-red-600">
                {gaps.filter((g) => g.severity === 'critical').length}
              </span>
              <span className="text-muted-foreground ml-1">Kritisch</span>
            </div>
            <div>
              <span className="font-medium text-yellow-600">
                {gaps.filter((g) => g.severity === 'warning').length}
              </span>
              <span className="text-muted-foreground ml-1">Warnungen</span>
            </div>
            <div>
              <span className="font-medium text-blue-600">
                {gaps.filter((g) => g.severity === 'info').length}
              </span>
              <span className="text-muted-foreground ml-1">Info</span>
            </div>
          </div>
        )}

        {/* No Gaps */}
        {gaps.length === 0 && (
          <div className="text-center py-6 text-muted-foreground">
            <Link2 className="w-8 h-8 mx-auto mb-2 opacity-50" />
            <p className="text-sm font-medium">Keine Luecken erkannt</p>
            <p className="text-xs">Alle Auftragsketten sind vollstaendig.</p>
          </div>
        )}

        {/* Gap List */}
        {displayGaps.map((gap, index) => (
          <GapAlertItem
            key={`${gap.chainId}-${gap.expectedType}-${index}`}
            gap={gap}
            onChainClick={onChainClick}
          />
        ))}

        {/* Show More */}
        {gaps.length > maxGaps && (
          <p className="text-xs text-center text-muted-foreground pt-2">
            {gaps.length - maxGaps} weitere Luecken nicht angezeigt
          </p>
        )}
      </CardContent>
    </Card>
  );
}

// ==================== Gap Alert Item ====================

function GapAlertItem({
  gap,
  onChainClick,
}: {
  gap: ChainGap;
  onChainClick?: (chainId: string) => void;
}) {
  const config = SEVERITY_CONFIG[gap.severity];
  const SeverityIcon = config.icon;

  return (
    <div
      className={cn(
        'flex items-start gap-3 p-3 border rounded-lg border-l-4 cursor-pointer hover:bg-muted/30 transition-colors',
        config.borderClass
      )}
      onClick={() => onChainClick?.(gap.chainId)}
    >
      <SeverityIcon className="w-4 h-4 mt-0.5 flex-shrink-0" />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1">
          <span className="font-medium text-sm truncate">{gap.chainName}</span>
          <Badge variant="outline" className={cn('text-xs flex-shrink-0', config.badgeClass)}>
            {config.label}
          </Badge>
        </div>
        <p className="text-xs text-muted-foreground">
          <span className="font-medium">{gap.expectedType}</span> fehlt nach{' '}
          <span className="italic">{gap.afterDocument}</span>
        </p>
        {gap.daysOverdue > 0 && (
          <p className="text-xs text-muted-foreground mt-0.5">
            {gap.daysOverdue} Tage ueberfaellig
          </p>
        )}
        {gap.suggestedMatches.length > 0 && (
          <div className="mt-1">
            <Button variant="outline" size="sm" className="h-6 text-xs">
              <Link2 className="w-3 h-3 mr-1" />
              {gap.suggestedMatches.length} Vorschlaege
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
