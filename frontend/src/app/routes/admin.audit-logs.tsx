/**
 * Admin Audit Logs Route
 *
 * Enterprise Audit-Log Viewer für Administratoren.
 * Zeigt alle System-Aktivitäten mit Filter- und Export-Funktionen.
 */

import { createFileRoute } from '@tanstack/react-router';
import { Shield, BarChart3, Clock, Users, CheckCircle, XCircle } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { AuditLogTable, useAuditStats } from '@/features/admin/audit';

export const Route = createFileRoute('/admin/audit-logs')({
  component: AdminAuditLogsPage,
});

// ==================== Stats Cards ====================

function StatsCards() {
  const { data: stats, isLoading, error } = useAuditStats(30);

  if (error) {
    return null; // Silently fail - table is the main content
  }

  if (isLoading) {
    return (
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Card key={i}>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <Skeleton className="h-4 w-24" />
              <Skeleton className="h-4 w-4" />
            </CardHeader>
            <CardContent>
              <Skeleton className="h-7 w-16" />
              <Skeleton className="h-3 w-32 mt-1" />
            </CardContent>
          </Card>
        ))}
      </div>
    );
  }

  if (!stats) return null;

  const cards = [
    {
      title: 'Gesamtaktionen',
      value: stats.total_actions.toLocaleString('de-DE'),
      description: `In den letzten ${stats.period_days} Tagen`,
      icon: BarChart3,
    },
    {
      title: 'Aktive Benutzer',
      value: stats.unique_users.toLocaleString('de-DE'),
      description: 'Eindeutige Benutzer',
      icon: Users,
    },
    {
      title: 'Erfolgsrate',
      value: `${stats.success_rate.toFixed(1)}%`,
      description: `${stats.error_count} Fehler`,
      icon: CheckCircle,
      valueColor: stats.success_rate >= 95 ? 'text-green-600' : stats.success_rate >= 80 ? 'text-yellow-600' : 'text-red-600',
    },
    {
      title: 'Fehler',
      value: stats.error_count.toLocaleString('de-DE'),
      description: 'Fehlgeschlagene Aktionen',
      icon: XCircle,
      valueColor: stats.error_count === 0 ? 'text-green-600' : 'text-red-600',
    },
  ];

  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
      {cards.map((card) => (
        <Card key={card.title}>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">{card.title}</CardTitle>
            <card.icon className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className={`text-2xl font-bold ${card.valueColor ?? ''}`}>
              {card.value}
            </div>
            <p className="text-xs text-muted-foreground">{card.description}</p>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

// ==================== Top Actions ====================

function TopActions() {
  const { data: stats, isLoading } = useAuditStats(30);

  if (isLoading || !stats) return null;

  const topActions = Object.entries(stats.actions_by_type)
    .sort(([, a], [, b]) => b - a)
    .slice(0, 5);

  if (topActions.length === 0) return null;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm font-medium">Häufigste Aktionen</CardTitle>
        <CardDescription>Top 5 in den letzten 30 Tagen</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          {topActions.map(([action, count]) => {
            const percentage = (count / stats.total_actions) * 100;
            return (
              <div key={action} className="space-y-1">
                <div className="flex justify-between text-sm">
                  <span className="font-mono text-muted-foreground">
                    {action.replace(/_/g, ' ')}
                  </span>
                  <span className="font-medium">{count.toLocaleString('de-DE')}</span>
                </div>
                <div className="h-2 bg-muted rounded-full overflow-hidden">
                  <div
                    className="h-full bg-primary rounded-full transition-all"
                    style={{ width: `${Math.min(percentage, 100)}%` }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}

// ==================== Active Users ====================

function ActiveUsers() {
  const { data: stats, isLoading } = useAuditStats(30);

  if (isLoading || !stats) return null;

  const topUsers = stats.actions_by_user.slice(0, 5);

  if (topUsers.length === 0) return null;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm font-medium">Aktivste Benutzer</CardTitle>
        <CardDescription>Top 5 in den letzten 30 Tagen</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          {topUsers.map((user) => {
            const percentage = (user.count / stats.total_actions) * 100;
            return (
              <div key={user.user_email} className="space-y-1">
                <div className="flex justify-between text-sm">
                  <span className="truncate max-w-[180px]">{user.user_email}</span>
                  <span className="font-medium">{user.count.toLocaleString('de-DE')}</span>
                </div>
                <div className="h-2 bg-muted rounded-full overflow-hidden">
                  <div
                    className="h-full bg-primary rounded-full transition-all"
                    style={{ width: `${Math.min(percentage * 2, 100)}%` }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}

// ==================== Main Page ====================

function AdminAuditLogsPage() {
  return (
    <div className="p-8 space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Shield className="h-8 w-8 text-primary" />
        <div>
          <h1 className="text-3xl font-bold">Audit-Protokoll</h1>
          <p className="text-muted-foreground">
            Vollständige Übersicht aller System-Aktivitäten mit Filter- und Export-Funktionen.
          </p>
        </div>
      </div>

      {/* Stats */}
      <StatsCards />

      {/* Charts Row */}
      <div className="grid gap-4 md:grid-cols-2">
        <TopActions />
        <ActiveUsers />
      </div>

      {/* Main Table */}
      <AuditLogTable maxItems={50} />
    </div>
  );
}
