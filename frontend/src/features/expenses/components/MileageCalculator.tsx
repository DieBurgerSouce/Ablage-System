/**
 * Mileage Calculator
 *
 * Berechnet Kilometergeld basierend auf gefahrenen Kilometern.
 * Standardsatz: EUR 0.30 pro km (§ 9 Abs. 1 Nr. 4 EStG).
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
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
import { Separator } from '@/components/ui/separator';
import { Car, Calculator, Loader2 } from 'lucide-react';
import { useCalculateMileage } from '../hooks/use-expense-queries';
import { formatCurrency, formatKilometers } from '../utils/format';
import type { MileageCalculation, MileageCalculateRequest } from '@/types/models/expense';

// Validierungs-Schema
const mileageSchema = z.object({
  kilometers: z.number().positive('Kilometer muss positiv sein'),
  is_round_trip: z.boolean().default(false),
  vehicle_type: z.enum(['car', 'motorcycle']).default('car'),
});

type MileageFormData = z.infer<typeof mileageSchema>;

interface MileageCalculatorProps {
  onCalculate?: (calculation: MileageCalculation) => void;
  onAddToReport?: (calculation: MileageCalculation) => void;
  className?: string;
}

export function MileageCalculator({
  onCalculate,
  onAddToReport,
  className,
}: MileageCalculatorProps) {
  const calculateMutation = useCalculateMileage();
  const [calculation, setCalculation] = React.useState<MileageCalculation | null>(null);

  const form = useForm<MileageFormData>({
    resolver: zodResolver(mileageSchema),
    defaultValues: {
      kilometers: 0,
      is_round_trip: false,
      vehicle_type: 'car',
    },
  });

  const onSubmit = async (data: MileageFormData) => {
    try {
      const request: MileageCalculateRequest = {
        kilometers: data.kilometers,
        is_round_trip: data.is_round_trip,
        vehicle_type: data.vehicle_type,
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
          <Car className="h-5 w-5" />
          Kilometergeld-Rechner
        </CardTitle>
        <CardDescription>
          Berechnet die Fahrtkostenerstattung (EUR 0.30/km)
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            <FormField
              control={form.control}
              name="kilometers"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Gefahrene Kilometer (einfach)</FormLabel>
                  <FormControl>
                    <Input
                      type="number"
                      step="0.1"
                      min="0"
                      placeholder="0"
                      {...field}
                      onChange={(e) => field.onChange(parseFloat(e.target.value) || 0)}
                    />
                  </FormControl>
                  <FormDescription>
                    Einfache Strecke in Kilometern
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="is_round_trip"
              render={({ field }) => (
                <FormItem className="flex flex-row items-center justify-between rounded-lg border p-3">
                  <div className="space-y-0.5">
                    <FormLabel>Hin- und Rückfahrt</FormLabel>
                    <FormDescription>
                      Kilometer werden verdoppelt
                    </FormDescription>
                  </div>
                  <FormControl>
                    <Switch
                      checked={field.value}
                      onCheckedChange={field.onChange}
                    />
                  </FormControl>
                </FormItem>
              )}
            />

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
                <span className="text-muted-foreground">Gesamtkilometer</span>
                <span className="font-mono">{formatKilometers(calculation.total_kilometers)}</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-muted-foreground">Satz pro km</span>
                <span className="font-mono">{formatCurrency(calculation.rate_per_km)}</span>
              </div>
              <Separator />
              <div className="flex justify-between items-center">
                <span className="font-medium">Erstattungsbetrag</span>
                <Badge variant="default" className="text-lg px-3">
                  {formatCurrency(calculation.total_amount)}
                </Badge>
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

export default MileageCalculator;
