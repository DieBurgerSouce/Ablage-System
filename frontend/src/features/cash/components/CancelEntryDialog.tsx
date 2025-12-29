/**
 * Cancel Entry Dialog
 *
 * Dialog zum Stornieren eines Kassenbucheintrags.
 * GoBD-konform: Erstellt eine Gegenbuchung statt den Eintrag zu löschen.
 */

import * as React from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';
import { Textarea } from '@/components/ui/textarea';
import { Card, CardContent } from '@/components/ui/card';
import { Loader2, AlertTriangle } from 'lucide-react';
import { useCancelEntry } from '../hooks/use-cash-queries';
import { formatCurrency, formatDate, formatEntryType } from '../utils/format';
import type { CashEntry } from '@/types/models/cash';

// Validierungs-Schema
const cancelSchema = z.object({
  cancellation_reason: z
    .string()
    .min(10, 'Begruendung muss mindestens 10 Zeichen haben')
    .max(500, 'Begruendung zu lang'),
});

type CancelFormData = z.infer<typeof cancelSchema>;

interface CancelEntryDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  entry: CashEntry | null;
  onSuccess?: (cancellationEntry: CashEntry) => void;
}

export function CancelEntryDialog({
  open,
  onOpenChange,
  entry,
  onSuccess,
}: CancelEntryDialogProps) {
  const cancelMutation = useCancelEntry();

  const form = useForm<CancelFormData>({
    resolver: zodResolver(cancelSchema),
    defaultValues: {
      cancellation_reason: '',
    },
  });

  // Formular zurücksetzen wenn Dialog oeffnet
  React.useEffect(() => {
    if (open) {
      form.reset({
        cancellation_reason: '',
      });
    }
  }, [open, form]);

  const onSubmit = async (data: CancelFormData) => {
    if (!entry) return;

    try {
      const result = await cancelMutation.mutateAsync({
        entryId: entry.id,
        data: {
          cancellation_reason: data.cancellation_reason,
        },
      });
      onSuccess?.(result);
      onOpenChange(false);
    } catch (error) {
      // Fehler werden vom Mutation-Hook behandelt
    }
  };

  if (!entry) return null;

  const isIncome = ['income', 'deposit', 'difference_plus', 'opening'].includes(entry.entry_type);

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle className="flex items-center gap-2 text-destructive">
            <AlertTriangle className="h-5 w-5" aria-hidden="true" />
            Eintrag stornieren
          </AlertDialogTitle>
          <AlertDialogDescription>
            Dieser Eintrag wird nicht gelöscht, sondern durch eine Gegenbuchung
            neutralisiert. Dies ist erforderlich für die GoBD-konforme
            Kassenbuchfuehrung.
          </AlertDialogDescription>
        </AlertDialogHeader>

        {/* Eintrag-Details */}
        <Card className="my-4">
          <CardContent className="pt-4 space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-muted-foreground">Eintrags-Nr.</span>
              <span className="font-mono">{entry.entry_number}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Datum</span>
              <span>{formatDate(entry.entry_date)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Typ</span>
              <span>{formatEntryType(entry.entry_type)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Beschreibung</span>
              <span className="text-right max-w-[200px] truncate">{entry.description}</span>
            </div>
            <div className="flex justify-between border-t pt-2">
              <span className="font-medium">Betrag</span>
              <span
                className={`font-mono font-bold ${isIncome ? 'text-green-600' : 'text-red-600'}`}
              >
                {isIncome ? '+' : '-'}{formatCurrency(Math.abs(entry.amount))}
              </span>
            </div>
          </CardContent>
        </Card>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            <FormField
              control={form.control}
              name="cancellation_reason"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Begruendung *</FormLabel>
                  <FormControl>
                    <Textarea
                      placeholder="Warum wird dieser Eintrag storniert?"
                      className="resize-none"
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <AlertDialogFooter>
              <AlertDialogCancel disabled={cancelMutation.isPending}>
                Abbrechen
              </AlertDialogCancel>
              <AlertDialogAction
                type="submit"
                className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                disabled={cancelMutation.isPending}
                onClick={(e) => {
                  e.preventDefault();
                  form.handleSubmit(onSubmit)();
                }}
              >
                {cancelMutation.isPending && (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" />
                )}
                Stornieren
              </AlertDialogAction>
            </AlertDialogFooter>
          </form>
        </Form>
      </AlertDialogContent>
    </AlertDialog>
  );
}

export default CancelEntryDialog;
