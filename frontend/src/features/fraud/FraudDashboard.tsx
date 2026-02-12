/**
 * Fraud Detection Dashboard
 *
 * Hauptseite für KI-gestützte Betrugserkennung.
 */

import { useState } from 'react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import { Badge } from '@/components/ui/badge';
import {
  ShieldAlert,
  AlertTriangle,
  RefreshCw,
  Settings,
  FileText,
  BarChart3,
} from 'lucide-react';
import {
  useFraudDashboard,
  useFraudAlerts,
  useFraudAnalysis,
  useFraudTypes,
} from './hooks/use-fraud';
import { FraudStatsCards } from './components/FraudStatsCards';
import { FraudAlertsTable } from './components/FraudAlertsTable';
import { FraudTypesChart } from './components/FraudTypesChart';
import { RiskLevelDistribution } from './components/RiskLevelDistribution';

export function FraudDashboard() {
  const [analysisDays, setAnalysisDays] = useState(90);
  const [riskFilter, setRiskFilter] = useState<string>('all');
  const [typeFilter, setTypeFilter] = useState<string>('all');

  const { data: dashboard, isLoading: dashboardLoading, refetch: refetchDashboard } = useFraudDashboard();
  const { data: analysis, isLoading: analysisLoading, refetch: refetchAnalysis } = useFraudAnalysis(analysisDays);
  const { data: fraudTypes } = useFraudTypes();

  const handleRefresh = () => {
    refetchDashboard();
    refetchAnalysis();
  };

  // Filter alerts
  const filteredAlerts = analysis?.alerts?.filter((alert) => {
    if (riskFilter !== 'all' && alert.risk_level !== riskFilter) return false;
    if (typeFilter !== 'all' && alert.type !== typeFilter) return false;
    return true;
  }) || [];

  return (
    <div className="container mx-auto py-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight flex items-center gap-2">
            <ShieldAlert className="h-8 w-8" />
            Fraud Detection
          </h1>
          <p className="text-muted-foreground">
            KI-gestützte Betrugserkennung und Risikoanalyse
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Select
            value={analysisDays.toString()}
            onValueChange={(v) => setAnalysisDays(parseInt(v))}
          >
            <SelectTrigger className="w-[140px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="30">30 Tage</SelectItem>
              <SelectItem value="60">60 Tage</SelectItem>
              <SelectItem value="90">90 Tage</SelectItem>
              <SelectItem value="180">180 Tage</SelectItem>
              <SelectItem value="365">1 Jahr</SelectItem>
            </SelectContent>
          </Select>
          <Button variant="outline" size="icon" onClick={handleRefresh}>
            <RefreshCw className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {/* Stats Cards */}
      {dashboardLoading ? (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-24" />
          ))}
        </div>
      ) : dashboard ? (
        <FraudStatsCards stats={dashboard} />
      ) : null}

      {/* Main Content Tabs */}
      <Tabs defaultValue="alerts" className="space-y-4">
        <TabsList>
          <TabsTrigger value="alerts" className="flex items-center gap-2">
            <AlertTriangle className="h-4 w-4" />
            Alerts
            {analysis && analysis.summary.total_alerts > 0 && (
              <Badge variant="secondary" className="ml-1">
                {analysis.summary.total_alerts}
              </Badge>
            )}
          </TabsTrigger>
          <TabsTrigger value="analysis" className="flex items-center gap-2">
            <BarChart3 className="h-4 w-4" />
            Analyse
          </TabsTrigger>
          <TabsTrigger value="types" className="flex items-center gap-2">
            <FileText className="h-4 w-4" />
            Fraud-Typen
          </TabsTrigger>
        </TabsList>

        {/* Alerts Tab */}
        <TabsContent value="alerts" className="space-y-4">
          {/* Filters */}
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              <span className="text-sm text-muted-foreground">Risiko:</span>
              <Select value={riskFilter} onValueChange={setRiskFilter}>
                <SelectTrigger className="w-[120px]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Alle</SelectItem>
                  <SelectItem value="critical">Kritisch</SelectItem>
                  <SelectItem value="high">Hoch</SelectItem>
                  <SelectItem value="medium">Mittel</SelectItem>
                  <SelectItem value="low">Niedrig</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-sm text-muted-foreground">Typ:</span>
              <Select value={typeFilter} onValueChange={setTypeFilter}>
                <SelectTrigger className="w-[160px]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Alle Typen</SelectItem>
                  <SelectItem value="duplicate_invoice">Duplikat</SelectItem>
                  <SelectItem value="price_anomaly">Preis-Anomalie</SelectItem>
                  <SelectItem value="phantom_supplier">Phantom-Lieferant</SelectItem>
                  <SelectItem value="expense_fraud">Spesen-Betrug</SelectItem>
                  <SelectItem value="kickback">Kickback</SelectItem>
                  <SelectItem value="shell_company">Shell-Company</SelectItem>
                  <SelectItem value="split_invoice">Invoice-Split</SelectItem>
                </SelectContent>
              </Select>
            </div>
            {(riskFilter !== 'all' || typeFilter !== 'all') && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setRiskFilter('all');
                  setTypeFilter('all');
                }}
              >
                Filter zurücksetzen
              </Button>
            )}
          </div>

          {analysisLoading ? (
            <Skeleton className="h-[400px]" />
          ) : (
            <FraudAlertsTable alerts={filteredAlerts} />
          )}
        </TabsContent>

        {/* Analysis Tab */}
        <TabsContent value="analysis" className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Risk Distribution */}
            {analysisLoading ? (
              <Skeleton className="h-[300px]" />
            ) : analysis ? (
              <RiskLevelDistribution summary={analysis.summary} />
            ) : null}

            {/* Fraud Types Chart */}
            {dashboardLoading ? (
              <Skeleton className="h-[300px]" />
            ) : dashboard ? (
              <FraudTypesChart data={dashboard.top_fraud_types} />
            ) : null}
          </div>

          {/* Analysis Summary */}
          {analysis && (
            <Card>
              <CardHeader>
                <CardTitle>Analysezusammenfassung</CardTitle>
                <CardDescription>
                  Zeitraum: {new Date(analysis.analysis_period.start).toLocaleDateString('de-DE')} -{' '}
                  {new Date(analysis.analysis_period.end).toLocaleDateString('de-DE')}
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
                  <div>
                    <p className="text-sm text-muted-foreground">Analysiert am</p>
                    <p className="font-medium">
                      {new Date(analysis.analyzed_at).toLocaleString('de-DE')}
                    </p>
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">Gesamte Alerts</p>
                    <p className="text-2xl font-bold">{analysis.summary.total_alerts}</p>
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">Kritisch + Hoch</p>
                    <p className="text-2xl font-bold text-red-600">
                      {analysis.summary.critical + analysis.summary.high}
                    </p>
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">Risiko-Summe</p>
                    <p className="text-2xl font-bold">
                      {new Intl.NumberFormat('de-DE', {
                        style: 'currency',
                        currency: 'EUR',
                        minimumFractionDigits: 0,
                      }).format(analysis.summary.estimated_risk_amount)}
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}
        </TabsContent>

        {/* Fraud Types Info Tab */}
        <TabsContent value="types" className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {fraudTypes?.map((type) => (
              <Card key={type.type}>
                <CardHeader>
                  <CardTitle className="text-base">{type.name}</CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-sm text-muted-foreground">{type.description}</p>
                </CardContent>
              </Card>
            ))}
          </div>

          {/* Info Card */}
          <Card className="bg-blue-50 dark:bg-blue-950 border-blue-200 dark:border-blue-800">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-blue-600">
                <Settings className="h-5 w-5" />
                Erkennungsmethoden
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              <p>
                <strong>Duplikat-Erkennung:</strong> Hash-basiert (Rechnungsnummer + Betrag + Lieferant)
                und Fuzzy-Match für ähnliche Beträge
              </p>
              <p>
                <strong>Preis-Anomalien:</strong> Statistische Analyse mit Z-Score gegenüber
                historischem Durchschnitt pro Lieferant
              </p>
              <p>
                <strong>Phantom-Lieferanten:</strong> Lieferanten mit Zahlungen aber ohne
                korrespondierende Lieferscheine/Bestellungen
              </p>
              <p>
                <strong>Shell-Companies:</strong> Netzwerk-Analyse auf gemeinsame Bankverbindungen
                und Adressen
              </p>
              <p>
                <strong>Invoice-Splitting:</strong> Erkennung von Rechnungsaufteilungen
                zur Umgehung von Genehmigungsgrenzen
              </p>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
