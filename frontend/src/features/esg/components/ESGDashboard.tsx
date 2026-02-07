/**
 * ESG Dashboard
 *
 * Uebersicht ueber alle ESG-Kennzahlen und -Metriken.
 * Verbunden mit der ESG API via TanStack Query Hooks.
 */

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Leaf, Users, Award, Target, TrendingUp, TrendingDown, AlertCircle } from 'lucide-react';
import {
  useESGDashboard,
  useCarbonTrend,
  useExpiringCertifications,
} from '../hooks/use-esg-queries';

export function ESGDashboard() {
  const { data: dashboard, isLoading: dashboardLoading, error: dashboardError } = useESGDashboard();
  const { data: carbonTrend, isLoading: trendLoading } = useCarbonTrend(12);
  const { data: expiringCerts } = useExpiringCertifications(90);

  // Calculate year-over-year change from trend data
  const yoyChange = carbonTrend && carbonTrend.length >= 12
    ? ((carbonTrend[carbonTrend.length - 1]?.total_kg ?? 0) - (carbonTrend[0]?.total_kg ?? 0)) /
      Math.max(carbonTrend[0]?.total_kg ?? 1, 1) * 100
    : 0;

  if (dashboardError) {
    return (
      <Alert variant="destructive">
        <AlertCircle className="h-4 w-4" />
        <AlertDescription>
          Fehler beim Laden des ESG-Dashboards: {dashboardError.message}
        </AlertDescription>
      </Alert>
    );
  }

  return (
    <div className="space-y-6">
      {/* KPI Cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4" role="region" aria-label="ESG-Kennzahlen">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">CO2-Emissionen</CardTitle>
            <Leaf className="h-4 w-4 text-green-600" />
          </CardHeader>
          <CardContent>
            {dashboardLoading ? (
              <Skeleton className="h-8 w-24" />
            ) : (
              <div className="text-2xl font-bold">
                {formatTonnes(dashboard?.carbon_footprint?.total_co2_kg)}
              </div>
            )}
            <p className="text-xs text-muted-foreground flex items-center gap-1">
              {yoyChange < 0 ? (
                <>
                  <TrendingDown className="h-3 w-3 text-green-600" />
                  <span className="text-green-600">{yoyChange.toFixed(1)}%</span>
                </>
              ) : (
                <>
                  <TrendingUp className="h-3 w-3 text-red-600" />
                  <span className="text-red-600">+{yoyChange.toFixed(1)}%</span>
                </>
              )}{' '}
              zum Vorjahr
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Lieferanten-Score</CardTitle>
            <Users className="h-4 w-4 text-blue-600" />
          </CardHeader>
          <CardContent>
            {dashboardLoading ? (
              <Skeleton className="h-8 w-20" />
            ) : (
              <div className="text-2xl font-bold">
                {dashboard?.supplier_risk?.avg_score?.toFixed(0) ?? 0}/100
              </div>
            )}
            <p className="text-xs text-muted-foreground flex items-center gap-1">
              <TrendingUp className="h-3 w-3 text-green-600" />
              <span className="text-green-600">
                {dashboard?.supplier_risk?.total_suppliers ?? 0}
              </span>{' '}
              Lieferanten bewertet
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Zertifizierungen</CardTitle>
            <Award className="h-4 w-4 text-amber-600" />
          </CardHeader>
          <CardContent>
            {dashboardLoading ? (
              <Skeleton className="h-8 w-12" />
            ) : (
              <div className="text-2xl font-bold">
                {dashboard?.certifications?.active_count ?? 0}
              </div>
            )}
            <p className="text-xs text-muted-foreground">
              {dashboard?.certifications?.expiring_soon_count ?? expiringCerts?.length ?? 0} laufen in 90 Tagen ab
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Ziel-Erreichung</CardTitle>
            <Target className="h-4 w-4 text-purple-600" />
          </CardHeader>
          <CardContent>
            {dashboardLoading ? (
              <Skeleton className="h-8 w-16" />
            ) : (
              <div className="text-2xl font-bold">
                {dashboard?.goals?.avg_progress?.toFixed(0) ?? 0}%
              </div>
            )}
            <p className="text-xs text-muted-foreground">
              {dashboard?.goals?.on_track_count ?? 0} von {dashboard?.goals?.total_count ?? 0} Zielen auf Kurs
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Charts Section */}
      <div className="grid gap-6 md:grid-cols-2" role="region" aria-label="ESG-Diagramme">
        <Card>
          <CardHeader>
            <CardTitle>CO2-Entwicklung</CardTitle>
            <CardDescription>
              Monatliche CO2-Emissionen im Jahresverlauf
            </CardDescription>
          </CardHeader>
          <CardContent>
            {trendLoading ? (
              <Skeleton className="h-[300px] w-full" />
            ) : carbonTrend && carbonTrend.length > 0 ? (
              <div className="h-[300px]" role="img" aria-label="CO2-Emissionen Trend Chart">
                {/* Chart implementation - simplified bar representation */}
                <div className="flex items-end justify-between h-full gap-1 pb-8">
                  {carbonTrend.slice(-12).map((point, index) => {
                    const maxValue = Math.max(...carbonTrend.map(p => p.total_kg || 0));
                    const height = maxValue > 0 ? ((point.total_kg || 0) / maxValue) * 100 : 0;
                    return (
                      <div
                        key={index}
                        className="flex-1 bg-green-500 rounded-t transition-all hover:bg-green-600"
                        style={{ height: `${height}%` }}
                        title={`${point.month}: ${formatTonnes(point.total_kg)}`}
                      />
                    );
                  })}
                </div>
              </div>
            ) : (
              <div className="h-[300px] flex items-center justify-center text-muted-foreground">
                Keine Daten vorhanden
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>ESG-Score nach Kategorie</CardTitle>
            <CardDescription>
              Aufschlüsselung nach E, S und G
            </CardDescription>
          </CardHeader>
          <CardContent>
            {dashboardLoading ? (
              <Skeleton className="h-[300px] w-full" />
            ) : dashboard ? (
              <div className="h-[300px] flex flex-col justify-center gap-4" role="img" aria-label="ESG Kategorie Scores">
                {/* Using supplier risk score and goals progress as category indicators */}
                <div className="space-y-2">
                  <div className="flex justify-between text-sm">
                    <span className="font-medium">{getCategoryLabel('environmental')}</span>
                    <span>{dashboard.goals?.avg_progress?.toFixed(0) ?? 0}/100</span>
                  </div>
                  <div className="h-3 bg-muted rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all ${getCategoryColor('environmental')}`}
                      style={{ width: `${dashboard.goals?.avg_progress ?? 0}%` }}
                    />
                  </div>
                </div>
                <div className="space-y-2">
                  <div className="flex justify-between text-sm">
                    <span className="font-medium">{getCategoryLabel('social')}</span>
                    <span>{dashboard.supplier_risk?.avg_score?.toFixed(0) ?? 0}/100</span>
                  </div>
                  <div className="h-3 bg-muted rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all ${getCategoryColor('social')}`}
                      style={{ width: `${dashboard.supplier_risk?.avg_score ?? 0}%` }}
                    />
                  </div>
                </div>
                <div className="space-y-2">
                  <div className="flex justify-between text-sm">
                    <span className="font-medium">{getCategoryLabel('governance')}</span>
                    <span>{((dashboard.certifications?.active_count ?? 0) > 0 ? 75 : 25)}/100</span>
                  </div>
                  <div className="h-3 bg-muted rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all ${getCategoryColor('governance')}`}
                      style={{ width: `${(dashboard.certifications?.active_count ?? 0) > 0 ? 75 : 25}%` }}
                    />
                  </div>
                </div>
              </div>
            ) : (
              <div className="h-[300px] flex items-center justify-center text-muted-foreground">
                Keine Kategorie-Scores vorhanden
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Recent Activity */}
      <Card>
        <CardHeader>
          <CardTitle>Aktuelle Aktivitäten</CardTitle>
          <CardDescription>
            Letzte ESG-relevante Ereignisse
          </CardDescription>
        </CardHeader>
        <CardContent>
          {dashboardLoading ? (
            <div className="space-y-4">
              {[...Array(3)].map((_, i) => (
                <Skeleton key={i} className="h-12 w-full" />
              ))}
            </div>
          ) : dashboard?.recent_activities && dashboard.recent_activities.length > 0 ? (
            <div className="space-y-4">
              {dashboard.recent_activities.map((activity, index) => (
                <div key={index} className="flex items-center gap-4">
                  <div className={`h-8 w-8 rounded-full flex items-center justify-center ${getActivityBg(activity.type)}`}>
                    {getActivityIcon(activity.type)}
                  </div>
                  <div>
                    <p className="text-sm font-medium">{activity.title}</p>
                    <p className="text-xs text-muted-foreground">
                      {formatRelativeTime(activity.timestamp)}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-8 text-muted-foreground">
              Keine aktuellen Aktivitäten
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

// Helper functions
function formatTonnes(kg?: number): string {
  if (kg === undefined || kg === null) return '0 t';
  const tonnes = kg / 1000;
  return `${tonnes.toLocaleString('de-DE', { maximumFractionDigits: 1 })} t`;
}

function getCategoryLabel(category: string): string {
  const labels: Record<string, string> = {
    environmental: 'Umwelt (E)',
    social: 'Soziales (S)',
    governance: 'Unternehmensführung (G)',
  };
  return labels[category] || category;
}

function getCategoryColor(category: string): string {
  const colors: Record<string, string> = {
    environmental: 'bg-green-500',
    social: 'bg-blue-500',
    governance: 'bg-purple-500',
  };
  return colors[category] || 'bg-gray-500';
}

function getActivityBg(type: string): string {
  const bgs: Record<string, string> = {
    emission: 'bg-green-100',
    supplier: 'bg-blue-100',
    certification: 'bg-amber-100',
    report: 'bg-purple-100',
    goal: 'bg-indigo-100',
  };
  return bgs[type] || 'bg-gray-100';
}

function getActivityIcon(type: string): React.ReactNode {
  const icons: Record<string, React.ReactNode> = {
    emission: <Leaf className="h-4 w-4 text-green-600" />,
    supplier: <Users className="h-4 w-4 text-blue-600" />,
    certification: <Award className="h-4 w-4 text-amber-600" />,
    report: <Target className="h-4 w-4 text-purple-600" />,
    goal: <Target className="h-4 w-4 text-indigo-600" />,
  };
  return icons[type] || <Leaf className="h-4 w-4 text-gray-600" />;
}

function formatRelativeTime(timestamp: string): string {
  const date = new Date(timestamp);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffMins < 60) return `Vor ${diffMins} Minuten`;
  if (diffHours < 24) return `Vor ${diffHours} Stunden`;
  if (diffDays === 1) return 'Vor 1 Tag';
  return `Vor ${diffDays} Tagen`;
}
