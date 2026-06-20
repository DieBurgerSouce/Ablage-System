/**
 * Per Diem Calculator
 *
 * Berechnet Verpflegungspauschalen basierend auf Reisedauer.
 * Gemäß § 9 Abs. 4a EStG:
 * - Ab 8h: EUR 14.00
 * - Ab 24h: EUR 28.00
 * - An- und Abreisetag bei mehrtägigen Reisen: EUR 14.00
 */

import * as React from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import { Separator } from '@/components/ui/separator';
import { Utensils, Calculator, Loader2, Info } from 'lucide-react';
import { useCalculatePerDiem } from '../hooks/use-expense-queries';
import { formatCurrency, formatHours } from '../utils/format';
import type { PerDiemCalculation, PerDiemCalculateRequest, MealsProvided } from '@/types/models/expense';

// Validierungs-Schema
const perDiemSchema = z.object({
  travel_start: z.string().min(1, 'Reisebeginn ist erforderlich'),
  travel_end: z.string().min(1, 'Reiseende ist erforderlich'),
  country: z.string().default('DE'),
  meals_breakfast: z.boolean().default(false),
  meals_lunch: z.boolean().default(false),
  meals_dinner: z.boolean().default(false),
}).refine((data) => {
  return new Date(data.travel_start) <= new Date(data.travel_end);
}, {
  message: 'Reiseende muss nach Reisebeginn liegen',
  path: ['travel_end'],
});

type PerDiemFormData = z.infer<typeof perDiemSchema>;
type PerDiemFormDataInput = z.input<typeof perDiemSchema>;

interface PerDiemCalculatorProps {
  onCalculate?: (calculation: PerDiemCalculation) => void;
  onAddToReport?: (calculation: PerDiemCalculation) => void;
  className?: string;
}

export function PerDiemCalculator({
  onCalculate,
  onAddToReport,
  className,
}: PerDiemCalculatorProps) {
  const calculateMutation = useCalculatePerDiem();
  const [calculation, setCalculation] = React.useState<PerDiemCalculation | null>(null);

  // Default: Heute 8:00 bis 18:00
  const today = new Date();
  const defaultStart = `${today.toISOString().split('T')[0]}T08:00`;
  const defaultEnd = `${today.toISOString().split('T')[0]}T18:00`;

  const form = useForm<PerDiemFormDataInput, unknown, PerDiemFormData>({
    resolver: zodResolver(perDiemSchema),
    defaultValues: {
      travel_start: defaultStart,
      travel_end: defaultEnd,
      country: 'DE',
      meals_breakfast: false,
      meals_lunch: false,
      meals_dinner: false,
    },
  });

  const onSubmit = async (data: PerDiemFormData) => {
    try {
      const mealsProvided: MealsProvided = {
        breakfast: data.meals_breakfast,
        lunch: data.meals_lunch,
        dinner: data.meals_dinner,
      };

      const request: PerDiemCalculateRequest = {
        travel_start: data.travel_start,
        travel_end: data.travel_end,
        country: data.country,
        meals_provided: mealsProvided,
      };

      const result = await calculateMutation.mutateAsync(request);
      setCalculation(result);
      onCalculate?.(result);
    } catch (error) {
      // Fehler werden vom Mutation-Hook behandelt
    }
  };

  const handleAddToReport = () => {
    if (calculation) {
      onAddToReport?.(calculation);
    }
  };

  return (
    <Card className={className}>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Utensils className="h-5 w-5" />
          Verpflegungspauschale-Rechner
        </CardTitle>
        <CardDescription>
          Berechnet Verpflegungsmehraufwand gemäß § 9 Abs. 4a EStG
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Form {...form}>
          {/* FIX Phase 7.6: Type-safe form handler - react-hook-form unterstützt async handlers */}
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <FormField
                control={form.control}
                name="travel_start"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Reisebeginn *</FormLabel>
                    <FormControl>
                      <Input type="datetime-local" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="travel_end"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Reiseende *</FormLabel>
                    <FormControl>
                      <Input type="datetime-local" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            <FormField
              control={form.control}
              name="country"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Land</FormLabel>
                  <Select onValueChange={field.onChange} value={field.value}>
                    <FormControl>
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      <SelectItem value="DE">Deutschland</SelectItem>
                      <SelectItem value="AT">Österreich</SelectItem>
                      <SelectItem value="CH">Schweiz</SelectItem>
                      <SelectItem value="FR">Frankreich</SelectItem>
                      <SelectItem value="NL">Niederlande</SelectItem>
                      <SelectItem value="BE">Belgien</SelectItem>
                      <SelectItem value="IT">Italien</SelectItem>
                      <SelectItem value="ES">Spanien</SelectItem>
                      <SelectItem value="UK">Großbritannien</SelectItem>
                      <SelectItem value="US">USA</SelectItem>
                    </SelectContent>
                  </Select>
                  <FormDescription>
                    Auslandsreisen haben höhere Pauschalen
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />

            <div className="space-y-3">
              <FormLabel>Gestellte Mahlzeiten</FormLabel>
              <FormDescription className="text-xs">
                Vom Arbeitgeber oder Dritten gestellte Mahlzeiten reduzieren die Pauschale
              </FormDescription>

              <div className="grid grid-cols-3 gap-4">
                <FormField
                  control={form.control}
                  name="meals_breakfast"
                  render={({ field }) => (
                    <FormItem className="flex flex-row items-center space-x-2 space-y-0">
                      <FormControl>
                        <Checkbox
                          checked={field.value}
                          onCheckedChange={field.onChange}
                        />
                      </FormControl>
                      <FormLabel className="text-sm font-normal">
                        Frühstück
                      </FormLabel>
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="meals_lunch"
                  render={({ field }) => (
                    <FormItem className="flex flex-row items-center space-x-2 space-y-0">
                      <FormControl>
                        <Checkbox
                          checked={field.value}
                          onCheckedChange={field.onChange}
                        />
                      </FormControl>
                      <FormLabel className="text-sm font-normal">
                        Mittagessen
                      </FormLabel>
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="meals_dinner"
                  render={({ field }) => (
                    <FormItem className="flex flex-row items-center space-x-2 space-y-0">
                      <FormControl>
                        <Checkbox
                          checked={field.value}
                          onCheckedChange={field.onChange}
                        />
                      </FormControl>
                      <FormLabel className="text-sm font-normal">
                        Abendessen
                      </FormLabel>
                    </FormItem>
                  )}
                />
              </div>
            </div>

            <Button
              type="submit"
              className="w-full"
              disabled={calculateMutation.isPending}
            >
              {calculateMutation.isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Calculator className="mr-2 h-4 w-4" />
              )}
              Berechnen
            </Button>
          </form>
        </Form>

        {/* Ergebnis */}
        {calculation && (
          <>
            <Separator className="my-4" />
            <div className="space-y-3">
              <div className="flex justify-between items-center">
                <span className="text-muted-foreground">Gesamtdauer</span>
                <span className="font-mono">{formatHours(calculation.total_hours)}</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-muted-foreground">Volle Tage (24h)</span>
                <span className="font-mono">{calculation.full_days ?? 0}</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-muted-foreground">An-/Abreisetage</span>
                <span className="font-mono">{calculation.partial_days ?? 0}</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-muted-foreground">Basissatz</span>
                <span className="font-mono">{formatCurrency(calculation.base_rate)}</span>
              </div>

              {(calculation.meal_deductions ?? calculation.meal_reductions ?? 0) > 0 && (
                <div className="flex justify-between items-center text-amber-600">
                  <span>Kürzung Mahlzeiten</span>
                  <span className="font-mono">-{formatCurrency(calculation.meal_deductions ?? calculation.meal_reductions ?? 0)}</span>
                </div>
              )}

              <Separator />
              <div className="flex justify-between items-center">
                <span className="font-medium">Erstattungsbetrag</span>
                <Badge variant="default" className="text-lg px-3">
                  {formatCurrency(calculation.total_amount)}
                </Badge>
              </div>

              {/* Info-Box */}
              <div className="flex items-start gap-2 p-3 rounded-lg bg-muted text-sm">
                <Info className="h-4 w-4 mt-0.5 text-muted-foreground shrink-0" />
                <div className="text-muted-foreground">
                  <p><strong>Inland (DE):</strong></p>
                  <ul className="list-disc list-inside ml-2">
                    <li>Ab 8h Abwesenheit: EUR 14.00</li>
                    <li>Ab 24h Abwesenheit: EUR 28.00</li>
                    <li>An-/Abreisetag: EUR 14.00</li>
                  </ul>
                </div>
              </div>

              {onAddToReport && (
                <Button
                  onClick={handleAddToReport}
                  variant="outline"
                  className="w-full mt-2"
                >
                  Zur Abrechnung hinzufügen
                </Button>
              )}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}

export default PerDiemCalculator;
