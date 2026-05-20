/**
 * Carbon Footprint Page
 *
 * Verwaltung und Tracking von CO2-Emissionen.
 * Verbunden mit der ESG API via TanStack Query Hooks.
 */

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Plus, Download, Filter, AlertCircle } from 'lucide-react';
import {
  useEmissions,
  useEmissionsSummary,
  useCarbonTrend,
} from '../hooks/use-esg-queries';

export function CarbonFootprintPage() {
  // Get current year for summary
  const currentYear = new Date().getFullYear();
  const periodStart = `${currentYear}-01-01`;
  const periodEnd = `${currentYear}-12-31`;

  const { data: summary, isLoading: summaryLoading, error: summaryError } = useEmissionsSummary(periodStart, periodEnd);
  const { data: emissions, isLoading: emissionsLoading } = useEmissions({ limit: 50 });
  const { data: carbonTrend, isLoading: trendLoading } = useCarbonTrend(12);

  if (summaryError) {
    return (
      <Alert variant="destructive">
        <AlertCircle className="h-4 w-4" />
        <AlertDescription>
          Fehler beim Laden der CO2-Daten: {summaryError.message}
        </AlertDescription>
      </Alert>
    );
  }

  return (
    <div className="space-y-6">
      {/* Actions */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">CO2-Fußabdruck</h2>
          <p className="text-sm text-muted-foreground">
            Erfassen und analysieren Sie Ihre CO2-Emissionen
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" disabled title="Kommt bald" aria-label="Emissionen filtern">
            <Filter className="h-4 w-4 mr-2" />
            Filter
          </Button>
          <Button variant="outline" size="sm" disabled title="Kommt bald" aria-label="Emissionen exportieren">
            <Download className="h-4 w-4 mr-2" />
            Export
          </Button>
          <Button size="sm" disabled title="Kommt bald" aria-label="Neue Emission erfassen">
            <Plus className="h-4 w-4 mr-2" />
            Emission erfassen
          </Button>
        </div>
      </div>

      {/* Scope Overview */}
      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Scope 1</CardTitle>
            <CardDescription>Direkte Emissionen</CardDescription>
          </CardHeader>
          <CardContent>
            {summaryLoading ? (
              <Skeleton className="h-8 w-24" />
            ) : (
              <div className="text-2xl font-bold">
                {formatTonnes(summary?.by_scope?.scope_1)}
              </div>
            )}
            <p className="text-xs text-muted-foreground">
              Fahrzeuge, Heizung, Produktion
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Scope 2</CardTitle>
            <CardDescription>Indirekte Emissionen (Energie)</CardDescription>
          </CardHeader>
          <CardContent>
            {summaryLoading ? (
              <Skeleton className="h-8 w-24" />
            ) : (
              <div className="text-2xl font-bold">
                {formatTonnes(summary?.by_scope?.scope_2)}
              </div>
            )}
            <p className="text-xs text-muted-foreground">
              Strom, Fernwärme
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Scope 3</CardTitle>
            <CardDescription>Lieferkette</CardDescription>
          </CardHeader>
          <CardContent>
            {summaryLoading ? (
              <Skeleton className="h-8 w-24" />
            ) : (
              <div className="text-2xl font-bold">
                {formatTonnes(summary?.by_scope?.scope_3)}
              </div>
            )}
            <p className="text-xs text-muted-foreground">
              Lieferanten, Transport, Entsorgung
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Emissions Table */}
      <Card>
        <CardHeader>
          <CardTitle>Emissionsquellen</CardTitle>
          <CardDescription>
            Aufschlüsselung nach Kategorien und Zeitraum
          </CardDescription>
        </CardHeader>
        <CardContent>
          {emissionsLoading ? (
            <div className="space-y-2">
              {[...Array(5)].map((_, i) => (
                <Skeleton key={i} className="h-12 w-full" />
              ))}
            </div>
          ) : emissions?.items && emissions.items.length > 0 ? (
            <div className="space-y-2" role="table" aria-label="Emissionsquellen">
              <div className="grid grid-cols-5 gap-4 p-3 text-sm font-medium text-muted-foreground border-b">
                <div>Kategorie</div>
                <div>Scope</div>
                <div>Verbrauch</div>
                <div>CO2e (kg)</div>
                <div>Datum</div>
              </div>
              {emissions.items.map((emission) => (
                <div
                  key={emission.id}
                  className="grid grid-cols-5 gap-4 p-3 text-sm border-b hover:bg-muted/50"
                >
                  <div className="font-medium">{emission.source_category}</div>
                  <div>{getScopeLabel(emission.scope)}</div>
                  <div>
                    {emission.consumption_value?.toLocaleString('de-DE')} {emission.consumption_unit}
                  </div>
                  <div>{emission.co2_equivalent_kg?.toLocaleString('de-DE', { maximumFractionDigits: 2 })}</div>
                  <div>{formatDate(emission.emission_date)}</div>
                </div>
              ))}
            </div>
          ) : (
            <div className="h-[200px] flex items-center justify-center text-muted-foreground">
              Keine Emissionen erfasst
            </div>
          )}
        </CardContent>
      </Card>

      {/* Trend Chart */}
      <Card>
        <CardHeader>
          <CardTitle>Emissionstrend</CardTitle>
          <CardDescription>
            Entwicklung der CO2-Emissionen über Zeit
          </CardDescription>
        </CardHeader>
        <CardContent>
          {trendLoading ? (
            <Skeleton className="h-[300px] w-full" />
          ) : carbonTrend && carbonTrend.length > 0 ? (
            <div className="h-[300px]" role="img" aria-label="CO2-Emissionstrend Chart">
              {/* Simple bar chart representation */}
              <div className="flex items-end justify-between h-full gap-1 pb-8">
                {carbonTrend.slice(-12).map((point, index) => {
                  const maxValue = Math.max(...carbonTrend.map(p => p.total_kg || 0));
                  const height = maxValue > 0 ? ((point.total_kg || 0) / maxValue) * 100 : 0;
                  return (
                    <div key={index} className="flex-1 flex flex-col items-center">
                      <div
                        className="w-full bg-green-500 rounded-t transition-all hover:bg-green-600"
                        style={{ height: `${height}%` }}
                        title={`${point.period}: ${formatTonnes(point.total_kg)}`}
                      />
                      <span className="text-xs text-muted-foreground mt-2 rotate-45 origin-left">
                        {point.period?.slice(-2)}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          ) : (
            <div className="h-[300px] flex items-center justify-center text-muted-foreground">
              Keine Trend-Daten vorhanden
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

// Helper functions
function formatTonnes(kg?: number): string {
  if (kg === undefined || kg === null) return '0 t CO2e';
  const tonnes = kg / 1000;
  return `${tonnes.toLocaleString('de-DE', { maximumFractionDigits: 1 })} t CO2e`;
}

function formatDate(dateString?: string): string {
  if (!dateString) return '-';
  return new Intl.DateTimeFormat('de-DE', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  }).format(new Date(dateString));
}

function getScopeLabel(scope?: string): string {
  const labels: Record<string, string> = {
    scope_1: 'Scope 1',
    scope_2: 'Scope 2',
    scope_3: 'Scope 3',
  };
  return labels[scope ?? ''] || scope || '-';
}
