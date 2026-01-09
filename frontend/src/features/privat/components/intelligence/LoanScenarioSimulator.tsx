/**
 * LoanScenarioSimulator - Kredit-Szenario-Simulator
 *
 * Ermoeglicht What-If Analysen fuer Kredite:
 * - Sonderzahlungen simulieren
 * - Umschuldung berechnen
 * - Tilgungsplan anzeigen
 * - Szenarien vergleichen
 */

import * as React from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Slider } from '@/components/ui/slider';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  Calculator,
  TrendingDown,
  Calendar,
  Euro,
  Percent,
  CheckCircle2,
  XCircle,
  ArrowRight,
  RefreshCw,
  PiggyBank,
  Clock,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { privatIntelligenceService } from '@/lib/api/services/privat-intelligence';
import type {
  ExtraPaymentScenario,
  RefinancingScenario,
  FullAmortizationSchedule,
} from '@/types/privat';

interface LoanScenarioSimulatorProps {
  loanId: string;
  loanName: string;
  currentBalance: number;
  interestRate: number;
  monthlyPayment: number;
  className?: string;
}

export function LoanScenarioSimulator({
  loanId,
  loanName,
  currentBalance,
  interestRate,
  monthlyPayment,
  className,
}: LoanScenarioSimulatorProps) {
  const [activeTab, setActiveTab] = React.useState('extra-payment');
  const [extraPayment, setExtraPayment] = React.useState(100);
  const [newRate, setNewRate] = React.useState(interestRate > 1 ? interestRate - 1 : 0.5);
  const [refinancingCosts, setRefinancingCosts] = React.useState(500);

  const formatCurrency = (amount: number): string => {
    return new Intl.NumberFormat('de-DE', {
      style: 'currency',
      currency: 'EUR',
      maximumFractionDigits: 0,
    }).format(amount);
  };

  const formatDate = (dateStr: string): string => {
    return new Date(dateStr).toLocaleDateString('de-DE', {
      month: 'short',
      year: 'numeric',
    });
  };

  // Extra Payment Simulation
  const extraPaymentMutation = useMutation({
    mutationFn: () => privatIntelligenceService.simulateExtraPayment(loanId, extraPayment),
  });

  // Refinancing Simulation
  const refinancingMutation = useMutation({
    mutationFn: () => privatIntelligenceService.simulateRefinancing(loanId, newRate, refinancingCosts),
  });

  // Full Amortization Schedule
  const {
    data: amortization,
    isLoading: amortizationLoading,
    refetch: refetchAmortization,
  } = useQuery({
    queryKey: ['amortization', loanId],
    queryFn: () => privatIntelligenceService.getFullAmortization(loanId),
    enabled: activeTab === 'amortization',
  });

  return (
    <Card className={cn('', className)}>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Calculator className="h-5 w-5 text-blue-500" />
          Kredit-Simulator
        </CardTitle>
        <CardDescription>
          {loanName} - Was-Waere-Wenn Analysen
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <TabsList className="grid w-full grid-cols-3">
            <TabsTrigger value="extra-payment" className="gap-1">
              <PiggyBank className="h-4 w-4" />
              Sonderzahlung
            </TabsTrigger>
            <TabsTrigger value="refinancing" className="gap-1">
              <Percent className="h-4 w-4" />
              Umschuldung
            </TabsTrigger>
            <TabsTrigger value="amortization" className="gap-1">
              <Calendar className="h-4 w-4" />
              Tilgungsplan
            </TabsTrigger>
          </TabsList>

          {/* Extra Payment Tab */}
          <TabsContent value="extra-payment" className="space-y-4 mt-4">
            <div className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="extra-payment">
                  Monatliche Sonderzahlung: {formatCurrency(extraPayment)}
                </Label>
                <Slider
                  id="extra-payment"
                  value={[extraPayment]}
                  onValueChange={([value]) => setExtraPayment(value)}
                  min={50}
                  max={Math.min(currentBalance / 12, 2000)}
                  step={50}
                />
                <div className="flex justify-between text-xs text-muted-foreground">
                  <span>{formatCurrency(50)}</span>
                  <span>{formatCurrency(Math.min(currentBalance / 12, 2000))}</span>
                </div>
              </div>

              <Button
                onClick={() => extraPaymentMutation.mutate()}
                disabled={extraPaymentMutation.isPending}
                className="w-full"
                aria-label="Sonderzahlung berechnen"
              >
                {extraPaymentMutation.isPending ? (
                  <RefreshCw className="h-4 w-4 animate-spin mr-2" aria-hidden="true" />
                ) : (
                  <Calculator className="h-4 w-4 mr-2" aria-hidden="true" />
                )}
                Berechnen
              </Button>

              {extraPaymentMutation.data && (
                <ExtraPaymentResult result={extraPaymentMutation.data} formatCurrency={formatCurrency} formatDate={formatDate} />
              )}
            </div>
          </TabsContent>

          {/* Refinancing Tab */}
          <TabsContent value="refinancing" className="space-y-4 mt-4">
            <div className="space-y-4">
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="new-rate">Neuer Zinssatz: {newRate.toFixed(2)}%</Label>
                  <Slider
                    id="new-rate"
                    value={[newRate]}
                    onValueChange={([value]) => setNewRate(value)}
                    min={0.5}
                    max={Math.max(interestRate, 5)}
                    step={0.1}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="refinancing-costs">Umschuldungskosten</Label>
                  <Input
                    id="refinancing-costs"
                    type="number"
                    value={refinancingCosts}
                    onChange={(e) => setRefinancingCosts(Number(e.target.value))}
                    min={0}
                    step={100}
                  />
                </div>
              </div>

              <div className="p-3 rounded-lg bg-muted text-sm">
                <p>
                  <strong>Aktueller Zinssatz:</strong> {interestRate.toFixed(2)}%
                </p>
                <p>
                  <strong>Differenz:</strong> {(interestRate - newRate).toFixed(2)} Prozentpunkte
                </p>
              </div>

              <Button
                onClick={() => refinancingMutation.mutate()}
                disabled={refinancingMutation.isPending}
                className="w-full"
                aria-label="Umschuldung berechnen"
              >
                {refinancingMutation.isPending ? (
                  <RefreshCw className="h-4 w-4 animate-spin mr-2" aria-hidden="true" />
                ) : (
                  <Calculator className="h-4 w-4 mr-2" aria-hidden="true" />
                )}
                Umschuldung berechnen
              </Button>

              {refinancingMutation.data && (
                <RefinancingResult result={refinancingMutation.data} formatCurrency={formatCurrency} />
              )}
            </div>
          </TabsContent>

          {/* Amortization Tab */}
          <TabsContent value="amortization" className="mt-4">
            {amortizationLoading ? (
              <div className="space-y-3">
                {[1, 2, 3, 4, 5].map((i) => (
                  <Skeleton key={i} className="h-12" />
                ))}
              </div>
            ) : amortization ? (
              <AmortizationDisplay schedule={amortization} formatCurrency={formatCurrency} formatDate={formatDate} />
            ) : (
              <div className="text-center py-8 text-muted-foreground">
                <Button onClick={() => refetchAmortization()} aria-label="Tilgungsplan laden">
                  Tilgungsplan laden
                </Button>
              </div>
            )}
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  );
}

interface ExtraPaymentResultProps {
  result: ExtraPaymentScenario;
  formatCurrency: (amount: number) => string;
  formatDate: (dateStr: string) => string;
}

function ExtraPaymentResult({ result, formatCurrency, formatDate }: ExtraPaymentResultProps) {
  return (
    <div className="space-y-4 p-4 rounded-lg bg-green-50 dark:bg-green-950/30">
      <h4 className="font-medium text-green-700 dark:text-green-400 flex items-center gap-2">
        <CheckCircle2 className="h-4 w-4" />
        Simulationsergebnis
      </h4>

      <div className="grid gap-3 md:grid-cols-2">
        <ResultItem
          label="Neue monatliche Rate"
          value={formatCurrency(result.newMonthlyPayment)}
          subtext={`+${formatCurrency(result.extraMonthlyPayment)} Sonderzahlung`}
        />
        <ResultItem
          label="Neue Restlaufzeit"
          value={`${result.newRemainingMonths} Monate`}
          subtext={`${result.monthsSaved} Monate gespart`}
          positive
        />
        <ResultItem
          label="Zinsersparnis"
          value={formatCurrency(result.interestSaved)}
          positive
        />
        <ResultItem
          label="Neues Ende"
          value={formatDate(result.newPayoffDate)}
          icon={<Calendar className="h-4 w-4" />}
        />
      </div>

      <div className="p-3 rounded bg-green-100 dark:bg-green-900/30 text-sm">
        <p className="font-medium text-green-800 dark:text-green-300">
          Mit {formatCurrency(result.extraMonthlyPayment)} monatlicher Sonderzahlung
          sparen Sie <strong>{formatCurrency(result.interestSaved)}</strong> an Zinsen
          und sind <strong>{result.monthsSaved} Monate</strong> frueher schuldenfrei!
        </p>
      </div>
    </div>
  );
}

interface RefinancingResultProps {
  result: RefinancingScenario;
  formatCurrency: (amount: number) => string;
}

function RefinancingResult({ result, formatCurrency }: RefinancingResultProps) {
  return (
    <div
      className={cn(
        'space-y-4 p-4 rounded-lg',
        result.isWorthwhile
          ? 'bg-green-50 dark:bg-green-950/30'
          : 'bg-orange-50 dark:bg-orange-950/30'
      )}
    >
      <h4
        className={cn(
          'font-medium flex items-center gap-2',
          result.isWorthwhile
            ? 'text-green-700 dark:text-green-400'
            : 'text-orange-700 dark:text-orange-400'
        )}
      >
        {result.isWorthwhile ? (
          <CheckCircle2 className="h-4 w-4" />
        ) : (
          <XCircle className="h-4 w-4" />
        )}
        {result.isWorthwhile ? 'Umschuldung empfohlen' : 'Umschuldung nicht empfohlen'}
      </h4>

      <div className="grid gap-3 md:grid-cols-2">
        <ResultItem
          label="Neuer Zinssatz"
          value={`${result.newRate.toFixed(2)}%`}
          subtext={`Aktuell: ${result.currentRate.toFixed(2)}%`}
        />
        <ResultItem
          label="Neue monatliche Rate"
          value={formatCurrency(result.newMonthlyPayment)}
          subtext={`Aktuell: ${formatCurrency(result.currentMonthlyPayment)}`}
        />
        <ResultItem
          label="Voraussichtliche Kosten"
          value={formatCurrency(result.refinancingCosts + result.estimatedPrepaymentPenalty)}
          subtext="inkl. Vorfaelligkeitsentschaedigung"
        />
        <ResultItem
          label="Gesamtersparnis"
          value={formatCurrency(result.totalSavings)}
          positive={result.totalSavings > 0}
        />
        {result.breakEvenMonths > 0 && (
          <ResultItem
            label="Break-Even"
            value={`${result.breakEvenMonths} Monate`}
            icon={<Clock className="h-4 w-4" />}
          />
        )}
      </div>

      <div
        className={cn(
          'p-3 rounded text-sm',
          result.isWorthwhile
            ? 'bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-300'
            : 'bg-orange-100 dark:bg-orange-900/30 text-orange-800 dark:text-orange-300'
        )}
      >
        <p className="font-medium">{result.recommendation}</p>
      </div>
    </div>
  );
}

interface ResultItemProps {
  label: string;
  value: string;
  subtext?: string;
  positive?: boolean;
  icon?: React.ReactNode;
}

function ResultItem({ label, value, subtext, positive, icon }: ResultItemProps) {
  return (
    <div className="p-3 rounded bg-white dark:bg-gray-900/50">
      <p className="text-xs text-muted-foreground mb-1">{label}</p>
      <p
        className={cn(
          'text-lg font-bold flex items-center gap-2',
          positive === true && 'text-green-600 dark:text-green-400',
          positive === false && 'text-red-600 dark:text-red-400'
        )}
      >
        {icon}
        {value}
      </p>
      {subtext && <p className="text-xs text-muted-foreground mt-1">{subtext}</p>}
    </div>
  );
}

interface AmortizationDisplayProps {
  schedule: FullAmortizationSchedule;
  formatCurrency: (amount: number) => string;
  formatDate: (dateStr: string) => string;
}

function AmortizationDisplay({ schedule, formatCurrency, formatDate }: AmortizationDisplayProps) {
  return (
    <div className="space-y-4">
      {/* Summary */}
      <div className="grid gap-3 md:grid-cols-4">
        <div className="p-3 rounded-lg bg-muted">
          <p className="text-xs text-muted-foreground">Kreditsumme</p>
          <p className="text-lg font-bold">{formatCurrency(schedule.principalAmount)}</p>
        </div>
        <div className="p-3 rounded-lg bg-muted">
          <p className="text-xs text-muted-foreground">Gesamtzinsen</p>
          <p className="text-lg font-bold text-red-600 dark:text-red-400">
            {formatCurrency(schedule.totalInterest)}
          </p>
        </div>
        <div className="p-3 rounded-lg bg-muted">
          <p className="text-xs text-muted-foreground">Gesamtkosten</p>
          <p className="text-lg font-bold">{formatCurrency(schedule.totalCost)}</p>
        </div>
        <div className="p-3 rounded-lg bg-muted">
          <p className="text-xs text-muted-foreground">Laufzeit</p>
          <p className="text-lg font-bold">{schedule.totalMonths} Monate</p>
        </div>
      </div>

      {/* Key Milestones */}
      <div className="p-3 rounded-lg bg-blue-50 dark:bg-blue-950/30">
        <h5 className="font-medium text-blue-700 dark:text-blue-400 mb-2">Meilensteine</h5>
        <div className="grid gap-2 md:grid-cols-2 text-sm">
          <p>
            <span className="text-muted-foreground">Zinsen Jahr 1:</span>{' '}
            <strong>{formatCurrency(schedule.summary.firstYearInterest)}</strong>
          </p>
          <p>
            <span className="text-muted-foreground">Zinsen letztes Jahr:</span>{' '}
            <strong>{formatCurrency(schedule.summary.lastYearInterest)}</strong>
          </p>
          <p>
            <span className="text-muted-foreground">Halbzeit:</span>{' '}
            <strong>{formatDate(schedule.summary.halfwayDate)}</strong>
          </p>
          <p>
            <span className="text-muted-foreground">Restschuld Halbzeit:</span>{' '}
            <strong>{formatCurrency(schedule.summary.halfwayBalance)}</strong>
          </p>
        </div>
      </div>

      {/* Schedule Table */}
      <ScrollArea className="h-[300px] rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-16">Monat</TableHead>
              <TableHead>Datum</TableHead>
              <TableHead className="text-right">Rate</TableHead>
              <TableHead className="text-right">Tilgung</TableHead>
              <TableHead className="text-right">Zinsen</TableHead>
              <TableHead className="text-right">Restschuld</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {schedule.schedule.map((entry) => (
              <TableRow key={entry.month}>
                <TableCell className="font-medium">{entry.month}</TableCell>
                <TableCell>{formatDate(entry.date)}</TableCell>
                <TableCell className="text-right">{formatCurrency(entry.payment)}</TableCell>
                <TableCell className="text-right text-green-600 dark:text-green-400">
                  {formatCurrency(entry.principal)}
                </TableCell>
                <TableCell className="text-right text-red-600 dark:text-red-400">
                  {formatCurrency(entry.interest)}
                </TableCell>
                <TableCell className="text-right font-medium">
                  {formatCurrency(entry.balance)}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </ScrollArea>
    </div>
  );
}

export default LoanScenarioSimulator;
