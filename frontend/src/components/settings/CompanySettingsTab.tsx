/**
 * Firmendaten Tab (nur Admin).
 *
 * Enthält alle Firmendetails für die Rechnungserkennung:
 * - Firmenname und alternative Namen
 * - Adresse
 * - Steueridentifikation (USt-IdNr., Steuernummer)
 * - Bankverbindung (IBAN, BIC)
 * - Kontaktdaten
 * - Handelsregister
 */

import { useState, useEffect } from 'react';
import { Loader2, Plus, X, Building2, AlertCircle } from 'lucide-react';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import {
    settingsService,
    type CompanySettingsUpdate,
} from '@/lib/api/services/settings';
import { useToast } from '@/components/ui/use-toast';

interface FormData {
    company_name: string;
    alternative_names: string[];
    street: string;
    postal_code: string;
    city: string;
    country: string;
    vat_id: string;
    tax_number: string;
    iban: string;
    bic: string;
    email: string;
    phone: string;
    website: string;
    commercial_register: string;
    court: string;
}

const emptyForm: FormData = {
    company_name: '',
    alternative_names: [],
    street: '',
    postal_code: '',
    city: '',
    country: 'Deutschland',
    vat_id: '',
    tax_number: '',
    iban: '',
    bic: '',
    email: '',
    phone: '',
    website: '',
    commercial_register: '',
    court: '',
};

export function CompanySettingsTab() {
    const { toast } = useToast();
    const [formData, setFormData] = useState<FormData>(emptyForm);
    const [newAlternativeName, setNewAlternativeName] = useState('');
    const [isLoading, setIsLoading] = useState(true);
    const [isSaving, setIsSaving] = useState(false);
    const [hasChanges, setHasChanges] = useState(false);
    const [isConfigured, setIsConfigured] = useState(false);
    const [errors, setErrors] = useState<Record<string, string>>({});

    useEffect(() => {
        const loadSettings = async () => {
            try {
                const data = await settingsService.getCompanySettings();
                if (settingsService.isCompanyConfigured(data)) {
                    setFormData({
                        company_name: data.company_name,
                        alternative_names: data.alternative_names || [],
                        street: data.street || '',
                        postal_code: data.postal_code || '',
                        city: data.city || '',
                        country: data.country || 'Deutschland',
                        vat_id: data.vat_id || '',
                        tax_number: data.tax_number || '',
                        iban: data.iban || '',
                        bic: data.bic || '',
                        email: data.email || '',
                        phone: data.phone || '',
                        website: data.website || '',
                        commercial_register: data.commercial_register || '',
                        court: data.court || '',
                    });
                    setIsConfigured(true);
                }
            } catch (error) {
                console.error('Fehler beim Laden der Firmendaten:', error);
            } finally {
                setIsLoading(false);
            }
        };
        loadSettings();
    }, []);

    const validateForm = (): boolean => {
        const newErrors: Record<string, string> = {};

        if (!formData.company_name.trim()) {
            newErrors.company_name = 'Firmenname ist erforderlich';
        }

        // Validate VAT ID (German: DE + 9 digits)
        if (formData.vat_id && !formData.vat_id.match(/^DE\d{9}$/)) {
            newErrors.vat_id = 'USt-IdNr. muss DE + 9 Ziffern sein (z.B. DE123456789)';
        }

        // Validate IBAN (simplified)
        if (formData.iban && formData.iban.length < 15) {
            newErrors.iban = 'IBAN muss mindestens 15 Zeichen haben';
        }

        // Validate BIC
        if (formData.bic && ![8, 11].includes(formData.bic.length)) {
            newErrors.bic = 'BIC muss 8 oder 11 Zeichen haben';
        }

        setErrors(newErrors);
        return Object.keys(newErrors).length === 0;
    };

    const handleInputChange = (field: keyof FormData, value: string) => {
        setFormData(prev => ({ ...prev, [field]: value }));
        setHasChanges(true);
        // Clear error for this field
        if (errors[field]) {
            setErrors(prev => {
                const newErrors = { ...prev };
                delete newErrors[field];
                return newErrors;
            });
        }
    };

    const handleAddAlternativeName = () => {
        if (newAlternativeName.trim() && !formData.alternative_names.includes(newAlternativeName.trim())) {
            setFormData(prev => ({
                ...prev,
                alternative_names: [...prev.alternative_names, newAlternativeName.trim()]
            }));
            setNewAlternativeName('');
            setHasChanges(true);
        }
    };

    const handleRemoveAlternativeName = (name: string) => {
        setFormData(prev => ({
            ...prev,
            alternative_names: prev.alternative_names.filter(n => n !== name)
        }));
        setHasChanges(true);
    };

    const handleSave = async () => {
        if (!validateForm()) {
            toast({
                title: 'Validierungsfehler',
                description: 'Bitte korrigieren Sie die markierten Felder.',
                variant: 'destructive',
            });
            return;
        }

        setIsSaving(true);
        try {
            const updateData: CompanySettingsUpdate = {
                company_name: formData.company_name,
                alternative_names: formData.alternative_names,
                street: formData.street || null,
                postal_code: formData.postal_code || null,
                city: formData.city || null,
                country: formData.country || 'Deutschland',
                vat_id: formData.vat_id ? formData.vat_id.toUpperCase().replace(/\s/g, '') : null,
                tax_number: formData.tax_number || null,
                iban: formData.iban ? formData.iban.toUpperCase().replace(/\s/g, '') : null,
                bic: formData.bic ? formData.bic.toUpperCase().replace(/\s/g, '') : null,
                email: formData.email || null,
                phone: formData.phone || null,
                website: formData.website || null,
                commercial_register: formData.commercial_register || null,
                court: formData.court || null,
            };

            await settingsService.updateCompanySettings(updateData);
            setHasChanges(false);
            setIsConfigured(true);
            toast({
                title: 'Gespeichert',
                description: 'Firmendaten wurden aktualisiert.',
            });
        } catch (error: unknown) {
            console.error('Fehler beim Speichern:', error);
            const errorMessage = error instanceof Error ? error.message : 'Unbekannter Fehler';
            toast({
                title: 'Fehler',
                description: `Firmendaten konnten nicht gespeichert werden: ${errorMessage}`,
                variant: 'destructive',
            });
        } finally {
            setIsSaving(false);
        }
    };

    if (isLoading) {
        return (
            <div className="flex items-center justify-center py-8">
                <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
            </div>
        );
    }

    return (
        <div className="space-y-6">
            {!isConfigured && (
                <Alert>
                    <Building2 className="h-4 w-4" />
                    <AlertTitle>Firmendaten nicht konfiguriert</AlertTitle>
                    <AlertDescription>
                        Konfigurieren Sie Ihre Firmendaten, um automatisch zwischen
                        Eingangs- und Ausgangsrechnungen unterscheiden zu können.
                    </AlertDescription>
                </Alert>
            )}

            {/* Firmenname */}
            <div className="space-y-2">
                <Label htmlFor="company-name" className="required">
                    Firmenname *
                </Label>
                <Input
                    id="company-name"
                    value={formData.company_name}
                    onChange={(e) => handleInputChange('company_name', e.target.value)}
                    placeholder="Ihre Firma GmbH"
                    className={errors.company_name ? 'border-destructive' : ''}
                />
                {errors.company_name && (
                    <p className="text-xs text-destructive">{errors.company_name}</p>
                )}
            </div>

            {/* Alternative Namen */}
            <div className="space-y-2">
                <Label>Alternative Firmennamen</Label>
                <p className="text-xs text-muted-foreground">
                    Weitere Schreibweisen für die automatische Erkennung in Dokumenten.
                </p>
                <div className="flex gap-2">
                    <Input
                        value={newAlternativeName}
                        onChange={(e) => setNewAlternativeName(e.target.value)}
                        placeholder="Alternative Schreibweise"
                        onKeyDown={(e) => {
                            if (e.key === 'Enter') {
                                e.preventDefault();
                                handleAddAlternativeName();
                            }
                        }}
                    />
                    <Button
                        type="button"
                        variant="outline"
                        size="icon"
                        onClick={handleAddAlternativeName}
                    >
                        <Plus className="w-4 h-4" />
                    </Button>
                </div>
                {formData.alternative_names.length > 0 && (
                    <div className="flex flex-wrap gap-2 mt-2">
                        {formData.alternative_names.map((name) => (
                            <Badge key={name} variant="secondary" className="gap-1">
                                {name}
                                <button
                                    type="button"
                                    onClick={() => handleRemoveAlternativeName(name)}
                                    className="hover:text-destructive"
                                >
                                    <X className="w-3 h-3" />
                                </button>
                            </Badge>
                        ))}
                    </div>
                )}
            </div>

            {/* Adresse */}
            <div className="space-y-4">
                <h3 className="text-sm font-medium">Adresse</h3>
                <div className="grid gap-4 sm:grid-cols-2">
                    <div className="space-y-2 sm:col-span-2">
                        <Label htmlFor="street">Straße</Label>
                        <Input
                            id="street"
                            value={formData.street}
                            onChange={(e) => handleInputChange('street', e.target.value)}
                            placeholder="Musterstraße 123"
                        />
                    </div>
                    <div className="space-y-2">
                        <Label htmlFor="postal-code">PLZ</Label>
                        <Input
                            id="postal-code"
                            value={formData.postal_code}
                            onChange={(e) => handleInputChange('postal_code', e.target.value)}
                            placeholder="12345"
                        />
                    </div>
                    <div className="space-y-2">
                        <Label htmlFor="city">Stadt</Label>
                        <Input
                            id="city"
                            value={formData.city}
                            onChange={(e) => handleInputChange('city', e.target.value)}
                            placeholder="Berlin"
                        />
                    </div>
                    <div className="space-y-2 sm:col-span-2">
                        <Label htmlFor="country">Land</Label>
                        <Input
                            id="country"
                            value={formData.country}
                            onChange={(e) => handleInputChange('country', e.target.value)}
                            placeholder="Deutschland"
                        />
                    </div>
                </div>
            </div>

            {/* Steueridentifikation */}
            <div className="space-y-4">
                <h3 className="text-sm font-medium">Steueridentifikation</h3>
                <div className="grid gap-4 sm:grid-cols-2">
                    <div className="space-y-2">
                        <Label htmlFor="vat-id">USt-IdNr.</Label>
                        <Input
                            id="vat-id"
                            value={formData.vat_id}
                            onChange={(e) => handleInputChange('vat_id', e.target.value.toUpperCase())}
                            placeholder="DE123456789"
                            className={errors.vat_id ? 'border-destructive' : ''}
                        />
                        {errors.vat_id && (
                            <p className="text-xs text-destructive">{errors.vat_id}</p>
                        )}
                    </div>
                    <div className="space-y-2">
                        <Label htmlFor="tax-number">Steuernummer</Label>
                        <Input
                            id="tax-number"
                            value={formData.tax_number}
                            onChange={(e) => handleInputChange('tax_number', e.target.value)}
                            placeholder="12/345/67890"
                        />
                    </div>
                </div>
            </div>

            {/* Bankverbindung */}
            <div className="space-y-4">
                <h3 className="text-sm font-medium">Bankverbindung</h3>
                <div className="grid gap-4 sm:grid-cols-2">
                    <div className="space-y-2">
                        <Label htmlFor="iban">IBAN</Label>
                        <Input
                            id="iban"
                            value={formData.iban}
                            onChange={(e) => handleInputChange('iban', e.target.value.toUpperCase())}
                            placeholder="DE89 3704 0044 0532 0130 00"
                            className={errors.iban ? 'border-destructive' : ''}
                        />
                        {errors.iban && (
                            <p className="text-xs text-destructive">{errors.iban}</p>
                        )}
                    </div>
                    <div className="space-y-2">
                        <Label htmlFor="bic">BIC</Label>
                        <Input
                            id="bic"
                            value={formData.bic}
                            onChange={(e) => handleInputChange('bic', e.target.value.toUpperCase())}
                            placeholder="COBADEFFXXX"
                            className={errors.bic ? 'border-destructive' : ''}
                        />
                        {errors.bic && (
                            <p className="text-xs text-destructive">{errors.bic}</p>
                        )}
                    </div>
                </div>
            </div>

            {/* Kontaktdaten */}
            <div className="space-y-4">
                <h3 className="text-sm font-medium">Kontaktdaten</h3>
                <div className="grid gap-4 sm:grid-cols-2">
                    <div className="space-y-2">
                        <Label htmlFor="email">E-Mail</Label>
                        <Input
                            id="email"
                            type="email"
                            value={formData.email}
                            onChange={(e) => handleInputChange('email', e.target.value)}
                            placeholder="buchhaltung@firma.de"
                        />
                    </div>
                    <div className="space-y-2">
                        <Label htmlFor="phone">Telefon</Label>
                        <Input
                            id="phone"
                            type="tel"
                            value={formData.phone}
                            onChange={(e) => handleInputChange('phone', e.target.value)}
                            placeholder="+49 30 12345678"
                        />
                    </div>
                    <div className="space-y-2 sm:col-span-2">
                        <Label htmlFor="website">Webseite</Label>
                        <Input
                            id="website"
                            type="url"
                            value={formData.website}
                            onChange={(e) => handleInputChange('website', e.target.value)}
                            placeholder="https://www.firma.de"
                        />
                    </div>
                </div>
            </div>

            {/* Handelsregister */}
            <div className="space-y-4">
                <h3 className="text-sm font-medium">Handelsregister</h3>
                <div className="grid gap-4 sm:grid-cols-2">
                    <div className="space-y-2">
                        <Label htmlFor="commercial-register">Handelsregister-Nr.</Label>
                        <Input
                            id="commercial-register"
                            value={formData.commercial_register}
                            onChange={(e) => handleInputChange('commercial_register', e.target.value)}
                            placeholder="HRB 12345"
                        />
                    </div>
                    <div className="space-y-2">
                        <Label htmlFor="court">Registergericht</Label>
                        <Input
                            id="court"
                            value={formData.court}
                            onChange={(e) => handleInputChange('court', e.target.value)}
                            placeholder="Amtsgericht Berlin"
                        />
                    </div>
                </div>
            </div>

            {/* Info */}
            <Alert variant="default">
                <AlertCircle className="h-4 w-4" />
                <AlertDescription>
                    Diese Daten werden verwendet, um bei hochgeladenen Rechnungen automatisch
                    zu erkennen, ob es sich um eine Eingangsrechnung (an Sie) oder
                    Ausgangsrechnung (von Ihnen) handelt.
                </AlertDescription>
            </Alert>

            {/* Save Button */}
            <div className="flex justify-end pt-4 border-t">
                <Button
                    onClick={handleSave}
                    disabled={!hasChanges || isSaving}
                >
                    {isSaving && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
                    Speichern
                </Button>
            </div>
        </div>
    );
}
