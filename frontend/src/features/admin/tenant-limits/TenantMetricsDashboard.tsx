/**
 * Tenant Metrics Dashboard
 *
 * Hauptseite für die Anzeige von Tenant-spezifischen Metriken,
 * Rate Limits und Quota-Nutzung.
 */

import { useState } from 'react';
import { useParams } from '@tanstack/react-router';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Skeleton } from '@/components/ui/skeleton';
import { BarChart3, Settings, Shield, TrendingUp } from 'lucide-react';
import { useOwnLimits, useCompanyLimits, useUsageMetrics, useViolations } from './hooks/use-tenant-limits';
import { LimitsCard } from './components/LimitsCard';
import { UsageChart } from './components/UsageChart';
import { ViolationsTable } from './components/ViolationsTable';
import { StatsCards } from './components/StatsCards';

type PeriodType = 'hourly' | 'daily' | 'monthly';
type TimeRange = '7' | '30' | '90' | '365';

export function TenantMetricsDashboard() {
  const { companyId: urlCompanyId } = useParams({ strict: false }) as { companyId?: string };
  const [periodType, setPeriodType] = useState<PeriodType>('daily');
  const [timeRange, setTimeRange] = useState<TimeRange>('30');
  const [violationsHours, setViolationsHours] = useState<number>(24);

  // Hole eigene Limits falls keine companyId in URL
  const {
    data: ownLimits,
    isLoading: ownLimitsLoading,
    error: ownLimitsError,
  } = useOwnLimits();

  // Hole spezifische Company-Limits falls companyId in URL (Admin-Mode)
  const {
    data: companyLimits,
    isLoading: companyLimitsLoading,
    error: companyLimitsError,
  } = useCompanyLimits(urlCompanyId);

  // Nutze eigene Limits oder Company-Limits
  const limits = urlCompanyId ? companyLimits : ownLimits;
  const limitsLoading = urlCompanyId ? companyLimitsLoading : ownLimitsLoading;
  const limitsError = urlCompanyId ? companyLimitsError : ownLimitsError;

  // Company ID für Metriken (eigene oder aus URL)
  const effectiveCompanyId = urlCompanyId || ownLimits?.company_id;

  const {
    data: usage,
    isLoading: usageLoading,
  } = useUsageMetrics(effectiveCompanyId, periodType, parseInt(timeRange));

  const {
    data: violations,
    isLoading: violationsLoading,
  } = useViolations(effectiveCompanyId, violationsHours);

  if (limitsError) {
    return (
      <Alert variant="destructive">
        <AlertTitle>Fehler beim Laden</AlertTitle>
        <AlertDescription>
          Die Tenant-Metriken konnten nicht geladen werden.
          {limitsError instanceof Error ? ` ${limitsError.message}` : ''}
        </AlertDescription>
      </Alert>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Tenant-Metriken</h1>
          <p className="text-muted-foreground">
            Übersicht über Nutzung, Limits und Performance
          </p>
        </div>

        {/* Time Controls */}
        <div className="flex items-center gap-2">
          <Select value={periodType} onValueChange={(v) => setPeriodType(v as PeriodType)}>
            <SelectTrigger className="w-[130px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="hourly">Stündlich</SelectItem>
              <SelectItem value="daily">Täglich</SelectItem>
              <SelectItem value="monthly">Monatlich</SelectItem>
            </SelectContent>
          </Select>

          <Select value={timeRange} onValueChange={(v) => setTimeRange(v as TimeRange)}>
            <SelectTrigger className="w-[120px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="7">7 Tage</SelectItem>
              <SelectItem value="30">30 Tage</SelectItem>
              <SelectItem value="90">90 Tage</SelectItem>
              <SelectItem value="365">1 Jahr</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* Tabs */}
      <Tabs defaultValue="overview" className="space-y-4">
        <TabsList>
          <TabsTrigger value="overview" className="gap-2">
            <TrendingUp className="h-4 w-4" />
            Übersicht
          </TabsTrigger>
          <TabsTrigger value="usage" className="gap-2">
            <BarChart3 className="h-4 w-4" />
            Nutzung
          </TabsTrigger>
          <TabsTrigger value="security" className="gap-2">
            <Shield className="h-4 w-4" />
            Sicherheit
          </TabsTrigger>
          <TabsTrigger value="limits" className="gap-2">
            <Settings className="h-4 w-4" />
            Limits
          </TabsTrigger>
        </TabsList>

        {/* Overview Tab */}
        <TabsContent value="overview" className="space-y-6">
          {/* Stats Cards */}
          {usageLoading ? (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {Array.from({ length: 6 }).map((_, i) => (
                <Skeleton key={i} className="h-24" />
              ))}
            </div>
          ) : usage ? (
            <StatsCards usage={usage} />
          ) : null}

          {/* Chart + Limits Side by Side */}
          <div className="grid lg:grid-cols-3 gap-6">
            <div className="lg:col-span-2">
              {usageLoading ? (
                <Skeleton className="h-[380px]" />
              ) : usage ? (
                <UsageChart timeline={usage.timeline} periodType={periodType} />
              ) : null}
            </div>
            <div>
              {limitsLoading ? (
                <Skeleton className="h-[380px]" />
              ) : limits ? (
                <LimitsCard limits={limits} usage={usage} />
              ) : null}
            </div>
          </div>
        </TabsContent>

        {/* Usage Tab */}
        <TabsContent value="usage" className="space-y-6">
          {usage ? (
            <>
              <StatsCards usage={usage} />
              <UsageChart timeline={usage.timeline} periodType={periodType} />
            </>
          ) : (
            <Skeleton className="h-[400px]" />
          )}
        </TabsContent>

        {/* Security Tab */}
        <TabsContent value="security" className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold">Rate-Limit-Verletzungen</h2>
            <Select
              value={violationsHours.toString()}
              onValueChange={(v) => setViolationsHours(parseInt(v))}
            >
              <SelectTrigger className="w-[140px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="1">Letzte Stunde</SelectItem>
                <SelectItem value="6">6 Stunden</SelectItem>
                <SelectItem value="24">24 Stunden</SelectItem>
                <SelectItem value="48">48 Stunden</SelectItem>
                <SelectItem value="168">7 Tage</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <ViolationsTable violations={violations ?? []} isLoading={violationsLoading} />
        </TabsContent>

        {/* Limits Tab */}
        <TabsContent value="limits" className="space-y-6">
          {limitsLoading ? (
            <Skeleton className="h-[400px]" />
          ) : limits ? (
            <div className="grid md:grid-cols-2 gap-6">
              <LimitsCard limits={limits} usage={usage} />
              <CustomLimitsCard limits={limits} />
            </div>
          ) : null}
        </TabsContent>
      </Tabs>
    </div>
  );
}

/**
 * Card für Custom-Limits (Admin-only)
 */
function CustomLimitsCard({ limits }: { limits: { custom_limits: Array<{ id: string; endpoint_pattern: string; requests_per_minute: number; requests_per_hour: number; requests_per_day: number; burst_limit: number; is_custom: boolean }> } }) {
  if (limits.custom_limits.length === 0) {
    return (
      <div className="rounded-lg border bg-muted/50 p-6 flex flex-col items-center justify-center text-center">
        <Settings className="h-12 w-12 text-muted-foreground mb-4" />
        <h3 className="font-medium">Keine Custom-Limits</h3>
        <p className="text-sm text-muted-foreground mt-1">
          Alle Endpoints verwenden die Standard-Tier-Limits.
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-lg border p-4 space-y-4">
      <h3 className="font-medium">Custom-Limits</h3>
      <div className="space-y-3">
        {limits.custom_limits.map((limit) => (
          <div key={limit.id} className="rounded border p-3 text-sm">
            <div className="font-mono text-xs text-muted-foreground mb-2">
              {limit.endpoint_pattern}
            </div>
            <div className="grid grid-cols-4 gap-2 text-center">
              <div>
                <div className="font-medium">{limit.requests_per_minute}</div>
                <div className="text-xs text-muted-foreground">/min</div>
              </div>
              <div>
                <div className="font-medium">{limit.requests_per_hour}</div>
                <div className="text-xs text-muted-foreground">/h</div>
              </div>
              <div>
                <div className="font-medium">{limit.requests_per_day}</div>
                <div className="text-xs text-muted-foreground">/Tag</div>
              </div>
              <div>
                <div className="font-medium">{limit.burst_limit}</div>
                <div className="text-xs text-muted-foreground">Burst</div>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
