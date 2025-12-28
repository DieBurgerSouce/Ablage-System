/**
 * TelefonProtokollDialog - Dialog zur Protokollierung von Telefonkontakten
 *
 * Formular für:
 * - Kontaktname
 * - Telefonnummer
 * - Ergebnis (Dropdown)
 * - Notizen
 * - Follow-up erforderlich? (Checkbox + Datum)
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
import { Checkbox } from '@/components/ui/checkbox';
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select';
import { useToast } from '@/components/ui/use-toast';
import {
    Phone,
    User,
    CalendarIcon,
    MessageSquare,
    CheckCircle2,
    XCircle,
    Voicemail,
    PhoneCall,
    AlertTriangle,
    Loader2,
} from 'lucide-react';
import { useLogPhoneCall } from '../hooks/use-banking-queries';
import type { PhoneCallOutcome } from '@/types/models/banking';

// ==================== Types ====================

interface TelefonProtokollDialogProps {
    dunningId: string;
    debtorName?: string;
    open: boolean;
    onOpenChange: (open: boolean) => void;
    onSuccess?: () => void;
}

interface FormState {
    contact_name: string;
    phone_number: string;
    outcome: PhoneCallOutcome | '';
    notes: string;
    follow_up_required: boolean;
    follow_up_date: string;
    follow_up_notes: string;
}

// ==================== Outcome Configuration ====================

const OUTCOME_CONFIG: Record<PhoneCallOutcome, {
    label: string;
    description: string;
    icon: React.ReactNode;
    color: string;
}> = {
    reached: {
        label: 'Erreicht',
        description: 'Ansprechpartner wurde erreicht',
        icon: <CheckCircle2 className="h-4 w-4" />,
        color: 'text-green-600',
    },
    not_reached: {
        label: 'Nicht erreicht',
        description: 'Niemand erreichbar',
        icon: <XCircle className="h-4 w-4" />,
        color: 'text-orange-600',
    },
    voicemail: {
        label: 'Mailbox',
        description: 'Nachricht auf Anrufbeantworter',
        icon: <Voicemail className="h-4 w-4" />,
        color: 'text-orange-600',
    },
    callback_requested: {
        label: 'Rückruf erbeten',
        description: 'Kunde bittet um Rückruf',
        icon: <PhoneCall className="h-4 w-4" />,
        color: 'text-blue-600',
    },
    payment_promised: {
        label: 'Zahlung zugesagt',
        description: 'Kunde hat Zahlung versprochen',
        icon: <CheckCircle2 className="h-4 w-4" />,
        color: 'text-green-600',
    },
    dispute_raised: {
        label: 'Reklamation',
        description: 'Kunde erhebt Einwände',
        icon: <AlertTriangle className="h-4 w-4" />,
        color: 'text-red-600',
    },
};

// ==================== Helper Functions ====================

function getDefaultFollowUpDate(): string {
    const date = new Date();
    date.setDate(date.getDate() + 3);
    return date.toISOString().split('T')[0];
}

// ==================== Main Component ====================

export function TelefonProtokollDialog({
    dunningId,
    debtorName,
    open,
    onOpenChange,
    onSuccess,
}: TelefonProtokollDialogProps) {
    const { toast } = useToast();
    const logPhoneCall = useLogPhoneCall();

    const [formState, setFormState] = useState<FormState>({
        contact_name: debtorName || '',
        phone_number: '',
        outcome: '',
        notes: '',
        follow_up_required: false,
        follow_up_date: '',
        follow_up_notes: '',
    });

    const [errors, setErrors] = useState<Partial<Record<keyof FormState, string>>>({});

    // Reset form when dialog opens with new debtor
    useEffect(() => {
        if (open) {
            setFormState({
                contact_name: debtorName || '',
                phone_number: '',
                outcome: '',
                notes: '',
                follow_up_required: false,
                follow_up_date: '',
                follow_up_notes: '',
            });
            setErrors({});
        }
    }, [open, debtorName]);

    // Auto-suggest follow-up for certain outcomes
    useEffect(() => {
        if (formState.outcome === 'callback_requested' || formState.outcome === 'payment_promised') {
            setFormState(prev => ({
                ...prev,
                follow_up_required: true,
                follow_up_date: prev.follow_up_date || getDefaultFollowUpDate(),
            }));
        }
    }, [formState.outcome]);

    const updateField = <K extends keyof FormState>(field: K, value: FormState[K]) => {
        setFormState(prev => ({ ...prev, [field]: value }));
        // Clear error when field is updated
        if (errors[field]) {
            setErrors(prev => ({ ...prev, [field]: undefined }));
        }
    };

    const validate = (): boolean => {
        const newErrors: Partial<Record<keyof FormState, string>> = {};

        if (!formState.contact_name.trim()) {
            newErrors.contact_name = 'Kontaktname ist erforderlich';
        }

        if (!formState.outcome) {
            newErrors.outcome = 'Bitte wählen Sie ein Ergebnis';
        }

        setErrors(newErrors);
        return Object.keys(newErrors).length === 0;
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();

        if (!validate()) {
            return;
        }

        try {
            await logPhoneCall.mutateAsync({
                dunningId,
                data: {
                    contact_name: formState.contact_name,
                    phone_number: formState.phone_number || undefined,
                    outcome: formState.outcome as PhoneCallOutcome,
                    notes: formState.notes || undefined,
                    follow_up_required: formState.follow_up_required,
                    follow_up_date: formState.follow_up_date || undefined,
                    follow_up_notes: formState.follow_up_notes || undefined,
                },
            });

            toast({
                title: 'Anruf protokolliert',
                description: `Telefonkontakt mit ${formState.contact_name} wurde gespeichert.`,
            });

            onOpenChange(false);
            onSuccess?.();
        } catch {
            toast({
                title: 'Fehler beim Speichern',
                description: 'Der Telefonkontakt konnte nicht gespeichert werden.',
                variant: 'destructive',
            });
        }
    };

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="sm:max-w-[500px]">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        <Phone className="h-5 w-5" />
                        Telefonkontakt protokollieren
                    </DialogTitle>
                    <DialogDescription>
                        Dokumentieren Sie den Telefonanruf zum Mahnvorgang.
                    </DialogDescription>
                </DialogHeader>

                <form onSubmit={handleSubmit} className="space-y-4">
                    {/* Contact Name */}
                    <div className="space-y-2">
                        <Label htmlFor="contact_name">
                            Kontaktname <span className="text-destructive">*</span>
                        </Label>
                        <div className="relative">
                            <User className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                            <Input
                                id="contact_name"
                                value={formState.contact_name}
                                onChange={(e) => updateField('contact_name', e.target.value)}
                                placeholder="Name der kontaktierten Person"
                                className="pl-10"
                            />
                        </div>
                        {errors.contact_name && (
                            <p className="text-sm text-destructive">{errors.contact_name}</p>
                        )}
                    </div>

                    {/* Phone Number */}
                    <div className="space-y-2">
                        <Label htmlFor="phone_number">Telefonnummer</Label>
                        <div className="relative">
                            <Phone className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                            <Input
                                id="phone_number"
                                value={formState.phone_number}
                                onChange={(e) => updateField('phone_number', e.target.value)}
                                placeholder="+49 ..."
                                className="pl-10"
                            />
                        </div>
                    </div>

                    {/* Outcome */}
                    <div className="space-y-2">
                        <Label>
                            Ergebnis <span className="text-destructive">*</span>
                        </Label>
                        <Select
                            value={formState.outcome}
                            onValueChange={(value) => updateField('outcome', value as PhoneCallOutcome)}
                        >
                            <SelectTrigger>
                                <SelectValue placeholder="Wählen Sie das Ergebnis..." />
                            </SelectTrigger>
                            <SelectContent>
                                {Object.entries(OUTCOME_CONFIG).map(([key, config]) => (
                                    <SelectItem key={key} value={key}>
                                        <div className="flex items-center gap-2">
                                            <span className={config.color}>
                                                {config.icon}
                                            </span>
                                            <div>
                                                <div className="font-medium">{config.label}</div>
                                                <div className="text-xs text-muted-foreground">
                                                    {config.description}
                                                </div>
                                            </div>
                                        </div>
                                    </SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                        {errors.outcome && (
                            <p className="text-sm text-destructive">{errors.outcome}</p>
                        )}
                    </div>

                    {/* Notes */}
                    <div className="space-y-2">
                        <Label htmlFor="notes">Notizen</Label>
                        <div className="relative">
                            <MessageSquare className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
                            <Textarea
                                id="notes"
                                value={formState.notes}
                                onChange={(e) => updateField('notes', e.target.value)}
                                placeholder="Gesprächsinhalt, Vereinbarungen, Anmerkungen..."
                                className="pl-10 min-h-[100px]"
                            />
                        </div>
                        <p className="text-xs text-muted-foreground">
                            Beschreiben Sie den Inhalt des Gesprächs
                        </p>
                    </div>

                    {/* Follow-up Required */}
                    <div className="flex flex-row items-start space-x-3 space-y-0 rounded-md border p-4">
                        <Checkbox
                            id="follow_up_required"
                            checked={formState.follow_up_required}
                            onCheckedChange={(checked) => updateField('follow_up_required', !!checked)}
                        />
                        <div className="space-y-1 leading-none">
                            <Label htmlFor="follow_up_required">
                                Follow-up erforderlich
                            </Label>
                            <p className="text-xs text-muted-foreground">
                                Wiedervorlage für erneuten Kontaktversuch planen
                            </p>
                        </div>
                    </div>

                    {/* Follow-up Date (conditional) */}
                    {formState.follow_up_required && (
                        <div className="space-y-4 rounded-md border p-4 bg-muted/30">
                            <div className="space-y-2">
                                <Label htmlFor="follow_up_date">Wiedervorlage am</Label>
                                <div className="relative">
                                    <CalendarIcon className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                                    <Input
                                        id="follow_up_date"
                                        type="date"
                                        value={formState.follow_up_date}
                                        onChange={(e) => updateField('follow_up_date', e.target.value)}
                                        min={new Date().toISOString().split('T')[0]}
                                        className="pl-10"
                                    />
                                </div>
                            </div>

                            <div className="space-y-2">
                                <Label htmlFor="follow_up_notes">Follow-up Notiz</Label>
                                <Input
                                    id="follow_up_notes"
                                    value={formState.follow_up_notes}
                                    onChange={(e) => updateField('follow_up_notes', e.target.value)}
                                    placeholder="z.B. Zahlungseingang prüfen, erneut anrufen..."
                                />
                            </div>
                        </div>
                    )}

                    <DialogFooter className="pt-4">
                        <Button
                            type="button"
                            variant="outline"
                            onClick={() => onOpenChange(false)}
                        >
                            Abbrechen
                        </Button>
                        <Button
                            type="submit"
                            disabled={logPhoneCall.isPending}
                        >
                            {logPhoneCall.isPending ? (
                                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                            ) : (
                                <CheckCircle2 className="h-4 w-4 mr-2" />
                            )}
                            Speichern
                        </Button>
                    </DialogFooter>
                </form>
            </DialogContent>
        </Dialog>
    );
}
