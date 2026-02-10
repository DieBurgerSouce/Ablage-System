/**
 * RecurringAlerts Component
 *
 * Zeigt fehlende Rechnungen und Preisaenderungen
 * als Alert-Cards an.
 */

import { AlertTriangle, TrendingUp, TrendingDown, Clock } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import {
  useMissingInvoices,
  usePriceChanges,
} from '../hooks/useRecurringInvoices';

// ==================== Helpers ====================

function formatEUR(amount: number): string {
  return new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency: 'EUR',
  }).format(amount);
}

function formatDate(dateStr: string): string {
  return new Intl.DateTimeFormat('de-DE', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  }).format(new Date(dateStr));
}

function formatPercent(value: number): string {
  const prefix = value > 0 ? '+' : '';
  return `${prefix}${value.toFixed(1)}%`;
}

// ==================== Component ====================

export default function RecurringAlerts() {
  const {
    data: missingInvoices,
    isLoading: isLoadingMissing,
  } = useMissingInvoices();

  const {
    data: priceChanges,
    isLoading: isLoadingPrices,
  } = usePriceChanges();

  const isLoading = isLoadingMissing || isLoadingPrices;

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-48 w-full" />
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Fehlende Rechnungen */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <AlertTriangle className="h-4 w-4 text-red-500" />
            Fehlende Rechnungen
          </CardTitle>
          <CardDescription>
            Erwartete Rechnungen, die noch nicht eingegangen sind
          </CardDescription>
        </CardHeader>
        <CardContent>
          {missingInvoices && missingInvoices.length > 0 ? (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {missingInvoices.map((item) => (
                <Card
                  key={`${item.recurring_invoice_id}-${item.expected_date}`}
                  className="border-red-200 bg-red-50 dark:border-red-800 dark:bg-red-950"
                >
                  <CardContent className="p-4">
                    <div className="flex items-start justify-between">
                      <div>
                        <p className="font-medium">{item.vendor_name}</p>
                        <p className="mt-1 text-sm text-muted-foreground">
                          Erwartet: {formatDate(item.expected_date)}
                        </p>
                        <p className="text-sm font-medium">
                          {formatEUR(item.expected_amount)}
                        </p>
                      </div>
                      <Badge variant="destructive" className="flex items-center gap-1">
                        <Clock className="h-3 w-3" />
                        {item.days_overdue} Tage
                      </Badge>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          ) : (
            <div className="py-8 text-center text-muted-foreground">
              Keine fehlenden Rechnungen. Alles auf Kurs.
            </div>
          )}
        </CardContent>
      </Card>

      {/* Preisaenderungen */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <TrendingUp className="h-4 w-4 text-orange-500" />
            Preisaenderungen
          </CardTitle>
          <CardDescription>
            Erkannte Preisaenderungen bei wiederkehrenden Rechnungen
          </CardDescription>
        </CardHeader>
        <CardContent>
          {priceChanges && priceChanges.length > 0 ? (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {priceChanges.map((item) => (
                <Card
                  key={`${item.recurring_invoice_id}-${item.change_date}`}
                  className="border-orange-200 bg-orange-50 dark:border-orange-800 dark:bg-orange-950"
                >
                  <CardContent className="p-4">
                    <div>
                      <p className="font-medium">{item.vendor_name}</p>
                      <div className="mt-2 flex items-center gap-2 text-sm">
                        <span className="text-muted-foreground">
                          {formatEUR(item.old_amount)}
                        </span>
                        <span className="text-muted-foreground">&rarr;</span>
                        <span className="font-medium">
                          {formatEUR(item.new_amount)}
                        </span>
                      </div>
                      <div className="mt-1 flex items-center justify-between">
                        <span className="text-xs text-muted-foreground">
                          {formatDate(item.change_date)}
                        </span>
                        <Badge
                          variant={item.change_percent > 0 ? 'destructive' : 'default'}
                          className="flex items-center gap-1"
                        >
                          {item.change_percent > 0 ? (
                            <TrendingUp className="h-3 w-3" />
                          ) : (
                            <TrendingDown className="h-3 w-3" />
                          )}
                          {formatPercent(item.change_percent)}
                        </Badge>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          ) : (
            <div className="py-8 text-center text-muted-foreground">
              Keine Preisaenderungen erkannt.
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
