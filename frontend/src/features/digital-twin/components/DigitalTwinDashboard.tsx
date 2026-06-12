/**
 * Digital Twin Dashboard - 360° Business Snapshot
 *
 * Zeigt einen umfassenden Überblick über das gesamte Unternehmen:
 * - Finanzielle Gesundheit
 * - Risiko-Übersicht
 * - Dokument-Pipeline
 * - Compliance-Status
 * - Wichtige Metriken
 * - Trends
 */

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import type {
  FinancialHealth,
  RiskOverview,
  DocumentPipeline,
  ComplianceStatus,
  KeyMetrics,
  Trends,
} from '../api/digital-twin-api';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { Skeleton } from '@/components/ui/skeleton';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { useDigitalTwinSnapshot } from '../hooks/use-digital-twin';
import {
  TrendingUp,
  TrendingDown,
  Minus,
  AlertTriangle,
  CheckCircle2,
  FileText,
  Users,
  Shield,
  Activity,
  DollarSign,
  Clock,
  Database,
} from 'lucide-react';

export function DigitalTwinDashboard() {
  const { data, isLoading, error, isRefetching } = useDigitalTwinSnapshot();

  if (isLoading) {
    return <DashboardSkeleton />;
  }

  if (error) {
    return (
      <Alert variant="destructive">
        <AlertTriangle className="h-4 w-4" />
        <AlertDescription>
          Fehler beim Laden des Digital Twin. Bitte versuchen Sie es später erneut.
        </AlertDescription>
      </Alert>
    );
  }

  if (!data) {
    return null;
  }

  return (
    <div className="space-y-6">
      {/* Header mit Aktualisierungs-Indikator */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-3xl font-bold tracking-tight font-display">Digital Twin</h2>
          <p className="text-muted-foreground mt-1">
            360° Echtzeit-Übersicht Ihres Unternehmens
          </p>
        </div>
        {isRefetching && (
          <Badge variant="outline" className="animate-pulse">
            <Activity className="mr-2 h-3 w-3" />
            Aktualisierung...
          </Badge>
        )}
      </div>

      {/* Dashboard Grid */}
      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
        <FinancialHealthCard data={data.financial_health} />
        <RiskOverviewCard data={data.risk_overview} />
        <DocumentPipelineCard data={data.document_pipeline} />
        <ComplianceStatusCard data={data.compliance_status} />
        <KeyMetricsCard data={data.key_metrics} />
        <TrendsCard data={data.trends} />
      </div>

      {/* Footer mit Zeitstempel */}
      <div className="text-center text-sm text-muted-foreground">
        Letzte Aktualisierung: {new Date(data.generated_at).toLocaleString('de-DE')}
      </div>
    </div>
  );
}

// ==================== Sub-Components ====================

function FinancialHealthCard({ data }: { data: FinancialHealth }) {
  const getScoreColor = (score: number) => {
    if (score >= 80) return 'text-green-600';
    if (score >= 60) return 'text-yellow-600';
    return 'text-red-600';
  };

  const getTrendIcon = (trend: string) => {
    switch (trend) {
      case 'up':
        return <TrendingUp className="h-4 w-4 text-green-600" />;
      case 'down':
        return <TrendingDown className="h-4 w-4 text-red-600" />;
      default:
        return <Minus className="h-4 w-4 text-gray-600" />;
    }
  };

  return (
    <Card data-tour="twin-financial">
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium">Finanzielle Gesundheit</CardTitle>
        <DollarSign className="h-4 w-4 text-muted-foreground" />
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Score Gauge */}
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-sm text-muted-foreground">Gesundheitsscore</span>
            <span className={`text-2xl font-bold ${getScoreColor(data.score)}`}>
              {data.score}/100
            </span>
          </div>
          <Progress value={data.score} className="h-2" />
        </div>

        {/* Cashflow */}
        <div className="flex items-center justify-between pt-2 border-t">
          <div>
            <p className="text-sm text-muted-foreground">Cashflow (Monat)</p>
            <p className="text-lg font-semibold">
              {new Intl.NumberFormat('de-DE', {
                style: 'currency',
                currency: 'EUR',
              }).format(data.cashflow.current_month)}
            </p>
          </div>
          <div className="flex items-center gap-1">
            {getTrendIcon(data.cashflow.trend)}
            <span className="text-sm font-medium">
              {Math.abs(data.cashflow.percentage_change).toFixed(1)}%
            </span>
          </div>
        </div>

        {/* Forderungen & Verbindlichkeiten */}
        <div className="space-y-2 pt-2 border-t">
          <div className="flex justify-between text-sm">
            <span className="text-muted-foreground">Forderungen</span>
            <span className="font-medium">
              {new Intl.NumberFormat('de-DE', {
                style: 'currency',
                currency: 'EUR',
                notation: 'compact',
              }).format(data.receivables.total)}
            </span>
          </div>
          {data.receivables.overdue > 0 && (
            <div className="flex justify-between text-sm text-orange-600">
              <span>Überfällig</span>
              <span className="font-medium">
                {new Intl.NumberFormat('de-DE', {
                  style: 'currency',
                  currency: 'EUR',
                  notation: 'compact',
                }).format(data.receivables.overdue)}
              </span>
            </div>
          )}
          <div className="flex justify-between text-sm">
            <span className="text-muted-foreground">Verbindlichkeiten</span>
            <span className="font-medium">
              {new Intl.NumberFormat('de-DE', {
                style: 'currency',
                currency: 'EUR',
                notation: 'compact',
              }).format(data.payables.total)}
            </span>
          </div>
        </div>

        {/* Liquiditätsrate */}
        <div className="pt-2 border-t">
          <div className="flex justify-between text-sm">
            <span className="text-muted-foreground">Liquiditätsrate</span>
            <span className="font-semibold">{data.liquidity_ratio.toFixed(2)}</span>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function RiskOverviewCard({ data }: { data: RiskOverview }) {
  const getScoreColor = (score: number) => {
    if (score < 30) return 'text-green-600';
    if (score < 60) return 'text-yellow-600';
    return 'text-red-600';
  };

  return (
    <Card data-tour="twin-risk">
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium">Risiko-Übersicht</CardTitle>
        <Shield className="h-4 w-4 text-muted-foreground" />
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Durchschnittlicher Risk Score */}
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-sm text-muted-foreground">Durchschn. Risiko-Score</span>
            <span className={`text-2xl font-bold ${getScoreColor(data.average_risk_score)}`}>
              {data.average_risk_score.toFixed(1)}
            </span>
          </div>
        </div>

        {/* Hochrisiko-Entitäten */}
        <div className="flex items-center justify-between pt-2 border-t">
          <span className="text-sm text-muted-foreground">Hochrisiko-Entitäten</span>
          <Badge variant={data.high_risk_count > 0 ? 'destructive' : 'outline'}>
            {data.high_risk_count}
          </Badge>
        </div>

        {/* Risiko-Verteilung */}
        <div className="space-y-2 pt-2 border-t">
          <p className="text-sm font-medium">Verteilung</p>
          <div className="grid grid-cols-2 gap-2 text-sm">
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">Niedrig</span>
              <Badge variant="outline" className="bg-green-50 text-green-700 border-green-200">
                {data.risk_distribution.low}
              </Badge>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">Mittel</span>
              <Badge variant="outline" className="bg-yellow-50 text-yellow-700 border-yellow-200">
                {data.risk_distribution.medium}
              </Badge>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">Hoch</span>
              <Badge variant="outline" className="bg-orange-50 text-orange-700 border-orange-200">
                {data.risk_distribution.high}
              </Badge>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">Kritisch</span>
              <Badge variant="outline" className="bg-red-50 text-red-700 border-red-200">
                {data.risk_distribution.critical}
              </Badge>
            </div>
          </div>
        </div>

        {/* Top Risiken */}
        {data.top_risks.length > 0 && (
          <div className="space-y-2 pt-2 border-t">
            <p className="text-sm font-medium">Top Risiken</p>
            <div className="space-y-1">
              {data.top_risks.slice(0, 3).map((risk) => (
                <div key={risk.entity_id} className="flex items-center justify-between text-sm">
                  <span className="truncate flex-1">{risk.entity_name}</span>
                  <Badge variant="outline" className="ml-2">
                    {risk.risk_score.toFixed(0)}
                  </Badge>
                </div>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function DocumentPipelineCard({ data }: { data: DocumentPipeline }) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium">Dokument-Pipeline</CardTitle>
        <FileText className="h-4 w-4 text-muted-foreground" />
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Dokumente nach Zeitraum */}
        <div className="grid grid-cols-3 gap-4 text-center">
          <div>
            <p className="text-2xl font-bold">{data.documents_today}</p>
            <p className="text-xs text-muted-foreground">Heute</p>
          </div>
          <div>
            <p className="text-2xl font-bold">{data.documents_week}</p>
            <p className="text-xs text-muted-foreground">Diese Woche</p>
          </div>
          <div>
            <p className="text-2xl font-bold">{data.documents_month}</p>
            <p className="text-xs text-muted-foreground">Diesen Monat</p>
          </div>
        </div>

        {/* Ausstehende Dokumente */}
        <div className="space-y-2 pt-2 border-t">
          <p className="text-sm font-medium">Ausstehend</p>
          <div className="space-y-2">
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">OCR-Verarbeitung</span>
              <Badge variant={data.pending_ocr > 0 ? 'secondary' : 'outline'}>
                {data.pending_ocr}
              </Badge>
            </div>
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">Review</span>
              <Badge variant={data.pending_review > 0 ? 'secondary' : 'outline'}>
                {data.pending_review}
              </Badge>
            </div>
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">Genehmigung</span>
              <Badge variant={data.pending_approval > 0 ? 'secondary' : 'outline'}>
                {data.pending_approval}
              </Badge>
            </div>
          </div>
        </div>

        {/* Durchschnittliche Verarbeitungszeit */}
        <div className="pt-2 border-t">
          <div className="flex items-center justify-between">
            <span className="text-sm text-muted-foreground">Ø Verarbeitungszeit</span>
            <div className="flex items-center gap-1">
              <Clock className="h-3 w-3" />
              <span className="text-sm font-semibold">
                {data.processing_time_avg_seconds.toFixed(1)}s
              </span>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function ComplianceStatusCard({ data }: { data: ComplianceStatus }) {
  const getScoreColor = (score: number) => {
    if (score >= 80) return 'text-green-600';
    if (score >= 60) return 'text-yellow-600';
    return 'text-red-600';
  };

  return (
    <Card data-tour="twin-compliance">
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium">Compliance-Status</CardTitle>
        <Shield className="h-4 w-4 text-muted-foreground" />
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Compliance Score */}
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-sm text-muted-foreground">Compliance-Score</span>
            <span className={`text-2xl font-bold ${getScoreColor(data.compliance_score)}`}>
              {data.compliance_score}/100
            </span>
          </div>
          <Progress value={data.compliance_score} className="h-2" />
        </div>

        {/* GDPR & GoBD Status */}
        <div className="space-y-2 pt-2 border-t">
          <div className="flex items-center justify-between">
            <span className="text-sm text-muted-foreground">GDPR-konform</span>
            {data.gdpr_compliant ? (
              <CheckCircle2 className="h-5 w-5 text-green-600" />
            ) : (
              <AlertTriangle className="h-5 w-5 text-red-600" />
            )}
          </div>
          <div className="flex items-center justify-between">
            <span className="text-sm text-muted-foreground">GoBD-konform</span>
            {data.gobd_compliant ? (
              <CheckCircle2 className="h-5 w-5 text-green-600" />
            ) : (
              <AlertTriangle className="h-5 w-5 text-red-600" />
            )}
          </div>
        </div>

        {/* Issues */}
        {data.issues.length > 0 && (
          <div className="space-y-2 pt-2 border-t">
            <p className="text-sm font-medium text-orange-600">Offene Probleme</p>
            <div className="space-y-1">
              {data.issues.slice(0, 3).map((issue, idx) => (
                <div key={idx} className="flex items-start gap-2 text-sm">
                  <AlertTriangle className="h-3 w-3 text-orange-600 mt-0.5 flex-shrink-0" />
                  <span className="text-muted-foreground text-xs">{issue}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Audit Dates */}
        <div className="space-y-1 pt-2 border-t text-xs text-muted-foreground">
          {data.last_audit_date && (
            <p>Letztes Audit: {new Date(data.last_audit_date).toLocaleDateString('de-DE')}</p>
          )}
          {data.next_audit_date && (
            <p>Nächstes Audit: {new Date(data.next_audit_date).toLocaleDateString('de-DE')}</p>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

function KeyMetricsCard({ data }: { data: KeyMetrics }) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium">Wichtige Metriken</CardTitle>
        <Activity className="h-4 w-4 text-muted-foreground" />
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid grid-cols-2 gap-4">
          <div>
            <p className="text-sm text-muted-foreground">Dokumente</p>
            <p className="text-2xl font-bold">{data.total_documents.toLocaleString('de-DE')}</p>
          </div>
          <div>
            <p className="text-sm text-muted-foreground">Entitäten</p>
            <p className="text-2xl font-bold">{data.total_entities.toLocaleString('de-DE')}</p>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4 pt-2 border-t">
          <div>
            <p className="text-sm text-muted-foreground">Ø Verarbeitung</p>
            <p className="text-lg font-semibold">{data.avg_processing_time.toFixed(1)}s</p>
          </div>
          <div>
            <p className="text-sm text-muted-foreground">Erfolgsrate</p>
            <p className="text-lg font-semibold">{(data.success_rate * 100).toFixed(1)}%</p>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4 pt-2 border-t">
          <div>
            <div className="flex items-center gap-2">
              <Database className="h-4 w-4 text-muted-foreground" />
              <div>
                <p className="text-sm text-muted-foreground">Speicher</p>
                <p className="text-lg font-semibold">{data.storage_used_gb.toFixed(1)} GB</p>
              </div>
            </div>
          </div>
          <div>
            <div className="flex items-center gap-2">
              <Users className="h-4 w-4 text-muted-foreground" />
              <div>
                <p className="text-sm text-muted-foreground">Aktive User</p>
                <p className="text-lg font-semibold">{data.active_users}</p>
              </div>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function TrendsCard({ data }: { data: Trends }) {
  const getTrendIcon = (trend: string) => {
    switch (trend) {
      case 'up':
        return <TrendingUp className="h-4 w-4 text-green-600" />;
      case 'down':
        return <TrendingDown className="h-4 w-4 text-red-600" />;
      default:
        return <Minus className="h-4 w-4 text-gray-600" />;
    }
  };

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium">Trends</CardTitle>
        <TrendingUp className="h-4 w-4 text-muted-foreground" />
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          {data.indicators.slice(0, 5).map((indicator, idx) => (
            <div key={idx} className="flex items-center justify-between">
              <div className="flex-1">
                <p className="text-sm font-medium">{indicator.metric}</p>
                <p className="text-xs text-muted-foreground">{indicator.period}</p>
              </div>
              <div className="flex items-center gap-2">
                {getTrendIcon(indicator.trend)}
                <span className="text-sm font-semibold">
                  {Math.abs(indicator.change_percentage).toFixed(1)}%
                </span>
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

function DashboardSkeleton() {
  return (
    <div className="space-y-6">
      <div>
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-4 w-96 mt-2" />
      </div>
      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <Card key={i}>
            <CardHeader>
              <Skeleton className="h-4 w-32" />
            </CardHeader>
            <CardContent className="space-y-2">
              <Skeleton className="h-16 w-full" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-full" />
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
