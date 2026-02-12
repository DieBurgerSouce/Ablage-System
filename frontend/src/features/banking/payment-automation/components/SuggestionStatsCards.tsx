/**
 * Suggestion Statistics Cards
 *
 * Übersichtskarten für Zahlungsvorschläge-Statistiken.
 */

import {
  Banknote,
  Clock,
  AlertTriangle,
  TrendingUp,
  Percent,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Badge } from '@/components/ui/badge';
import { useAutomationStatistics, useSkontoAlerts } from '../hooks/usePaymentAutomation';

export function SuggestionStatsCards() {
  const { data: stats, isLoading: statsLoading } = useAutomationStatistics(30);
  const { data: alerts, isLoading: alertsLoading } = useSkontoAlerts(7);

  const isLoading = statsLoading || alertsLoading;

  if (isLoading) {
    return (
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-32" />
        ))}
      </div>
    );
  }

  const criticalAlerts = alerts?.filter((a) => a.urgency === 'critical').length || 0;
  const warningAlerts = alerts?.filter((a) => a.urgency === 'warning').length || 0;
  const totalPotentialSavings = alerts?.reduce((sum, a) => sum + a.potential_savings, 0) || 0;

  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
      {/* Offene Rechnungen */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Offene Rechnungen</CardTitle>
          <Clock className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">{stats?.open_invoices || 0}</div>
          <div className="flex items-center gap-2 mt-2">
            {(stats?.overdue_invoices || 0) > 0 && (
              <Badge variant="destructive" className="text-xs">
                {stats?.overdue_invoices} überfällig
              </Badge>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Skonto-Alerts */}
      <Card className={criticalAlerts > 0 ? 'border-amber-500' : ''}>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Skonto-Alerts</CardTitle>
          <Banknote className={`h-4 w-4 ${criticalAlerts > 0 ? 'text-amber-500' : 'text-muted-foreground'}`} />
        </CardHeader>
        <CardContent>
          <div className={`text-2xl font-bold ${criticalAlerts > 0 ? 'text-amber-500' : ''}`}>
            {(alerts?.length || 0)}
          </div>
          <div className="flex items-center gap-2 mt-2">
            {criticalAlerts > 0 && (
              <Badge variant="destructive" className="text-xs">
                {criticalAlerts} kritisch
              </Badge>
            )}
            {warningAlerts > 0 && (
              <Badge variant="outline" className="text-xs text-amber-500 border-amber-500">
                {warningAlerts} bald
              </Badge>
            )}
          </div>
          <p className="text-xs text-muted-foreground mt-2">
            {totalPotentialSavings.toLocaleString('de-DE', { style: 'currency', currency: 'EUR' })} möglich
          </p>
        </CardContent>
      </Card>

      {/* Skonto-Nutzung */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Skonto-Nutzung</CardTitle>
          <Percent className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">
            {((stats?.skonto_usage_rate || 0) * 100).toFixed(0)}%
          </div>
          <div className="flex items-center gap-2 mt-2 text-xs text-muted-foreground">
            <span className="text-green-500">{stats?.skonto_used_count || 0} genutzt</span>
            <span>|</span>
            <span className="text-red-500">{stats?.skonto_missed_count || 0} verpasst</span>
          </div>
          <p className="text-xs text-muted-foreground mt-2">
            {(stats?.missed_savings || 0).toLocaleString('de-DE', { style: 'currency', currency: 'EUR' })} verpasst
          </p>
        </CardContent>
      </Card>

      {/* Ersparnisse */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Skonto-Ersparnis</CardTitle>
          <TrendingUp className="h-4 w-4 text-green-500" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold text-green-600">
            {(stats?.skonto_savings || 0).toLocaleString('de-DE', { style: 'currency', currency: 'EUR' })}
          </div>
          <p className="text-xs text-muted-foreground mt-2">
            letzte {stats?.period_days || 30} Tage
          </p>
          <p className="text-xs text-muted-foreground">
            {(stats?.invoices_paid || 0)} Rechnungen bezahlt
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
