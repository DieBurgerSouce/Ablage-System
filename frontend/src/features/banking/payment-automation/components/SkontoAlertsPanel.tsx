/**
 * Skonto Alerts Panel
 *
 * Zeigt Warnungen für bald ablaufende Skonto-Fristen.
 */

import {
  AlertTriangle,
  Banknote,
  Clock,
  ChevronRight,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { useSkontoAlerts, type SkontoAlert } from '../hooks/usePaymentAutomation';

function formatCurrency(amount: number): string {
  return amount.toLocaleString('de-DE', { style: 'currency', currency: 'EUR' });
}

function formatDate(dateString: string | null): string {
  if (!dateString) return '-';
  return new Date(dateString).toLocaleDateString('de-DE');
}

function AlertItem({ alert }: { alert: SkontoAlert }) {
  const urgencyConfig = {
    critical: {
      bgColor: 'bg-red-50 dark:bg-red-950',
      borderColor: 'border-red-200 dark:border-red-800',
      textColor: 'text-red-600',
      icon: AlertTriangle,
    },
    warning: {
      bgColor: 'bg-amber-50 dark:bg-amber-950',
      borderColor: 'border-amber-200 dark:border-amber-800',
      textColor: 'text-amber-600',
      icon: Clock,
    },
    info: {
      bgColor: 'bg-blue-50 dark:bg-blue-950',
      borderColor: 'border-blue-200 dark:border-blue-800',
      textColor: 'text-blue-600',
      icon: Banknote,
    },
  };

  const config = urgencyConfig[alert.urgency];
  const Icon = config.icon;

  return (
    <div className={`p-4 rounded-lg border ${config.bgColor} ${config.borderColor}`}>
      <div className="flex items-start justify-between">
        <div className="flex items-start gap-3">
          <Icon className={`h-5 w-5 mt-0.5 ${config.textColor}`} />
          <div>
            <div className="flex items-center gap-2">
              <p className="font-medium">{alert.invoice_number || 'Rechnung'}</p>
              <Badge variant="outline" className={`text-xs ${config.textColor}`}>
                {alert.days_remaining === 0
                  ? 'Heute!'
                  : alert.days_remaining === 1
                    ? 'Morgen'
                    : `${alert.days_remaining} Tage`}
              </Badge>
            </div>
            <p className="text-sm text-muted-foreground mt-1">
              {formatCurrency(alert.amount)} - {alert.skonto_percentage}% Skonto
            </p>
            <p className="text-sm mt-1">{alert.message}</p>
          </div>
        </div>
        <div className="text-right">
          <p className="text-lg font-bold text-green-600">
            {formatCurrency(alert.potential_savings)}
          </p>
          <p className="text-xs text-muted-foreground">Ersparnis</p>
        </div>
      </div>
    </div>
  );
}

export function SkontoAlertsPanel() {
  const { data: alerts, isLoading } = useSkontoAlerts(14);

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <Skeleton className="h-6 w-40" />
          <Skeleton className="h-4 w-56 mt-2" />
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-24 w-full" />
            ))}
          </div>
        </CardContent>
      </Card>
    );
  }

  const criticalAlerts = alerts?.filter((a) => a.urgency === 'critical') || [];
  const warningAlerts = alerts?.filter((a) => a.urgency === 'warning') || [];
  const infoAlerts = alerts?.filter((a) => a.urgency === 'info') || [];

  const totalPotentialSavings = alerts?.reduce((sum, a) => sum + a.potential_savings, 0) || 0;

  return (
    <Card className={criticalAlerts.length > 0 ? 'border-red-500' : warningAlerts.length > 0 ? 'border-amber-500' : ''}>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="flex items-center gap-2">
              <Banknote className="h-5 w-5" />
              Skonto-Alerts
              {alerts && alerts.length > 0 && (
                <Badge variant={criticalAlerts.length > 0 ? 'destructive' : 'secondary'}>
                  {alerts.length}
                </Badge>
              )}
            </CardTitle>
            <CardDescription>
              Ablaufende Skonto-Fristen in den nächsten 14 Tagen
            </CardDescription>
          </div>
          {totalPotentialSavings > 0 && (
            <div className="text-right">
              <p className="text-sm text-muted-foreground">Mögliche Ersparnis</p>
              <p className="text-xl font-bold text-green-600">
                {formatCurrency(totalPotentialSavings)}
              </p>
            </div>
          )}
        </div>
      </CardHeader>
      <CardContent>
        {alerts && alerts.length > 0 ? (
          <div className="space-y-6">
            {/* Critical Alerts */}
            {criticalAlerts.length > 0 && (
              <div className="space-y-3">
                <h4 className="text-sm font-medium text-red-600 flex items-center gap-2">
                  <AlertTriangle className="h-4 w-4" />
                  Kritisch ({criticalAlerts.length})
                </h4>
                {criticalAlerts.map((alert) => (
                  <AlertItem key={alert.invoice_id} alert={alert} />
                ))}
              </div>
            )}

            {/* Warning Alerts */}
            {warningAlerts.length > 0 && (
              <div className="space-y-3">
                <h4 className="text-sm font-medium text-amber-600 flex items-center gap-2">
                  <Clock className="h-4 w-4" />
                  Bald fällig ({warningAlerts.length})
                </h4>
                {warningAlerts.map((alert) => (
                  <AlertItem key={alert.invoice_id} alert={alert} />
                ))}
              </div>
            )}

            {/* Info Alerts */}
            {infoAlerts.length > 0 && (
              <div className="space-y-3">
                <h4 className="text-sm font-medium text-blue-600 flex items-center gap-2">
                  <Banknote className="h-4 w-4" />
                  Informativ ({infoAlerts.length})
                </h4>
                {infoAlerts.slice(0, 3).map((alert) => (
                  <AlertItem key={alert.invoice_id} alert={alert} />
                ))}
                {infoAlerts.length > 3 && (
                  <p className="text-sm text-muted-foreground text-center">
                    +{infoAlerts.length - 3} weitere
                  </p>
                )}
              </div>
            )}
          </div>
        ) : (
          <div className="text-center py-8 text-muted-foreground">
            <Banknote className="h-12 w-12 mx-auto mb-4 opacity-20" />
            <p>Keine Skonto-Alerts</p>
            <p className="text-sm mt-1">
              Alle Rechnungen mit Skonto wurden rechtzeitig bearbeitet
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
