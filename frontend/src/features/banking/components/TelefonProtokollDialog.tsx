/**
 * TelefonProtokollDialog - Dialog zur Protokollierung von Telefonkontakten
 *
 * Formular fuer:
 * - Kontaktname
 * - Telefonnummer
 * - Ergebnis (Dropdown)
 * - Notizen
 * - Follow-up erforderlich? (Checkbox + Datum)
 */

import { useState, useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
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
import { Calendar } from '@/components/ui/calendar';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import {
    Form,
    FormControl,
    FormDescription,
    FormField,
    FormItem,
    FormLabel,
    FormMessage,
} from '@/components/ui/form';
import { toast } from 'sonner';
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
import { cn } from '@/lib/utils';

// ==================== Types ====================

interface TelefonProtokollDialogProps {
    dunningId: string;
    debtorName?: string;
    open: boolean;
    onOpenChange: (open: boolean) => void;
    onSuccess?: () => void;
}

// ==================== Schema ====================

const phoneCallSchema = z.object({
    contact_name: z.string().min(1, 'Kontaktname ist erforderlich'),
    phone_number: z.string().optional(),
    outcome: z.enum([
        'reached',
        'not_reached',
        'voicemail',
        'callback_requested',
        'payment_promised',
        'dispute_raised',
    ] as const, {
        required_error: 'Bitte waehlen Sie ein Ergebnis',
    }),
    notes: z.string().optional(),
    follow_up_required: z.boolean().default(false),
    follow_up_date: z.date().optional().nullable(),
    follow_up_notes: z.string().optional(),
});

type PhoneCallFormData = z.infer<typeof phoneCallSchema>;

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
        label: 'Rueckruf erbeten',
        description: 'Kunde bittet um Rueckruf',
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
        description: 'Kunde erhebt Einwaende',
        icon: <AlertTriangle className="h-4 w-4" />,
        color: 'text-red-600',
    },
};

// ==================== Main Component ====================

export function TelefonProtokollDialog({
    dunningId,
    debtorName,
    open,
    onOpenChange,
    onSuccess,
}: TelefonProtokollDialogProps) {
    const logPhoneCall = useLogPhoneCall();

    const form = useForm<PhoneCallFormData>({
        resolver: zodResolver(phoneCallSchema),
        defaultValues: {
            contact_name: debtorName || '',
            phone_number: '',
            outcome: undefined,
            notes: '',
            follow_up_required: false,
            follow_up_date: null,
            follow_up_notes: '',
        },
    });

    const watchFollowUp = form.watch('follow_up_required');
    const watchOutcome = form.watch('outcome');

    // Reset form when dialog opens with new debtor
    useEffect(() => {
        if (open) {
            form.reset({
                contact_name: debtorName || '',
                phone_number: '',
                outcome: undefined,
                notes: '',
                follow_up_required: false,
                follow_up_date: null,
                follow_up_notes: '',
            });
        }
    }, [open, debtorName, form]);

    // Auto-suggest follow-up for certain outcomes
    useEffect(() => {
        if (watchOutcome === 'callback_requested' || watchOutcome === 'payment_promised') {
            form.setValue('follow_up_required', true);
            if (!form.getValues('follow_up_date')) {
                // Set default follow-up to 3 days from now
                const followUpDate = new Date();
                followUpDate.setDate(followUpDate.getDate() + 3);
                form.setValue('follow_up_date', followUpDate);
            }
        }
    }, [watchOutcome, form]);

    const onSubmit = async (data: PhoneCallFormData) => {
        try {
            await logPhoneCall.mutateAsync({
                dunningId,
                data: {
                    contact_name: data.contact_name,
                    phone_number: data.phone_number || undefined,
                    outcome: data.outcome,
                    notes: data.notes || undefined,
                    follow_up_required: data.follow_up_required,
                    follow_up_date: data.follow_up_date?.toISOString().split('T')[0],
                    follow_up_notes: data.follow_up_notes || undefined,
                },
            });

            toast.success('Anruf protokolliert', {
                description: `Telefonkontakt mit ${data.contact_name} wurde gespeichert.`,
            });

            onOpenChange(false);
            onSuccess?.();
        } catch (error) {
            toast.error('Fehler beim Speichern', {
                description: 'Der Telefonkontakt konnte nicht gespeichert werden.',
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

                <Form {...form}>
                    <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
                        {/* Contact Name */}
                        <FormField
                            control={form.control}
                            name="contact_name"
                            render={({ field }) => (
                                <FormItem>
                                    <FormLabel>
                                        Kontaktname <span className="text-destructive">*</span>
                                    </FormLabel>
                                    <FormControl>
                                        <div className="relative">
                                            <User className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                                            <Input
                                                {...field}
                                                placeholder="Name der kontaktierten Person"
                                                className="pl-10"
                                            />
                                        </div>
                                    </FormControl>
                                    <FormMessage />
                                </FormItem>
                            )}
                        />

                        {/* Phone Number */}
                        <FormField
                            control={form.control}
                            name="phone_number"
                            render={({ field }) => (
                                <FormItem>
                                    <FormLabel>Telefonnummer</FormLabel>
                                    <FormControl>
                                        <div className="relative">
                                            <Phone className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                                            <Input
                                                {...field}
                                                placeholder="+49 ..."
                                                className="pl-10"
                                            />
                                        </div>
                                    </FormControl>
                                    <FormMessage />
                                </FormItem>
                            )}
                        />

                        {/* Outcome */}
                        <FormField
                            control={form.control}
                            name="outcome"
                            render={({ field }) => (
                                <FormItem>
                                    <FormLabel>
                                        Ergebnis <span className="text-destructive">*</span>
                                    </FormLabel>
                                    <Select
                                        onValueChange={field.onChange}
                                        value={field.value}
                                    >
                                        <FormControl>
                                            <SelectTrigger>
                                                <SelectValue placeholder="Waehlen Sie das Ergebnis..." />
                                            </SelectTrigger>
                                        </FormControl>
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
                                    <FormMessage />
                                </FormItem>
                            )}
                        />

                        {/* Notes */}
                        <FormField
                            control={form.control}
                            name="notes"
                            render={({ field }) => (
                                <FormItem>
                                    <FormLabel>Notizen</FormLabel>
                                    <FormControl>
                                        <div className="relative">
                                            <MessageSquare className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
                                            <Textarea
                                                {...field}
                                                placeholder="Gespraechsinhalt, Vereinbarungen, Anmerkungen..."
                                                className="pl-10 min-h-[100px]"
                                            />
                                        </div>
                                    </FormControl>
                                    <FormDescription>
                                        Beschreiben Sie den Inhalt des Gespraechs
                                    </FormDescription>
                                    <FormMessage />
                                </FormItem>
                            )}
                        />

                        {/* Follow-up Required */}
                        <FormField
                            control={form.control}
                            name="follow_up_required"
                            render={({ field }) => (
                                <FormItem className="flex flex-row items-start space-x-3 space-y-0 rounded-md border p-4">
                                    <FormControl>
                                        <Checkbox
                                            checked={field.value}
                                            onCheckedChange={field.onChange}
                                        />
                                    </FormControl>
                                    <div className="space-y-1 leading-none">
                                        <FormLabel>
                                            Follow-up erforderlich
                                        </FormLabel>
                                        <FormDescription>
                                            Wiedervorlage fuer erneuten Kontaktversuch planen
                                        </FormDescription>
                                    </div>
                                </FormItem>
                            )}
                        />

                        {/* Follow-up Date (conditional) */}
                        {watchFollowUp && (
                            <div className="space-y-4 rounded-md border p-4 bg-muted/30">
                                <FormField
                                    control={form.control}
                                    name="follow_up_date"
                                    render={({ field }) => (
                                        <FormItem className="flex flex-col">
                                            <FormLabel>Wiedervorlage am</FormLabel>
                                            <Popover>
                                                <PopoverTrigger asChild>
                                                    <FormControl>
                                                        <Button
                                                            variant="outline"
                                                            className={cn(
                                                                'w-full pl-3 text-left font-normal',
                                                                !field.value && 'text-muted-foreground'
                                                            )}
                                                        >
                                                            <CalendarIcon className="mr-2 h-4 w-4" />
                                                            {field.value ? (
                                                                format(field.value, 'PPP', { locale: de })
                                                            ) : (
                                                                <span>Datum waehlen</span>
                                                            )}
                                                        </Button>
                                                    </FormControl>
                                                </PopoverTrigger>
                                                <PopoverContent className="w-auto p-0" align="start">
                                                    <Calendar
                                                        mode="single"
                                                        selected={field.value ?? undefined}
                                                        onSelect={field.onChange}
                                                        disabled={(date) => date < new Date()}
                                                        locale={de}
                                                        initialFocus
                                                    />
                                                </PopoverContent>
                                            </Popover>
                                            <FormMessage />
                                        </FormItem>
                                    )}
                                />

                                <FormField
                                    control={form.control}
                                    name="follow_up_notes"
                                    render={({ field }) => (
                                        <FormItem>
                                            <FormLabel>Follow-up Notiz</FormLabel>
                                            <FormControl>
                                                <Input
                                                    {...field}
                                                    placeholder="z.B. Zahlungseingang pruefen, erneut anrufen..."
                                                />
                                            </FormControl>
                                            <FormMessage />
                                        </FormItem>
                                    )}
                                />
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
                </Form>
            </DialogContent>
        </Dialog>
    );
}
