/**
 * Digital Twin Dashboard Page
 *
 * Main 360-degree company snapshot dashboard with all sections.
 */

import { useDigitalTwin } from '../hooks/useDigitalTwin';
import { FinancialHealthCard } from './FinancialHealthCard';
import { RiskOverviewCard } from './RiskOverviewCard';
import { DocumentPipelineCard } from './DocumentPipelineCard';
import { ComplianceCard } from './ComplianceCard';
import { KeyMetricsCard } from './KeyMetricsCard';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Loader2, RefreshCw } from 'lucide-react';

export function DigitalTwinDashboard() {
  const {
    data: digitalTwin,
    isLoading,
    error,
    refetch,
  } = useDigitalTwin();

  // Error state
  if (error) {
    return (
      <div className="container mx-auto p-6">
        <Card>
          <CardContent className="p-6">
            <div className="text-center text-red-600 dark:text-red-400">
              Fehler beim Laden des Digital Twin.{' '}
              <Button
                variant="link"
                onClick={() => refetch()}
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
  if (isLoading || !digitalTwin) {
    return (
      <div className="container mx-auto p-6">
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
          <span className="ml-3 text-muted-foreground">
            Digital Twin wird geladen...
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
            Digital Twin
          </h1>
          <p className="text-muted-foreground mt-1">
            360-Grad Unternehmensansicht in Echtzeit
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => refetch()}
          className="gap-2"
        >
          <RefreshCw className="w-4 h-4" />
          Aktualisieren
        </Button>
      </div>

      {/* Main Grid - 6 Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {/* Financial Health */}
        <FinancialHealthCard data={digitalTwin.financialHealth} />

        {/* Risk Overview */}
        <RiskOverviewCard data={digitalTwin.riskOverview} />

        {/* Document Pipeline */}
        <DocumentPipelineCard data={digitalTwin.documentPipeline} />

        {/* Compliance */}
        <ComplianceCard data={digitalTwin.compliance} />

        {/* Key Metrics - Spans 2 columns */}
        <div className="md:col-span-2">
          <KeyMetricsCard data={digitalTwin.keyMetrics} />
        </div>
      </div>

      {/* Last Updated Footer */}
      <div className="text-xs text-muted-foreground text-center pt-4 border-t border-border">
        Letzte Aktualisierung:{' '}
        {digitalTwin.generatedAt.toLocaleString('de-DE', {
          day: '2-digit',
          month: '2-digit',
          year: 'numeric',
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit',
        })}
        {' • '}
        <span className="text-muted-foreground/70">
          Automatische Aktualisierung alle 60 Sekunden
        </span>
      </div>
    </div>
  );
}
