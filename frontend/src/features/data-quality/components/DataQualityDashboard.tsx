/**
 * Data Quality Dashboard - Datenqualitäts-Überwachung
 *
 * Zeigt Datenqualitätsprobleme und bietet One-Click-Fixes.
 * - Gesamtscore mit Trend
 * - Probleme nach Schweregrad gruppiert
 * - Historischer Trend
 * - Quick Actions für Cleanup
 */

import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Progress } from '@/components/ui/progress';
import {
  useDataQualityReport,
  useDataQualityTrend,
  useFixDataQualityIssue,
} from '../hooks/use-data-quality';
import {
  AlertTriangle,
  CheckCircle2,
  TrendingUp,
  TrendingDown,
  Minus,
  Activity,
  Sparkles,
  AlertCircle,
} from 'lucide-react';

export function DataQualityDashboard() {
  const [trendMonths] = useState(6);
  const { data: report, isLoading, error, isRefetching } = useDataQualityReport();
  const { data: trend, isLoading: trendLoading } = useDataQualityTrend(trendMonths);
  const fixMutation = useFixDataQualityIssue();

  if (isLoading) {
    return <DashboardSkeleton />;
  }

  if (error) {
    return (
      <Alert variant="destructive">
        <AlertTriangle className="h-4 w-4" />
        <AlertDescription>
          Fehler beim Laden der Datenqualität. Bitte versuchen Sie es später erneut.
        </AlertDescription>
      </Alert>
    );
  }

  if (!report) {
    return null;
  }

  const handleFix = (category: string, action: string) => {
    fixMutation.mutate({ category, action });
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-3xl font-bold tracking-tight font-display">
            Datenqualität
          </h2>
          <p className="text-muted-foreground mt-1">
            Überwachung und Bereinigung der Datenbankqualität
          </p>
        </div>
        {isRefetching && (
          <Badge variant="outline" className="animate-pulse">
            <Activity className="mr-2 h-3 w-3" />
            Aktualisierung...
          </Badge>
        )}
      </div>

      <div className="grid gap-6 md:grid-cols-3">
        {/* Overall Score Card */}
        <Card className="md:col-span-1">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Sparkles className="h-5 w-5" />
              Gesamtscore
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-sm text-muted-foreground">Qualitätsscore</span>
                <span className={`text-3xl font-bold ${getScoreColor(report.overall_score)}`}>
                  {report.overall_score}/100
                </span>
              </div>
              <Progress value={report.overall_score} className="h-3" />
            </div>

            {/* Trend Indicator */}
            <div className="flex items-center justify-between pt-2 border-t">
              <span className="text-sm text-muted-foreground">Trend</span>
              <div className="flex items-center gap-2">
                {getTrendIcon(report.trend)}
                <span className="text-sm font-medium capitalize">{getTrendLabel(report.trend)}</span>
              </div>
            </div>

            {/* Last Check */}
            <div className="pt-2 border-t text-xs text-muted-foreground">
              Letzte Prüfung: {new Date(report.last_check).toLocaleString('de-DE')}
            </div>
          </CardContent>
        </Card>

        {/* Trend Chart */}
        <Card className="md:col-span-2">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Activity className="h-5 w-5" />
              Qualitätsverlauf ({trendMonths} Monate)
            </CardTitle>
          </CardHeader>
          <CardContent>
            {trendLoading ? (
              <Skeleton className="h-48 w-full" />
            ) : trend ? (
              <div className="space-y-4">
                <div className="h-48 flex items-end justify-between gap-2">
                  {trend.trend_data.map((point, idx) => {
                    const height = `${point.score}%`;
                    const isLast = idx === trend.trend_data.length - 1;
                    return (
                      <div key={point.month} className="flex-1 flex flex-col items-center gap-2">
                        <div className="w-full flex flex-col items-center justify-end h-full">
                          <span className="text-xs font-medium mb-1">{point.score}</span>
                          <div
                            className={`w-full rounded-t ${
                              isLast ? 'bg-primary' : 'bg-muted'
                            }`}
                            style={{ height }}
                          />
                        </div>
                        <span className="text-xs text-muted-foreground">{point.month}</span>
                      </div>
                    );
                  })}
                </div>

                <div className="flex items-center justify-between pt-4 border-t">
                  <div>
                    <p className="text-sm text-muted-foreground">Durchschnittsscore</p>
                    <p className="text-lg font-semibold">{trend.average_score.toFixed(1)}/100</p>
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">Verbesserung</p>
                    <p className="text-lg font-semibold flex items-center gap-1">
                      {trend.improvement_percentage >= 0 ? (
                        <TrendingUp className="h-4 w-4 text-green-600" />
                      ) : (
                        <TrendingDown className="h-4 w-4 text-red-600" />
                      )}
                      {Math.abs(trend.improvement_percentage).toFixed(1)}%
                    </p>
                  </div>
                </div>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground text-center py-8">
                Keine Trenddaten verfügbar
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Issues List */}
      {report.issues.length > 0 ? (
        <div className="space-y-4">
          <h3 className="text-xl font-semibold">Gefundene Probleme</h3>

          {/* Group by Severity */}
          {['critical', 'high', 'medium', 'low'].map((severity) => {
            const issuesForSeverity = report.issues.filter((i) => i.severity === severity);
            if (issuesForSeverity.length === 0) return null;

            return (
              <Card key={severity}>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Badge variant={getSeverityVariant(severity as any)}>
                      {getSeverityLabel(severity)}
                    </Badge>
                    <span className="text-base">
                      {issuesForSeverity.length}{' '}
                      {issuesForSeverity.length === 1 ? 'Problem' : 'Probleme'}
                    </span>
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-4">
                    {issuesForSeverity.map((issue, idx) => (
                      <div
                        key={idx}
                        className="flex items-start justify-between gap-4 p-4 rounded-lg border"
                      >
                        <div className="flex-1 space-y-2">
                          <div className="flex items-start gap-2">
                            <AlertCircle className="h-5 w-5 text-muted-foreground mt-0.5 flex-shrink-0" />
                            <div className="space-y-1">
                              <h4 className="font-semibold">{issue.title}</h4>
                              <p className="text-sm text-muted-foreground">
                                {issue.description}
                              </p>
                              <Badge variant="outline">{issue.count} betroffene Einträge</Badge>
                            </div>
                          </div>
                        </div>
                        <Button
                          size="sm"
                          onClick={() => handleFix(issue.category, issue.action_endpoint)}
                          disabled={fixMutation.isPending}
                        >
                          {fixMutation.isPending ? 'Wird bereinigt...' : issue.action_label}
                        </Button>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      ) : (
        <Card>
          <CardContent className="text-center py-12">
            <CheckCircle2 className="h-16 w-16 text-green-600 mx-auto mb-4" />
            <h3 className="text-xl font-semibold mb-2">Perfekte Datenqualität!</h3>
            <p className="text-muted-foreground">
              Es wurden keine Qualitätsprobleme gefunden. Ihre Daten sind in hervorragendem Zustand.
            </p>
          </CardContent>
        </Card>
      )}

      {/* Quick Actions */}
      {report.issues.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Schnellaktionen</CardTitle>
            <CardDescription>
              Häufige Bereinigungsaktionen für bessere Datenqualität
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
              {report.issues.slice(0, 6).map((issue, idx) => (
                <Button
                  key={idx}
                  variant="outline"
                  className="justify-start"
                  onClick={() => handleFix(issue.category, issue.action_endpoint)}
                  disabled={fixMutation.isPending}
                >
                  <Sparkles className="mr-2 h-4 w-4" />
                  {issue.action_label}
                </Button>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

// ==================== Helper Functions ====================

function getScoreColor(score: number): string {
  if (score >= 80) return 'text-green-600';
  if (score >= 60) return 'text-yellow-600';
  return 'text-red-600';
}

function getTrendIcon(trend: string) {
  switch (trend) {
    case 'improving':
      return <TrendingUp className="h-4 w-4 text-green-600" />;
    case 'degrading':
      return <TrendingDown className="h-4 w-4 text-red-600" />;
    default:
      return <Minus className="h-4 w-4 text-gray-600" />;
  }
}

function getTrendLabel(trend: string): string {
  switch (trend) {
    case 'improving':
      return 'Verbessernd';
    case 'degrading':
      return 'Verschlechternd';
    default:
      return 'Stabil';
  }
}

function getSeverityVariant(
  severity: 'low' | 'medium' | 'high' | 'critical'
): 'default' | 'secondary' | 'destructive' | 'outline' {
  switch (severity) {
    case 'critical':
      return 'destructive';
    case 'high':
      return 'destructive';
    case 'medium':
      return 'secondary';
    default:
      return 'outline';
  }
}

function getSeverityLabel(severity: string): string {
  switch (severity) {
    case 'critical':
      return 'Kritisch';
    case 'high':
      return 'Hoch';
    case 'medium':
      return 'Mittel';
    case 'low':
      return 'Niedrig';
    default:
      return severity;
  }
}

function DashboardSkeleton() {
  return (
    <div className="space-y-6">
      <div>
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-4 w-96 mt-2" />
      </div>
      <div className="grid gap-6 md:grid-cols-3">
        <Card>
          <CardHeader>
            <Skeleton className="h-6 w-32" />
          </CardHeader>
          <CardContent>
            <Skeleton className="h-24 w-full" />
          </CardContent>
        </Card>
        <Card className="md:col-span-2">
          <CardHeader>
            <Skeleton className="h-6 w-48" />
          </CardHeader>
          <CardContent>
            <Skeleton className="h-48 w-full" />
          </CardContent>
        </Card>
      </div>
      <div className="space-y-4">
        {Array.from({ length: 3 }).map((_, i) => (
          <Card key={i}>
            <CardHeader>
              <Skeleton className="h-6 w-32" />
            </CardHeader>
            <CardContent>
              <Skeleton className="h-32 w-full" />
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
