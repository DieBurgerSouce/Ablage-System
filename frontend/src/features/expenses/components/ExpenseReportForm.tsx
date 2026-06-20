/**
 * Expense Report Form
 *
 * Formular zum Erstellen/Bearbeiten einer Spesenabrechnung.
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
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Button } from '@/components/ui/button';
import { Loader2 } from 'lucide-react';
import { useCreateExpenseReport, useUpdateExpenseReport } from '../hooks/use-expense-queries';
import type { ExpenseReport, ExpenseReportCreate, ExpenseReportUpdate } from '@/types/models/expense';

// Validierungs-Schema
const reportSchema = z.object({
  title: z.string().min(1, 'Titel ist erforderlich').max(100, 'Titel zu lang'),
  description: z.string().max(1000, 'Beschreibung zu lang').optional(),
  period_start: z.string().min(1, 'Startdatum ist erforderlich'),
  period_end: z.string().min(1, 'Enddatum ist erforderlich'),
}).refine((data) => {
  return new Date(data.period_start) <= new Date(data.period_end);
}, {
  message: 'Enddatum muss nach Startdatum liegen',
  path: ['period_end'],
});

type ReportFormData = z.infer<typeof reportSchema>;

interface ExpenseReportFormProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  report?: ExpenseReport | null;
  onSuccess?: (report: ExpenseReport) => void;
}

export function ExpenseReportForm({
  open,
  onOpenChange,
  report,
  onSuccess,
}: ExpenseReportFormProps) {
  const isEditing = !!report;
  const createMutation = useCreateExpenseReport();
  const updateMutation = useUpdateExpenseReport();

  // Default Zeitraum: aktueller Monat
  const today = new Date();
  const monthStart = new Date(today.getFullYear(), today.getMonth(), 1).toISOString().split('T')[0];
  const monthEnd = new Date(today.getFullYear(), today.getMonth() + 1, 0).toISOString().split('T')[0];

  const form = useForm<ReportFormData>({
    resolver: zodResolver(reportSchema),
    defaultValues: {
      title: report?.title ?? '',
      description: report?.description ?? '',
      period_start: report?.period_start ?? monthStart,
      period_end: report?.period_end ?? monthEnd,
    },
  });

  // Formular zurücksetzen wenn Report wechselt
  React.useEffect(() => {
    if (open) {
      form.reset({
        title: report?.title ?? '',
        description: report?.description ?? '',
        period_start: report?.period_start ?? monthStart,
        period_end: report?.period_end ?? monthEnd,
      });
    }
  }, [open, report, form, monthStart, monthEnd]);

  const onSubmit = async (data: ReportFormData) => {
    try {
      if (isEditing && report) {
        const updateData: ExpenseReportUpdate = {
          title: data.title,
          description: data.description,
          period_start: data.period_start,
          period_end: data.period_end,
        };
        const result = await updateMutation.mutateAsync({
          id: report.id,
          data: updateData,
        });
        onSuccess?.(result);
      } else {
        const createData: ExpenseReportCreate = {
          title: data.title,
          description: data.description,
          period_start: data.period_start,
          period_end: data.period_end,
        };
        const result = await createMutation.mutateAsync(createData);
        onSuccess?.(result);
      }
      onOpenChange(false);
    } catch (error) {
      // Fehler werden vom Mutation-Hook behandelt
    }
  };

  const isSubmitting = createMutation.isPending || updateMutation.isPending;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle>
            {isEditing ? 'Abrechnung bearbeiten' : 'Neue Spesenabrechnung'}
          </DialogTitle>
          <DialogDescription>
            {isEditing
              ? 'Ändern Sie die Abrechnungsdetails.'
              : 'Erstellen Sie eine neue Spesenabrechnung für Ihre Ausgaben.'}
          </DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            <FormField
              control={form.control}
              name="title"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Titel *</FormLabel>
                  <FormControl>
                    <Input
                      placeholder="z.B. Dienstreise Berlin, Messebesuch..."
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
                name="period_start"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Von *</FormLabel>
                    <FormControl>
                      <Input type="date" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="period_end"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Bis *</FormLabel>
                    <FormControl>
                      <Input type="date" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            <FormField
              control={form.control}
              name="description"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Beschreibung</FormLabel>
                  <FormControl>
                    <Textarea
                      placeholder="Optionale Beschreibung oder Bemerkungen..."
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
                disabled={isSubmitting}
              >
                Abbrechen
              </Button>
              <Button type="submit" disabled={isSubmitting}>
                {isSubmitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                {isEditing ? 'Speichern' : 'Erstellen'}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}

export default ExpenseReportForm;
