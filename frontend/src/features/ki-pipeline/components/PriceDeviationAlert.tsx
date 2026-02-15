/**
 * PriceDeviationAlert Component
 * Alert banner/card for price anomalies
 */

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { AlertTriangle, TrendingUp, TrendingDown, Calendar } from 'lucide-react';
import { cn } from '@/lib/utils';
import { FIELD_LABELS, type PriceDeviation } from '../types/ki-pipeline-types';

interface PriceDeviationAlertProps {
  deviation: PriceDeviation;
  variant?: 'card' | 'banner';
  className?: string;
}

export function PriceDeviationAlert({
  deviation,
  variant = 'card',
  className,
}: PriceDeviationAlertProps) {
  const isIncrease = deviation.actual_value > deviation.expected_value;
  const percentAbs = Math.abs(deviation.deviation_percent);
  const isLargeDeviation = percentAbs >= 10;

  const fieldLabel = FIELD_LABELS[deviation.field] || deviation.field;

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('de-DE', {
      style: 'currency',
      currency: 'EUR',
    }).format(value);
  };

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return new Intl.DateTimeFormat('de-DE', {
      dateStyle: 'short',
      timeStyle: 'short',
    }).format(date);
  };

  const getSeverityColor = () => {
    if (percentAbs >= 20) return 'text-red-600 dark:text-red-400';
    if (percentAbs >= 10) return 'text-orange-600 dark:text-orange-400';
    return 'text-yellow-600 dark:text-yellow-400';
  };

  const getBadgeClass = () => {
    if (percentAbs >= 20) return 'bg-red-500 text-white';
    if (percentAbs >= 10) return 'bg-orange-500 text-white';
    return 'bg-yellow-500 text-white';
  };

  const getBorderClass = () => {
    if (percentAbs >= 20) return 'border-red-500';
    if (percentAbs >= 10) return 'border-orange-500';
    return 'border-yellow-500';
  };

  if (variant === 'banner') {
    return (
      <div
        className={cn(
          'flex items-center gap-4 p-4 border-l-4 rounded-lg',
          getBorderClass(),
          isLargeDeviation ? 'bg-red-50 dark:bg-red-950/20' : 'bg-yellow-50 dark:bg-yellow-950/20',
          className
        )}
      >
        <div className="flex-shrink-0">
          <AlertTriangle className={cn('h-5 w-5', getSeverityColor())} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="font-semibold text-sm">
              Preisabweichung: {fieldLabel}
            </span>
            <Badge className={cn('font-semibold', getBadgeClass())}>
              {isIncrease ? '+' : ''}
              {deviation.deviation_percent.toFixed(1)}%
            </Badge>
          </div>
          <div className="text-xs text-muted-foreground space-y-1">
            <div className="flex items-center gap-4">
              <span>
                Erwartet: {formatCurrency(deviation.expected_value)}
              </span>
              <span className={getSeverityColor()}>
                Aktuell: {formatCurrency(deviation.actual_value)}
              </span>
            </div>
            {deviation.supplier_name && (
              <div>Lieferant: {deviation.supplier_name}</div>
            )}
            {deviation.document_number && (
              <div>Beleg: {deviation.document_number}</div>
            )}
          </div>
        </div>
      </div>
    );
  }

  return (
    <Card
      className={cn(
        'w-full border-l-4',
        getBorderClass(),
        isLargeDeviation && 'bg-red-50 dark:bg-red-950/10',
        className
      )}
    >
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between">
          <CardTitle className="flex items-center gap-2 text-base">
            <AlertTriangle className={cn('h-4 w-4', getSeverityColor())} />
            Preisabweichung
          </CardTitle>
          <Badge className={cn('font-semibold', getBadgeClass())}>
            {isIncrease ? (
              <TrendingUp className="h-3 w-3 mr-1" />
            ) : (
              <TrendingDown className="h-3 w-3 mr-1" />
            )}
            {isIncrease ? '+' : ''}
            {deviation.deviation_percent.toFixed(1)}%
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="space-y-2">
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">Feld:</span>
            <span className="font-medium">{fieldLabel}</span>
          </div>
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">Erwarteter Preis:</span>
            <span className="font-medium">
              {formatCurrency(deviation.expected_value)}
            </span>
          </div>
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">Aktueller Preis:</span>
            <span className={cn('font-semibold', getSeverityColor())}>
              {formatCurrency(deviation.actual_value)}
            </span>
          </div>
        </div>

        <div className="pt-2 border-t space-y-1 text-xs text-muted-foreground">
          {deviation.supplier_name && (
            <div>Lieferant: {deviation.supplier_name}</div>
          )}
          {deviation.document_number && (
            <div>Belegnummer: {deviation.document_number}</div>
          )}
          <div className="flex items-center gap-1">
            <Calendar className="h-3 w-3" />
            <span>{formatDate(deviation.created_at)}</span>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
