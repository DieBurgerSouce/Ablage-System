/**
 * SteuerPage - Steueroptimierung Dashboard
 *
 * Hauptseite fuer Steuer-relevante Informationen:
 * - Absetzbare Betraege nach Kategorie
 * - Fristen-Kalender
 * - DATEV-Export
 * - Absetzbarkeits-Checker
 */

import { useState } from 'react';
import {
  Calculator,
  Calendar,
  Download,
  FileSearch,
  Info,
  TrendingUp,
  AlertTriangle,
} from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Skeleton } from '@/components/ui/skeleton';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

import { SteuerKategorien } from './components/SteuerKategorien';
import { FristenKalender } from './components/FristenKalender';
import { AbsetzbarkeitsChecker } from './components/AbsetzbarkeitsChecker';
import { DATEVExportButton } from './components/DATEVExportButton';
import { useTaxOptimization, useTaxDeadlines, useYearComparison } from './hooks';
import { useDefaultSpace } from '../hooks/use-privat-queries';

// Hilfsfunktion fuer Waehrungsformatierung
const formatCurrency = (value: number): string => {
  return new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency: 'EUR',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);
};

export function SteuerPage() {
  const currentYear = new Date().getFullYear();
  const [selectedYear, setSelectedYear] = useState(currentYear);
  const [activeTab, setActiveTab] = useState('kategorien');

  // Space ID
  const { defaultSpaceId, isLoading: spaceLoading } = useDefaultSpace();
  const spaceId = defaultSpaceId ?? '';

  // Queries
  const { data: taxOptimization, isLoading: taxLoading } = useTaxOptimization(
    spaceId,
    { taxYear: selectedYear },
    { enabled: !!spaceId }
  );
  const { data: deadlinesData, isLoading: deadlinesLoading } = useTaxDeadlines(
    spaceId,
    selectedYear,
    { enabled: !!spaceId }
  );
  const { data: comparison, isLoading: comparisonLoading } = useYearComparison(
    spaceId,
    selectedYear,
    { enabled: !!spaceId }
  );

  // Daten extrahieren
  const deductions = taxOptimization;
  const deadlines = deadlinesData?.upcoming ?? [];

  const isLoading = spaceLoading || taxLoading || deadlinesLoading || comparisonLoading;

  // Gesamtsumme berechnen
  const totalDeductible = deductions?.summaries?.reduce(
    (sum, s) => sum + s.totalDeductible,
    0
  ) ?? 0;

  // Naechste wichtige Frist
  const nextDeadline = deadlines?.find((d) => new Date(d.dueDate) > new Date());

  // Jahre fuer Auswahl (letzte 3 Jahre)
  const years = [currentYear, currentYear - 1, currentYear - 2];

  if (isLoading) {
    return (
      <div className="container mx-auto py-6 space-y-6">
        <Skeleton className="h-10 w-64" />
        <div className="grid gap-4 md:grid-cols-4">
          {[1, 2, 3, 4].map((i) => (
            <Skeleton key={i} className="h-32" />
          ))}
        </div>
        <Skeleton className="h-96" />
      </div>
    );
  }

  return (
    <div className="container mx-auto py-6 space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold tracking-tight flex items-center gap-2">
              <Calculator className="h-8 w-8" />
              Steueroptimierung
            </h1>
            <p className="text-muted-foreground mt-1">
              Ueberblick ueber absetzbare Betraege und Steuerfristen
            </p>
          </div>

          <div className="flex items-center gap-4">
            <Select
              value={selectedYear.toString()}
              onValueChange={(v) => setSelectedYear(parseInt(v, 10))}
            >
              <SelectTrigger className="w-32">
                <SelectValue placeholder="Jahr" />
              </SelectTrigger>
              <SelectContent>
                {years.map((year) => (
                  <SelectItem key={year} value={year.toString()}>
                    {year}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>

            <DATEVExportButton year={selectedYear} />
          </div>
        </div>

        {/* Statistik-Karten */}
        <div className="grid gap-4 md:grid-cols-4">
          {/* Gesamt absetzbar */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Gesamt absetzbar
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-2xl font-bold text-green-600">
                {formatCurrency(totalDeductible)}
              </p>
              <p className="text-xs text-muted-foreground mt-1">
                {deductions?.summaries?.length ?? 0} Kategorien
              </p>
            </CardContent>
          </Card>

          {/* Geschaetzte Erstattung */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Gesch. Erstattung
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-2xl font-bold">
                {formatCurrency(deductions?.estimatedRefund ?? 0)}
              </p>
              <p className="text-xs text-muted-foreground mt-1">
                bei 35% Grenzsteuersatz
              </p>
            </CardContent>
          </Card>

          {/* Vergleich Vorjahr */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                vs. Vorjahr
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex items-center gap-2">
                {comparison?.change !== undefined && (
                  <>
                    <TrendingUp
                      className={`h-5 w-5 ${
                        comparison.change >= 0 ? 'text-green-500' : 'text-red-500 rotate-180'
                      }`}
                    />
                    <span
                      className={`text-2xl font-bold ${
                        comparison.change >= 0 ? 'text-green-600' : 'text-red-600'
                      }`}
                    >
                      {comparison.change >= 0 ? '+' : ''}
                      {comparison.change.toFixed(1)}%
                    </span>
                  </>
                )}
              </div>
              <p className="text-xs text-muted-foreground mt-1">
                {comparison?.previousYearTotal !== undefined
                  ? `Vorjahr: ${formatCurrency(comparison.previousYearTotal)}`
                  : 'Keine Vorjahresdaten'}
              </p>
            </CardContent>
          </Card>

          {/* Naechste Frist */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Naechste Frist
              </CardTitle>
            </CardHeader>
            <CardContent>
              {nextDeadline ? (
                <>
                  <p className="text-lg font-semibold">{nextDeadline.name}</p>
                  <div className="flex items-center gap-2 mt-1">
                    <Calendar className="h-4 w-4 text-muted-foreground" />
                    <span className="text-sm">
                      {new Date(nextDeadline.dueDate).toLocaleDateString('de-DE')}
                    </span>
                    {nextDeadline.daysRemaining !== undefined && nextDeadline.daysRemaining <= 14 && (
                      <Badge variant="destructive" className="text-xs">
                        {nextDeadline.daysRemaining} Tage
                      </Badge>
                    )}
                  </div>
                </>
              ) : (
                <p className="text-muted-foreground">Keine Fristen</p>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Warnung fuer kritische Fristen */}
        {nextDeadline && nextDeadline.daysRemaining !== undefined && nextDeadline.daysRemaining <= 7 && (
          <Alert variant="destructive">
            <AlertTriangle className="h-4 w-4" />
            <AlertTitle>Frist beachten!</AlertTitle>
            <AlertDescription>
              Die Frist fuer <strong>{nextDeadline.name}</strong> endet in{' '}
              {nextDeadline.daysRemaining} Tagen (
              {new Date(nextDeadline.dueDate).toLocaleDateString('de-DE')}).
            </AlertDescription>
          </Alert>
        )}

        {/* Tabs */}
        <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-6">
          <TabsList className="grid w-full grid-cols-3">
            <TabsTrigger value="kategorien" className="flex items-center gap-2">
              <Calculator className="h-4 w-4" />
              Kategorien
            </TabsTrigger>
            <TabsTrigger value="fristen" className="flex items-center gap-2">
              <Calendar className="h-4 w-4" />
              Fristen
            </TabsTrigger>
            <TabsTrigger value="checker" className="flex items-center gap-2">
              <FileSearch className="h-4 w-4" />
              Absetzbarkeit pruefen
            </TabsTrigger>
          </TabsList>

          {/* Kategorien Tab */}
          <TabsContent value="kategorien">
            <div className="grid gap-6 lg:grid-cols-3">
              <div className="lg:col-span-2">
                <SteuerKategorien
                  summaries={deductions?.summaries ?? []}
                  isLoading={taxLoading}
                />
              </div>
              <div className="space-y-4">
                {/* Tipps */}
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2 text-base">
                      <Info className="h-5 w-5" />
                      Steuer-Tipps
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    {deductions?.tips?.map((tip, idx) => (
                      <div
                        key={idx}
                        className="flex items-start gap-2 text-sm"
                      >
                        <div className="h-1.5 w-1.5 bg-blue-500 rounded-full mt-2" />
                        <p className="text-muted-foreground">{tip}</p>
                      </div>
                    )) ?? (
                      <p className="text-sm text-muted-foreground">
                        Laden Sie mehr Belege hoch, um personalisierte Tipps zu erhalten.
                      </p>
                    )}
                  </CardContent>
                </Card>

                {/* Nicht genutzte Potenziale */}
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2 text-base">
                      <TrendingUp className="h-5 w-5" />
                      Ungenutztes Potenzial
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    {deductions?.unusedPotential?.map((item, idx) => (
                      <div
                        key={idx}
                        className="flex items-center justify-between"
                      >
                        <span className="text-sm">{item.category}</span>
                        <Badge variant="secondary">
                          {formatCurrency(item.remainingLimit)}
                        </Badge>
                      </div>
                    )) ?? (
                      <p className="text-sm text-muted-foreground">
                        Alle Hoechstbetraege sind ausgeschoepft.
                      </p>
                    )}
                  </CardContent>
                </Card>
              </div>
            </div>
          </TabsContent>

          {/* Fristen Tab */}
          <TabsContent value="fristen">
            <FristenKalender
              deadlines={deadlines ?? []}
              year={selectedYear}
              isLoading={deadlinesLoading}
            />
          </TabsContent>

          {/* Checker Tab */}
          <TabsContent value="checker">
            <AbsetzbarkeitsChecker year={selectedYear} />
          </TabsContent>
        </Tabs>
    </div>
  );
}

export default SteuerPage;
