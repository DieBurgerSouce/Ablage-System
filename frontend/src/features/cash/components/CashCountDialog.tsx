/**
 * Cash Count Dialog
 *
 * Dialog für Kassensturz (Zaehlprotokoll).
 * Ermöglicht das Erfassen des tatsaechlichen Kassenbestands und
 * erstellt bei Differenz automatisch eine Differenzbuchung.
 */

import * as React from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Loader2, Calculator, AlertTriangle, CheckCircle2 } from 'lucide-react';
import { usePerformCashCount, useRegister } from '../hooks/use-cash-queries';
import { formatCurrency } from '../utils/format';
import type { CashRegister, CashCount, CashCountCreate } from '@/types/models/cash';
import { cn } from '@/lib/utils';

// Muenzstäckelungen
const COIN_DENOMINATIONS = [
  { value: 0.01, label: '1 Cent' },
  { value: 0.02, label: '2 Cent' },
  { value: 0.05, label: '5 Cent' },
  { value: 0.10, label: '10 Cent' },
  { value: 0.20, label: '20 Cent' },
  { value: 0.50, label: '50 Cent' },
  { value: 1.00, label: '1 Euro' },
  { value: 2.00, label: '2 Euro' },
];

// Scheinstäckelungen
const NOTE_DENOMINATIONS = [
  { value: 5, label: '5 Euro' },
  { value: 10, label: '10 Euro' },
  { value: 20, label: '20 Euro' },
  { value: 50, label: '50 Euro' },
  { value: 100, label: '100 Euro' },
  { value: 200, label: '200 Euro' },
  { value: 500, label: '500 Euro' },
];

// Validierungs-Schema
const cashCountSchema = z.object({
  counted_amount: z.number().min(0, 'Betrag muss positiv sein'),
  notes: z.string().max(500).optional(),
  denomination_counts: z.record(z.number().min(0)).optional(),
});

type CashCountFormData = z.infer<typeof cashCountSchema>;

interface CashCountDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  register: CashRegister | null;
  onSuccess?: (cashCount: CashCount) => void;
}

export function CashCountDialog({
  open,
  onOpenChange,
  register,
  onSuccess,
}: CashCountDialogProps) {
  const { data: currentRegister } = useRegister(register?.id ?? '');
  const performCashCount = usePerformCashCount();

  const [showDetailedCount, setShowDetailedCount] = React.useState(false);
  const [denominationCounts, setDenominationCounts] = React.useState<Record<string, number>>({});

  const form = useForm<CashCountFormData>({
    resolver: zodResolver(cashCountSchema),
    defaultValues: {
      counted_amount: 0,
      notes: '',
      denomination_counts: {},
    },
  });

  const countedAmount = form.watch('counted_amount');
  const expectedBalance = currentRegister?.current_balance ?? register?.current_balance ?? 0;
  const difference = countedAmount - expectedBalance;

  // Berechne Summe aus Stäckelungen
  const calculatedTotal = React.useMemo(() => {
    let total = 0;
    for (const [denom, count] of Object.entries(denominationCounts)) {
      total += parseFloat(denom) * (count || 0);
    }
    return Math.round(total * 100) / 100;
  }, [denominationCounts]);

  // Aktualisiere counted_amount wenn sich Stäckelungen ändern
  React.useEffect(() => {
    if (showDetailedCount) {
      form.setValue('counted_amount', calculatedTotal);
    }
  }, [calculatedTotal, showDetailedCount, form]);

  // Formular zurücksetzen wenn Dialog oeffnet
  React.useEffect(() => {
    if (open) {
      form.reset({
        counted_amount: 0,
        notes: '',
        denomination_counts: {},
      });
      setDenominationCounts({});
      setShowDetailedCount(false);
    }
  }, [open, form]);

  const updateDenomination = (value: number, count: number) => {
    setDenominationCounts((prev) => ({
      ...prev,
      [value.toString()]: count,
    }));
  };

  const onSubmit = async (data: CashCountFormData) => {
    if (!register) return;

    try {
      const createData: CashCountCreate = {
        register_id: register.id,
        counted_amount: data.counted_amount,
        notes: data.notes,
        denomination_counts: showDetailedCount ? denominationCounts : undefined,
      };

      const result = await performCashCount.mutateAsync(createData);
      onSuccess?.(result);
      onOpenChange(false);
    } catch (error) {
      // Fehler werden vom Mutation-Hook behandelt
    }
  };

  if (!register) return null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Calculator className="h-5 w-5" aria-hidden="true" />
            Kassensturz: {register.name}
          </DialogTitle>
          <DialogDescription>
            Erfassen Sie den tatsaechlichen Kassenbestand.
          </DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            {/* Soll-Bestand */}
            <Card>
              <CardContent className="pt-4">
                <div className="flex justify-between items-center">
                  <span className="text-sm text-muted-foreground">Soll-Bestand (Buchsaldo)</span>
                  <span className="text-lg font-mono font-bold">
                    {formatCurrency(expectedBalance)}
                  </span>
                </div>
              </CardContent>
            </Card>

            {/* Gezaehlter Betrag */}
            <FormField
              control={form.control}
              name="counted_amount"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Gezaehlter Betrag (EUR) *</FormLabel>
                  <FormControl>
                    <Input
                      type="number"
                      step="0.01"
                      min="0"
                      placeholder="0.00"
                      className="text-lg font-mono"
                      {...field}
                      onChange={(e) => field.onChange(parseFloat(e.target.value) || 0)}
                      disabled={showDetailedCount}
                    />
                  </FormControl>
                  <FormDescription>
                    <Button
                      type="button"
                      variant="link"
                      size="sm"
                      className="p-0 h-auto"
                      onClick={() => setShowDetailedCount(!showDetailedCount)}
                    >
                      {showDetailedCount
                        ? 'Direkteingabe verwenden'
                        : 'Mit Stäckelungen zaehlen'}
                    </Button>
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />

            {/* Detailliertes Zaehlen nach Stäckelungen */}
            {showDetailedCount && (
              <Card>
                <CardContent className="pt-4 space-y-4">
                  {/* Scheine */}
                  <div role="group" aria-labelledby="note-denominations-label">
                    <h4 id="note-denominations-label" className="font-medium text-sm mb-2">
                      Scheine
                    </h4>
                    <div className="grid grid-cols-4 gap-2">
                      {NOTE_DENOMINATIONS.map((d, index) => (
                        <div key={d.value} className="space-y-1">
                          <label
                            htmlFor={`note-${d.value}`}
                            className="text-xs text-muted-foreground"
                          >
                            {d.label}
                          </label>
                          <Input
                            id={`note-${d.value}`}
                            type="number"
                            min="0"
                            className="h-8 text-sm"
                            value={denominationCounts[d.value.toString()] || ''}
                            onChange={(e) =>
                              updateDenomination(d.value, parseInt(e.target.value) || 0)
                            }
                            aria-label={`Anzahl ${d.label} Scheine`}
                            tabIndex={0}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter') {
                                e.preventDefault();
                                // Fokus auf nächstes Feld
                                const nextIndex = index + 1;
                                if (nextIndex < NOTE_DENOMINATIONS.length) {
                                  const nextId = `note-${NOTE_DENOMINATIONS[nextIndex].value}`;
                                  document.getElementById(nextId)?.focus();
                                } else {
                                  // Wechsel zu Münzen
                                  document.getElementById(`coin-${COIN_DENOMINATIONS[0].value}`)?.focus();
                                }
                              }
                            }}
                          />
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Muenzen */}
                  <div role="group" aria-labelledby="coin-denominations-label">
                    <h4 id="coin-denominations-label" className="font-medium text-sm mb-2">
                      Muenzen
                    </h4>
                    <div className="grid grid-cols-4 gap-2">
                      {COIN_DENOMINATIONS.map((d, index) => (
                        <div key={d.value} className="space-y-1">
                          <label
                            htmlFor={`coin-${d.value}`}
                            className="text-xs text-muted-foreground"
                          >
                            {d.label}
                          </label>
                          <Input
                            id={`coin-${d.value}`}
                            type="number"
                            min="0"
                            className="h-8 text-sm"
                            value={denominationCounts[d.value.toString()] || ''}
                            onChange={(e) =>
                              updateDenomination(d.value, parseInt(e.target.value) || 0)
                            }
                            aria-label={`Anzahl ${d.label} Muenzen`}
                            tabIndex={0}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter') {
                                e.preventDefault();
                                const nextIndex = index + 1;
                                if (nextIndex < COIN_DENOMINATIONS.length) {
                                  const nextId = `coin-${COIN_DENOMINATIONS[nextIndex].value}`;
                                  document.getElementById(nextId)?.focus();
                                } else {
                                  // Fokus auf Submit-Button
                                  form.handleSubmit(onSubmit)();
                                }
                              }
                            }}
                          />
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Summe */}
                  <div className="flex justify-between items-center pt-2 border-t">
                    <span className="font-medium">Summe</span>
                    <span className="text-lg font-mono font-bold">
                      {formatCurrency(calculatedTotal)}
                    </span>
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Differenz-Anzeige */}
            {countedAmount > 0 && (
              <Card
                className={cn(
                  difference === 0
                    ? 'border-green-500 bg-green-50 dark:bg-green-950'
                    : 'border-yellow-500 bg-yellow-50 dark:bg-yellow-950'
                )}
              >
                <CardContent className="pt-4">
                  <div className="flex justify-between items-center">
                    <div className="flex items-center gap-2">
                      {difference === 0 ? (
                        <CheckCircle2 className="h-5 w-5 text-green-600" aria-hidden="true" />
                      ) : (
                        <AlertTriangle className="h-5 w-5 text-yellow-600" aria-hidden="true" />
                      )}
                      <span className="font-medium">Differenz</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span
                        className={cn(
                          'text-lg font-mono font-bold',
                          difference > 0 && 'text-green-600',
                          difference < 0 && 'text-red-600'
                        )}
                      >
                        {difference >= 0 ? '+' : ''}{formatCurrency(difference)}
                      </span>
                      {difference !== 0 && (
                        <Badge variant={difference > 0 ? 'default' : 'destructive'}>
                          {difference > 0 ? 'Überschuss' : 'Fehlbetrag'}
                        </Badge>
                      )}
                    </div>
                  </div>
                  {difference !== 0 && (
                    <p className="text-sm text-muted-foreground mt-2">
                      Es wird automatisch eine Differenzbuchung erstellt.
                    </p>
                  )}
                </CardContent>
              </Card>
            )}

            {/* Bemerkungen */}
            <FormField
              control={form.control}
              name="notes"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Bemerkungen</FormLabel>
                  <FormControl>
                    <Textarea
                      placeholder="Optionale Bemerkungen zum Kassensturz..."
                      className="resize-none"
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => onOpenChange(false)}
                disabled={performCashCount.isPending}
              >
                Abbrechen
              </Button>
              <Button type="submit" disabled={performCashCount.isPending || countedAmount <= 0}>
                {performCashCount.isPending && (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" />
                )}
                Kassensturz durchführen
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}

export default CashCountDialog;
