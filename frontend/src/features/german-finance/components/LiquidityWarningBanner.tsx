/**
 * LiquidityWarningBanner Component
 *
 * Alert banner for liquidity warnings
 */

import { useState } from 'react';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { AlertTriangle, X, TrendingDown, Info } from 'lucide-react';
import { useLiquidityWarnings } from '../hooks/use-german-finance-queries';
import type { LiquidityWarning } from '../types/german-finance-types';

const formatEuro = (amount: number): string => {
  return new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency: 'EUR',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(amount);
};

const formatDate = (date: Date): string => {
  return date.toLocaleDateString('de-DE', {
    day: '2-digit',
    month: 'long',
    year: 'numeric',
  });
};

const getSeverityConfig = (severity: LiquidityWarning['severity']) => {
  switch (severity) {
    case 'critical':
      return {
        icon: AlertTriangle,
        variant: 'destructive' as const,
        className: 'border-red-600 bg-red-50 dark:bg-red-950',
        iconClassName: 'text-red-600',
      };
    case 'warning':
      return {
        icon: TrendingDown,
        variant: 'default' as const,
        className: 'border-yellow-600 bg-yellow-50 dark:bg-yellow-950',
        iconClassName: 'text-yellow-600',
      };
    case 'info':
      return {
        icon: Info,
        variant: 'default' as const,
        className: 'border-blue-600 bg-blue-50 dark:bg-blue-950',
        iconClassName: 'text-blue-600',
      };
  }
};

interface WarningItemProps {
  warning: LiquidityWarning;
  onDismiss: () => void;
}

function WarningItem({ warning, onDismiss }: WarningItemProps) {
  const config = getSeverityConfig(warning.severity);
  const Icon = config.icon;

  return (
    <Alert variant={config.variant} className={config.className}>
      <Icon className={`h-4 w-4 ${config.iconClassName}`} />
      <AlertTitle className="flex items-center justify-between">
        <span>Liquiditätswarnung</span>
        <Button
          variant="ghost"
          size="sm"
          className="h-6 w-6 p-0"
          onClick={onDismiss}
        >
          <X className="h-4 w-4" />
          <span className="sr-only">Schließen</span>
        </Button>
      </AlertTitle>
      <AlertDescription className="mt-2 space-y-2">
        <p>{warning.message}</p>
        {warning.expectedDate && (
          <p className="text-sm">
            <strong>Erwartetes Datum:</strong> {formatDate(warning.expectedDate)}
          </p>
        )}
        {warning.shortfallAmount !== null && warning.shortfallAmount > 0 && (
          <p className="text-sm font-semibold">
            <strong>Fehlbetrag:</strong> {formatEuro(warning.shortfallAmount)}
          </p>
        )}
      </AlertDescription>
    </Alert>
  );
}

export function LiquidityWarningBanner() {
  const { data: warnings, isLoading } = useLiquidityWarnings();
  const [dismissedIds, setDismissedIds] = useState<Set<string>>(new Set());

  if (isLoading) {
    return <Skeleton className="h-24 w-full" />;
  }

  if (!warnings || warnings.length === 0) {
    return null;
  }

  // Filter out dismissed warnings and sort by severity
  const activeWarnings = warnings.filter((warning) => {
    const warningId = `${warning.severity}-${warning.message}-${warning.expectedDate}`;
    return !dismissedIds.has(warningId);
  });

  // Sort by severity: critical -> warning -> info
  const severityOrder = { critical: 0, warning: 1, info: 2 };
  activeWarnings.sort((a, b) => severityOrder[a.severity] - severityOrder[b.severity]);

  if (activeWarnings.length === 0) {
    return null;
  }

  const handleDismiss = (warning: LiquidityWarning) => {
    const warningId = `${warning.severity}-${warning.message}-${warning.expectedDate}`;
    setDismissedIds(new Set(dismissedIds).add(warningId));
  };

  return (
    <div className="space-y-4">
      {activeWarnings.map((warning, index) => {
        const warningId = `${warning.severity}-${warning.message}-${warning.expectedDate}`;
        return (
          <WarningItem
            key={warningId + index}
            warning={warning}
            onDismiss={() => handleDismiss(warning)}
          />
        );
      })}
    </div>
  );
}
