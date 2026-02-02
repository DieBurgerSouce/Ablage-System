/**
 * PensionGapCalculator Component
 *
 * Interaktiver Rentenluecken-Rechner mit Eingabeformular
 * und detaillierter Ergebnis-Visualisierung.
 */

import * as React from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Slider } from '@/components/ui/slider';
import { Skeleton } from '@/components/ui/skeleton';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Progress } from '@/components/ui/progress';
import {
  Calculator,
  AlertTriangle,
  TrendingUp,
  Target,
  Coins,
  PiggyBank,
  ChevronRight,
  Info,
} from 'lucide-react';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { useCalculatePensionGap } from '../hooks/useRetirementQueries';
import type { PensionGapResult, PensionGapRequest } from '@/lib/api/services/retirement';

interface PensionGapCalculatorProps {
  spaceId: string;
  initialData?: Partial<PensionGapRequest>;
  onCalculated?: (result: PensionGapResult) => void;
}

// Formatierung
const formatCurrency = (value: number): string =>
  new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency: 'EUR',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);

const formatPercent = (value: number): string =>
  new Intl.NumberFormat('de-DE', {
    style: 'percent',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);

export function PensionGapCalculator({
  spaceId,
  initialData,
  onCalculated,
}: PensionGapCalculatorProps) {
  // Form State
  const [birthDate, setBirthDate] = React.useState(initialData?.birthDate ?? '1980-01-01');
  const [grossIncome, setGrossIncome] = React.useState(initialData?.currentGrossAnnualIncome ?? 50000);
  const [replacementRatio, setReplacementRatio] = React.useState(
    (initialData?.targetReplacementRatio ?? 0.8) * 100
  );
  const [pensionPoints, setPensionPoints] = React.useState(initialData?.currentPensionPoints ?? 0);
  const [retirementAge, setRetirementAge] = React.useState(initialData?.retirementAge ?? 67);

  // Result State
  const [result, setResult] = React.useState<PensionGapResult | null>(null);

  // Mutation
  const calculateMutation = useCalculatePensionGap();

  const handleCalculate = async () => {
    const request: PensionGapRequest = {
      birthDate,
      currentGrossAnnualIncome: grossIncome,
      targetReplacementRatio: replacementRatio / 100,
      currentPensionPoints: pensionPoints,
      retirementAge,
    };

    try {
      const data = await calculateMutation.mutateAsync({ spaceId, request });
      setResult(data);
      onCalculated?.(data);
    } catch (error) {
      // Error wird vom API-Client behandelt
    }
  };

  // Berechne Alter aus Geburtsdatum
  const currentAge = React.useMemo(() => {
    const birth = new Date(birthDate);
    const today = new Date();
    let age = today.getFullYear() - birth.getFullYear();
    const monthDiff = today.getMonth() - birth.getMonth();
    if (monthDiff < 0 || (monthDiff === 0 && today.getDate() < birth.getDate())) {
      age--;
    }
    return age;
  }, [birthDate]);

  const yearsToRetirement = Math.max(0, retirementAge - currentAge);

  return (
    <div className="space-y-6">
      {/* Eingabe-Formular */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Calculator className="h-5 w-5" />
            Rentenluecken-Rechner
          </CardTitle>
          <CardDescription>
            Berechnen Sie Ihre voraussichtliche Rentenluecke und den erforderlichen Sparbetrag.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="grid gap-6 md:grid-cols-2">
            {/* Geburtsdatum */}
            <div className="space-y-2">
              <Label htmlFor="birthDate">Geburtsdatum</Label>
              <Input
                id="birthDate"
                type="date"
                value={birthDate}
                onChange={(e) => setBirthDate(e.target.value)}
              />
              <p className="text-sm text-muted-foreground">
                Aktuelles Alter: {currentAge} Jahre
              </p>
            </div>

            {/* Bruttoeinkommen */}
            <div className="space-y-2">
              <Label htmlFor="grossIncome">Bruttojahreseinkommen</Label>
              <div className="relative">
                <Input
                  id="grossIncome"
                  type="number"
                  value={grossIncome}
                  onChange={(e) => setGrossIncome(Number(e.target.value))}
                  className="pr-12"
                />
                <span className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground">
                  EUR
                </span>
              </div>
            </div>

            {/* Rentenalter */}
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <Label>Geplantes Rentenalter</Label>
                <span className="text-sm font-medium">{retirementAge} Jahre</span>
              </div>
              <Slider
                value={[retirementAge]}
                onValueChange={([value]) => setRetirementAge(value)}
                min={60}
                max={70}
                step={1}
              />
              <p className="text-sm text-muted-foreground">
                Noch {yearsToRetirement} Jahre bis zur Rente
              </p>
            </div>

            {/* Ersatzquote */}
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Label>Ziel-Ersatzquote</Label>
                  <TooltipProvider>
                    <Tooltip>
                      <TooltipTrigger>
                        <Info className="h-4 w-4 text-muted-foreground" />
                      </TooltipTrigger>
                      <TooltipContent className="max-w-xs">
                        <p>
                          Wie viel Prozent Ihres aktuellen Nettoeinkommens moechten Sie
                          im Ruhestand haben? 80% ist ein gaengiger Richtwert.
                        </p>
                      </TooltipContent>
                    </Tooltip>
                  </TooltipProvider>
                </div>
                <span className="text-sm font-medium">{replacementRatio}%</span>
              </div>
              <Slider
                value={[replacementRatio]}
                onValueChange={([value]) => setReplacementRatio(value)}
                min={50}
                max={100}
                step={5}
              />
            </div>

            {/* Bereits erworbene Rentenpunkte */}
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <Label htmlFor="pensionPoints">Bereits erworbene Rentenpunkte</Label>
                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger>
                      <Info className="h-4 w-4 text-muted-foreground" />
                    </TooltipTrigger>
                    <TooltipContent className="max-w-xs">
                      <p>
                        Finden Sie diese Information auf Ihrer Renteninformation
                        der Deutschen Rentenversicherung.
                      </p>
                    </TooltipContent>
                  </Tooltip>
                </TooltipProvider>
              </div>
              <Input
                id="pensionPoints"
                type="number"
                step="0.1"
                value={pensionPoints}
                onChange={(e) => setPensionPoints(Number(e.target.value))}
              />
            </div>
          </div>

          <Button
            onClick={handleCalculate}
            disabled={calculateMutation.isPending}
            className="w-full"
          >
            {calculateMutation.isPending ? (
              'Berechnung laeuft...'
            ) : (
              <>
                Rentenluecke berechnen
                <ChevronRight className="ml-2 h-4 w-4" />
              </>
            )}
          </Button>
        </CardContent>
      </Card>

      {/* Loading */}
      {calculateMutation.isPending && (
        <Card>
          <CardContent className="pt-6">
            <div className="space-y-4">
              <Skeleton className="h-4 w-3/4" />
              <Skeleton className="h-4 w-1/2" />
              <Skeleton className="h-32" />
            </div>
          </CardContent>
        </Card>
      )}

      {/* Ergebnis */}
      {result && !calculateMutation.isPending && (
        <PensionGapResultCard result={result} />
      )}

      {/* Fehler */}
      {calculateMutation.isError && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Berechnungsfehler</AlertTitle>
          <AlertDescription>
            Die Rentenluecke konnte nicht berechnet werden. Bitte versuchen Sie es erneut.
          </AlertDescription>
        </Alert>
      )}
    </div>
  );
}

// ==================== Result Card ====================

interface PensionGapResultCardProps {
  result: PensionGapResult;
}

function PensionGapResultCard({ result }: PensionGapResultCardProps) {
  // Prozentuale Deckung
  const coveragePercent =
    result.targetMonthlyIncome > 0
      ? (result.totalExpectedPension / result.targetMonthlyIncome) * 100
      : 100;

  // Farbe basierend auf Deckung
  const coverageColor =
    coveragePercent >= 100
      ? 'text-green-600'
      : coveragePercent >= 80
        ? 'text-yellow-600'
        : 'text-red-600';

  const progressColor =
    coveragePercent >= 100
      ? 'bg-green-500'
      : coveragePercent >= 80
        ? 'bg-yellow-500'
        : 'bg-red-500';

  return (
    <div className="space-y-6">
      {/* Hauptergebnis */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Target className="h-5 w-5" />
            Ihre Rentenluecke
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Deckungsfortschritt */}
          <div className="space-y-2">
            <div className="flex items-center justify-between text-sm">
              <span>Prognostizierte Deckung</span>
              <span className={coverageColor}>{coveragePercent.toFixed(0)}%</span>
            </div>
            <Progress value={Math.min(coveragePercent, 100)} className={progressColor} />
          </div>

          {/* Hauptzahlen */}
          <div className="grid gap-4 md:grid-cols-3">
            <div className="rounded-lg border p-4 text-center">
              <p className="text-sm text-muted-foreground">Zieleinkommen</p>
              <p className="text-2xl font-bold">{formatCurrency(result.targetMonthlyIncome)}</p>
              <p className="text-xs text-muted-foreground">/Monat</p>
            </div>
            <div className="rounded-lg border p-4 text-center">
              <p className="text-sm text-muted-foreground">Prognostizierte Rente</p>
              <p className="text-2xl font-bold text-green-600">
                {formatCurrency(result.totalExpectedPension)}
              </p>
              <p className="text-xs text-muted-foreground">/Monat</p>
            </div>
            <div className="rounded-lg border p-4 text-center bg-red-50 dark:bg-red-950">
              <p className="text-sm text-muted-foreground">Rentenluecke</p>
              <p className="text-2xl font-bold text-red-600">
                {formatCurrency(result.pensionGap)}
              </p>
              <p className="text-xs text-muted-foreground">/Monat</p>
            </div>
          </div>

          {/* Rentenquellen-Aufschluesselung */}
          <div className="space-y-3">
            <h4 className="font-medium">Rentenquellen-Aufschluesselung</h4>
            <div className="space-y-2">
              <PensionSourceRow
                label="Gesetzliche Rente (DRV)"
                value={result.expectedStatutoryPension}
                total={result.targetMonthlyIncome}
                icon={<Coins className="h-4 w-4" />}
              />
              <PensionSourceRow
                label="Riester-Rente"
                value={result.expectedRiester}
                total={result.targetMonthlyIncome}
                icon={<PiggyBank className="h-4 w-4" />}
              />
              <PensionSourceRow
                label="Ruerup/Basisrente"
                value={result.expectedRuerup}
                total={result.targetMonthlyIncome}
                icon={<PiggyBank className="h-4 w-4" />}
              />
              <PensionSourceRow
                label="Betriebliche Altersvorsorge"
                value={result.expectedBav}
                total={result.targetMonthlyIncome}
                icon={<TrendingUp className="h-4 w-4" />}
              />
              <PensionSourceRow
                label="Private Vorsorge"
                value={result.expectedPrivate}
                total={result.targetMonthlyIncome}
                icon={<PiggyBank className="h-4 w-4" />}
              />
              <PensionSourceRow
                label="Investment-Einkommen (4%-Regel)"
                value={result.expectedInvestmentIncome}
                total={result.targetMonthlyIncome}
                icon={<TrendingUp className="h-4 w-4" />}
              />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Rentenpunkte */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Rentenpunkte-Prognose</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="rounded-lg border p-4">
              <p className="text-sm text-muted-foreground">Aktuell erworben</p>
              <p className="text-2xl font-bold">{result.currentPensionPoints.toFixed(2)}</p>
              <p className="text-xs text-muted-foreground">Entgeltpunkte</p>
            </div>
            <div className="rounded-lg border p-4">
              <p className="text-sm text-muted-foreground">Bei Renteneintritt</p>
              <p className="text-2xl font-bold text-blue-600">
                {result.projectedPensionPoints.toFixed(2)}
              </p>
              <p className="text-xs text-muted-foreground">Entgeltpunkte (prognostiziert)</p>
            </div>
          </div>
          <p className="mt-3 text-sm text-muted-foreground">
            1 Entgeltpunkt = ca. 39,32 EUR monatliche Rente (Stand 2026)
          </p>
        </CardContent>
      </Card>

      {/* Kapitalluecke & Sparrate */}
      {result.pensionGap > 0 && (
        <Card className="border-orange-200 bg-orange-50 dark:border-orange-800 dark:bg-orange-950">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-orange-700 dark:text-orange-300">
              <AlertTriangle className="h-5 w-5" />
              Handlungsbedarf
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-4 md:grid-cols-2">
              <div>
                <p className="text-sm text-muted-foreground">Benoetiges Kapital</p>
                <p className="text-2xl font-bold">{formatCurrency(result.capitalNeededForGap)}</p>
                <p className="text-xs text-muted-foreground">
                  um Luecke mit 4%-Regel zu schliessen
                </p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Erforderliche Sparrate</p>
                <p className="text-2xl font-bold text-orange-600">
                  {formatCurrency(result.monthlySavingsRequired)}
                </p>
                <p className="text-xs text-muted-foreground">/Monat bis Renteneintritt</p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Empfehlungen */}
      {result.recommendations.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Empfehlungen</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-2">
              {result.recommendations.map((rec, index) => (
                <li key={index} className="flex items-start gap-2 text-sm">
                  <ChevronRight className="h-4 w-4 mt-0.5 text-primary shrink-0" />
                  <span>{rec}</span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

// ==================== Helper Components ====================

interface PensionSourceRowProps {
  label: string;
  value: number;
  total: number;
  icon: React.ReactNode;
}

function PensionSourceRow({ label, value, total, icon }: PensionSourceRowProps) {
  const percent = total > 0 ? (value / total) * 100 : 0;

  if (value <= 0) return null;

  return (
    <div className="flex items-center gap-3">
      <div className="text-muted-foreground">{icon}</div>
      <div className="flex-1">
        <div className="flex items-center justify-between text-sm">
          <span>{label}</span>
          <span className="font-medium">{formatCurrency(value)}</span>
        </div>
        <Progress value={percent} className="h-1.5 mt-1" />
      </div>
      <span className="text-xs text-muted-foreground w-10 text-right">
        {percent.toFixed(0)}%
      </span>
    </div>
  );
}

export default PensionGapCalculator;
