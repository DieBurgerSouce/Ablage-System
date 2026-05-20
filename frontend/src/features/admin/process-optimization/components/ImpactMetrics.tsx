/**
 * Impact Metrics Component
 *
 * Zeigt den ROI und die Auswirkungen der Automatisierungen.
 */

import { TrendingUp, Clock, DollarSign, Zap, Target } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { Skeleton } from '@/components/ui/skeleton';
import { useSuggestionStats, useProcessHealth, useMetricsSummary } from '../hooks/useProcessMining';

// Annahmen für ROI-Berechnung
const HOURLY_RATE = 50; // EUR pro Stunde
const WORKING_HOURS_PER_WEEK = 40;
const WEEKS_PER_YEAR = 50;

export function ImpactMetrics() {
  const { data: stats, isLoading: statsLoading } = useSuggestionStats();
  const { data: health, isLoading: healthLoading } = useProcessHealth(30);
  const { data: metrics, isLoading: metricsLoading } = useMetricsSummary(30);

  const isLoading = statsLoading || healthLoading || metricsLoading;

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <Skeleton className="h-6 w-48" />
          <Skeleton className="h-4 w-64 mt-1" />
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 gap-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-24" />
            ))}
          </div>
        </CardContent>
      </Card>
    );
  }

  // Berechnungen
  const realizedSavingsHours = stats?.realized_savings_hours || 0;
  const realizedSavingsCost = realizedSavingsHours * HOURLY_RATE;
  const pendingSavingsHours = Object.values(stats?.by_status || {}).reduce(
    (acc, { savings }) => acc + savings,
    0
  ) - realizedSavingsHours;
  const pendingSavingsCost = pendingSavingsHours * HOURLY_RATE;

  // Automatisierungsgrad-Verbesserung
  const automationRate = metrics?.automation_rate || 0;
  const automationTarget = 0.8; // 80% Ziel
  const automationProgress = (automationRate / automationTarget) * 100;

  // Zeit pro Woche gespart
  const weeklySavedHours = realizedSavingsHours / WEEKS_PER_YEAR;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <TrendingUp className="h-5 w-5" />
          Auswirkungen & ROI
        </CardTitle>
        <CardDescription>
          Realisierte und potenzielle Einsparungen durch Automatisierung
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 gap-4">
          {/* Realisierte Einsparungen */}
          <div className="p-4 bg-green-50 rounded-lg">
            <div className="flex items-center gap-2 text-green-700 mb-2">
              <DollarSign className="h-4 w-4" />
              <span className="text-sm font-medium">Realisierte Einsparungen</span>
            </div>
            <div className="text-2xl font-bold text-green-700">
              {realizedSavingsCost.toLocaleString('de-DE')} EUR
            </div>
            <div className="text-sm text-green-600">
              {realizedSavingsHours.toFixed(0)} Stunden/Jahr
            </div>
          </div>

          {/* Potenzielle Einsparungen */}
          <div className="p-4 bg-blue-50 rounded-lg">
            <div className="flex items-center gap-2 text-blue-700 mb-2">
              <Target className="h-4 w-4" />
              <span className="text-sm font-medium">Potenzielle Einsparungen</span>
            </div>
            <div className="text-2xl font-bold text-blue-700">
              {pendingSavingsCost.toLocaleString('de-DE')} EUR
            </div>
            <div className="text-sm text-blue-600">
              {pendingSavingsHours.toFixed(0)} Stunden/Jahr
            </div>
          </div>

          {/* Zeit pro Woche */}
          <div className="p-4 bg-purple-50 rounded-lg">
            <div className="flex items-center gap-2 text-purple-700 mb-2">
              <Clock className="h-4 w-4" />
              <span className="text-sm font-medium">Gespart pro Woche</span>
            </div>
            <div className="text-2xl font-bold text-purple-700">
              {weeklySavedHours.toFixed(1)}h
            </div>
            <div className="text-sm text-purple-600">
              {((weeklySavedHours / WORKING_HOURS_PER_WEEK) * 100).toFixed(1)}% der Arbeitszeit
            </div>
          </div>

          {/* Aktivierte Automatisierungen */}
          <div className="p-4 bg-orange-50 rounded-lg">
            <div className="flex items-center gap-2 text-orange-700 mb-2">
              <Zap className="h-4 w-4" />
              <span className="text-sm font-medium">Aktive Automatisierungen</span>
            </div>
            <div className="text-2xl font-bold text-orange-700">
              {stats?.total_activated || 0}
            </div>
            <div className="text-sm text-orange-600">
              {stats?.total_pending || 0} weitere verfügbar
            </div>
          </div>
        </div>

        {/* Automatisierungsfortschritt */}
        <div className="mt-6 p-4 bg-muted/50 rounded-lg">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-medium">Automatisierungsgrad</span>
            <span className="text-sm text-muted-foreground">
              {(automationRate * 100).toFixed(1)}% / {automationTarget * 100}% Ziel
            </span>
          </div>
          <Progress value={automationProgress} className="h-3" />
          <p className="text-xs text-muted-foreground mt-2">
            {automationProgress >= 100
              ? 'Ziel erreicht!'
              : `Noch ${((automationTarget - automationRate) * 100).toFixed(1)}% bis zum Ziel`}
          </p>
        </div>

        {/* Prozessgesundheit */}
        {health && (
          <div className="mt-4 p-4 border rounded-lg">
            <div className="flex items-center justify-between">
              <div>
                <div className="font-medium">Aktuelle Prozessgesundheit</div>
                <div className="text-sm text-muted-foreground">
                  Basierend auf den letzten {health.period_days} Tagen
                </div>
              </div>
              <div className="text-right">
                <div className="text-3xl font-bold">
                  {(health.health_score * 100).toFixed(0)}%
                </div>
                <div className="text-lg font-medium text-primary">
                  Note {health.health_grade}
                </div>
              </div>
            </div>
            <div className="grid grid-cols-3 gap-4 mt-4 text-sm">
              <div>
                <div className="text-muted-foreground">Bottleneck-Score</div>
                <div className="font-medium">
                  {((1 - health.components.bottleneck_score) * 100).toFixed(0)}% frei
                </div>
              </div>
              <div>
                <div className="text-muted-foreground">Erfolgsrate</div>
                <div className="font-medium">
                  {(health.components.success_rate * 100).toFixed(1)}%
                </div>
              </div>
              <div>
                <div className="text-muted-foreground">Automatisierung</div>
                <div className="font-medium">
                  {(health.components.automation_rate * 100).toFixed(1)}%
                </div>
              </div>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
