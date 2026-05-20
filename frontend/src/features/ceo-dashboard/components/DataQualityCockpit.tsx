/**
 * Data Quality Cockpit Page
 *
 * Main data quality dashboard with score, issues, and trend.
 */

import { useState } from 'react';
import {
  useQualityReport,
  useQualityTrend,
  useFixQualityIssue,
} from '../hooks/useDataQuality';
import { QualityScoreGauge } from './QualityScoreGauge';
import { QualityIssueCard } from './QualityIssueCard';
import { QualityTrendChart } from './QualityTrendChart';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Loader2, RefreshCw } from 'lucide-react';
import type { QualityCategory } from '../types/data-quality-types';

export function DataQualityCockpit() {
  const [trendMonths, setTrendMonths] = useState(6);
  const [fixingCategory, setFixingCategory] = useState<QualityCategory | null>(
    null
  );

  const {
    data: report,
    isLoading: reportLoading,
    error: reportError,
    refetch: refetchReport,
  } = useQualityReport();

  const {
    data: trend,
    isLoading: trendLoading,
    error: trendError,
  } = useQualityTrend(trendMonths);

  const { mutate: fixIssue } = useFixQualityIssue();

  const handleFix = (category: QualityCategory) => {
    setFixingCategory(category);
    fixIssue(category, {
      onSettled: () => {
        setFixingCategory(null);
      },
    });
  };

  // Error state
  if (reportError || trendError) {
    return (
      <div className="container mx-auto p-6">
        <Card>
          <CardContent className="p-6">
            <div className="text-center text-red-600 dark:text-red-400">
              Fehler beim Laden des Datenqualität-Cockpits.{' '}
              <Button
                variant="link"
                onClick={() => refetchReport()}
                className="text-red-600 dark:text-red-400"
              >
                Erneut versuchen
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  // Loading state
  if (reportLoading || !report) {
    return (
      <div className="container mx-auto p-6">
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
          <span className="ml-3 text-muted-foreground">
            Datenqualität wird geladen...
          </span>
        </div>
      </div>
    );
  }

  return (
    <div className="container mx-auto p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">
            Datenqualität-Cockpit
          </h1>
          <p className="text-muted-foreground mt-1">
            Überwachen und verbessern Sie die Qualität Ihrer Daten
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => refetchReport()}
          className="gap-2"
        >
          <RefreshCw className="w-4 h-4" />
          Aktualisieren
        </Button>
      </div>

      {/* Top Row - Score and Trend */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Quality Score Gauge */}
        <QualityScoreGauge score={report.overallScore} />

        {/* Quality Trend Chart */}
        {trendLoading || !trend ? (
          <Card>
            <CardContent className="p-6">
              <div className="flex items-center justify-center h-[300px]">
                <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
                <span className="ml-3 text-muted-foreground">
                  Trend wird geladen...
                </span>
              </div>
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium">Zeitraum:</span>
              <Select
                value={trendMonths.toString()}
                onValueChange={(value) => setTrendMonths(parseInt(value))}
              >
                <SelectTrigger className="w-[180px]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="3">3 Monate</SelectItem>
                  <SelectItem value="6">6 Monate</SelectItem>
                  <SelectItem value="12">12 Monate</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <QualityTrendChart data={trend} />
          </div>
        )}
      </div>

      {/* Issues List */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-2xl font-bold tracking-tight">
            Qualitätsprobleme
          </h2>
          <div className="text-sm text-muted-foreground">
            {report.issues.length} Problem{report.issues.length !== 1 ? 'e' : ''}{' '}
            gefunden
          </div>
        </div>

        {report.issues.length > 0 ? (
          <div className="space-y-3">
            {report.issues
              .sort((a, b) => {
                // Sort by severity (critical first) then by count
                const severityOrder = {
                  critical: 0,
                  high: 1,
                  medium: 2,
                  low: 3,
                };
                const severityDiff =
                  severityOrder[a.severity] - severityOrder[b.severity];
                if (severityDiff !== 0) return severityDiff;
                return b.count - a.count;
              })
              .map((issue) => (
                <QualityIssueCard
                  key={issue.category}
                  issue={issue}
                  onFix={() => handleFix(issue.category)}
                  isFixing={fixingCategory === issue.category}
                />
              ))}
          </div>
        ) : (
          <Card>
            <CardContent className="p-12">
              <div className="text-center text-muted-foreground">
                <div className="text-4xl mb-4">🎉</div>
                <div className="text-lg font-semibold">
                  Keine Qualitätsprobleme gefunden!
                </div>
                <div className="text-sm mt-2">
                  Ihre Daten sind in einem ausgezeichneten Zustand.
                </div>
              </div>
            </CardContent>
          </Card>
        )}
      </div>

      {/* Footer */}
      <div className="text-xs text-muted-foreground text-center pt-4 border-t border-border">
        Letzte Aktualisierung:{' '}
        {report.calculatedAt.toLocaleString('de-DE', {
          day: '2-digit',
          month: '2-digit',
          year: 'numeric',
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit',
        })}
        {' • '}
        <span className="text-muted-foreground/70">
          {report.totalDocuments.toLocaleString('de-DE')} Dokumente analysiert
        </span>
      </div>
    </div>
  );
}
