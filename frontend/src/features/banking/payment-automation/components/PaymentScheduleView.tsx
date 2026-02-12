/**
 * Payment Schedule View
 *
 * Kalenderansicht für geplante Zahlungen.
 */

import { useState } from 'react';
import {
  Calendar,
  ChevronLeft,
  ChevronRight,
  Banknote,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { usePaymentSchedule, type PaymentStrategy } from '../hooks/usePaymentAutomation';

function formatCurrency(amount: number): string {
  return amount.toLocaleString('de-DE', { style: 'currency', currency: 'EUR' });
}

function formatDate(dateString: string): string {
  const date = new Date(dateString);
  return date.toLocaleDateString('de-DE', { weekday: 'short', day: '2-digit', month: '2-digit' });
}

function getDayOfWeek(dateString: string): number {
  return new Date(dateString).getDay();
}

export function PaymentScheduleView() {
  const [periodDays, setPeriodDays] = useState(30);
  const [strategy, setStrategy] = useState<PaymentStrategy>('skonto_optimized');

  const { data: schedule, isLoading } = usePaymentSchedule(periodDays, strategy);

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <Skeleton className="h-6 w-48" />
          <Skeleton className="h-4 w-64 mt-2" />
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-24 w-full" />
            ))}
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <div>
          <CardTitle className="flex items-center gap-2">
            <Calendar className="h-5 w-5" />
            Zahlungskalender
          </CardTitle>
          <CardDescription>
            Geplante Zahlungen nach Datum gruppiert
          </CardDescription>
        </div>
        <div className="flex items-center gap-2">
          <Select value={String(periodDays)} onValueChange={(v) => setPeriodDays(Number(v))}>
            <SelectTrigger className="w-[140px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="7">7 Tage</SelectItem>
              <SelectItem value="14">14 Tage</SelectItem>
              <SelectItem value="30">30 Tage</SelectItem>
              <SelectItem value="60">60 Tage</SelectItem>
              <SelectItem value="90">90 Tage</SelectItem>
            </SelectContent>
          </Select>
          <Select value={strategy} onValueChange={(v) => setStrategy(v as PaymentStrategy)}>
            <SelectTrigger className="w-[180px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="skonto_optimized">Skonto-optimiert</SelectItem>
              <SelectItem value="cashflow_optimized">Cashflow-optimiert</SelectItem>
              <SelectItem value="deadline_based">Nach Fälligkeit</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </CardHeader>
      <CardContent>
        {schedule && schedule.entries.length > 0 ? (
          <div className="space-y-4">
            {/* Summary */}
            <div className="flex items-center justify-between p-4 bg-muted rounded-lg">
              <div>
                <p className="text-sm text-muted-foreground">Gesamtsumme im Zeitraum</p>
                <p className="text-2xl font-bold">{formatCurrency(schedule.total_amount)}</p>
              </div>
              {schedule.total_skonto_savings > 0 && (
                <div className="text-right">
                  <p className="text-sm text-muted-foreground">Skonto-Ersparnis</p>
                  <p className="text-xl font-bold text-green-600">
                    {formatCurrency(schedule.total_skonto_savings)}
                  </p>
                </div>
              )}
            </div>

            {/* Schedule Entries */}
            <div className="space-y-3">
              {schedule.entries.map((entry) => {
                const dayOfWeek = getDayOfWeek(entry.date);
                const isWeekend = dayOfWeek === 0 || dayOfWeek === 6;

                return (
                  <div
                    key={entry.date}
                    className={`border rounded-lg p-4 ${isWeekend ? 'bg-muted/50' : ''}`}
                  >
                    <div className="flex items-center justify-between mb-3">
                      <div className="flex items-center gap-3">
                        <div className="text-center min-w-[60px]">
                          <p className="text-xs text-muted-foreground uppercase">
                            {new Date(entry.date).toLocaleDateString('de-DE', { weekday: 'short' })}
                          </p>
                          <p className="text-lg font-bold">
                            {new Date(entry.date).getDate()}
                          </p>
                          <p className="text-xs text-muted-foreground">
                            {new Date(entry.date).toLocaleDateString('de-DE', { month: 'short' })}
                          </p>
                        </div>
                        <div className="border-l pl-3">
                          <p className="font-medium">{entry.payment_count} Zahlung(en)</p>
                          <p className="text-sm text-muted-foreground">
                            {formatCurrency(entry.total_amount)}
                          </p>
                        </div>
                      </div>
                      {entry.skonto_savings > 0 && (
                        <Badge variant="outline" className="text-green-500 border-green-500">
                          <Banknote className="h-3 w-3 mr-1" />
                          {formatCurrency(entry.skonto_savings)} Skonto
                        </Badge>
                      )}
                    </div>

                    {/* Payment Details */}
                    <div className="grid gap-2 ml-[72px]">
                      {entry.payments.map((payment, idx) => (
                        <div
                          key={idx}
                          className="flex items-center justify-between text-sm p-2 bg-background rounded"
                        >
                          <div className="flex items-center gap-2">
                            <Badge
                              variant="outline"
                              className={`text-xs ${
                                payment.priority === 'critical'
                                  ? 'text-red-500 border-red-500'
                                  : payment.priority === 'high'
                                    ? 'text-orange-500 border-orange-500'
                                    : ''
                              }`}
                            >
                              {payment.priority}
                            </Badge>
                            <span>{payment.invoice_number}</span>
                            <span className="text-muted-foreground">-</span>
                            <span className="text-muted-foreground">{payment.entity_name}</span>
                          </div>
                          <span className="font-medium">{formatCurrency(payment.amount)}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        ) : (
          <div className="text-center py-8 text-muted-foreground">
            <Calendar className="h-12 w-12 mx-auto mb-4 opacity-20" />
            <p>Keine geplanten Zahlungen im Zeitraum</p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
