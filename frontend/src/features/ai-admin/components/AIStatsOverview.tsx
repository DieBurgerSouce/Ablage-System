/**
 * AI Stats Overview
 *
 * Statistik-Dashboard fuer KI-Performance.
 */

import { useState } from 'react';
import { BarChart3, TrendingUp, CheckCircle, Loader2, Calendar } from 'lucide-react';

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Progress } from '@/components/ui/progress';

import { useAccuracyStats, useLearningProgress } from '../hooks/useAIAdmin';
import type { DecisionType } from '../types';

// =============================================================================
// Decision Type Labels
// =============================================================================

const DECISION_TYPE_LABELS: Record<DecisionType, string> = {
  document_classification: 'Dokumenten-Klassifizierung',
  entity_linking: 'Entitäts-Verknüpfung',
  invoice_matching: 'Rechnungs-Matching',
  payment_matching: 'Zahlungs-Matching',
  ocr_correction: 'OCR-Korrektur',
  anomaly_detection: 'Anomalie-Erkennung',
  duplicate_detection: 'Duplikat-Erkennung',
  auto_categorization: 'Auto-Kategorisierung',
};

// =============================================================================
// Period Selector
// =============================================================================

interface PeriodSelectorProps {
  value: number;
  onChange: (value: number) => void;
}

function PeriodSelector({ value, onChange }: PeriodSelectorProps) {
  return (
    <div className="flex items-center gap-2">
      <Calendar className="h-4 w-4 text-muted-foreground" />
      <Select value={value.toString()} onValueChange={(v) => onChange(Number(v))}>
        <SelectTrigger className="w-[180px]">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="7">Letzte 7 Tage</SelectItem>
          <SelectItem value="30">Letzte 30 Tage</SelectItem>
          <SelectItem value="90">Letzte 90 Tage</SelectItem>
        </SelectContent>
      </Select>
    </div>
  );
}

// =============================================================================
// Stats Card Component
// =============================================================================

interface StatsCardProps {
  decisionType: DecisionType;
  stats: {
    total_decisions: number;
    auto_applied: number;
    reviewed: number;
    approved: number;
    corrected: number;
    rejected: number;
    accuracy_rate: number;
    correction_rate: number;
    avg_confidence: number;
  };
}

function StatsCard({ decisionType, stats }: StatsCardProps) {
  const label = DECISION_TYPE_LABELS[decisionType];
  const autoApplyRate = stats.total_decisions > 0
    ? (stats.auto_applied / stats.total_decisions) * 100
    : 0;

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">{label}</CardTitle>
        <CardDescription>
          {stats.total_decisions} Entscheidungen insgesamt
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Accuracy Badge */}
        <div className="flex items-center justify-between">
          <span className="text-sm text-muted-foreground">Genauigkeit</span>
          <Badge
            variant={
              stats.accuracy_rate >= 0.9
                ? 'default'
                : stats.accuracy_rate >= 0.7
                  ? 'secondary'
                  : 'destructive'
            }
          >
            {(stats.accuracy_rate * 100).toFixed(1)}%
          </Badge>
        </div>

        {/* Auto-Apply Progress */}
        <div className="space-y-2">
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">Automatisch angewendet</span>
            <span className="font-semibold">{stats.auto_applied}</span>
          </div>
          <Progress value={autoApplyRate} className="h-2" />
        </div>

        {/* Review Stats */}
        <div className="grid grid-cols-3 gap-2 text-xs">
          <div className="space-y-1">
            <p className="text-muted-foreground">Genehmigt</p>
            <p className="font-semibold text-green-600">{stats.approved}</p>
          </div>
          <div className="space-y-1">
            <p className="text-muted-foreground">Korrigiert</p>
            <p className="font-semibold text-yellow-600">{stats.corrected}</p>
          </div>
          <div className="space-y-1">
            <p className="text-muted-foreground">Abgelehnt</p>
            <p className="font-semibold text-red-600">{stats.rejected}</p>
          </div>
        </div>

        {/* Avg Confidence */}
        <div className="flex items-center justify-between pt-2 border-t">
          <span className="text-sm text-muted-foreground">Ø Konfidenz</span>
          <span className="text-sm font-semibold">
            {(stats.avg_confidence * 100).toFixed(1)}%
          </span>
        </div>
      </CardContent>
    </Card>
  );
}

// =============================================================================
// Main Component
// =============================================================================

export function AIStatsOverview() {
  const [days, setDays] = useState(30);
  const { data: stats, isLoading: statsLoading } = useAccuracyStats(days);
  const { data: learningProgress, isLoading: progressLoading } = useLearningProgress(days);

  const isLoading = statsLoading || progressLoading;

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  const totalDecisions = stats?.reduce((sum, s) => sum + s.total_decisions, 0) || 0;
  const totalAutoApplied = stats?.reduce((sum, s) => sum + s.auto_applied, 0) || 0;
  const avgAccuracy = stats && stats.length > 0
    ? stats.reduce((sum, s) => sum + s.accuracy_rate, 0) / stats.length
    : 0;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold flex items-center gap-2">
            <BarChart3 className="h-5 w-5" />
            KI-Performance Statistiken
          </h3>
          <p className="text-sm text-muted-foreground">
            Übersicht über Genauigkeit und Automatisierung
          </p>
        </div>
        <PeriodSelector value={days} onChange={setDays} />
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card>
          <CardHeader className="pb-3">
            <CardDescription>Gesamt-Entscheidungen</CardDescription>
            <CardTitle className="text-3xl">{totalDecisions}</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <TrendingUp className="h-4 w-4" />
              <span>Letzte {days} Tage</span>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <CardDescription>Automatisch angewendet</CardDescription>
            <CardTitle className="text-3xl">{totalAutoApplied}</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <CheckCircle className="h-4 w-4" />
              <span>
                {totalDecisions > 0
                  ? ((totalAutoApplied / totalDecisions) * 100).toFixed(1)
                  : 0}
                % der Entscheidungen
              </span>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <CardDescription>Durchschnittliche Genauigkeit</CardDescription>
            <CardTitle className="text-3xl">{(avgAccuracy * 100).toFixed(1)}%</CardTitle>
          </CardHeader>
          <CardContent>
            <Badge
              variant={avgAccuracy >= 0.9 ? 'default' : avgAccuracy >= 0.7 ? 'secondary' : 'destructive'}
            >
              {avgAccuracy >= 0.9 ? 'Ausgezeichnet' : avgAccuracy >= 0.7 ? 'Gut' : 'Verbesserungsbedarf'}
            </Badge>
          </CardContent>
        </Card>
      </div>

      {/* Learning Progress Summary */}
      {learningProgress && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Lern-Fortschritt</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <p className="text-muted-foreground">Verbesserungsrate</p>
                <p className="text-2xl font-bold text-green-600">
                  {learningProgress.improvement_rate
                    ? `+${(learningProgress.improvement_rate * 100).toFixed(1)}%`
                    : 'N/A'}
                </p>
              </div>
              <div>
                <p className="text-muted-foreground">Kürzliche Korrekturen</p>
                <p className="text-2xl font-bold">{learningProgress.recent_corrections || 0}</p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Detail Stats per Decision Type */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {stats?.map((stat) => (
          <StatsCard
            key={stat.decision_type}
            decisionType={stat.decision_type as DecisionType}
            stats={stat}
          />
        ))}
      </div>
    </div>
  );
}
