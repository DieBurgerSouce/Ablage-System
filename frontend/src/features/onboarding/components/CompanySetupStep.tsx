/**
 * Schritt 2: Firma einrichten
 *
 * Erfasst Firmendetails:
 * - Name, Adresse
 * - Steuernummer, USt-ID
 * - IBAN (fuer Eingangs/Ausgangsrechnung-Erkennung)
 */

import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { cn } from '@/lib/utils'
import { Building2, Info } from 'lucide-react'
import { Alert, AlertDescription } from '@/components/ui/alert'

export interface CompanySetupFormData {
  name: string
  address_street: string
  address_city: string
  address_postal_code: string
  address_country: string
  tax_number: string
  vat_id: string
  iban: string
  email: string
  phone: string
}

interface CompanySetupStepProps {
  data: CompanySetupFormData
  onChange: (updates: Partial<CompanySetupFormData>) => void
  errors: Record<string, string>
}

const COUNTRIES = [
  { value: 'DE', label: 'Deutschland' },
  { value: 'AT', label: 'Oesterreich' },
  { value: 'CH', label: 'Schweiz' },
]

export function CompanySetupStep({ data, onChange, errors }: CompanySetupStepProps) {
  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="text-center pb-2">
        <div className="p-3 rounded-full bg-primary/10 border border-primary/20 inline-block mb-3">
          <Building2 className="w-8 h-8 text-primary" aria-hidden="true" />
        </div>
        <h2 className="text-lg font-semibold">Firma einrichten</h2>
        <p className="text-sm text-muted-foreground mt-1">
          Grunddaten Ihrer Firma fuer die automatische Dokumentenverarbeitung.
        </p>
      </div>

      {/* Firmenname */}
      <div className="space-y-1.5">
        <Label htmlFor="onb-company-name" className="text-sm font-medium">
          Firmenname <span className="text-destructive">*</span>
        </Label>
        <Input
          id="onb-company-name"
          value={data.name}
          onChange={(e) => onChange({ name: e.target.value })}
          placeholder="Muster GmbH"
          className={cn(errors.name && 'border-destructive')}
          aria-describedby={errors.name ? 'onb-name-error' : undefined}
          aria-invalid={!!errors.name}
        />
        {errors.name && (
          <p id="onb-name-error" className="text-xs text-destructive">
            {errors.name}
          </p>
        )}
      </div>

      {/* Steuer */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label htmlFor="onb-tax-number" className="text-sm font-medium">
            Steuernummer
          </Label>
          <Input
            id="onb-tax-number"
            value={data.tax_number}
            onChange={(e) => onChange({ tax_number: e.target.value })}
            placeholder="123/456/78901"
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="onb-vat-id" className="text-sm font-medium">
            USt-IdNr.
          </Label>
          <Input
            id="onb-vat-id"
            value={data.vat_id}
            onChange={(e) => onChange({ vat_id: e.target.value.toUpperCase() })}
            placeholder="DE123456789"
            className={cn(errors.vat_id && 'border-destructive')}
            aria-describedby={errors.vat_id ? 'onb-vat-error' : undefined}
            aria-invalid={!!errors.vat_id}
          />
          {errors.vat_id && (
            <p id="onb-vat-error" className="text-xs text-destructive">
              {errors.vat_id}
            </p>
          )}
        </div>
      </div>

      {/* IBAN */}
      <div className="space-y-1.5">
        <Label htmlFor="onb-iban" className="text-sm font-medium">
          IBAN (eigenes Bankkonto)
        </Label>
        <Input
          id="onb-iban"
          value={data.iban}
          onChange={(e) => onChange({ iban: e.target.value.toUpperCase().replace(/\s/g, '') })}
          placeholder="DE89 3704 0044 0532 0130 00"
          className={cn(errors.iban && 'border-destructive')}
          aria-describedby="onb-iban-hint"
        />
        <p id="onb-iban-hint" className="text-xs text-muted-foreground">
          Wird zur automatischen Erkennung von Eingangs- und Ausgangsrechnungen verwendet.
        </p>
      </div>

      {/* Adresse */}
      <fieldset className="space-y-3">
        <legend className="text-sm font-medium text-muted-foreground">Adresse</legend>
        <Input
          value={data.address_street}
          onChange={(e) => onChange({ address_street: e.target.value })}
          placeholder="Strasse und Hausnummer"
          aria-label="Strasse und Hausnummer"
        />
        <div className="grid grid-cols-3 gap-3">
          <Input
            value={data.address_postal_code}
            onChange={(e) => onChange({ address_postal_code: e.target.value })}
            placeholder="PLZ"
            maxLength={10}
            aria-label="Postleitzahl"
          />
          <div className="col-span-2">
            <Input
              value={data.address_city}
              onChange={(e) => onChange({ address_city: e.target.value })}
              placeholder="Stadt"
              aria-label="Stadt"
            />
          </div>
        </div>
        <Select
          value={data.address_country}
          onValueChange={(value) => onChange({ address_country: value })}
        >
          <SelectTrigger aria-label="Land auswaehlen">
            <SelectValue placeholder="Land" />
          </SelectTrigger>
          <SelectContent>
            {COUNTRIES.map((c) => (
              <SelectItem key={c.value} value={c.value}>
                {c.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </fieldset>

      {/* Kontakt */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label htmlFor="onb-email" className="text-sm font-medium">E-Mail</Label>
          <Input
            id="onb-email"
            type="email"
            value={data.email}
            onChange={(e) => onChange({ email: e.target.value })}
            placeholder="info@firma.de"
            className={cn(errors.email && 'border-destructive')}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="onb-phone" className="text-sm font-medium">Telefon</Label>
          <Input
            id="onb-phone"
            type="tel"
            value={data.phone}
            onChange={(e) => onChange({ phone: e.target.value })}
            placeholder="+49 123 456789"
          />
        </div>
      </div>

      <Alert>
        <Info className="h-4 w-4" aria-hidden="true" />
        <AlertDescription className="text-xs">
          Diese Daten koennen spaeter jederzeit unter Einstellungen geaendert werden.
        </AlertDescription>
      </Alert>
    </div>
  )
}

/** Validates company setup form data */
export function validateCompanySetup(data: CompanySetupFormData): Record<string, string> {
  const errors: Record<string, string> = {}

  if (!data.name.trim()) {
    errors.name = 'Firmenname ist erforderlich'
  }

  if (data.vat_id && !/^DE[0-9]{9}$/.test(data.vat_id.replace(/\s/g, ''))) {
    errors.vat_id = 'Ungueltiges Format (DE + 9 Ziffern)'
  }

  if (data.email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(data.email)) {
    errors.email = 'Ungueltige E-Mail-Adresse'
  }

  return errors
}
