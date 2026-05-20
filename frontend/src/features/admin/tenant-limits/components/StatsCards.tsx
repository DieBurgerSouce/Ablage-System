/**
 * Stats Cards Component
 *
 * Zeigt wichtige Kennzahlen als Karten-Grid.
 */

import { Card, CardContent } from '@/components/ui/card';
import {
  Activity,
  AlertCircle,
  Clock,
  FileText,
  TrendingDown,
  TrendingUp,
  Users,
} from 'lucide-react';
import type { UsageSummaryResponse } from '../hooks/use-tenant-limits';

interface StatsCardsProps {
  usage: UsageSummaryResponse;
}

export function StatsCards({ usage }: StatsCardsProps) {
  const rateLimitPercent = usage.rate_limit_percentage;
  const isHighRateLimit = rateLimitPercent > 5;

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
      {/* Gesamtanfragen */}
      <StatCard
        title="Gesamtanfragen"
        value={formatNumber(usage.total_requests)}
        icon={<Activity className="h-4 w-4" />}
        description={`${usage.data_points} Datenpunkte`}
        trend={null}
      />

      {/* Rate-Limited */}
      <StatCard
        title="Rate-Limited"
        value={`${rateLimitPercent.toFixed(1)}%`}
        icon={<AlertCircle className="h-4 w-4" />}
        description={`${formatNumber(usage.rate_limited_requests)} Anfragen`}
        variant={isHighRateLimit ? 'destructive' : 'default'}
        trend={isHighRateLimit ? 'up' : 'down'}
      />

      {/* Durchschnittliche Antwortzeit */}
      <StatCard
        title="Ø Antwortzeit"
        value={usage.avg_response_time_ms ? `${Math.round(usage.avg_response_time_ms)}ms` : '-'}
        icon={<Clock className="h-4 w-4" />}
        description="Durchschnitt"
        trend={null}
      />

      {/* Verarbeitete Dokumente */}
      <StatCard
        title="Dokumente"
        value={formatNumber(usage.documents_processed)}
        icon={<FileText className="h-4 w-4" />}
        description={`${formatNumber(usage.pages_processed)} Seiten`}
        trend={null}
      />

      {/* Aktive Benutzer */}
      <StatCard
        title="Aktive Benutzer"
        value={usage.active_users}
        icon={<Users className="h-4 w-4" />}
        description="im Zeitraum"
        trend={null}
      />

      {/* Speichernutzung */}
      <StatCard
        title="Speicher"
        value={formatBytes(usage.storage_used_bytes)}
        icon={<FileText className="h-4 w-4" />}
        description="belegt"
        trend={null}
      />
    </div>
  );
}

interface StatCardProps {
  title: string;
  value: string | number;
  icon: React.ReactNode;
  description: string;
  variant?: 'default' | 'destructive';
  trend: 'up' | 'down' | null;
}

function StatCard({ title, value, icon, description, variant = 'default', trend }: StatCardProps) {
  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-center justify-between">
          <span className="text-sm text-muted-foreground">{title}</span>
          <span className={variant === 'destructive' ? 'text-destructive' : 'text-muted-foreground'}>
            {icon}
          </span>
        </div>
        <div className="mt-2 flex items-baseline gap-2">
          <span className={`text-2xl font-bold ${variant === 'destructive' ? 'text-destructive' : ''}`}>
            {value}
          </span>
          {trend && (
            <span className={trend === 'up' ? 'text-destructive' : 'text-green-500'}>
              {trend === 'up' ? (
                <TrendingUp className="h-4 w-4" />
              ) : (
                <TrendingDown className="h-4 w-4" />
              )}
            </span>
          )}
        </div>
        <p className="text-xs text-muted-foreground mt-1">{description}</p>
      </CardContent>
    </Card>
  );
}

function formatNumber(num: number): string {
  if (num >= 1_000_000) return `${(num / 1_000_000).toFixed(1)}M`;
  if (num >= 1_000) return `${(num / 1_000).toFixed(1)}K`;
  return num.toString();
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`;
}
