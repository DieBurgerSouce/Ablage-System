/**
 * Expense Item Form
 *
 * Formular zum Hinzufügen einer Position zur Spesenabrechnung.
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Button } from '@/components/ui/button';
import { Loader2, Receipt, Car, Utensils } from 'lucide-react';
import { useAddExpenseItem } from '../hooks/use-expense-queries';
import { MileageCalculator } from './MileageCalculator';
import { PerDiemCalculator } from './PerDiemCalculator';
import type { ExpenseItem, ExpenseItemCreate, ExpenseType, MileageCalculation, PerDiemCalculation } from '@/types/models/expense';

// Validierungs-Schema
const itemSchema = z.object({
  expense_type: z.enum(['receipt', 'mileage', 'per_diem', 'flat_rate']),
  description: z.string().min(1, 'Beschreibung ist erforderlich').max(500),
  amount: z.number().positive('Betrag muss positiv sein'),
  expense_date: z.string().min(1, 'Datum ist erforderlich'),
  receipt_number: z.string().max(50).optional(),
  tax_rate: z.number().min(0).max(100).optional(),
  // Spezifische Felder
  kilometers: z.number().optional(),
  travel_start: z.string().optional(),
  travel_end: z.string().optional(),
});

type ItemFormData = z.infer<typeof itemSchema>;

interface ExpenseItemFormProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  reportId: string;
  onSuccess?: (item: ExpenseItem) => void;
}

export function ExpenseItemForm({
  open,
  onOpenChange,
  reportId,
  onSuccess,
}: ExpenseItemFormProps) {
  const addMutation = useAddExpenseItem();
  const [activeTab, setActiveTab] = React.useState<string>('receipt');

  const today = new Date().toISOString().split('T')[0];

  const form = useForm<ItemFormData>({
    resolver: zodResolver(itemSchema),
    defaultValues: {
      expense_type: 'receipt',
      description: '',
      amount: 0,
      expense_date: today,
      receipt_number: '',
      tax_rate: 19,
    },
  });

  // Formular zurücksetzen wenn Dialog öffnet
  React.useEffect(() => {
    if (open) {
      form.reset({
        expense_type: 'receipt',
        description: '',
        amount: 0,
        expense_date: today,
        receipt_number: '',
        tax_rate: 19,
      });
      setActiveTab('receipt');
    }
  }, [open, form, today]);

  // Tab-Wechsel aktualisiert expense_type
  React.useEffect(() => {
    form.setValue('expense_type', activeTab as ExpenseType);
  }, [activeTab, form]);

  const onSubmit = async (data: ItemFormData) => {
    try {
      const createData: ExpenseItemCreate = {
        expense_type: data.expense_type,
        description: data.description,
        amount: data.amount,
        expense_date: data.expense_date,
        receipt_number: data.receipt_number,
        tax_rate: data.tax_rate,
        // Backend-Vertrag: mileage_km (travel_start/_end existieren im
        // Create-Schema nicht — sie fliessen nur in die Beschreibung ein)
        mileage_km: data.kilometers,
      };

      const result = await addMutation.mutateAsync({
        reportId,
        data: createData,
      });
      onSuccess?.(result);
      onOpenChange(false);
    } catch (error) {
      // Fehler werden vom Mutation-Hook behandelt
    }
  };

  const handleMileageCalculation = (calc: MileageCalculation) => {
    form.setValue('amount', calc.total_amount);
    form.setValue('kilometers', calc.kilometers);
    form.setValue('description', `Kilometergeld: ${calc.kilometers} km x EUR ${calc.rate_per_km}`);
  };

  const handlePerDiemCalculation = (calc: PerDiemCalculation) => {
    form.setValue('amount', calc.total_amount);
    form.setValue('travel_start', calc.travel_start);
    form.setValue('travel_end', calc.travel_end);
    const fullDaysText = (calc.full_days ?? 0) > 0 ? `${calc.full_days} volle Tage` : '';
    const partialDaysText = (calc.partial_days ?? 0) > 0 ? `${calc.partial_days} An-/Abreisetage` : '';
    const daysText = [fullDaysText, partialDaysText].filter(Boolean).join(', ');
    form.setValue('description', `Verpflegungspauschale: ${daysText}`);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[600px]">
        <DialogHeader>
          <DialogTitle>Position hinzufügen</DialogTitle>
          <DialogDescription>
            Fügen Sie eine neue Position zur Spesenabrechnung hinzu.
          </DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            <Tabs value={activeTab} onValueChange={setActiveTab}>
              <TabsList className="grid w-full grid-cols-3">
                <TabsTrigger value="receipt" className="flex items-center gap-2">
                  <Receipt className="h-4 w-4" />
                  Beleg
                </TabsTrigger>
                <TabsTrigger value="mileage" className="flex items-center gap-2">
                  <Car className="h-4 w-4" />
                  Kilometer
                </TabsTrigger>
                <TabsTrigger value="per_diem" className="flex items-center gap-2">
                  <Utensils className="h-4 w-4" />
                  Verpflegung
                </TabsTrigger>
              </TabsList>

              {/* Beleg-Tab */}
              <TabsContent value="receipt" className="space-y-4">
                <FormField
                  control={form.control}
                  name="expense_date"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Datum *</FormLabel>
                      <FormControl>
                        <Input type="date" max={today} {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="description"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Beschreibung *</FormLabel>
                      <FormControl>
                        <Textarea
                          placeholder="z.B. Taxifahrt zum Kunden, Hotelrechnung..."
                          className="resize-none"
                          {...field}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <div className="grid gap-4 sm:grid-cols-2">
                  <FormField
                    control={form.control}
                    name="amount"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Betrag (EUR) *</FormLabel>
                        <FormControl>
                          <Input
                            type="number"
                            step="0.01"
                            min="0.01"
                            placeholder="0.00"
                            {...field}
                            onChange={(e) => field.onChange(parseFloat(e.target.value) || 0)}
                          />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />

                  <FormField
                    control={form.control}
                    name="receipt_number"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Belegnummer</FormLabel>
                        <FormControl>
                          <Input placeholder="Optional" {...field} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </div>
              </TabsContent>

              {/* Kilometer-Tab */}
              <TabsContent value="mileage" className="space-y-4">
                <MileageCalculator onCalculate={handleMileageCalculation} />

                <FormField
                  control={form.control}
                  name="expense_date"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Datum *</FormLabel>
                      <FormControl>
                        <Input type="date" max={today} {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </TabsContent>

              {/* Verpflegung-Tab */}
              <TabsContent value="per_diem" className="space-y-4">
                <PerDiemCalculator onCalculate={handlePerDiemCalculation} />
              </TabsContent>
            </Tabs>

            {/* Gemeinsame Felder (am Ende anzeigen) */}
            {activeTab !== 'receipt' && (
              <FormField
                control={form.control}
                name="description"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Beschreibung</FormLabel>
                    <FormControl>
                      <Input {...field} readOnly className="bg-muted" />
                    </FormControl>
                    <FormDescription>
                      Wird automatisch ausgefüllt
                    </FormDescription>
                  </FormItem>
                )}
              />
            )}

            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => onOpenChange(false)}
                disabled={addMutation.isPending}
              >
                Abbrechen
              </Button>
              <Button type="submit" disabled={addMutation.isPending || form.watch('amount') <= 0}>
                {addMutation.isPending && (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                )}
                Hinzufügen
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}

export default ExpenseItemForm;
