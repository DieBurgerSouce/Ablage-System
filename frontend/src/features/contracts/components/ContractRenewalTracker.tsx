/**
 * ContractRenewalTracker - Anstehende Verlängerungen und Ablaufdaten
 *
 * Features:
 * - Farbcodierte Zeilen nach Dringlichkeit
 * - Sortierung nach Ablaufdatum
 * - Aktionsbuttons (Verlängern, Kündigen, Details)
 * - Filter nach Zeitraum
 */

import { useState, useMemo } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { RefreshCw, Clock, CheckCircle, Eye } from 'lucide-react';
import { format, parseISO } from 'date-fns';
import { de } from 'date-fns/locale';
import type { ContractRenewalItem } from '../api/contract-lifecycle-api';

interface ContractRenewalTrackerProps {
  renewals?: ContractRenewalItem[];
  isLoading: boolean;
  onViewContract?: (contractId: string) => void;
  onRenewContract?: (contractId: string) => void;
  onTerminateContract?: (contractId: string) => void;
}

const formatCurrency = (value: number): string =>
  new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency: 'EUR',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);

const formatDate = (dateStr: string): string => {
  try {
    return format(parseISO(dateStr), 'dd.MM.yyyy', { locale: de });
  } catch {
    return dateStr;
  }
};

type UrgencyLevel = 'critical' | 'warning' | 'caution' | 'ok';

function getUrgencyLevel(daysUntilExpiry: number): UrgencyLevel {
  if (daysUntilExpiry < 30) return 'critical';
  if (daysUntilExpiry < 60) return 'warning';
  if (daysUntilExpiry < 90) return 'caution';
  return 'ok';
}

const urgencyConfig: Record<UrgencyLevel, {
  rowClass: string;
  badgeVariant: 'destructive' | 'default' | 'secondary' | 'outline';
  label: string;
}> = {
  critical: {
    rowClass: 'bg-red-50 border-l-4 border-l-red-500',
    badgeVariant: 'destructive',
    label: 'Kritisch',
  },
  warning: {
    rowClass: 'bg-orange-50 border-l-4 border-l-orange-500',
    badgeVariant: 'default',
    label: 'Warnung',
  },
  caution: {
    rowClass: 'bg-yellow-50 border-l-4 border-l-yellow-400',
    badgeVariant: 'secondary',
    label: 'Bald fällig',
  },
  ok: {
    rowClass: 'bg-green-50 border-l-4 border-l-green-400',
    badgeVariant: 'outline',
    label: 'Im Plan',
  },
};

type TimeRange = '30' | '60' | '90' | '180' | 'all';

export function ContractRenewalTracker({
  renewals,
  isLoading,
  onViewContract,
  onRenewContract,
  onTerminateContract,
}: ContractRenewalTrackerProps) {
  const [timeRange, setTimeRange] = useState<TimeRange>('90');

  const filteredRenewals = useMemo(() => {
    if (!renewals) return [];
    const maxDays = timeRange === 'all' ? Infinity : parseInt(timeRange, 10);
    return renewals
      .filter((r) => r.days_until_expiry <= maxDays)
      .sort((a, b) => a.days_until_expiry - b.days_until_expiry);
  }, [renewals, timeRange]);

  const stats = useMemo(() => {
    if (!filteredRenewals.length) return { critical: 0, actionRequired: 0, total: 0 };
    return {
      critical: filteredRenewals.filter((r) => r.days_until_expiry < 30).length,
      actionRequired: filteredRenewals.filter((r) => r.action_required).length,
      total: filteredRenewals.length,
    };
  }, [filteredRenewals]);

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-medium">Verlängerungstracker</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-16 w-full" />
            ))}
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <Clock className="h-4 w-4" />
              Verlängerungstracker
            </CardTitle>
            <CardDescription className="mt-1">
              {stats.critical > 0 && (
                <span className="text-red-600 font-medium">{stats.critical} kritisch</span>
              )}
              {stats.critical > 0 && stats.actionRequired > 0 && ' · '}
              {stats.actionRequired > 0 && (
                <span className="text-orange-600 font-medium">
                  {stats.actionRequired} Entscheidung nötig
                </span>
              )}
              {stats.critical === 0 && stats.actionRequired === 0 && (
                <span className="text-green-600">Keine dringenden Verlängerungen</span>
              )}
            </CardDescription>
          </div>
          <Select value={timeRange} onValueChange={(v) => setTimeRange(v as TimeRange)}>
            <SelectTrigger className="w-40">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="30">30 Tage</SelectItem>
              <SelectItem value="60">60 Tage</SelectItem>
              <SelectItem value="90">90 Tage</SelectItem>
              <SelectItem value="180">180 Tage</SelectItem>
              <SelectItem value="all">Alle</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </CardHeader>
      <CardContent>
        {filteredRenewals.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            <CheckCircle className="h-8 w-8 mx-auto mb-2 opacity-50" />
            Keine Verlängerungen im gewählten Zeitraum
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-muted-foreground">
                  <th className="text-left py-2 pr-3 font-medium">Vertrag</th>
                  <th className="text-left py-2 px-3 font-medium">Partner</th>
                  <th className="text-left py-2 px-3 font-medium">Ablaufdatum</th>
                  <th className="text-left py-2 px-3 font-medium">Kündigungsfrist</th>
                  <th className="text-right py-2 px-3 font-medium">Jahreskosten</th>
                  <th className="text-center py-2 px-3 font-medium">Status</th>
                  <th className="text-right py-2 pl-3 font-medium">Aktion</th>
                </tr>
              </thead>
              <tbody>
                {filteredRenewals.map((renewal) => {
                  const urgency = getUrgencyLevel(renewal.days_until_expiry);
                  const config = urgencyConfig[urgency];

                  return (
                    <tr
                      key={renewal.contract_id}
                      className={`${config.rowClass} border-b last:border-0 hover:opacity-90 transition-opacity`}
                    >
                      <td className="py-3 pr-3">
                        <div className="font-medium">{renewal.contract_name}</div>
                        <div className="text-xs text-muted-foreground">
                          {renewal.days_until_expiry} Tage verbleibend
                        </div>
                      </td>
                      <td className="py-3 px-3">{renewal.partner_name}</td>
                      <td className="py-3 px-3 tabular-nums">
                        {formatDate(renewal.expires_at)}
                      </td>
                      <td className="py-3 px-3 tabular-nums">
                        {renewal.notice_deadline ? formatDate(renewal.notice_deadline) : '–'}
                      </td>
                      <td className="py-3 px-3 text-right tabular-nums">
                        {formatCurrency(renewal.annual_cost)}
                      </td>
                      <td className="py-3 px-3 text-center">
                        <div className="flex flex-col items-center gap-1">
                          <Badge variant={config.badgeVariant}>
                            {config.label}
                          </Badge>
                          {renewal.auto_renewal && (
                            <span className="text-xs text-muted-foreground flex items-center gap-1">
                              <RefreshCw className="h-3 w-3" />
                              Auto
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="py-3 pl-3">
                        <div className="flex justify-end gap-1">
                          {onRenewContract && (
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => onRenewContract(renewal.contract_id)}
                            >
                              Verlängern
                            </Button>
                          )}
                          {onTerminateContract && (
                            <Button
                              variant="outline"
                              size="sm"
                              className="text-orange-600 hover:text-orange-700"
                              onClick={() => onTerminateContract(renewal.contract_id)}
                            >
                              Kündigen
                            </Button>
                          )}
                          {onViewContract && (
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => onViewContract(renewal.contract_id)}
                            >
                              <Eye className="h-4 w-4" />
                            </Button>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
