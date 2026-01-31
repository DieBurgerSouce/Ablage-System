/**
 * Risk Scoring Demo Page
 *
 * Beispiel-Seite zur Demonstration aller Risk Scoring Komponenten.
 * Diese Datei dient als Referenz für die Integration.
 */

import { useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Badge } from '@/components/ui/badge';
import {
  RiskScoreGauge,
  RiskScoreBadge,
  RiskIndicator,
  RiskFactorBreakdown,
  FactorContributionChart,
  RiskAlertBanner,
  RiskAlertBadge,
  RiskTrendChart,
  RiskDistributionChart,
  EntityRiskMiniChart,
  HighRiskEntitiesTable,
  RiskEntityList,
  RiskDashboard,
  RiskProfilePage,
} from '../index';

// Mock Data
const mockEntityRisk = {
  entityId: '123e4567-e89b-12d3-a456-426614174000',
  entityName: 'Muster GmbH',
  entityType: 'customer' as const,
  riskScore: 78.5,
  paymentBehaviorScore: 42.3,
  riskFactors: [
    {
      name: 'payment_delay' as const,
      value: 0.85,
      weight: 0.35,
      contribution: 29.75,
      rawValue: 45,
    },
    {
      name: 'default_rate' as const,
      value: 0.65,
      weight: 0.25,
      contribution: 16.25,
      rawValue: 0.35,
    },
    {
      name: 'invoice_volume' as const,
      value: 0.45,
      weight: 0.15,
      contribution: 6.75,
      rawValue: 12500,
    },
    {
      name: 'document_frequency' as const,
      value: 0.75,
      weight: 0.1,
      contribution: 7.5,
      rawValue: 2.5,
    },
    {
      name: 'relationship_age' as const,
      value: 0.60,
      weight: 0.15,
      contribution: 9.0,
      rawValue: 8,
    },
  ],
  calculatedAt: new Date(),
  isHighRisk: true,
  riskLevel: 'critical' as const,
};

const mockTrendData = Array.from({ length: 30 }, (_, i) => ({
  date: new Date(Date.now() - (29 - i) * 24 * 60 * 60 * 1000),
  averageScore: 60 + Math.random() * 20,
  highRiskCount: Math.floor(10 + Math.random() * 5),
}));

const mockDistribution = {
  low: 45,
  medium: 30,
  high: 15,
  critical: 10,
};

const mockHighRiskEntities = [
  mockEntityRisk,
  {
    ...mockEntityRisk,
    entityId: '223e4567-e89b-12d3-a456-426614174001',
    entityName: 'Beispiel AG',
    riskScore: 65.2,
    riskLevel: 'high' as const,
  },
];

export function RiskScoringDemo() {
  const [selectedTab, setSelectedTab] = useState('gauges');

  return (
    <div className="container mx-auto py-8 space-y-6">
      <div>
        <h1 className="text-3xl font-bold">Risk Scoring UI Demo</h1>
        <p className="text-muted-foreground mt-2">
          Demonstration aller verfügbaren Risk Scoring Komponenten
        </p>
      </div>

      <Tabs value={selectedTab} onValueChange={setSelectedTab}>
        <TabsList className="grid w-full grid-cols-5">
          <TabsTrigger value="gauges">Gauges</TabsTrigger>
          <TabsTrigger value="factors">Faktoren</TabsTrigger>
          <TabsTrigger value="alerts">Alerts</TabsTrigger>
          <TabsTrigger value="charts">Charts</TabsTrigger>
          <TabsTrigger value="tables">Tables</TabsTrigger>
        </TabsList>

        {/* Gauges Tab */}
        <TabsContent value="gauges" className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Risk Score Gauges</CardTitle>
              <CardDescription>
                Verschiedene Größen und Varianten der Risiko-Score Anzeige
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-8">
              {/* Gauges */}
              <div>
                <h3 className="font-medium mb-4">RiskScoreGauge Größen</h3>
                <div className="flex flex-wrap items-end gap-8">
                  <div>
                    <p className="text-xs text-muted-foreground mb-2">Small</p>
                    <RiskScoreGauge score={78.5} size="sm" />
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground mb-2">Medium (default)</p>
                    <RiskScoreGauge score={78.5} size="md" />
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground mb-2">Large</p>
                    <RiskScoreGauge score={78.5} size="lg" />
                  </div>
                </div>
              </div>

              {/* Badges */}
              <div>
                <h3 className="font-medium mb-4">RiskScoreBadge Varianten</h3>
                <div className="flex flex-wrap items-center gap-4">
                  <RiskScoreBadge score={15} size="sm" />
                  <RiskScoreBadge score={35} size="md" />
                  <RiskScoreBadge score={65} size="lg" />
                  <RiskScoreBadge score={85} size="lg" />
                </div>
              </div>

              {/* Indicators */}
              <div>
                <h3 className="font-medium mb-4">RiskIndicator (Mini)</h3>
                <div className="flex flex-wrap items-center gap-4">
                  <RiskIndicator score={15} />
                  <RiskIndicator score={35} />
                  <RiskIndicator score={65} />
                  <RiskIndicator score={85} />
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Factors Tab */}
        <TabsContent value="factors" className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Risikofaktoren Breakdown</CardTitle>
              <CardDescription>
                Detaillierte Aufschlüsselung der 5 Haupt-Risikofaktoren
              </CardDescription>
            </CardHeader>
            <CardContent>
              <RiskFactorBreakdown
                factors={mockEntityRisk.riskFactors}
                showWeights
              />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Factor Contribution Chart</CardTitle>
              <CardDescription>Stacked Bar mit Beiträgen</CardDescription>
            </CardHeader>
            <CardContent>
              <FactorContributionChart factors={mockEntityRisk.riskFactors} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Kompakte Darstellung</CardTitle>
              <CardDescription>Für Sidebars oder kleinere Bereiche</CardDescription>
            </CardHeader>
            <CardContent>
              <RiskFactorBreakdown
                factors={mockEntityRisk.riskFactors}
                compact
                showWeights={false}
              />
            </CardContent>
          </Card>
        </TabsContent>

        {/* Alerts Tab */}
        <TabsContent value="alerts" className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Risk Alert Banner</CardTitle>
              <CardDescription>Warnung-Banner für Hoch-Risiko Entities</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <RiskAlertBanner entityRisk={mockEntityRisk} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Kompakte Variante</CardTitle>
              <CardDescription>Für Listen oder kleinere Bereiche</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <RiskAlertBanner entityRisk={mockEntityRisk} compact />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Risk Alert Badges</CardTitle>
              <CardDescription>Mini-Variante für Inline-Verwendung</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="flex flex-wrap items-center gap-4">
                <RiskAlertBadge riskLevel="high" score={65} />
                <RiskAlertBadge riskLevel="critical" score={85} />
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Charts Tab */}
        <TabsContent value="charts" className="space-y-6">
          <RiskTrendChart data={mockTrendData} showHighRiskCount />

          <Card>
            <CardHeader>
              <CardTitle>Risiko-Verteilung</CardTitle>
              <CardDescription>Verteilung nach Risikostufen</CardDescription>
            </CardHeader>
            <CardContent>
              <RiskDistributionChart
                distribution={mockDistribution}
                totalEntities={100}
              />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Entity Mini Chart</CardTitle>
              <CardDescription>Kompakter Verlauf für Detail-Seiten</CardDescription>
            </CardHeader>
            <CardContent>
              <EntityRiskMiniChart
                data={mockTrendData.map(d => ({
                  date: d.date,
                  score: d.averageScore,
                }))}
                height={150}
              />
            </CardContent>
          </Card>
        </TabsContent>

        {/* Tables Tab */}
        <TabsContent value="tables" className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>High Risk Entities Table</CardTitle>
              <CardDescription>
                Erweiterbare Tabelle mit detaillierten Informationen
              </CardDescription>
            </CardHeader>
            <CardContent>
              <HighRiskEntitiesTable
                entities={mockHighRiskEntities}
                onRecalculate={() => {/* Demo: Neuberechnung getriggert */}}
              />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Kompakte Liste</CardTitle>
              <CardDescription>Für Sidebars oder Widgets</CardDescription>
            </CardHeader>
            <CardContent>
              <HighRiskEntitiesTable
                entities={mockHighRiskEntities}
                compact
              />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Risk Entity List</CardTitle>
              <CardDescription>Einfache Liste mit Links</CardDescription>
            </CardHeader>
            <CardContent>
              <RiskEntityList entities={mockHighRiskEntities} maxItems={5} />
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* Full Dashboard Demo */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>Risk Dashboard (Live-Daten)</CardTitle>
              <CardDescription>
                Vollständiges Dashboard mit echten API-Daten
              </CardDescription>
            </div>
            <Badge variant="outline">Live</Badge>
          </div>
        </CardHeader>
        <CardContent>
          <RiskDashboard />
        </CardContent>
      </Card>

      {/* Full Profile Demo */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>Risk Profile Page (Mock-Daten)</CardTitle>
              <CardDescription>
                Vollständige Entity-Analyse-Seite
              </CardDescription>
            </div>
            <Badge variant="outline">Mock</Badge>
          </div>
        </CardHeader>
        <CardContent>
          {/* Note: In real usage, this would be a separate route */}
          <div className="border rounded-lg p-4 bg-muted/30">
            <p className="text-sm text-muted-foreground text-center">
              Diese Komponente wird normalerweise als vollständige Seite verwendet.
              <br />
              Siehe: <code>/kunden/:entityId</code> oder <code>/lieferanten/:entityId</code>
            </p>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
