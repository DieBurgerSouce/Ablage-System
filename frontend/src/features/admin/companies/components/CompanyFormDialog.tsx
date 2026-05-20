/**
 * CompanyFormDialog - Formular zum Erstellen/Bearbeiten einer Firma
 */

import { useEffect } from 'react';
import { useForm } from 'react-hook-form';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Separator } from '@/components/ui/separator';
import { Loader2 } from 'lucide-react';
import type { Company, CompanyCreate, CompanyUpdate } from '@/types/models/company';
import { LEGAL_FORM_OPTIONS, KONTENRAHMEN_OPTIONS } from '@/types/models/company';

interface CompanyFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  company: Company | null;
  onSubmit: (data: CompanyCreate | CompanyUpdate) => Promise<void>;
  isSubmitting: boolean;
}

type FormData = {
  name: string;
  short_name: string;
  display_name: string;
  legal_form: string;
  vat_id: string;
  tax_number: string;
  commercial_register: string;
  court: string;
  street: string;
  street_number: string;
  postal_code: string;
  city: string;
  country: string;
  email: string;
  phone: string;
  website: string;
  iban: string;
  bic: string;
  bank_name: string;
  default_currency: string;
  fiscal_year_start: string;
  kontenrahmen: string;
};

export function CompanyFormDialog({
  open,
  onOpenChange,
  company,
  onSubmit,
  isSubmitting,
}: CompanyFormDialogProps) {
  const isEditing = !!company;

  const { register, handleSubmit, reset, setValue, watch, formState: { errors } } = useForm<FormData>({
    defaultValues: {
      name: '',
      short_name: '',
      display_name: '',
      legal_form: '',
      vat_id: '',
      tax_number: '',
      commercial_register: '',
      court: '',
      street: '',
      street_number: '',
      postal_code: '',
      city: '',
      country: 'DE',
      email: '',
      phone: '',
      website: '',
      iban: '',
      bic: '',
      bank_name: '',
      default_currency: 'EUR',
      fiscal_year_start: '1',
      kontenrahmen: 'SKR03',
    },
  });

  // Reset form when company changes
  useEffect(() => {
    if (company) {
      reset({
        name: company.name,
        short_name: company.short_name || '',
        display_name: company.display_name || '',
        legal_form: company.legal_form || '',
        vat_id: company.vat_id || '',
        tax_number: company.tax_number || '',
        commercial_register: company.commercial_register || '',
        court: company.court || '',
        street: company.street || '',
        street_number: company.street_number || '',
        postal_code: company.postal_code || '',
        city: company.city || '',
        country: company.country || 'DE',
        email: company.email || '',
        phone: company.phone || '',
        website: company.website || '',
        iban: company.iban || '',
        bic: company.bic || '',
        bank_name: company.bank_name || '',
        default_currency: company.default_currency || 'EUR',
        fiscal_year_start: String(company.fiscal_year_start || 1),
        kontenrahmen: company.kontenrahmen || 'SKR03',
      });
    } else {
      reset({
        name: '',
        short_name: '',
        display_name: '',
        legal_form: '',
        vat_id: '',
        tax_number: '',
        commercial_register: '',
        court: '',
        street: '',
        street_number: '',
        postal_code: '',
        city: '',
        country: 'DE',
        email: '',
        phone: '',
        website: '',
        iban: '',
        bic: '',
        bank_name: '',
        default_currency: 'EUR',
        fiscal_year_start: '1',
        kontenrahmen: 'SKR03',
      });
    }
  }, [company, reset]);

  const onFormSubmit = async (data: FormData) => {
    const payload: CompanyCreate | CompanyUpdate = {
      name: data.name,
      short_name: data.short_name || undefined,
      display_name: data.display_name || undefined,
      legal_form: data.legal_form || undefined,
      vat_id: data.vat_id || undefined,
      tax_number: data.tax_number || undefined,
      commercial_register: data.commercial_register || undefined,
      court: data.court || undefined,
      street: data.street || undefined,
      street_number: data.street_number || undefined,
      postal_code: data.postal_code || undefined,
      city: data.city || undefined,
      country: data.country || 'DE',
      email: data.email || undefined,
      phone: data.phone || undefined,
      website: data.website || undefined,
      iban: data.iban || undefined,
      bic: data.bic || undefined,
      bank_name: data.bank_name || undefined,
      default_currency: data.default_currency || 'EUR',
      fiscal_year_start: parseInt(data.fiscal_year_start) || 1,
      kontenrahmen: data.kontenrahmen as 'SKR03' | 'SKR04',
    };

    await onSubmit(payload);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>
            {isEditing ? 'Firma bearbeiten' : 'Neue Firma erstellen'}
          </DialogTitle>
          <DialogDescription>
            {isEditing
              ? 'Bearbeiten Sie die Firmendaten.'
              : 'Erstellen Sie eine neue Firma für Ihr Multi-Mandanten-System.'}
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit(onFormSubmit)} className="space-y-4">
          <Tabs defaultValue="general">
            <TabsList className="grid w-full grid-cols-4">
              <TabsTrigger value="general">Allgemein</TabsTrigger>
              <TabsTrigger value="legal">Rechtlich</TabsTrigger>
              <TabsTrigger value="contact">Kontakt</TabsTrigger>
              <TabsTrigger value="banking">Banking</TabsTrigger>
            </TabsList>

            {/* Allgemein Tab */}
            <TabsContent value="general" className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="name">Firmenname *</Label>
                  <Input
                    id="name"
                    {...register('name', { required: 'Firmenname ist erforderlich' })}
                    placeholder="Muster GmbH"
                  />
                  {errors.name && (
                    <p className="text-sm text-destructive">{errors.name.message}</p>
                  )}
                </div>
                <div className="space-y-2">
                  <Label htmlFor="short_name">Kurzname (für URLs)</Label>
                  <Input
                    id="short_name"
                    {...register('short_name')}
                    placeholder="muster"
                  />
                  <p className="text-xs text-muted-foreground">
                    Wird für Ordner-Namen und URLs verwendet
                  </p>
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="display_name">Anzeigename</Label>
                <Input
                  id="display_name"
                  {...register('display_name')}
                  placeholder="Muster GmbH - Zentrale"
                />
              </div>

              <Separator />

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="kontenrahmen">Kontenrahmen</Label>
                  <Select
                    value={watch('kontenrahmen')}
                    onValueChange={(value) => setValue('kontenrahmen', value)}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Kontenrahmen wählen" />
                    </SelectTrigger>
                    <SelectContent>
                      {KONTENRAHMEN_OPTIONS.map((opt) => (
                        <SelectItem key={opt.value} value={opt.value}>
                          {opt.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="fiscal_year_start">Geschäftsjahr beginnt</Label>
                  <Select
                    value={watch('fiscal_year_start')}
                    onValueChange={(value) => setValue('fiscal_year_start', value)}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Monat wählen" />
                    </SelectTrigger>
                    <SelectContent>
                      {[
                        'Januar', 'Februar', 'März', 'April', 'Mai', 'Juni',
                        'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember'
                      ].map((month, i) => (
                        <SelectItem key={i + 1} value={String(i + 1)}>
                          {month}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </TabsContent>

            {/* Rechtlich Tab */}
            <TabsContent value="legal" className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="legal_form">Rechtsform</Label>
                  <Select
                    value={watch('legal_form')}
                    onValueChange={(value) => setValue('legal_form', value)}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Rechtsform wählen" />
                    </SelectTrigger>
                    <SelectContent>
                      {LEGAL_FORM_OPTIONS.map((opt) => (
                        <SelectItem key={opt.value} value={opt.value}>
                          {opt.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="vat_id">USt-IdNr.</Label>
                  <Input
                    id="vat_id"
                    {...register('vat_id')}
                    placeholder="DE123456789"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="tax_number">Steuernummer</Label>
                  <Input
                    id="tax_number"
                    {...register('tax_number')}
                    placeholder="123/456/78901"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="commercial_register">Handelsregister</Label>
                  <Input
                    id="commercial_register"
                    {...register('commercial_register')}
                    placeholder="HRB 12345"
                  />
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="court">Registergericht</Label>
                <Input
                  id="court"
                  {...register('court')}
                  placeholder="Amtsgericht Musterstadt"
                />
              </div>
            </TabsContent>

            {/* Kontakt Tab */}
            <TabsContent value="contact" className="space-y-4">
              <div className="grid grid-cols-3 gap-4">
                <div className="col-span-2 space-y-2">
                  <Label htmlFor="street">Strasse</Label>
                  <Input
                    id="street"
                    {...register('street')}
                    placeholder="Musterstrasse"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="street_number">Nr.</Label>
                  <Input
                    id="street_number"
                    {...register('street_number')}
                    placeholder="123"
                  />
                </div>
              </div>

              <div className="grid grid-cols-3 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="postal_code">PLZ</Label>
                  <Input
                    id="postal_code"
                    {...register('postal_code')}
                    placeholder="12345"
                  />
                </div>
                <div className="col-span-2 space-y-2">
                  <Label htmlFor="city">Stadt</Label>
                  <Input
                    id="city"
                    {...register('city')}
                    placeholder="Musterstadt"
                  />
                </div>
              </div>

              <Separator />

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="email">E-Mail</Label>
                  <Input
                    id="email"
                    type="email"
                    {...register('email')}
                    placeholder="info@muster.de"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="phone">Telefon</Label>
                  <Input
                    id="phone"
                    {...register('phone')}
                    placeholder="+49 123 456789"
                  />
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="website">Website</Label>
                <Input
                  id="website"
                  {...register('website')}
                  placeholder="https://www.muster.de"
                />
              </div>
            </TabsContent>

            {/* Banking Tab */}
            <TabsContent value="banking" className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="iban">IBAN</Label>
                <Input
                  id="iban"
                  {...register('iban')}
                  placeholder="DE12 3456 7890 1234 5678 90"
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="bic">BIC</Label>
                  <Input
                    id="bic"
                    {...register('bic')}
                    placeholder="DEUTDEDB123"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="bank_name">Bank</Label>
                  <Input
                    id="bank_name"
                    {...register('bank_name')}
                    placeholder="Deutsche Bank"
                  />
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="default_currency">Währung</Label>
                <Select
                  value={watch('default_currency')}
                  onValueChange={(value) => setValue('default_currency', value)}
                >
                  <SelectTrigger className="w-32">
                    <SelectValue placeholder="Währung" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="EUR">EUR</SelectItem>
                    <SelectItem value="CHF">CHF</SelectItem>
                    <SelectItem value="USD">USD</SelectItem>
                    <SelectItem value="GBP">GBP</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </TabsContent>
          </Tabs>

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
              {isSubmitting && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              {isEditing ? 'Speichern' : 'Erstellen'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
