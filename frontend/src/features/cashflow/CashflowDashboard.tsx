/**
 * Predictive Cash-Flow Dashboard
 *
 * Hauptseite fuer Liquiditaetsprognose und Zahlungsempfehlungen.
 */

import { useState } from 'react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import {
  TrendingUp,
  Wallet,
  Sparkles,
  Calculator,
  RefreshCw,
  AlertTriangle,
} from 'lucide-react';
import { useLiquidityForecast, usePaymentRecommendations, useCashflowSummary, useRunScenario } from './hooks/use-cashflow';
import { LiquidityChart } from './components/LiquidityChart';
import { RecommendationsTable } from './components/RecommendationsTable';
import { CashflowSummaryCards } from './components/CashflowSummaryCards';
import type { ScenarioRequest } from './api/cashflow-api';

export function CashflowDashboard() {
  const [forecastDays, setForecastDays] = useState(30);
  const [activeScenario, setActiveScenario] = useState<string | null>(null);

  const { data: summary, isLoading: summaryLoading, refetch: refetchSummary } = useCashflowSummary();
  const { data: forecast, isLoading: forecastLoading, refetch: refetchForecast } = useLiquidityForecast(forecastDays);
  const { data: recommendations, isLoading: recommendationsLoading, refetch: refetchRecommendations } = usePaymentRecommendations();
  const runScenario = useRunScenario();

  const handleRefresh = () => {
    refetchSummary();
    refetchForecast();
    refetchRecommendations();
  };

  const handleRunScenario = (scenarioType: ScenarioRequest['scenario_type']) => {
    setActiveScenario(scenarioType);

    const parameters: Record<string, unknown> = {};
    if (scenarioType === 'delayed_payments') {
      parameters.delay_days = 14;
      parameters.affected_percentage = 30;
    } else if (scenarioType === 'large_expense') {
      parameters.expense_amount = 50000;
      parameters.expense_date = new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString().split('T')[0];
    } else if (scenarioType === 'revenue_drop') {
      parameters.drop_percentage = 20;
    }

    runScenario.mutate({ scenario_type: scenarioType, parameters });
  };

  const handlePayInvoice = (invoiceId: string) => {
    // Navigate to invoice payment or open modal
    console.log('Pay invoice:', invoiceId);
  };

  return (
    <div className="container mx-auto py-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight flex items-center gap-2">
            <Wallet className="h-8 w-8" />
            Predictive Cash-Flow
          </h1>
          <p className="text-muted-foreground">
            KI-gestuetzte Liquiditaetsprognose und Zahlungsoptimierung
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Select
            value={forecastDays.toString()}
            onValueChange={(v) => setForecastDays(parseInt(v))}
          >
            <SelectTrigger className="w-[140px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="7">7 Tage</SelectItem>
              <SelectItem value="14">14 Tage</SelectItem>
              <SelectItem value="30">30 Tage</SelectItem>
              <SelectItem value="60">60 Tage</SelectItem>
              <SelectItem value="90">90 Tage</SelectItem>
            </SelectContent>
          </Select>
          <Button variant="outline" size="icon" onClick={handleRefresh}>
            <RefreshCw className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {/* Summary Cards */}
      {summaryLoading ? (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <Skeleton key={i} className="h-24" />
          ))}
        </div>
      ) : summary ? (
        <CashflowSummaryCards summary={summary} />
      ) : null}

      {/* Main Content Tabs */}
      <Tabs defaultValue="forecast" className="space-y-4">
        <TabsList>
          <TabsTrigger value="forecast" className="flex items-center gap-2">
            <TrendingUp className="h-4 w-4" />
            Prognose
          </TabsTrigger>
          <TabsTrigger value="recommendations" className="flex items-center gap-2">
            <Sparkles className="h-4 w-4" />
            Empfehlungen
          </TabsTrigger>
          <TabsTrigger value="scenarios" className="flex items-center gap-2">
            <Calculator className="h-4 w-4" />
            Szenarien
          </TabsTrigger>
        </TabsList>

        {/* Forecast Tab */}
        <TabsContent value="forecast" className="space-y-4">
          {forecastLoading ? (
            <Skeleton className="h-[400px]" />
          ) : forecast ? (
            <>
              <LiquidityChart forecast={forecast.forecast} currency={forecast.currency} />

              {/* Warnings */}
              {forecast.warnings.length > 0 && (
                <Card className="border-amber-200 dark:border-amber-800">
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2 text-amber-600">
                      <AlertTriangle className="h-5 w-5" />
                      Warnungen ({forecast.warnings.length})
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-2">
                      {forecast.warnings.map((warning, index) => (
                        <div
                          key={index}
                          className={`flex items-center gap-2 p-2 rounded ${
                            warning.type === 'critical'
                              ? 'bg-red-50 dark:bg-red-950 text-red-700 dark:text-red-300'
                              : 'bg-amber-50 dark:bg-amber-950 text-amber-700 dark:text-amber-300'
                          }`}
                        >
                          <Badge variant={warning.type === 'critical' ? 'destructive' : 'secondary'}>
                            {warning.type === 'critical' ? 'Kritisch' : 'Warnung'}
                          </Badge>
                          <span className="text-sm">
                            {new Date(warning.date).toLocaleDateString('de-DE')}: {warning.message}
                          </span>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* Forecast Stats */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <Card>
                  <CardHeader className="pb-2">
                    <CardDescription>Minimaler Stand</CardDescription>
                    <CardTitle className={forecast.min_balance < 0 ? 'text-red-600' : ''}>
                      {new Intl.NumberFormat('de-DE', {
                        style: 'currency',
                        currency: forecast.currency,
                      }).format(forecast.min_balance)}
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <p className="text-xs text-muted-foreground">
                      am {new Date(forecast.min_balance_date).toLocaleDateString('de-DE')}
                    </p>
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader className="pb-2">
                    <CardDescription>Erwartete Eingaenge</CardDescription>
                    <CardTitle className="text-green-600">
                      {new Intl.NumberFormat('de-DE', {
                        style: 'currency',
                        currency: forecast.currency,
                      }).format(forecast.total_expected_inflows)}
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <p className="text-xs text-muted-foreground">
                      in den naechsten {forecast.forecast_days} Tagen
                    </p>
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader className="pb-2">
                    <CardDescription>Erwartete Ausgaenge</CardDescription>
                    <CardTitle className="text-orange-600">
                      {new Intl.NumberFormat('de-DE', {
                        style: 'currency',
                        currency: forecast.currency,
                      }).format(forecast.total_expected_outflows)}
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <p className="text-xs text-muted-foreground">
                      in den naechsten {forecast.forecast_days} Tagen
                    </p>
                  </CardContent>
                </Card>
              </div>
            </>
          ) : (
            <Card>
              <CardContent className="py-8 text-center text-muted-foreground">
                Keine Prognosedaten verfuegbar
              </CardContent>
            </Card>
          )}
        </TabsContent>

        {/* Recommendations Tab */}
        <TabsContent value="recommendations">
          {recommendationsLoading ? (
            <Skeleton className="h-[400px]" />
          ) : (
            <RecommendationsTable
              recommendations={recommendations || []}
              onPayInvoice={handlePayInvoice}
            />
          )}
        </TabsContent>

        {/* Scenarios Tab */}
        <TabsContent value="scenarios" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>What-If Szenarien</CardTitle>
              <CardDescription>
                Simulieren Sie verschiedene Szenarien und deren Auswirkungen auf Ihre Liquiditaet
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <Card
                  className={`cursor-pointer transition-colors hover:border-primary ${
                    activeScenario === 'delayed_payments' ? 'border-primary' : ''
                  }`}
                  onClick={() => handleRunScenario('delayed_payments')}
                >
                  <CardHeader>
                    <CardTitle className="text-base">Zahlungsverzoegerung</CardTitle>
                    <CardDescription>
                      30% der Kunden zahlen 14 Tage spaeter
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={runScenario.isPending}
                    >
                      {runScenario.isPending && activeScenario === 'delayed_payments'
                        ? 'Berechne...'
                        : 'Simulieren'}
                    </Button>
                  </CardContent>
                </Card>

                <Card
                  className={`cursor-pointer transition-colors hover:border-primary ${
                    activeScenario === 'large_expense' ? 'border-primary' : ''
                  }`}
                  onClick={() => handleRunScenario('large_expense')}
                >
                  <CardHeader>
                    <CardTitle className="text-base">Grosse Ausgabe</CardTitle>
                    <CardDescription>
                      Ungeplante Ausgabe von 50.000 EUR in 7 Tagen
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={runScenario.isPending}
                    >
                      {runScenario.isPending && activeScenario === 'large_expense'
                        ? 'Berechne...'
                        : 'Simulieren'}
                    </Button>
                  </CardContent>
                </Card>

                <Card
                  className={`cursor-pointer transition-colors hover:border-primary ${
                    activeScenario === 'revenue_drop' ? 'border-primary' : ''
                  }`}
                  onClick={() => handleRunScenario('revenue_drop')}
                >
                  <CardHeader>
                    <CardTitle className="text-base">Umsatzrueckgang</CardTitle>
                    <CardDescription>
                      20% weniger Einnahmen als erwartet
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={runScenario.isPending}
                    >
                      {runScenario.isPending && activeScenario === 'revenue_drop'
                        ? 'Berechne...'
                        : 'Simulieren'}
                    </Button>
                  </CardContent>
                </Card>
              </div>
            </CardContent>
          </Card>

          {/* Scenario Results */}
          {runScenario.data && (
            <Card className={
              runScenario.data.impact === 'negative'
                ? 'border-red-200 dark:border-red-800'
                : runScenario.data.impact === 'positive'
                ? 'border-green-200 dark:border-green-800'
                : ''
            }>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  Szenario-Ergebnis
                  <Badge
                    variant={
                      runScenario.data.impact === 'negative'
                        ? 'destructive'
                        : runScenario.data.impact === 'positive'
                        ? 'default'
                        : 'secondary'
                    }
                  >
                    {runScenario.data.impact === 'negative'
                      ? 'Negativ'
                      : runScenario.data.impact === 'positive'
                      ? 'Positiv'
                      : 'Neutral'}
                  </Badge>
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <p className="text-sm text-muted-foreground">Basis Min. Stand</p>
                    <p className="text-xl font-bold">
                      {new Intl.NumberFormat('de-DE', {
                        style: 'currency',
                        currency: 'EUR',
                      }).format(runScenario.data.base_min_balance)}
                    </p>
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">Szenario Min. Stand</p>
                    <p className={`text-xl font-bold ${
                      runScenario.data.scenario_min_balance < 0 ? 'text-red-600' : ''
                    }`}>
                      {new Intl.NumberFormat('de-DE', {
                        style: 'currency',
                        currency: 'EUR',
                      }).format(runScenario.data.scenario_min_balance)}
                    </p>
                  </div>
                </div>

                <div className="text-sm">
                  <p className="font-medium">Differenz:</p>
                  <p className={
                    runScenario.data.scenario_min_balance - runScenario.data.base_min_balance < 0
                      ? 'text-red-600'
                      : 'text-green-600'
                  }>
                    {new Intl.NumberFormat('de-DE', {
                      style: 'currency',
                      currency: 'EUR',
                      signDisplay: 'always',
                    }).format(runScenario.data.scenario_min_balance - runScenario.data.base_min_balance)}
                  </p>
                </div>

                {/* Scenario Forecast Chart */}
                {runScenario.data.forecast.length > 0 && (
                  <LiquidityChart forecast={runScenario.data.forecast} currency="EUR" />
                )}
              </CardContent>
            </Card>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}
