/**
 * RetirementPlanningPage - Altersvorsorge Dashboard
 *
 * Hauptseite für Altersvorsorge-Planung:
 * - Rentenlücken-Rechner
 * - Monte-Carlo-Simulation
 * - Rentenpunkte-Tracking
 * - Riester/Rürup Optimierung
 */

import { useState } from 'react';
import { PiggyBank, Calculator, BarChart3, TrendingUp, Coins, AlertCircle, ChevronRight, Info } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Skeleton } from '@/components/ui/skeleton';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';

import { PensionGapCalculator } from './components/PensionGapCalculator';
import { MonteCarloSimulation } from './components/MonteCarloSimulation';
import { useDefaultSpace } from '../hooks/use-privat-queries';
import { useRetirementSummary, useRiesterOptimization as useRiesterOptimizationQuery } from './hooks';
import type {
  RetirementSummaryRequest,
  RiesterOptimizationRequest,
} from '@/lib/api/services/retirement';

// Standard-Annahme für die Übersichts-Berechnung: Alter 35 (ISO-Datum,
// stabil pro Seitenaufruf — individuelle Werte über den Rechner-Tab)
const DEFAULT_BIRTH_DATE = new Date(
  new Date().getFullYear() - 35,
  0,
  1
).toISOString().slice(0, 10);

// Formatierung
const formatCurrency = (value: number): string =>
  new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency: 'EUR',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);

// Stats-Komponente
interface StatsCardsProps {
  currentPensionPoints: number;
  projectedPensionPoints: number;
  expectedStatutoryPension: number;
  totalPrivatePension: number;
  pensionGapCoverage: number;
}

function StatsCards({
  currentPensionPoints,
  projectedPensionPoints,
  expectedStatutoryPension,
  totalPrivatePension,
  pensionGapCoverage,
}: StatsCardsProps) {
  const coverageColor =
    pensionGapCoverage >= 100
      ? 'text-green-600'
      : pensionGapCoverage >= 80
        ? 'text-yellow-600'
        : 'text-red-600';

  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium text-muted-foreground">
            Rentenpunkte
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-bold">{currentPensionPoints.toFixed(1)}</span>
            <span className="text-sm text-muted-foreground">
              → {projectedPensionPoints.toFixed(1)}
            </span>
          </div>
          <p className="text-xs text-muted-foreground mt-1">
            Aktuell → Projektion bei Renteneintritt
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium text-muted-foreground">
            Gesetzliche Rente (mtl.)
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-2xl font-bold">{formatCurrency(expectedStatutoryPension)}</p>
          <p className="text-xs text-muted-foreground mt-1">
            Prognostiziert bei Renteneintritt
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium text-muted-foreground">
            Private Vorsorge (mtl.)
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-2xl font-bold">{formatCurrency(totalPrivatePension)}</p>
          <p className="text-xs text-muted-foreground mt-1">
            Riester + Rürup + bAV + Privat
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium text-muted-foreground">
            Rentenlücken-Deckung
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            <p className={`text-2xl font-bold ${coverageColor}`}>
              {pensionGapCoverage.toFixed(0)}%
            </p>
            <Progress
              value={Math.min(pensionGapCoverage, 100)}
              className="h-2"
            />
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

// Riester/Rürup Card
interface SubsidyCardProps {
  type: 'riester' | 'ruerup';
  currentContribution: number;
  maxContribution: number;
  expectedSubsidy: number;
  taxSaving: number;
  recommendations: string[];
  isLoading: boolean;
}

function SubsidyCard({
  type,
  currentContribution,
  maxContribution,
  expectedSubsidy,
  taxSaving,
  recommendations,
  isLoading,
}: SubsidyCardProps) {
  const title = type === 'riester' ? 'Riester-Rente' : 'Rürup/Basisrente';
  const subtitle = type === 'riester'
    ? 'Staatliche Zulagen und Steuervorteile'
    : 'Steuerlich absetzbare Basisversorgung';

  const utilizationPercent = maxContribution > 0
    ? (currentContribution / maxContribution) * 100
    : 0;

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <Skeleton className="h-6 w-32" />
          <Skeleton className="h-4 w-48" />
        </CardHeader>
        <CardContent>
          <Skeleton className="h-20" />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <PiggyBank className="h-5 w-5" />
          {title}
        </CardTitle>
        <CardDescription>{subtitle}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Auslastung */}
        <div className="space-y-2">
          <div className="flex justify-between text-sm">
            <span>Ausschöpfung Höchstbetrag</span>
            <span className="font-medium">{utilizationPercent.toFixed(0)}%</span>
          </div>
          <Progress value={utilizationPercent} className="h-2" />
          <div className="flex justify-between text-xs text-muted-foreground">
            <span>{formatCurrency(currentContribution)}</span>
            <span>max. {formatCurrency(maxContribution)}</span>
          </div>
        </div>

        {/* Vorteile */}
        <div className="grid grid-cols-2 gap-4">
          <div className="rounded-lg border p-3">
            <p className="text-xs text-muted-foreground">
              {type === 'riester' ? 'Staatliche Zulage' : 'Steuervorteil'}
            </p>
            <p className="text-lg font-bold text-green-600">
              {formatCurrency(type === 'riester' ? expectedSubsidy : taxSaving)}
            </p>
          </div>
          {type === 'riester' && (
            <div className="rounded-lg border p-3">
              <p className="text-xs text-muted-foreground">Steuerersparnis</p>
              <p className="text-lg font-bold text-green-600">{formatCurrency(taxSaving)}</p>
            </div>
          )}
        </div>

        {/* Empfehlungen */}
        {recommendations.length > 0 && (
          <div className="space-y-2 pt-2 border-t">
            <p className="text-sm font-medium">Optimierungspotenzial:</p>
            <ul className="space-y-1">
              {recommendations.slice(0, 2).map((rec, idx) => (
                <li key={idx} className="flex items-start gap-2 text-sm text-muted-foreground">
                  <ChevronRight className="h-4 w-4 mt-0.5 shrink-0 text-blue-500" />
                  <span>{rec}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// Loading State
function LoadingState() {
  return (
    <div className="space-y-6 p-8">
      <div>
        <Skeleton className="h-10 w-64" />
        <Skeleton className="h-4 w-96 mt-2" />
      </div>
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {[1, 2, 3, 4].map((i) => (
          <Skeleton key={i} className="h-32" />
        ))}
      </div>
      <Skeleton className="h-10 w-full" />
      <Skeleton className="h-96" />
    </div>
  );
}

// Main Component
export function RetirementPlanningPage() {
  const [activeTab, setActiveTab] = useState('rechner');

  const { defaultSpaceId, isLoading: spacesLoading, hasSpaces } = useDefaultSpace();
  const spaceId = defaultSpaceId;

  // Verwende RetirementSummary mit Default-Request.
  // Backend-Vertrag (POST .../retirement/summary): birth_date +
  // current_gross_annual_income sind PFLICHT. Die Seite hat (noch) keine
  // Eingabemaske dafür — Standard-Annahmen wie bisher (50.000 € Einkommen,
  // Alter 35); individuelle Berechnung läuft über den Rentenlücken-Rechner-Tab.
  const defaultRequest: RetirementSummaryRequest = {
    birthDate: DEFAULT_BIRTH_DATE,
    currentGrossAnnualIncome: 50000,
  };
  const {
    data: retirementData,
    isLoading: summaryLoading,
    error: summaryError,
  } = useRetirementSummary(spaceId ?? '', spaceId ? defaultRequest : null, {
    enabled: !!spaceId,
  });

  // Riester-Optimierung mit Default-Request (Backend-Vertrag:
  // gross_annual_income + marginal_tax_rate sind Pflicht)
  const riesterRequest: RiesterOptimizationRequest = {
    grossAnnualIncome: 50000,
    marginalTaxRate: 0.35,
    childrenBornAfter2007: 0,
  };
  const { data: riesterOptimization, isLoading: riesterLoading } = useRiesterOptimizationQuery(
    spaceId ?? '',
    spaceId ? riesterRequest : null,
    { enabled: !!spaceId }
  );

  // Rürup wird aus Summary oder Riester abgeleitet (vereinfacht)
  const ruerupOptimization = riesterOptimization ? {
    currentContribution: 0,
    maxContribution: 27565,
    taxSaving: 0,
    recommendations: ['Prüfen Sie Rürup als Ergänzung zur gesetzlichen Rente'],
  } : null;
  const ruerupLoading = riesterLoading;

  const isLoading = spacesLoading || summaryLoading;

  // Erstelle overview-Objekt aus retirementData (echter Backend-Vertrag:
  // die Kennzahlen liegen in pensionGapAnalysis, nicht flach auf der Summary)
  const gap = retirementData?.pensionGapAnalysis;
  const overview = retirementData && gap ? {
    summary: {
      currentPensionPoints: gap.currentPensionPoints,
      projectedPensionPoints: gap.projectedPensionPoints,
      expectedStatutoryPension: gap.expectedStatutoryPension,
      totalPrivatePension:
        gap.expectedRiester + gap.expectedRuerup + gap.expectedBav + gap.expectedPrivate,
      pensionGapCoverage:
        gap.targetMonthlyIncome > 0
          ? (gap.totalExpectedPension / gap.targetMonthlyIncome) * 100
          : 0,
      retirementAge: gap.retirementAge,
    },
  } : null;

  const overviewError = summaryError;

  // Kein Space
  if (!spacesLoading && !hasSpaces) {
    return (
      <div className="flex items-center justify-center h-96 p-8">
        <Card className="max-w-md">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <PiggyBank className="h-5 w-5" />
              Kein Bereich vorhanden
            </CardTitle>
            <CardDescription>
              Erstellen Sie zuerst einen Privat-Bereich, um die Altersvorsorge-Planung zu nutzen.
            </CardDescription>
          </CardHeader>
        </Card>
      </div>
    );
  }

  if (isLoading) {
    return <LoadingState />;
  }

  if (overviewError) {
    return (
      <div className="p-8">
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertTitle>Fehler beim Laden</AlertTitle>
          <AlertDescription>
            Die Altersvorsorge-Daten konnten nicht geladen werden.
          </AlertDescription>
        </Alert>
      </div>
    );
  }

  const summaryData = overview?.summary;

  return (
    <div className="space-y-6 p-8">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold tracking-tight flex items-center gap-2">
              <PiggyBank className="h-8 w-8" />
              Altersvorsorge
            </h1>
            <p className="text-muted-foreground mt-1">
              Rentenlücke berechnen und Vorsorge optimieren
            </p>
          </div>

          {summaryData?.retirementAge && (
            <Badge variant="outline" className="text-lg px-4 py-2">
              Renteneintritt: {summaryData.retirementAge} Jahre
            </Badge>
          )}
        </div>

        {/* Stats Cards */}
        {summaryData && (
          <StatsCards
            currentPensionPoints={summaryData.currentPensionPoints}
            projectedPensionPoints={summaryData.projectedPensionPoints}
            expectedStatutoryPension={summaryData.expectedStatutoryPension}
            totalPrivatePension={summaryData.totalPrivatePension}
            pensionGapCoverage={summaryData.pensionGapCoverage}
          />
        )}

        {/* Warning bei Handlungsbedarf */}
        {summaryData && summaryData.pensionGapCoverage < 80 && (
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertTitle>Handlungsbedarf</AlertTitle>
            <AlertDescription>
              Ihre prognostizierte Rentendeckung liegt bei nur{' '}
              <strong>{summaryData.pensionGapCoverage.toFixed(0)}%</strong>. Wir empfehlen,
              Ihre Altersvorsorge zu überprüfen und zu optimieren.
            </AlertDescription>
          </Alert>
        )}

        {/* Tabs */}
        <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-6">
          <TabsList className="grid w-full grid-cols-4">
            <TabsTrigger value="rechner" className="flex items-center gap-2">
              <Calculator className="h-4 w-4" />
              Rentenlücke
            </TabsTrigger>
            <TabsTrigger value="simulation" className="flex items-center gap-2">
              <BarChart3 className="h-4 w-4" />
              Monte-Carlo
            </TabsTrigger>
            <TabsTrigger value="förderung" className="flex items-center gap-2">
              <Coins className="h-4 w-4" />
              Riester/Rürup
            </TabsTrigger>
            <TabsTrigger value="strategien" className="flex items-center gap-2">
              <TrendingUp className="h-4 w-4" />
              Entnahmestrategien
            </TabsTrigger>
          </TabsList>

          {/* Rentenlücken-Rechner */}
          <TabsContent value="rechner">
            {spaceId && <PensionGapCalculator spaceId={spaceId} />}
          </TabsContent>

          {/* Monte-Carlo-Simulation */}
          <TabsContent value="simulation">
            {spaceId && <MonteCarloSimulation spaceId={spaceId} />}
          </TabsContent>

          {/* Riester/Rürup */}
          <TabsContent value="förderung">
            <div className="grid gap-6 md:grid-cols-2">
              <SubsidyCard
                type="riester"
                // Backend-Vertrag (RiesterOptimization): optimaler Eigenbeitrag,
                // Zulagen-Summe und Steuervorteil; ein Bestandsbeitrag ist im
                // Ergebnis nicht enthalten (Request ohne currentRiesterContribution -> 0).
                currentContribution={0}
                maxContribution={riesterOptimization?.optimalEigenbeitrag ?? 2100}
                expectedSubsidy={riesterOptimization?.totalZulagen ?? 0}
                taxSaving={riesterOptimization?.taxBenefit ?? 0}
                recommendations={riesterOptimization?.recommendations ?? []}
                isLoading={riesterLoading}
              />
              <SubsidyCard
                type="ruerup"
                currentContribution={ruerupOptimization?.currentContribution ?? 0}
                maxContribution={ruerupOptimization?.maxContribution ?? 27565}
                expectedSubsidy={0}
                taxSaving={ruerupOptimization?.taxSaving ?? 0}
                recommendations={ruerupOptimization?.recommendations ?? []}
                isLoading={ruerupLoading}
              />
            </div>

            {/* Zusätzliche Infos */}
            <Card className="mt-6">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Info className="h-5 w-5" />
                  Wissenswertes
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid gap-4 md:grid-cols-2">
                  <div className="space-y-2">
                    <h4 className="font-medium">Riester-Rente (Stand 2026)</h4>
                    <ul className="text-sm text-muted-foreground space-y-1">
                      <li>• Grundzulage: 175 EUR/Jahr</li>
                      <li>• Kinderzulage: 300 EUR/Kind (ab 2008 geboren)</li>
                      <li>• Eigenbeitrag: 4% vom Vorjahres-Brutto</li>
                      <li>• Höchstbetrag: 2.100 EUR inkl. Zulagen</li>
                    </ul>
                  </div>
                  <div className="space-y-2">
                    <h4 className="font-medium">Rürup/Basisrente (Stand 2026)</h4>
                    <ul className="text-sm text-muted-foreground space-y-1">
                      <li>• Höchstbetrag: 27.565 EUR (Ledige)</li>
                      <li>• Absetzbar: 100% (seit 2025)</li>
                      <li>• Besteuerung: Nach Renteneintritt</li>
                      <li>• Keine Kapitalisierung möglich</li>
                    </ul>
                  </div>
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          {/* Entnahmestrategien */}
          <TabsContent value="strategien">
            <div className="grid gap-6 md:grid-cols-2">
              {/* 4%-Regel */}
              <Card>
                <CardHeader>
                  <CardTitle>4%-Regel (SWR)</CardTitle>
                  <CardDescription>
                    Safe Withdrawal Rate - Trinity Study Ansatz
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <p className="text-sm text-muted-foreground">
                    Entnehmen Sie jährlich 4% Ihres Anfangskapitals (inflationsangepasst).
                    Historisch betrachtet hält das Portfolio damit mindestens 30 Jahre.
                  </p>
                  <div className="rounded-lg border p-4 bg-muted/50">
                    <p className="text-sm font-medium">Beispiel:</p>
                    <p className="text-sm text-muted-foreground">
                      Bei 500.000 EUR Kapital → 20.000 EUR/Jahr → 1.667 EUR/Monat
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge variant="outline" className="bg-green-50">Erfolgsrate: ~95%</Badge>
                    <Badge variant="outline">30 Jahre Horizont</Badge>
                  </div>
                </CardContent>
              </Card>

              {/* Dynamische Entnahme */}
              <Card>
                <CardHeader>
                  <CardTitle>Dynamische Entnahme</CardTitle>
                  <CardDescription>
                    Anpassung an Marktentwicklung
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <p className="text-sm text-muted-foreground">
                    Entnahmerate variiert basierend auf Portfolio-Performance.
                    In guten Jahren mehr, in schlechten Jahren weniger entnehmen.
                  </p>
                  <div className="rounded-lg border p-4 bg-muted/50">
                    <p className="text-sm font-medium">Regeln:</p>
                    <ul className="text-sm text-muted-foreground space-y-1 mt-1">
                      <li>• Basis: 4% des aktuellen Portfolio-Werts</li>
                      <li>• Floor: -5% vs. Vorjahr</li>
                      <li>• Cap: +10% vs. Vorjahr</li>
                    </ul>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge variant="outline" className="bg-green-50">Erfolgsrate: ~98%</Badge>
                    <Badge variant="outline">Variable Einnahmen</Badge>
                  </div>
                </CardContent>
              </Card>

              {/* Bucket-Strategie */}
              <Card>
                <CardHeader>
                  <CardTitle>Bucket-Strategie</CardTitle>
                  <CardDescription>
                    Zeitbasierte Aufteilung des Vermögens
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <p className="text-sm text-muted-foreground">
                    Vermögen in Zeitabschnitte (Buckets) aufteilen.
                    Kurzfristig sicher, langfristig in Aktien.
                  </p>
                  <div className="space-y-2">
                    <div className="flex items-center justify-between text-sm">
                      <span>Bucket 1 (0-3 Jahre)</span>
                      <Badge>Tagesgeld/Anleihen</Badge>
                    </div>
                    <div className="flex items-center justify-between text-sm">
                      <span>Bucket 2 (4-10 Jahre)</span>
                      <Badge>Mischfonds</Badge>
                    </div>
                    <div className="flex items-center justify-between text-sm">
                      <span>Bucket 3 (10+ Jahre)</span>
                      <Badge>Aktien-ETFs</Badge>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge variant="outline" className="bg-green-50">Psychologisch vorteilhaft</Badge>
                  </div>
                </CardContent>
              </Card>

              {/* Variable Percentage Withdrawal */}
              <Card>
                <CardHeader>
                  <CardTitle>VPW (Variable Percentage)</CardTitle>
                  <CardDescription>
                    Alterbasierte Entnahme
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <p className="text-sm text-muted-foreground">
                    Entnahmerate steigt mit dem Alter, da die verbleibende
                    Lebenserwartung sinkt. Basiert auf Sterbetafeln.
                  </p>
                  <div className="rounded-lg border p-4 bg-muted/50">
                    <p className="text-sm font-medium">Beispiel:</p>
                    <ul className="text-sm text-muted-foreground space-y-1 mt-1">
                      <li>• Alter 65: 3,5%</li>
                      <li>• Alter 75: 5,0%</li>
                      <li>• Alter 85: 7,5%</li>
                    </ul>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge variant="outline" className="bg-green-50">Kapitalaufbrauchend</Badge>
                    <Badge variant="outline">Höhere Entnahmen</Badge>
                  </div>
                </CardContent>
              </Card>
            </div>
          </TabsContent>
        </Tabs>
    </div>
  );
}

export default RetirementPlanningPage;
