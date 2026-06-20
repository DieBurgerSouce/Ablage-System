/**
 * Estate Planning Page - Nachlassplanung
 *
 * Hauptseite für die Nachlassplanung mit:
 * - Vermögensübersicht
 * - Erbschaftsteuer-Rechner
 * - Begünstigte-Verwaltung
 * - Vollmachten-Management
 * - Nießbrauch-Berechnung
 */

import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { Badge } from '@/components/ui/badge';
import {
  Scale,
  Users,
  FileText,
  Calculator,
  Clock,
  AlertCircle,
  TrendingUp,
  Building2,
  Car,
  Wallet,
  PiggyBank,
  AlertTriangle,
  CheckCircle2,
  Landmark,
} from 'lucide-react';

import { useDefaultSpace } from '../hooks/use-privat-queries';
import { useEstateOverview } from './hooks';
import { AssetDistribution } from './AssetDistribution';
import { InheritanceTaxCalculator } from './InheritanceTaxCalculator';
import { BeneficiaryList } from './BeneficiaryList';
import { PowerOfAttorneyManager } from './PowerOfAttorneyManager';
import { NiessbrauchCalculator } from './NiessbrauchCalculator';
import { TimeControlledAccess } from './TimeControlledAccess';

// ==================== Currency Formatter ====================

const formatCurrency = (value: number): string => {
  return new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency: 'EUR',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);
};

// ==================== Summary Cards ====================

interface SummaryCardsProps {
  netEstate: number;
  totalAssets: number;
  totalLiabilities: number;
  totalTax: number;
  beneficiaryCount: number;
  poaCount: number;
  missingPoaCount: number;
}

function SummaryCards({
  netEstate,
  totalAssets,
  totalLiabilities,
  totalTax,
  beneficiaryCount,
  poaCount,
  missingPoaCount,
}: SummaryCardsProps) {
  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Netto-Nachlass</CardTitle>
          <Landmark className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">{formatCurrency(netEstate)}</div>
          <p className="text-xs text-muted-foreground">
            Vermögen: {formatCurrency(totalAssets)} | Schulden: {formatCurrency(totalLiabilities)}
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Geschätzte Erbschaftsteuer</CardTitle>
          <Scale className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold text-orange-600">{formatCurrency(totalTax)}</div>
          <p className="text-xs text-muted-foreground">
            {netEstate > 0
              ? `${((totalTax / netEstate) * 100).toFixed(1)}% des Nachlasses`
              : 'Kein Nachlass'}
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Begünstigte</CardTitle>
          <Users className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">{beneficiaryCount}</div>
          <p className="text-xs text-muted-foreground">
            Erben und Vermächtnisnehmer
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Vollmachten</CardTitle>
          <FileText className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="flex items-center gap-2">
            <span className="text-2xl font-bold">{poaCount}</span>
            {missingPoaCount > 0 && (
              <Badge variant="destructive" className="text-xs">
                {missingPoaCount} fehlen
              </Badge>
            )}
          </div>
          <p className="text-xs text-muted-foreground">
            Vorsorge-, General- und Bankvollmachten
          </p>
        </CardContent>
      </Card>
    </div>
  );
}

// ==================== Warnings Section ====================

interface WarningsSectionProps {
  warnings: string[];
  missingPoas: string[];
}

function WarningsSection({ warnings, missingPoas }: WarningsSectionProps) {
  if (warnings.length === 0 && missingPoas.length === 0) {
    return null;
  }

  return (
    <div className="space-y-4">
      {missingPoas.length > 0 && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Fehlende Vollmachten</AlertTitle>
          <AlertDescription>
            <p className="mb-2">
              Folgende wichtige Vollmachten fehlen noch:
            </p>
            <ul className="list-disc list-inside">
              {missingPoas.map((poa) => (
                <li key={poa}>{poa}</li>
              ))}
            </ul>
          </AlertDescription>
        </Alert>
      )}

      {warnings.map((warning, index) => (
        <Alert key={index}>
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>{warning}</AlertDescription>
        </Alert>
      ))}
    </div>
  );
}

// ==================== Recommendations Section ====================

interface RecommendationsSectionProps {
  recommendations: string[];
}

function RecommendationsSection({ recommendations }: RecommendationsSectionProps) {
  if (recommendations.length === 0) {
    return null;
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <CheckCircle2 className="h-5 w-5 text-green-600" />
          Empfehlungen
        </CardTitle>
        <CardDescription>
          Tipps zur Optimierung Ihrer Nachlassplanung
        </CardDescription>
      </CardHeader>
      <CardContent>
        <ul className="space-y-2">
          {recommendations.map((rec, index) => (
            <li key={index} className="flex items-start gap-2 text-sm">
              <TrendingUp className="h-4 w-4 mt-0.5 text-green-600 shrink-0" />
              <span>{rec}</span>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}

// ==================== Asset Overview ====================

interface AssetOverviewProps {
  realEstateValue: number;
  investmentValue: number;
  vehicleValue: number;
  otherAssets: number;
  mortgageDebt: number;
  otherDebt: number;
}

function AssetOverview({
  realEstateValue,
  investmentValue,
  vehicleValue,
  otherAssets,
  mortgageDebt,
  otherDebt,
}: AssetOverviewProps) {
  const totalAssets = realEstateValue + investmentValue + vehicleValue + otherAssets;
  const totalLiabilities = mortgageDebt + otherDebt;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Wallet className="h-5 w-5" />
          Vermögensübersicht
        </CardTitle>
        <CardDescription>
          Aufschlüsselung nach Vermögensklassen
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          {/* Vermögen */}
          <div className="space-y-2">
            <h4 className="font-semibold text-sm text-green-700 dark:text-green-400">
              Aktiva ({formatCurrency(totalAssets)})
            </h4>
            <div className="grid gap-2">
              {realEstateValue > 0 && (
                <div className="flex items-center justify-between text-sm">
                  <span className="flex items-center gap-2">
                    <Building2 className="h-4 w-4" />
                    Immobilien
                  </span>
                  <span>{formatCurrency(realEstateValue)}</span>
                </div>
              )}
              {investmentValue > 0 && (
                <div className="flex items-center justify-between text-sm">
                  <span className="flex items-center gap-2">
                    <TrendingUp className="h-4 w-4" />
                    Kapitalanlagen
                  </span>
                  <span>{formatCurrency(investmentValue)}</span>
                </div>
              )}
              {vehicleValue > 0 && (
                <div className="flex items-center justify-between text-sm">
                  <span className="flex items-center gap-2">
                    <Car className="h-4 w-4" />
                    Fahrzeuge
                  </span>
                  <span>{formatCurrency(vehicleValue)}</span>
                </div>
              )}
              {otherAssets > 0 && (
                <div className="flex items-center justify-between text-sm">
                  <span className="flex items-center gap-2">
                    <PiggyBank className="h-4 w-4" />
                    Sonstiges
                  </span>
                  <span>{formatCurrency(otherAssets)}</span>
                </div>
              )}
            </div>
          </div>

          {/* Verbindlichkeiten */}
          {totalLiabilities > 0 && (
            <div className="space-y-2 pt-2 border-t">
              <h4 className="font-semibold text-sm text-red-700 dark:text-red-400">
                Passiva ({formatCurrency(totalLiabilities)})
              </h4>
              <div className="grid gap-2">
                {mortgageDebt > 0 && (
                  <div className="flex items-center justify-between text-sm">
                    <span>Hypothekenschulden</span>
                    <span className="text-red-600">-{formatCurrency(mortgageDebt)}</span>
                  </div>
                )}
                {otherDebt > 0 && (
                  <div className="flex items-center justify-between text-sm">
                    <span>Sonstige Schulden</span>
                    <span className="text-red-600">-{formatCurrency(otherDebt)}</span>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

// ==================== Loading State ====================

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
      <div className="grid gap-4 md:grid-cols-2">
        <Skeleton className="h-64" />
        <Skeleton className="h-64" />
      </div>
    </div>
  );
}

// ==================== Main Component ====================

export function EstatePlanningPage() {
  const { defaultSpaceId, isLoading: spacesLoading, hasSpaces } = useDefaultSpace();
  const spaceId = defaultSpaceId;

  const {
    data: overview,
    isLoading: overviewLoading,
    error: overviewError,
    refetch: refetchOverview,
  } = useEstateOverview(spaceId ?? '', {
    enabled: !!spaceId,
  });

  const isLoading = spacesLoading || overviewLoading;

  // Kein Space vorhanden
  if (!spacesLoading && !hasSpaces) {
    return (
      <div className="flex items-center justify-center h-96 p-8">
        <Card className="max-w-md">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Scale className="h-5 w-5" />
              Kein Bereich vorhanden
            </CardTitle>
            <CardDescription>
              Erstellen Sie zuerst einen Privat-Bereich, um die Nachlassplanung zu nutzen.
            </CardDescription>
          </CardHeader>
        </Card>
      </div>
    );
  }

  // Loading State
  if (isLoading) {
    return <LoadingState />;
  }

  // Error State
  if (overviewError) {
    return (
      <div className="p-8">
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertTitle>Fehler beim Laden</AlertTitle>
          <AlertDescription>
            Die Nachlassplanung konnte nicht geladen werden.
            <Button
              variant="outline"
              size="sm"
              className="ml-4"
              onClick={() => refetchOverview()}
            >
              Erneut versuchen
            </Button>
          </AlertDescription>
        </Alert>
      </div>
    );
  }

  const summary = overview?.summary;

  return (
    <div className="space-y-6 p-8">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold tracking-tight flex items-center gap-3">
          <Scale className="h-8 w-8" />
          Nachlassplanung
        </h1>
        <p className="text-muted-foreground mt-1">
          Erbschaftsteuer-Planung, Begünstigte und Vollmachten verwalten
        </p>
      </div>

      {/* Summary Cards */}
      {summary && (
        <SummaryCards
          netEstate={summary.netEstate}
          totalAssets={summary.totalAssets}
          totalLiabilities={summary.totalLiabilities}
          totalTax={summary.totalEstimatedTax}
          beneficiaryCount={summary.beneficiaries.length}
          poaCount={summary.activePowersOfAttorney.length}
          missingPoaCount={summary.missingEssentialPoas.length}
        />
      )}

      {/* Warnings */}
      {summary && (
        <WarningsSection
          warnings={summary.warnings}
          missingPoas={summary.missingEssentialPoas}
        />
      )}

      {/* Main Tabs */}
      <Tabs defaultValue="overview" className="space-y-6">
        <TabsList className="grid w-full grid-cols-2 lg:grid-cols-6 lg:w-auto">
          <TabsTrigger value="overview" className="flex items-center gap-2">
            <Wallet className="h-4 w-4" />
            Übersicht
          </TabsTrigger>
          <TabsTrigger value="beneficiaries" className="flex items-center gap-2">
            <Users className="h-4 w-4" />
            Begünstigte
          </TabsTrigger>
          <TabsTrigger value="tax" className="flex items-center gap-2">
            <Calculator className="h-4 w-4" />
            Steuer
          </TabsTrigger>
          <TabsTrigger value="poa" className="flex items-center gap-2">
            <FileText className="h-4 w-4" />
            Vollmachten
          </TabsTrigger>
          <TabsTrigger value="usufruct" className="flex items-center gap-2">
            <Building2 className="h-4 w-4" />
            Niessbrauch
          </TabsTrigger>
          <TabsTrigger value="access" className="flex items-center gap-2">
            <Clock className="h-4 w-4" />
            Zugriff
          </TabsTrigger>
        </TabsList>

        {/* Overview Tab */}
        <TabsContent value="overview" className="space-y-6">
          <div className="grid gap-6 md:grid-cols-2">
            {summary && (
              <AssetOverview
                realEstateValue={summary.realEstateValue}
                investmentValue={summary.investmentValue}
                vehicleValue={summary.vehicleValue}
                otherAssets={summary.otherAssets}
                mortgageDebt={summary.mortgageDebt}
                otherDebt={summary.otherDebt}
              />
            )}
            <AssetDistribution
              summary={summary ?? null}
              giftPlans={overview?.giftPlans ?? []}
            />
          </div>
          {summary && (
            <RecommendationsSection recommendations={summary.recommendations} />
          )}
        </TabsContent>

        {/* Beneficiaries Tab */}
        <TabsContent value="beneficiaries">
          {spaceId && <BeneficiaryList spaceId={spaceId} />}
        </TabsContent>

        {/* Tax Calculator Tab */}
        <TabsContent value="tax">
          {spaceId && (
            <InheritanceTaxCalculator
              spaceId={spaceId}
              taxCalculation={overview?.taxCalculation ?? null}
            />
          )}
        </TabsContent>

        {/* Powers of Attorney Tab */}
        <TabsContent value="poa">
          {spaceId && <PowerOfAttorneyManager spaceId={spaceId} />}
        </TabsContent>

        {/* Usufruct Calculator Tab */}
        <TabsContent value="usufruct">
          {spaceId && <NiessbrauchCalculator spaceId={spaceId} />}
        </TabsContent>

        {/* Time-Controlled Access Tab */}
        <TabsContent value="access">
          {spaceId && <TimeControlledAccess spaceId={spaceId} />}
        </TabsContent>
      </Tabs>
    </div>
  );
}

export default EstatePlanningPage;
