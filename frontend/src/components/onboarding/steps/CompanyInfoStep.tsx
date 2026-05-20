/**
 * Firmendetails-Schritt im Setup-Wizard
 *
 * Erfasst Grunddaten der Firma:
 * - Firmenname (Pflicht)
 * - Steuernummer, USt-ID
 * - Adresse
 * - Kontaktdaten
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
import type { CompanySetupData } from '../CompanySetupWizard'

interface CompanyInfoStepProps {
    data: CompanySetupData
    onChange: (updates: Partial<CompanySetupData>) => void
    errors: Record<string, string>
}

const COUNTRIES = [
    { value: 'DE', label: 'Deutschland' },
    { value: 'AT', label: 'Österreich' },
    { value: 'CH', label: 'Schweiz' },
]

export function CompanyInfoStep({ data, onChange, errors }: CompanyInfoStepProps) {
    return (
        <div className="space-y-6">
            {/* Firmenname */}
            <div className="space-y-2">
                <Label htmlFor="company-name" className="text-sm font-medium">
                    Firmenname <span className="text-destructive">*</span>
                </Label>
                <Input
                    id="company-name"
                    value={data.name}
                    onChange={(e) => onChange({ name: e.target.value })}
                    placeholder="Muster GmbH"
                    className={cn(errors.name && 'border-destructive')}
                    aria-describedby={errors.name ? 'company-name-error' : undefined}
                    aria-invalid={!!errors.name}
                />
                {errors.name && (
                    <p id="company-name-error" className="text-xs text-destructive">
                        {errors.name}
                    </p>
                )}
            </div>

            {/* Steuernummern */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="space-y-2">
                    <Label htmlFor="tax-number" className="text-sm font-medium">
                        Steuernummer
                    </Label>
                    <Input
                        id="tax-number"
                        value={data.tax_number}
                        onChange={(e) => onChange({ tax_number: e.target.value })}
                        placeholder="123/456/78901"
                        aria-describedby={errors.tax_number ? 'tax-number-error' : undefined}
                    />
                    {errors.tax_number && (
                        <p id="tax-number-error" className="text-xs text-destructive">
                            {errors.tax_number}
                        </p>
                    )}
                </div>

                <div className="space-y-2">
                    <Label htmlFor="vat-id" className="text-sm font-medium">
                        USt-IdNr.
                    </Label>
                    <Input
                        id="vat-id"
                        value={data.vat_id}
                        onChange={(e) => onChange({ vat_id: e.target.value.toUpperCase() })}
                        placeholder="DE123456789"
                        className={cn(errors.vat_id && 'border-destructive')}
                        aria-describedby={errors.vat_id ? 'vat-id-error' : undefined}
                        aria-invalid={!!errors.vat_id}
                    />
                    {errors.vat_id && (
                        <p id="vat-id-error" className="text-xs text-destructive">
                            {errors.vat_id}
                        </p>
                    )}
                </div>
            </div>

            {/* Adresse */}
            <fieldset className="space-y-4">
                <legend className="text-sm font-medium text-muted-foreground">
                    Adresse
                </legend>

                <div className="space-y-2">
                    <Label htmlFor="address-street" className="text-sm font-medium">
                        Straße und Hausnummer
                    </Label>
                    <Input
                        id="address-street"
                        value={data.address_street}
                        onChange={(e) => onChange({ address_street: e.target.value })}
                        placeholder="Musterstraße 123"
                    />
                </div>

                <div className="grid grid-cols-3 gap-4">
                    <div className="space-y-2">
                        <Label htmlFor="address-postal" className="text-sm font-medium">
                            PLZ
                        </Label>
                        <Input
                            id="address-postal"
                            value={data.address_postal_code}
                            onChange={(e) => onChange({ address_postal_code: e.target.value })}
                            placeholder="12345"
                            maxLength={10}
                        />
                    </div>

                    <div className="space-y-2 col-span-2">
                        <Label htmlFor="address-city" className="text-sm font-medium">
                            Stadt
                        </Label>
                        <Input
                            id="address-city"
                            value={data.address_city}
                            onChange={(e) => onChange({ address_city: e.target.value })}
                            placeholder="Musterstadt"
                        />
                    </div>
                </div>

                <div className="space-y-2">
                    <Label htmlFor="address-country" className="text-sm font-medium">
                        Land
                    </Label>
                    <Select
                        value={data.address_country}
                        onValueChange={(value) => onChange({ address_country: value })}
                    >
                        <SelectTrigger id="address-country">
                            <SelectValue placeholder="Land auswählen" />
                        </SelectTrigger>
                        <SelectContent>
                            {COUNTRIES.map((country) => (
                                <SelectItem key={country.value} value={country.value}>
                                    {country.label}
                                </SelectItem>
                            ))}
                        </SelectContent>
                    </Select>
                </div>
            </fieldset>

            {/* Kontaktdaten */}
            <fieldset className="space-y-4">
                <legend className="text-sm font-medium text-muted-foreground">
                    Kontaktdaten
                </legend>

                <div className="space-y-2">
                    <Label htmlFor="company-email" className="text-sm font-medium">
                        E-Mail
                    </Label>
                    <Input
                        id="company-email"
                        type="email"
                        value={data.email}
                        onChange={(e) => onChange({ email: e.target.value })}
                        placeholder="info@firma.de"
                        className={cn(errors.email && 'border-destructive')}
                        aria-describedby={errors.email ? 'email-error' : undefined}
                        aria-invalid={!!errors.email}
                    />
                    {errors.email && (
                        <p id="email-error" className="text-xs text-destructive">
                            {errors.email}
                        </p>
                    )}
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div className="space-y-2">
                        <Label htmlFor="company-phone" className="text-sm font-medium">
                            Telefon
                        </Label>
                        <Input
                            id="company-phone"
                            type="tel"
                            value={data.phone}
                            onChange={(e) => onChange({ phone: e.target.value })}
                            placeholder="+49 123 456789"
                        />
                    </div>

                    <div className="space-y-2">
                        <Label htmlFor="company-website" className="text-sm font-medium">
                            Website
                        </Label>
                        <Input
                            id="company-website"
                            type="url"
                            value={data.website}
                            onChange={(e) => onChange({ website: e.target.value })}
                            placeholder="https://www.firma.de"
                        />
                    </div>
                </div>
            </fieldset>
        </div>
    )
}
