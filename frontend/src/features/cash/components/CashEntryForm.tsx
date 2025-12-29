/**
 * Cash Entry Form
 *
 * Formular zum Erstellen eines neuen Kassenbucheintrags.
 * Unterstuetzt alle Eintragstypen inkl. Bewirtungskosten.
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
import { Textarea } from '@/components/ui/textarea';
import { Button } from '@/components/ui/button';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { Loader2, AlertTriangle, HelpCircle } from 'lucide-react';
import { useCreateEntry, useCategories } from '../hooks/use-cash-queries';
import { cashService } from '@/lib/api/services/cash';
import { EntertainmentFields } from './EntertainmentFields';
import type { CashEntry, CashEntryType, CashEntryCreate, DuplicateCheckResult } from '@/types/models/cash';

// Eintragstypen
const ENTRY_TYPES: { value: CashEntryType; label: string; isExpense: boolean }[] = [
  { value: 'income', label: 'Einnahme', isExpense: false },
  { value: 'expense', label: 'Ausgabe', isExpense: true },
  { value: 'deposit', label: 'Einlage (von Bank)', isExpense: false },
  { value: 'withdrawal', label: 'Entnahme (zur Bank)', isExpense: true },
  { value: 'entertainment', label: 'Bewirtungskosten', isExpense: true },
  { value: 'travel', label: 'Reisekosten', isExpense: true },
  { value: 'office', label: 'Buerobedarf', isExpense: true },
  { value: 'fuel', label: 'Kraftstoff', isExpense: true },
  { value: 'parking', label: 'Parkgebuehren', isExpense: true },
  { value: 'postage', label: 'Porto', isExpense: true },
  { value: 'tips', label: 'Trinkgeld', isExpense: true },
  { value: 'gifts', label: 'Geschenke', isExpense: true },
];

// MwSt-Saetze
const TAX_RATES = [
  { value: 0, label: '0% (keine MwSt)' },
  { value: 7, label: '7% (ermaessigt)' },
  { value: 19, label: '19% (Standard)' },
];

// Bewirtungs-Schema
const entertainmentSchema = z.object({
  business_reason: z.string().min(1, 'Geschaeftlicher Anlass ist erforderlich'),
  location: z.string().min(1, 'Ort ist erforderlich'),
  guests: z.array(z.object({
    name: z.string().min(1, 'Name ist erforderlich'),
    company: z.string().optional(),
  })).min(1, 'Mindestens ein Teilnehmer ist erforderlich'),
});

// Validierungs-Schema
const entrySchema = z.object({
  entry_type: z.string().min(1, 'Typ ist erforderlich'),
  amount: z.number().positive('Betrag muss positiv sein'),
  description: z.string().min(1, 'Beschreibung ist erforderlich').max(500),
  entry_date: z.string().min(1, 'Datum ist erforderlich'),
  category_id: z.string().optional(),
  tax_rate: z.number().min(0).max(100).optional(),
  receipt_number: z.string().max(50).optional(),
  entertainment_data: entertainmentSchema.optional(),
}).refine((data) => {
  // Bewirtungsdaten sind erforderlich bei Typ 'entertainment'
  if (data.entry_type === 'entertainment') {
    return data.entertainment_data !== undefined;
  }
  return true;
}, {
  message: 'Bewirtungsdaten sind erforderlich',
  path: ['entertainment_data'],
});

type EntryFormData = z.infer<typeof entrySchema>;

interface CashEntryFormProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  registerId: string;
  onSuccess?: (entry: CashEntry) => void;
}

export function CashEntryForm({
  open,
  onOpenChange,
  registerId,
  onSuccess,
}: CashEntryFormProps) {
  const createMutation = useCreateEntry();
  const { data: categoriesResponse } = useCategories();
  const categories = categoriesResponse?.categories ?? [];

  const today = new Date().toISOString().split('T')[0];

  // Duplikat-Warnung State
  const [duplicateWarning, setDuplicateWarning] = React.useState<{
    show: boolean;
    data: DuplicateCheckResult | null;
    pendingData: EntryFormData | null;
  }>({
    show: false,
    data: null,
    pendingData: null,
  });
  const [isCheckingDuplicate, setIsCheckingDuplicate] = React.useState(false);

  const form = useForm<EntryFormData>({
    resolver: zodResolver(entrySchema),
    defaultValues: {
      entry_type: 'expense',
      amount: 0,
      description: '',
      entry_date: today,
      category_id: undefined,
      tax_rate: 19,
      receipt_number: '',
      entertainment_data: undefined,
    },
  });

  const entryType = form.watch('entry_type');
  const amount = form.watch('amount');
  const isEntertainment = entryType === 'entertainment';

  // Bewirtungsdaten initialisieren wenn Typ wechselt
  React.useEffect(() => {
    if (isEntertainment) {
      form.setValue('entertainment_data', {
        business_reason: '',
        location: '',
        guests: [{ name: '', company: '' }],
      });
    } else {
      form.setValue('entertainment_data', undefined);
    }
  }, [isEntertainment, form]);

  // Formular zuruecksetzen wenn Dialog oeffnet
  React.useEffect(() => {
    if (open) {
      form.reset({
        entry_type: 'expense',
        amount: 0,
        description: '',
        entry_date: today,
        category_id: undefined,
        tax_rate: 19,
        receipt_number: '',
        entertainment_data: undefined,
      });
    }
  }, [open, form, today]);

  // Eigentliches Speichern ohne Duplikat-Check
  const saveEntry = async (data: EntryFormData) => {
    try {
      const createData: CashEntryCreate = {
        register_id: registerId,
        entry_type: data.entry_type as CashEntryType,
        amount: data.amount,
        description: data.description,
        entry_date: data.entry_date,
        category_id: data.category_id,
        tax_rate: data.tax_rate,
        receipt_number: data.receipt_number,
        entertainment_data: data.entertainment_data,
      };

      const result = await createMutation.mutateAsync(createData);
      onSuccess?.(result);
      onOpenChange(false);
    } catch (error) {
      // Fehler werden vom Mutation-Hook behandelt
    }
  };

  // Submit mit Duplikat-Check
  const onSubmit = async (data: EntryFormData) => {
    setIsCheckingDuplicate(true);
    try {
      // Duplikat-Check durchfuehren
      const duplicateCheck = await cashService.checkDuplicate({
        register_id: registerId,
        amount: data.amount,
        entry_date: data.entry_date,
        description: data.description,
        receipt_number: data.receipt_number,
      });

      if (duplicateCheck.is_duplicate) {
        // Warnung anzeigen
        setDuplicateWarning({
          show: true,
          data: duplicateCheck,
          pendingData: data,
        });
      } else {
        // Kein Duplikat - direkt speichern
        await saveEntry(data);
      }
    } catch (error) {
      // Bei Fehler im Duplikat-Check trotzdem speichern
      await saveEntry(data);
    } finally {
      setIsCheckingDuplicate(false);
    }
  };

  // Duplikat-Warnung bestaetigen
  const handleDuplicateConfirm = async () => {
    if (duplicateWarning.pendingData) {
      await saveEntry(duplicateWarning.pendingData);
    }
    setDuplicateWarning({ show: false, data: null, pendingData: null });
  };

  // Duplikat-Warnung abbrechen
  const handleDuplicateCancel = () => {
    setDuplicateWarning({ show: false, data: null, pendingData: null });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className={isEntertainment ? 'sm:max-w-[600px]' : 'sm:max-w-[425px]'}>
        <DialogHeader>
          <DialogTitle>Neuer Kassenbucheintrag</DialogTitle>
          <DialogDescription>
            Erfassen Sie eine neue Kassenbewegung.
          </DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              {/* Eintragstyp */}
              <FormField
                control={form.control}
                name="entry_type"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Typ *</FormLabel>
                    <Select onValueChange={field.onChange} value={field.value}>
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue placeholder="Typ waehlen" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        {ENTRY_TYPES.map((type) => (
                          <SelectItem key={type.value} value={type.value}>
                            {type.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )}
              />

              {/* Datum */}
              <FormField
                control={form.control}
                name="entry_date"
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
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              {/* Betrag */}
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

              {/* MwSt-Satz mit Tooltip */}
              <FormField
                control={form.control}
                name="tax_rate"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel className="flex items-center gap-1">
                      MwSt-Satz
                      <TooltipProvider>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <HelpCircle className="h-3 w-3 text-muted-foreground cursor-help" aria-hidden="true" />
                          </TooltipTrigger>
                          <TooltipContent side="top" className="max-w-xs">
                            <div className="space-y-1 text-sm">
                              <p><strong>19%</strong> - Standard fuer Waren und Dienstleistungen</p>
                              <p><strong>7%</strong> - Ermaessigt fuer Lebensmittel, Buecher, Zeitungen</p>
                              <p><strong>0%</strong> - Steuerfreie Umsaetze</p>
                            </div>
                          </TooltipContent>
                        </Tooltip>
                      </TooltipProvider>
                    </FormLabel>
                    <Select
                      onValueChange={(v) => field.onChange(parseInt(v))}
                      value={field.value?.toString()}
                    >
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue placeholder="MwSt waehlen" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        {TAX_RATES.map((rate) => (
                          <SelectItem key={rate.value} value={rate.value.toString()}>
                            {rate.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            {/* Beschreibung */}
            <FormField
              control={form.control}
              name="description"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Beschreibung *</FormLabel>
                  <FormControl>
                    <Textarea
                      placeholder="Kurze Beschreibung der Buchung..."
                      className="resize-none"
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <div className="grid gap-4 sm:grid-cols-2">
              {/* Kategorie mit Tooltip */}
              <FormField
                control={form.control}
                name="category_id"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel className="flex items-center gap-1">
                      Kategorie
                      <TooltipProvider>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <HelpCircle className="h-3 w-3 text-muted-foreground cursor-help" aria-hidden="true" />
                          </TooltipTrigger>
                          <TooltipContent side="top" className="max-w-xs">
                            <div className="text-sm">
                              <p>Ordnet die Buchung einem Buchungskonto zu (SKR03/SKR04).</p>
                              <p className="mt-1 text-muted-foreground">Wird fuer DATEV-Export verwendet.</p>
                            </div>
                          </TooltipContent>
                        </Tooltip>
                      </TooltipProvider>
                    </FormLabel>
                    <Select onValueChange={field.onChange} value={field.value}>
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue placeholder="Kategorie waehlen" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        {categories.map((cat) => (
                          <SelectItem key={cat.id} value={cat.id}>
                            {cat.name} ({cat.skr03_account || cat.skr04_account})
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )}
              />

              {/* Belegnummer mit Tooltip */}
              <FormField
                control={form.control}
                name="receipt_number"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel className="flex items-center gap-1">
                      Belegnummer
                      <TooltipProvider>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <HelpCircle className="h-3 w-3 text-muted-foreground cursor-help" aria-hidden="true" />
                          </TooltipTrigger>
                          <TooltipContent side="top" className="max-w-xs">
                            <div className="text-sm">
                              <p>Externe Referenz wie Rechnungsnummer oder Quittungsnummer.</p>
                              <p className="mt-1 text-muted-foreground">Optional - wird fuer GoBD-Compliance empfohlen.</p>
                            </div>
                          </TooltipContent>
                        </Tooltip>
                      </TooltipProvider>
                    </FormLabel>
                    <FormControl>
                      <Input placeholder="Optional" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            {/* Bewirtungskosten-Felder */}
            {isEntertainment && (
              <EntertainmentFields form={form} amount={amount} />
            )}

            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => onOpenChange(false)}
                disabled={createMutation.isPending || isCheckingDuplicate}
              >
                Abbrechen
              </Button>
              <Button
                type="submit"
                disabled={createMutation.isPending || isCheckingDuplicate}
              >
                {(createMutation.isPending || isCheckingDuplicate) && (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" />
                )}
                Buchen
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>

      {/* Duplikat-Warnung Dialog */}
      <AlertDialog open={duplicateWarning.show} onOpenChange={handleDuplicateCancel}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle className="flex items-center gap-2">
              <AlertTriangle className="h-5 w-5 text-amber-500" aria-hidden="true" />
              Moegliches Duplikat erkannt
            </AlertDialogTitle>
            <AlertDialogDescription asChild>
              <div className="space-y-3">
                <p>
                  Es existiert bereits eine aehnliche Buchung:
                </p>
                {duplicateWarning.data?.existing_entry && (
                  <div className="rounded-md border bg-muted/50 p-3 text-sm">
                    <div className="grid gap-1">
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">Beleg-Nr.:</span>
                        <span className="font-medium">
                          {duplicateWarning.data.existing_entry.entry_number}
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">Datum:</span>
                        <span className="font-medium">
                          {duplicateWarning.data.existing_entry.entry_date || '-'}
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">Betrag:</span>
                        <span className="font-medium">
                          {duplicateWarning.data.existing_entry.amount?.toFixed(2)} EUR
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">Beschreibung:</span>
                        <span className="font-medium truncate max-w-[200px]">
                          {duplicateWarning.data.existing_entry.description || '-'}
                        </span>
                      </div>
                    </div>
                  </div>
                )}
                <p className="text-amber-600">
                  Moechten Sie die Buchung trotzdem erstellen?
                </p>
              </div>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel onClick={handleDuplicateCancel}>
              Abbrechen
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDuplicateConfirm}
              className="bg-amber-600 hover:bg-amber-700"
            >
              Trotzdem buchen
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Dialog>
  );
}

export default CashEntryForm;
