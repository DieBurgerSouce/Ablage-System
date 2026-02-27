/**
 * DiscrepancyCard - Detailkarte fuer eine einzelne Abweichung
 *
 * Zeigt:
 * - Kategorie-Icon + deutsches Label
 * - Schweregrad-Badge (Info, Warnung, Fehler, Kritisch)
 * - Erwartet vs. Tatsaechlich mit visuellem Diff (rot/gruen)
 * - Abweichungsprozentsatz
 * - Geloest-Status
 * - Optionale gelernte Toleranz-Info
 */

import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import {
  DollarSign,
  Hash,
  Package,
  Calendar,
  Tag,
  CheckCircle2,
  Clock,
  Info,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import type {
  DiscrepancyResponse,
  DiscrepancyCategory,
  DiscrepancySeverity,
} from '@/features/po-matching/types/po-matching-types';

// ==================== Konfiguration ====================

const CATEGORY_CONFIG: Record<
  DiscrepancyCategory,
  { label: string; icon: React.ComponentType<{ className?: string }> }
> = {
  amount: { label: 'Betrag', icon: DollarSign },
  quantity: { label: 'Menge', icon: Hash },
  item: { label: 'Artikel', icon: Package },
  date: { label: 'Datum', icon: Calendar },
  price: { label: 'Preis', icon: Tag },
};

const SEVERITY_CONFIG: Record<
  DiscrepancySeverity,
  { label: string; className: string }
> = {
  info: {
    label: 'Info',
    className: 'bg-blue-100 text-blue-800 border-blue-200',
  },
  warning: {
    label: 'Warnung',
    className: 'bg-yellow-100 text-yellow-800 border-yellow-200',
  },
  error: {
    label: 'Fehler',
    className: 'bg-red-100 text-red-800 border-red-200',
  },
  critical: {
    label: 'Kritisch',
    className: 'bg-red-600 text-white border-red-700',
  },
};

// ==================== Hilfsfunktionen ====================

function formatEUR(value: number | null): string {
  if (value === null || value === undefined) return '-';
  return new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency: 'EUR',
  }).format(value);
}

function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined) return '-';
  return `${value.toFixed(1)}%`;
}

function formatDate(isoDate: string | null): string {
  if (!isoDate) return '-';
  return new Intl.DateTimeFormat('de-DE', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  }).format(new Date(isoDate));
}

// ==================== Props ====================

interface DiscrepancyCardProps {
  discrepancy: DiscrepancyResponse;
  /** Optionale gelernte Toleranz in Prozent */
  learnedTolerance?: number;
}

// ==================== Component ====================

export function DiscrepancyCard({
  discrepancy,
  learnedTolerance,
}: DiscrepancyCardProps) {
  const catConfig = CATEGORY_CONFIG[discrepancy.category];
  const sevConfig = SEVERITY_CONFIG[discrepancy.severity];
  const CategoryIcon = catConfig.icon;

  const expectedDisplay =
    discrepancy.expected_amount !== null
      ? formatEUR(discrepancy.expected_amount)
      : discrepancy.expected_value ?? '-';

  const actualDisplay =
    discrepancy.actual_amount !== null
      ? formatEUR(discrepancy.actual_amount)
      : discrepancy.actual_value ?? '-';

  return (
    <Card
      className={cn(
        'transition-colors',
        discrepancy.resolved
          ? 'border-green-200 bg-green-50/30'
          : discrepancy.severity === 'critical'
            ? 'border-red-300'
            : discrepancy.severity === 'error'
              ? 'border-red-200'
              : undefined
      )}
    >
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2 text-sm font-medium">
            <CategoryIcon className="h-4 w-4 text-muted-foreground" />
            {catConfig.label}
          </CardTitle>
          <div className="flex items-center gap-2">
            <Badge
              variant="outline"
              className={cn('text-xs', sevConfig.className)}
            >
              {sevConfig.label}
            </Badge>
            {discrepancy.resolved ? (
              <TooltipProvider>
                <Tooltip>
                  <TooltipTrigger>
                    <CheckCircle2 className="h-4 w-4 text-green-600" />
                  </TooltipTrigger>
                  <TooltipContent>
                    <p>
                      Gel\u00f6st
                      {discrepancy.resolved_at
                        ? ` am ${formatDate(discrepancy.resolved_at)}`
                        : ''}
                    </p>
                  </TooltipContent>
                </Tooltip>
              </TooltipProvider>
            ) : (
              <TooltipProvider>
                <Tooltip>
                  <TooltipTrigger>
                    <Clock className="h-4 w-4 text-muted-foreground" />
                  </TooltipTrigger>
                  <TooltipContent>
                    <p>Offen</p>
                  </TooltipContent>
                </Tooltip>
              </TooltipProvider>
            )}
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-3">
        {/* Beschreibung */}
        <p className="text-sm text-muted-foreground">
          {discrepancy.description}
        </p>

        {/* Erwartet vs. Tatsaechlich */}
        <div className="grid grid-cols-2 gap-3">
          <div className="rounded-md border border-green-200 bg-green-50/50 p-2">
            <p className="text-xs text-muted-foreground mb-0.5">Erwartet</p>
            <p className="text-sm font-semibold tabular-nums text-green-800">
              {expectedDisplay}
            </p>
          </div>
          <div className="rounded-md border border-red-200 bg-red-50/50 p-2">
            <p className="text-xs text-muted-foreground mb-0.5">
              Tats\u00e4chlich
            </p>
            <p className="text-sm font-semibold tabular-nums text-red-800">
              {actualDisplay}
            </p>
          </div>
        </div>

        {/* Abweichung + Toleranz */}
        <div className="flex items-center justify-between text-sm">
          {discrepancy.deviation_percent !== null && (
            <div className="flex items-center gap-1">
              <span className="text-muted-foreground">Abweichung:</span>
              <span
                className={cn(
                  'font-semibold tabular-nums',
                  Math.abs(discrepancy.deviation_percent) > 5
                    ? 'text-red-600'
                    : 'text-yellow-600'
                )}
              >
                {formatPercent(discrepancy.deviation_percent)}
              </span>
            </div>
          )}

          {learnedTolerance !== undefined && (
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger>
                  <div className="flex items-center gap-1 text-xs text-blue-600">
                    <Info className="h-3 w-3" />
                    <span>Toleranz: {formatPercent(learnedTolerance)}</span>
                  </div>
                </TooltipTrigger>
                <TooltipContent>
                  <p>Gelernte Toleranz aus bisherigen Freigaben</p>
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          )}
        </div>

        {/* Aufloesung */}
        {discrepancy.resolved && discrepancy.resolution_notes && (
          <div className="rounded-md bg-muted/50 p-2 text-xs">
            <span className="font-medium">Aufl\u00f6sung: </span>
            {discrepancy.resolution_notes}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
