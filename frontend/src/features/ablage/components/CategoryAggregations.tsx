/**
 * CategoryAggregations - Summen-Karten für Kategorie-Seiten
 *
 * Zeigt aggregierte Daten wie:
 * - Gesamtanzahl Dokumente
 * - Gesamtbetrag (bei Rechnungen)
 * - Offene Beträge
 * - Überfällige Dokumente
 */

import { FileText, Euro, AlertTriangle, Clock } from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import type { CategoryDocumentAggregations } from '../types';

interface CategoryAggregationsProps {
  aggregations: CategoryDocumentAggregations | undefined;
  isLoading?: boolean;
  showPaymentInfo?: boolean;
}

const formatAmount = (amount: number, currency = 'EUR') => {
  return amount.toLocaleString('de-DE', {
    style: 'currency',
    currency,
  });
};

function AggregationCard({
  title,
  value,
  icon: Icon,
  description,
  variant = 'default',
}: {
  title: string;
  value: string | number;
  icon: React.ElementType;
  description?: string;
  variant?: 'default' | 'warning' | 'destructive';
}) {
  const variantClasses = {
    default: 'text-primary',
    warning: 'text-amber-500',
    destructive: 'text-destructive',
  };

  return (
    <Card>
      <CardContent className="pt-6">
        <div className="flex items-start justify-between">
          <div>
            <p className="text-sm font-medium text-muted-foreground">{title}</p>
            <p className={`text-2xl font-bold mt-1 ${variantClasses[variant]}`}>
              {value}
            </p>
            {description && (
              <p className="text-xs text-muted-foreground mt-1">{description}</p>
            )}
          </div>
          <Icon className={`w-5 h-5 ${variantClasses[variant]}`} aria-hidden="true" />
        </div>
      </CardContent>
    </Card>
  );
}

function LoadingSkeleton() {
  return (
    <Card>
      <CardContent className="pt-6">
        <div className="flex items-start justify-between">
          <div className="space-y-2">
            <Skeleton className="h-4 w-24" />
            <Skeleton className="h-8 w-32" />
          </div>
          <Skeleton className="h-5 w-5" />
        </div>
      </CardContent>
    </Card>
  );
}

export function CategoryAggregations({
  aggregations,
  isLoading,
  showPaymentInfo = false,
}: CategoryAggregationsProps) {
  if (isLoading) {
    return (
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4" role="status" aria-label="Lade Statistiken">
        <LoadingSkeleton />
        <LoadingSkeleton />
        {showPaymentInfo && <LoadingSkeleton />}
        {showPaymentInfo && <LoadingSkeleton />}
      </div>
    );
  }

  if (!aggregations) {
    return null;
  }

  return (
    <div
      className="grid grid-cols-2 md:grid-cols-4 gap-4"
      role="region"
      aria-label="Kategorie-Statistiken"
    >
      <AggregationCard
        title="Dokumente"
        value={aggregations.totalDocuments}
        icon={FileText}
        description={`${aggregations.documentsByStatus?.completed || 0} verarbeitet`}
      />

      {showPaymentInfo && (
        <>
          <AggregationCard
            title="Gesamtbetrag"
            value={formatAmount(aggregations.totalAmount, aggregations.currency)}
            icon={Euro}
          />

          <AggregationCard
            title="Offen"
            value={formatAmount(aggregations.totalOpen, aggregations.currency)}
            icon={Clock}
            variant={aggregations.totalOpen > 0 ? 'warning' : 'default'}
            description={`${aggregations.documentsByPaymentStatus?.offen || 0} Rechnungen`}
          />

          <AggregationCard
            title="Überfällig"
            value={aggregations.overdueCount}
            icon={AlertTriangle}
            variant={aggregations.overdueCount > 0 ? 'destructive' : 'default'}
            description={
              aggregations.overdueCount > 0
                ? formatAmount(aggregations.totalOverdue, aggregations.currency)
                : 'Keine überfälligen Rechnungen'
            }
          />
        </>
      )}

      {!showPaymentInfo && (
        <AggregationCard
          title="Zeitraum"
          value={
            aggregations.earliestDate && aggregations.latestDate
              ? `${new Date(aggregations.earliestDate).toLocaleDateString('de-DE', {
                  month: 'short',
                  year: 'numeric',
                })} - ${new Date(aggregations.latestDate).toLocaleDateString('de-DE', {
                  month: 'short',
                  year: 'numeric',
                })}`
              : '-'
          }
          icon={Clock}
        />
      )}
    </div>
  );
}
