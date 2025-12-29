/**
 * CustomerDunningOverrideForm - Kundenspezifische Mahneinstellungen
 *
 * Formular für individuelle Debitor-Konfiguration:
 * - Zahlungsziel (Tage)
 * - Maximale Mahnstufe
 * - Bevorzugte Kontaktmethode
 * - Ausschluss von automatischer Mahnung
 */

import { useState, useEffect } from 'react';
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
import { Textarea } from '@/components/ui/textarea';
import { Switch } from '@/components/ui/switch';
import { Skeleton } from '@/components/ui/skeleton';
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select';
import { useToast } from '@/components/ui/use-toast';
import {
    Building2,
    Mail,
    Phone,
    FileText,
    AlertTriangle,
    Loader2,
    Save,
    Info,
} from 'lucide-react';
import {
    useCustomerDunningSettings,
    useSetCustomerDunningSettings,
} from '../hooks/use-banking-queries';
import type { ContactMethod, CustomerDunningOverrideUpdate } from '@/types/models/banking';

// ==================== Types ====================

interface CustomerDunningOverrideFormProps {
    businessEntityId: string;
    businessEntityName?: string;
    open: boolean;
    onOpenChange: (open: boolean) => void;
    onSuccess?: () => void;
}

interface FormState {
    custom_payment_terms_days: number | '';
    max_mahn_stufe: number | '';
    preferred_contact_method: ContactMethod;
    exclude_from_auto_dunning: boolean;
    exclusion_reason: string;
    notes: string;
}

// ==================== Constants ====================

const CONTACT_METHODS: { value: ContactMethod; label: string; icon: React.ReactNode }[] = [
    { value: 'email', label: 'E-Mail', icon: <Mail className="h-4 w-4" /> },
    { value: 'phone', label: 'Telefon', icon: <Phone className="h-4 w-4" /> },
    { value: 'letter', label: 'Brief', icon: <FileText className="h-4 w-4" /> },
];

const MAX_STAGES = [
    { value: '0', label: 'Keine Mahnung (nur Erinnerung)' },
    { value: '1', label: 'Stufe 1 - Zahlungserinnerung' },
    { value: '2', label: 'Stufe 2 - 1. Mahnung' },
    { value: '3', label: 'Stufe 3 - 2. Mahnung' },
    { value: '4', label: 'Stufe 4 - Letzte Mahnung' },
    { value: '5', label: 'Stufe 5 - Inkasso (Standard)' },
];

// ==================== Main Component ====================

export function CustomerDunningOverrideForm({
    businessEntityId,
    businessEntityName,
    open,
    onOpenChange,
    onSuccess,
}: CustomerDunningOverrideFormProps) {
    const { toast } = useToast();

    // Queries
    const {
        data: existingSettings,
        isLoading,
        isError,
    } = useCustomerDunningSettings(businessEntityId, open);

    const setSettings = useSetCustomerDunningSettings();

    // Form state
    const [formState, setFormState] = useState<FormState>({
        custom_payment_terms_days: '',
        max_mahn_stufe: '',
        preferred_contact_method: 'email',
        exclude_from_auto_dunning: false,
        exclusion_reason: '',
        notes: '',
    });

    // Load existing settings when available
    useEffect(() => {
        if (existingSettings && open) {
            setFormState({
                custom_payment_terms_days: existingSettings.custom_payment_terms_days ?? '',
                max_mahn_stufe: existingSettings.max_mahn_stufe ?? '',
                preferred_contact_method: (existingSettings.preferred_contact_method as ContactMethod) ?? 'email',
                exclude_from_auto_dunning: existingSettings.exclude_from_auto_dunning ?? false,
                exclusion_reason: existingSettings.exclusion_reason ?? '',
                notes: existingSettings.notes ?? '',
            });
        }
    }, [existingSettings, open]);

    // Reset on close
    useEffect(() => {
        if (!open) {
            setFormState({
                custom_payment_terms_days: '',
                max_mahn_stufe: '',
                preferred_contact_method: 'email',
                exclude_from_auto_dunning: false,
                exclusion_reason: '',
                notes: '',
            });
        }
    }, [open]);

    // Handlers
    const updateField = <K extends keyof FormState>(field: K, value: FormState[K]) => {
        setFormState((prev) => ({ ...prev, [field]: value }));
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();

        const data: CustomerDunningOverrideUpdate = {
            preferred_contact_method: formState.preferred_contact_method,
            exclude_from_auto_dunning: formState.exclude_from_auto_dunning,
        };

        // Only include optional fields if they have values
        if (formState.custom_payment_terms_days !== '') {
            data.custom_payment_terms_days = Number(formState.custom_payment_terms_days);
        }
        if (formState.max_mahn_stufe !== '') {
            data.max_mahn_stufe = Number(formState.max_mahn_stufe);
        }
        if (formState.exclusion_reason.trim()) {
            data.exclusion_reason = formState.exclusion_reason.trim();
        }
        if (formState.notes.trim()) {
            data.notes = formState.notes.trim();
        }

        try {
            await setSettings.mutateAsync({
                businessEntityId,
                data,
            });

            toast({
                title: 'Einstellungen gespeichert',
                description: `Mahneinstellungen für ${businessEntityName || 'Kunde'} wurden aktualisiert.`,
            });

            onOpenChange(false);
            onSuccess?.();
        } catch {
            toast({
                title: 'Fehler beim Speichern',
                description: 'Die Mahneinstellungen konnten nicht gespeichert werden.',
                variant: 'destructive',
            });
        }
    };

    // Loading state
    if (isLoading) {
        return (
            <Dialog open={open} onOpenChange={onOpenChange}>
                <DialogContent className="sm:max-w-[500px]">
                    <DialogHeader>
                        <DialogTitle>Mahneinstellungen laden...</DialogTitle>
                    </DialogHeader>
                    <div className="space-y-4 py-4">
                        <Skeleton className="h-10 w-full" />
                        <Skeleton className="h-10 w-full" />
                        <Skeleton className="h-10 w-full" />
                        <Skeleton className="h-20 w-full" />
                    </div>
                </DialogContent>
            </Dialog>
        );
    }

    // Error state
    if (isError) {
        return (
            <Dialog open={open} onOpenChange={onOpenChange}>
                <DialogContent className="sm:max-w-[500px]">
                    <DialogHeader>
                        <DialogTitle className="flex items-center gap-2 text-destructive">
                            <AlertTriangle className="h-5 w-5" />
                            Fehler
                        </DialogTitle>
                        <DialogDescription>
                            Die Mahneinstellungen konnten nicht geladen werden.
                        </DialogDescription>
                    </DialogHeader>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => onOpenChange(false)}>
                            Schließen
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        );
    }

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="sm:max-w-[550px]">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        <Building2 className="h-5 w-5" />
                        Kundenspezifische Mahneinstellungen
                    </DialogTitle>
                    <DialogDescription>
                        Individuelle Mahnkonfiguration für{' '}
                        <span className="font-medium">{businessEntityName || 'Kunde'}</span>
                    </DialogDescription>
                </DialogHeader>

                <form onSubmit={handleSubmit} className="space-y-4 py-4">
                    {/* Payment Terms */}
                    <div className="space-y-2">
                        <Label htmlFor="payment_terms">Individuelles Zahlungsziel (Tage)</Label>
                        <Input
                            id="payment_terms"
                            type="number"
                            min={0}
                            max={365}
                            placeholder="Standard verwenden"
                            value={formState.custom_payment_terms_days}
                            onChange={(e) =>
                                updateField(
                                    'custom_payment_terms_days',
                                    e.target.value === '' ? '' : Number(e.target.value)
                                )
                            }
                        />
                        <p className="text-xs text-muted-foreground">
                            Leer lassen für Standard-Zahlungsziel (30 Tage)
                        </p>
                    </div>

                    {/* Max Dunning Stage */}
                    <div className="space-y-2">
                        <Label>Maximale Mahnstufe</Label>
                        <Select
                            value={formState.max_mahn_stufe === '' ? 'default' : String(formState.max_mahn_stufe)}
                            onValueChange={(value) =>
                                updateField(
                                    'max_mahn_stufe',
                                    value === 'default' ? '' : Number(value)
                                )
                            }
                        >
                            <SelectTrigger>
                                <SelectValue placeholder="Standard (alle Stufen)" />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value="default">
                                    <span className="text-muted-foreground">Standard (alle Stufen)</span>
                                </SelectItem>
                                {MAX_STAGES.map((stage) => (
                                    <SelectItem key={stage.value} value={stage.value}>
                                        {stage.label}
                                    </SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                        <p className="text-xs text-muted-foreground">
                            Begrenzt, wie weit die automatische Eskalation geht
                        </p>
                    </div>

                    {/* Preferred Contact Method */}
                    <div className="space-y-2">
                        <Label>Bevorzugte Kontaktmethode</Label>
                        <Select
                            value={formState.preferred_contact_method}
                            onValueChange={(value) =>
                                updateField('preferred_contact_method', value as ContactMethod)
                            }
                        >
                            <SelectTrigger>
                                <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                                {CONTACT_METHODS.map((method) => (
                                    <SelectItem key={method.value} value={method.value}>
                                        <div className="flex items-center gap-2">
                                            {method.icon}
                                            {method.label}
                                        </div>
                                    </SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                    </div>

                    {/* Exclude from Auto-Dunning */}
                    <div className="flex flex-row items-center justify-between rounded-lg border p-4">
                        <div className="space-y-0.5">
                            <Label htmlFor="exclude_auto" className="text-base">
                                Von automatischer Mahnung ausschließen
                            </Label>
                            <p className="text-xs text-muted-foreground">
                                Keine automatischen Mahnungen für diesen Kunden
                            </p>
                        </div>
                        <Switch
                            id="exclude_auto"
                            checked={formState.exclude_from_auto_dunning}
                            onCheckedChange={(checked) =>
                                updateField('exclude_from_auto_dunning', checked)
                            }
                        />
                    </div>

                    {/* Exclusion Reason (conditional) */}
                    {formState.exclude_from_auto_dunning && (
                        <div className="space-y-2">
                            <Label htmlFor="exclusion_reason">Grund für Ausschluss</Label>
                            <Input
                                id="exclusion_reason"
                                value={formState.exclusion_reason}
                                onChange={(e) => updateField('exclusion_reason', e.target.value)}
                                placeholder="z.B. Dauerhafte Zahlungsvereinbarung, VIP-Kunde..."
                            />
                        </div>
                    )}

                    {/* Notes */}
                    <div className="space-y-2">
                        <Label htmlFor="notes">Interne Notizen</Label>
                        <Textarea
                            id="notes"
                            value={formState.notes}
                            onChange={(e) => updateField('notes', e.target.value)}
                            placeholder="Optionale Hinweise zum Mahnverhalten..."
                            rows={3}
                        />
                    </div>

                    {/* Info Box */}
                    <div className="rounded-lg border border-blue-200 bg-blue-50/50 p-3">
                        <div className="flex items-start gap-2">
                            <Info className="h-4 w-4 text-blue-600 mt-0.5" />
                            <div className="text-xs text-blue-800">
                                <p className="font-medium">Hinweis</p>
                                <p>
                                    Diese Einstellungen überschreiben die Standard-Mahnkonfiguration
                                    nur für diesen spezifischen Geschäftspartner.
                                </p>
                            </div>
                        </div>
                    </div>

                    <DialogFooter className="pt-4">
                        <Button
                            type="button"
                            variant="outline"
                            onClick={() => onOpenChange(false)}
                        >
                            Abbrechen
                        </Button>
                        <Button type="submit" disabled={setSettings.isPending}>
                            {setSettings.isPending ? (
                                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                            ) : (
                                <Save className="h-4 w-4 mr-2" />
                            )}
                            Speichern
                        </Button>
                    </DialogFooter>
                </form>
            </DialogContent>
        </Dialog>
    );
}
