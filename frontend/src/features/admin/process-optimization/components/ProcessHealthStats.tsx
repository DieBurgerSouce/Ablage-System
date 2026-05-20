/**
 * Process Health Stats Component
 *
 * Zeigt Gesundheits-Statistiken des Prozesses.
 */

import {
  Activity,
  TrendingUp,
  AlertTriangle,
  Zap,
  Clock,
  CheckCircle,
  Bot,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { useProcessHealth, useMetricsSummary } from '../hooks/useProcessMining';

interface StatCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  icon: React.ComponentType<{ className?: string }>;
  trend?: 'up' | 'down' | 'neutral';
  trendValue?: string;
  variant?: 'default' | 'success' | 'warning' | 'danger';
}

function StatCard({
  title,
  value,
  subtitle,
  icon: Icon,
  trend,
  trendValue,
  variant = 'default',
}: StatCardProps) {
  const variantStyles = {
    default: 'text-primary',
    success: 'text-green-500',
    warning: 'text-yellow-500',
    danger: 'text-red-500',
  };

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium">{title}</CardTitle>
        <Icon className={`h-4 w-4 ${variantStyles[variant]}`} />
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-bold">{value}</div>
        {subtitle && (
          <p className="text-xs text-muted-foreground">{subtitle}</p>
        )}
        {trend && trendValue && (
          <div className="flex items-center gap-1 mt-1">
            {trend === 'up' && (
              <TrendingUp className="h-3 w-3 text-green-500" />
            )}
            {trend === 'down' && (
              <TrendingUp className="h-3 w-3 text-red-500 transform rotate-180" />
            )}
            <span
              className={`text-xs ${
                trend === 'up' ? 'text-green-500' : trend === 'down' ? 'text-red-500' : ''
              }`}
            >
              {trendValue}
            </span>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export function ProcessHealthStats() {
  const { data: health, isLoading: healthLoading } = useProcessHealth(30);
  const { data: metrics, isLoading: metricsLoading } = useMetricsSummary(30);

  const isLoading = healthLoading || metricsLoading;

  if (isLoading) {
    return (
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Card key={i}>
            <CardHeader className="pb-2">
              <Skeleton className="h-4 w-24" />
            </CardHeader>
            <CardContent>
              <Skeleton className="h-8 w-16" />
              <Skeleton className="h-3 w-32 mt-2" />
            </CardContent>
          </Card>
        ))}
      </div>
    );
  }

  const gradeStyles: Record<string, string> = {
    A: 'bg-green-100 text-green-800',
    B: 'bg-blue-100 text-blue-800',
    C: 'bg-yellow-100 text-yellow-800',
    D: 'bg-orange-100 text-orange-800',
    F: 'bg-red-100 text-red-800',
  };

  const getVariantFromGrade = (grade: string): StatCardProps['variant'] => {
    if (grade === 'A' || grade === 'B') return 'success';
    if (grade === 'C') return 'warning';
    return 'danger';
  };

  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
      {/* Prozessgesundheit */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Prozessgesundheit</CardTitle>
          <Activity className="h-4 w-4 text-primary" />
        </CardHeader>
        <CardContent>
          <div className="flex items-center gap-2">
            <span className="text-2xl font-bold">
              {health ? `${(health.health_score * 100).toFixed(0)}%` : '-'}
            </span>
            {health && (
              <Badge className={gradeStyles[health.health_grade] || 'bg-gray-100'}>
                Note {health.health_grade}
              </Badge>
            )}
          </div>
          <p className="text-xs text-muted-foreground mt-1">
            {health?.bottleneck_count || 0} Engpässe erkannt
          </p>
        </CardContent>
      </Card>

      {/* Erfolgsrate */}
      <StatCard
        title="Erfolgsrate"
        value={metrics ? `${(metrics.success_rate * 100).toFixed(1)}%` : '-'}
        subtitle={`${metrics?.total_events || 0} Events analysiert`}
        icon={CheckCircle}
        variant={
          metrics && metrics.success_rate >= 0.95
            ? 'success'
            : metrics && metrics.success_rate >= 0.8
            ? 'warning'
            : 'danger'
        }
      />

      {/* Automatisierungsgrad */}
      <StatCard
        title="Automatisierungsgrad"
        value={metrics ? `${(metrics.automation_rate * 100).toFixed(1)}%` : '-'}
        subtitle={`${metrics?.automated_events || 0} automatisiert`}
        icon={Bot}
        variant={
          metrics && metrics.automation_rate >= 0.7
            ? 'success'
            : metrics && metrics.automation_rate >= 0.4
            ? 'warning'
            : 'default'
        }
      />

      {/* Durchschnittliche Dauer */}
      <StatCard
        title="Durchschnittliche Dauer"
        value={
          metrics
            ? metrics.avg_duration_ms > 60000
              ? `${(metrics.avg_duration_ms / 60000).toFixed(1)}m`
              : `${(metrics.avg_duration_ms / 1000).toFixed(1)}s`
            : '-'
        }
        subtitle={`${metrics?.unique_documents || 0} Dokumente verarbeitet`}
        icon={Clock}
        variant="default"
      />
    </div>
  );
}
