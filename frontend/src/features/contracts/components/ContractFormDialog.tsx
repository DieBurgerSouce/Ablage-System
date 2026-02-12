/**
 * ContractFormDialog - Dialog zum Erstellen/Bearbeiten von Verträgen
 *
 * Features:
 * - Multi-Step Form
 * - Validierung
 * - Partei-Suche
 * - Datumsauswahl
 */

import { useState, useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { format } from 'date-fns';
import { de } from 'date-fns/locale';
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { Calendar } from '@/components/ui/calendar';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { cn } from '@/lib/utils';
import { CalendarIcon, Loader2 } from 'lucide-react';
import type { ContractCreateRequest, ContractUpdateRequest, Contract } from '../types/contract-types';
import {
  ContractType,
  ContractStatus,
  CONTRACT_TYPE_LABELS,
  CONTRACT_STATUS_LABELS,
} from '../types/contract-types';

interface ContractFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  contract?: Contract | null;
  onSubmit: (data: ContractCreateRequest | ContractUpdateRequest) => Promise<void>;
  isLoading: boolean;
}

type FormData = {
  contract_number: string;
  title: string;
  contract_type: ContractType;
  description: string;
  status?: ContractStatus;
  party_a_name: string;
  party_a_signatory: string;
  party_b_name: string;
  party_b_signatory: string;
  contract_date: Date | undefined;
  start_date: Date | undefined;
  end_date: Date | undefined;
  notice_period_days: number;
  auto_renewal: boolean;
  renewal_period_months: number;
  total_value: number;
  monthly_value: number;
  currency: string;
  payment_terms: string;
  governing_law: string;
  notes: string;
};

function DatePickerField({
  value,
  onChange,
  label,
}: {
  value: Date | undefined;
  onChange: (date: Date | undefined) => void;
  label: string;
}) {
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          className={cn(
            'w-full justify-start text-left font-normal',
            !value && 'text-muted-foreground'
          )}
        >
          <CalendarIcon className="mr-2 h-4 w-4" />
          {value ? format(value, 'dd.MM.yyyy', { locale: de }) : label}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-auto p-0" align="start">
        <Calendar
          mode="single"
          selected={value}
          onSelect={onChange}
          locale={de}
          initialFocus
        />
      </PopoverContent>
    </Popover>
  );
}

export function ContractFormDialog({
  open,
  onOpenChange,
  contract,
  onSubmit,
  isLoading,
}: ContractFormDialogProps) {
  const isEdit = !!contract;
  const [step, setStep] = useState(1);
  const totalSteps = 3;

  const form = useForm<FormData>({
    defaultValues: {
      contract_number: '',
      title: '',
      contract_type: ContractType.SERVICE,
      description: '',
      status: ContractStatus.DRAFT,
      party_a_name: '',
      party_a_signatory: '',
      party_b_name: '',
      party_b_signatory: '',
      contract_date: undefined,
      start_date: undefined,
      end_date: undefined,
      notice_period_days: 30,
      auto_renewal: false,
      renewal_period_months: 12,
      total_value: 0,
      monthly_value: 0,
      currency: 'EUR',
      payment_terms: '',
      governing_law: 'Deutsches Recht',
      notes: '',
    },
  });

  // Reset form when contract changes
  useEffect(() => {
    if (contract) {
      form.reset({
        contract_number: contract.contract_number,
        title: contract.title,
        contract_type: contract.contract_type as ContractType,
        description: contract.description || '',
        status: contract.status as ContractStatus,
        party_a_name: contract.party_a_name || '',
        party_a_signatory: contract.party_a_signatory || '',
        party_b_name: contract.party_b_name || '',
        party_b_signatory: contract.party_b_signatory || '',
        contract_date: contract.contract_date ? new Date(contract.contract_date) : undefined,
        start_date: contract.start_date ? new Date(contract.start_date) : undefined,
        end_date: contract.end_date ? new Date(contract.end_date) : undefined,
        notice_period_days: contract.notice_period_days,
        auto_renewal: contract.auto_renewal,
        renewal_period_months: contract.renewal_period_months || 12,
        total_value: contract.total_value || 0,
        monthly_value: contract.monthly_value || 0,
        currency: contract.currency,
        payment_terms: contract.payment_terms || '',
        governing_law: contract.governing_law,
        notes: contract.notes || '',
      });
    } else {
      form.reset();
    }
    setStep(1);
  }, [contract, form, open]);

  const handleSubmit = async (data: FormData) => {
    const submitData: ContractCreateRequest | ContractUpdateRequest = {
      contract_number: data.contract_number,
      title: data.title,
      contract_type: data.contract_type,
      description: data.description || undefined,
      party_a_name: data.party_a_name || undefined,
      party_a_signatory: data.party_a_signatory || undefined,
      party_b_name: data.party_b_name || undefined,
      party_b_signatory: data.party_b_signatory || undefined,
      contract_date: data.contract_date?.toISOString().split('T')[0],
      start_date: data.start_date?.toISOString().split('T')[0] || new Date().toISOString().split('T')[0],
      end_date: data.end_date?.toISOString().split('T')[0],
      notice_period_days: data.notice_period_days,
      auto_renewal: data.auto_renewal,
      renewal_period_months: data.auto_renewal ? data.renewal_period_months : undefined,
      total_value: data.total_value || undefined,
      monthly_value: data.monthly_value || undefined,
      currency: data.currency,
      payment_terms: data.payment_terms || undefined,
      governing_law: data.governing_law,
      notes: data.notes || undefined,
    };

    if (isEdit) {
      (submitData as ContractUpdateRequest).status = data.status;
    }

    await onSubmit(submitData);
    onOpenChange(false);
  };

  const nextStep = () => {
    if (step < totalSteps) setStep(step + 1);
  };

  const prevStep = () => {
    if (step > 1) setStep(step - 1);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[600px]">
        <DialogHeader>
          <DialogTitle>
            {isEdit ? 'Vertrag bearbeiten' : 'Neuer Vertrag'}
          </DialogTitle>
          <DialogDescription>
            Schritt {step} von {totalSteps}:{' '}
            {step === 1 ? 'Grunddaten' : step === 2 ? 'Parteien & Laufzeit' : 'Finanzen & Notizen'}
          </DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4">
            {/* Step 1: Basic Info */}
            {step === 1 && (
              <div className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <FormField
                    control={form.control}
                    name="contract_number"
                    rules={{ required: 'Vertragsnummer erforderlich' }}
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Vertragsnummer *</FormLabel>
                        <FormControl>
                          <Input placeholder="V-2026-001" {...field} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />

                  <FormField
                    control={form.control}
                    name="contract_type"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Vertragstyp</FormLabel>
                        <Select
                          value={field.value}
                          onValueChange={field.onChange}
                        >
                          <FormControl>
                            <SelectTrigger>
                              <SelectValue />
                            </SelectTrigger>
                          </FormControl>
                          <SelectContent>
                            {Object.entries(CONTRACT_TYPE_LABELS).map(([value, label]) => (
                              <SelectItem key={value} value={value}>
                                {label}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </div>

                <FormField
                  control={form.control}
                  name="title"
                  rules={{ required: 'Titel erforderlich' }}
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Titel *</FormLabel>
                      <FormControl>
                        <Input placeholder="Wartungsvertrag Server-Infrastruktur" {...field} />
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
                      <FormLabel>Beschreibung</FormLabel>
                      <FormControl>
                        <Textarea
                          placeholder="Kurze Beschreibung des Vertragsgegenstands..."
                          {...field}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                {isEdit && (
                  <FormField
                    control={form.control}
                    name="status"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Status</FormLabel>
                        <Select
                          value={field.value}
                          onValueChange={field.onChange}
                        >
                          <FormControl>
                            <SelectTrigger>
                              <SelectValue />
                            </SelectTrigger>
                          </FormControl>
                          <SelectContent>
                            {Object.entries(CONTRACT_STATUS_LABELS).map(([value, label]) => (
                              <SelectItem key={value} value={value}>
                                {label}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                )}
              </div>
            )}

            {/* Step 2: Parties & Timeline */}
            {step === 2 && (
              <div className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-4">
                    <h4 className="font-medium text-sm">Partei A (Wir)</h4>
                    <FormField
                      control={form.control}
                      name="party_a_name"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Name</FormLabel>
                          <FormControl>
                            <Input placeholder="Unsere Firma GmbH" {...field} />
                          </FormControl>
                        </FormItem>
                      )}
                    />
                    <FormField
                      control={form.control}
                      name="party_a_signatory"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Unterzeichner</FormLabel>
                          <FormControl>
                            <Input placeholder="Max Mustermann" {...field} />
                          </FormControl>
                        </FormItem>
                      )}
                    />
                  </div>

                  <div className="space-y-4">
                    <h4 className="font-medium text-sm">Partei B (Partner)</h4>
                    <FormField
                      control={form.control}
                      name="party_b_name"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Name</FormLabel>
                          <FormControl>
                            <Input placeholder="Partner GmbH" {...field} />
                          </FormControl>
                        </FormItem>
                      )}
                    />
                    <FormField
                      control={form.control}
                      name="party_b_signatory"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Unterzeichner</FormLabel>
                          <FormControl>
                            <Input placeholder="Erika Musterfrau" {...field} />
                          </FormControl>
                        </FormItem>
                      )}
                    />
                  </div>
                </div>

                <div className="grid grid-cols-3 gap-4">
                  <FormField
                    control={form.control}
                    name="contract_date"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Vertragsdatum</FormLabel>
                        <DatePickerField
                          value={field.value}
                          onChange={field.onChange}
                          label="Datum wählen"
                        />
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name="start_date"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Beginn *</FormLabel>
                        <DatePickerField
                          value={field.value}
                          onChange={field.onChange}
                          label="Beginn wählen"
                        />
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name="end_date"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Ende</FormLabel>
                        <DatePickerField
                          value={field.value}
                          onChange={field.onChange}
                          label="Ende wählen"
                        />
                      </FormItem>
                    )}
                  />
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <FormField
                    control={form.control}
                    name="notice_period_days"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Kündigungsfrist (Tage)</FormLabel>
                        <FormControl>
                          <Input
                            type="number"
                            min={0}
                            {...field}
                            onChange={(e) => field.onChange(parseInt(e.target.value) || 0)}
                          />
                        </FormControl>
                      </FormItem>
                    )}
                  />

                  <FormField
                    control={form.control}
                    name="auto_renewal"
                    render={({ field }) => (
                      <FormItem className="flex flex-row items-center justify-between rounded-lg border p-4">
                        <div className="space-y-0.5">
                          <FormLabel className="text-base">Auto-Verlängerung</FormLabel>
                          <FormDescription>
                            Vertrag verlängert sich automatisch
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
                </div>

                {form.watch('auto_renewal') && (
                  <FormField
                    control={form.control}
                    name="renewal_period_months"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Verlängerungszeitraum (Monate)</FormLabel>
                        <FormControl>
                          <Input
                            type="number"
                            min={1}
                            {...field}
                            onChange={(e) => field.onChange(parseInt(e.target.value) || 12)}
                          />
                        </FormControl>
                      </FormItem>
                    )}
                  />
                )}
              </div>
            )}

            {/* Step 3: Financials & Notes */}
            {step === 3 && (
              <div className="space-y-4">
                <div className="grid grid-cols-3 gap-4">
                  <FormField
                    control={form.control}
                    name="total_value"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Gesamtwert</FormLabel>
                        <FormControl>
                          <Input
                            type="number"
                            min={0}
                            step={0.01}
                            placeholder="0.00"
                            {...field}
                            onChange={(e) => field.onChange(parseFloat(e.target.value) || 0)}
                          />
                        </FormControl>
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name="monthly_value"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Monatswert</FormLabel>
                        <FormControl>
                          <Input
                            type="number"
                            min={0}
                            step={0.01}
                            placeholder="0.00"
                            {...field}
                            onChange={(e) => field.onChange(parseFloat(e.target.value) || 0)}
                          />
                        </FormControl>
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name="currency"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Währung</FormLabel>
                        <Select
                          value={field.value}
                          onValueChange={field.onChange}
                        >
                          <FormControl>
                            <SelectTrigger>
                              <SelectValue />
                            </SelectTrigger>
                          </FormControl>
                          <SelectContent>
                            <SelectItem value="EUR">EUR</SelectItem>
                            <SelectItem value="USD">USD</SelectItem>
                            <SelectItem value="CHF">CHF</SelectItem>
                            <SelectItem value="GBP">GBP</SelectItem>
                          </SelectContent>
                        </Select>
                      </FormItem>
                    )}
                  />
                </div>

                <FormField
                  control={form.control}
                  name="payment_terms"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Zahlungsbedingungen</FormLabel>
                      <FormControl>
                        <Input placeholder="z.B. 30 Tage netto, 2% Skonto bei 10 Tagen" {...field} />
                      </FormControl>
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="governing_law"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Anwendbares Recht</FormLabel>
                      <FormControl>
                        <Input placeholder="Deutsches Recht" {...field} />
                      </FormControl>
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="notes"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Notizen</FormLabel>
                      <FormControl>
                        <Textarea
                          placeholder="Interne Notizen zum Vertrag..."
                          rows={4}
                          {...field}
                        />
                      </FormControl>
                    </FormItem>
                  )}
                />
              </div>
            )}

            <DialogFooter className="flex justify-between">
              <div>
                {step > 1 && (
                  <Button type="button" variant="outline" onClick={prevStep}>
                    Zurück
                  </Button>
                )}
              </div>
              <div className="flex gap-2">
                <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
                  Abbrechen
                </Button>
                {step < totalSteps ? (
                  <Button type="button" onClick={nextStep}>
                    Weiter
                  </Button>
                ) : (
                  <Button type="submit" disabled={isLoading}>
                    {isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                    {isEdit ? 'Speichern' : 'Erstellen'}
                  </Button>
                )}
              </div>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
