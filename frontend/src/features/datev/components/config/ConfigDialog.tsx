/**
 * DATEV Konfigurations-Dialog
 *
 * Formular zum Erstellen und Bearbeiten von DATEV-Konfigurationen.
 */

import { useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
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
import { Checkbox } from '@/components/ui/checkbox';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import {
    Collapsible,
    CollapsibleContent,
    CollapsibleTrigger,
} from '@/components/ui/collapsible';
import { useToast } from '@/components/ui/use-toast';
import { ChevronDown, Loader2 } from 'lucide-react';
import { configurationSchema, type ConfigurationFormData } from '@/features/datev/utils/validation';
import { useCreateConfig, useUpdateConfig } from '@/features/datev/hooks/use-datev-queries';
import type { DATEVConfigurationResponse } from '@/lib/api/services/datev';

interface ConfigDialogProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    config?: DATEVConfigurationResponse | null;
}

export function ConfigDialog({ open, onOpenChange, config }: ConfigDialogProps) {
    const isEdit = !!config;
    const { toast } = useToast();

    const createConfig = useCreateConfig();
    const updateConfig = useUpdateConfig();

    const {
        register,
        handleSubmit,
        reset,
        watch,
        setValue,
        clearErrors,
        formState: { errors, isSubmitting },
    } = useForm<ConfigurationFormData>({
        resolver: zodResolver(configurationSchema),
        defaultValues: {
            berater_nr: '',
            mandanten_nr: '',
            wj_beginn: new Date().getFullYear() + '-01-01',
            kontenrahmen: 'SKR03',
            incoming_expense_account: '',
            incoming_creditor_account: '',
            outgoing_revenue_account: '',
            outgoing_debtor_account: '',
            sammelkonto_kreditoren: '1600',
            sammelkonto_debitoren: '1400',
            sachkontenlange: 4,
            buchungstext_format: '{invoice_number}',
            is_default: false,
        },
    });

    // Live Error Clearing: Fehler löschen wenn Nutzer Feld korrigiert
    useEffect(() => {
        const subscription = watch((_, { name }) => {
            if (name && errors[name as keyof typeof errors]) {
                clearErrors(name as keyof ConfigurationFormData);
            }
        });
        return () => subscription.unsubscribe();
    }, [watch, clearErrors, errors]);

    // Bei Bearbeitung: Formular mit vorhandenen Daten fuellen
    useEffect(() => {
        if (config) {
            reset({
                berater_nr: config.berater_nr,
                mandanten_nr: config.mandanten_nr,
                wj_beginn: config.wj_beginn,
                kontenrahmen: config.kontenrahmen,
                incoming_expense_account: config.incoming_expense_account || '',
                incoming_creditor_account: config.incoming_creditor_account || '',
                outgoing_revenue_account: config.outgoing_revenue_account || '',
                outgoing_debtor_account: config.outgoing_debtor_account || '',
                sammelkonto_kreditoren: config.sammelkonto_kreditoren,
                sammelkonto_debitoren: config.sammelkonto_debitoren,
                sachkontenlange: config.sachkontenlange,
                buchungstext_format: config.buchungstext_format,
                is_default: config.is_default,
            });
        } else {
            reset({
                berater_nr: '',
                mandanten_nr: '',
                wj_beginn: new Date().getFullYear() + '-01-01',
                kontenrahmen: 'SKR03',
                incoming_expense_account: '',
                incoming_creditor_account: '',
                outgoing_revenue_account: '',
                outgoing_debtor_account: '',
                sammelkonto_kreditoren: '1600',
                sammelkonto_debitoren: '1400',
                sachkontenlange: 4,
                buchungstext_format: '{invoice_number}',
                is_default: false,
            });
        }
    }, [config, reset]);

    const onSubmit = async (data: ConfigurationFormData) => {
        try {
            // Leere Strings zu undefined konvertieren
            const cleanData = {
                ...data,
                incoming_expense_account: data.incoming_expense_account || undefined,
                incoming_creditor_account: data.incoming_creditor_account || undefined,
                outgoing_revenue_account: data.outgoing_revenue_account || undefined,
                outgoing_debtor_account: data.outgoing_debtor_account || undefined,
            };

            if (isEdit && config) {
                await updateConfig.mutateAsync({ id: config.id, data: cleanData });
                toast({
                    title: 'Konfiguration aktualisiert',
                    description: `Berater ${data.berater_nr} / Mandant ${data.mandanten_nr} wurde aktualisiert.`,
                });
            } else {
                await createConfig.mutateAsync(cleanData);
                toast({
                    title: 'Konfiguration erstellt',
                    description: `Neue Konfiguration für Berater ${data.berater_nr} wurde erstellt.`,
                });
            }
            onOpenChange(false);
        } catch (error: unknown) {
            const errorMessage = error instanceof Error ? error.message : 'Unbekannter Fehler';
            toast({
                title: 'Fehler beim Speichern',
                description: errorMessage,
                variant: 'destructive',
            });
        }
    };

    const kontenrahmen = watch('kontenrahmen');

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
                <DialogHeader>
                    <DialogTitle>
                        {isEdit ? 'Konfiguration bearbeiten' : 'Neue DATEV-Konfiguration'}
                    </DialogTitle>
                    <DialogDescription>
                        Geben Sie die Daten Ihres Steuerberaters und die gewuenschten
                        Kontenrahmen-Einstellungen ein.
                    </DialogDescription>
                </DialogHeader>

                <form onSubmit={handleSubmit(onSubmit)} className="space-y-6">
                    {/* Pflichtfelder */}
                    <div className="space-y-4">
                        <h4 className="font-medium text-sm text-muted-foreground uppercase tracking-wide">
                            Steuerberater-Daten
                        </h4>

                        <div className="grid grid-cols-2 gap-4">
                            <div className="space-y-2">
                                <Label htmlFor="berater_nr">Beraternummer *</Label>
                                <Input
                                    id="berater_nr"
                                    placeholder="1234567"
                                    {...register('berater_nr')}
                                />
                                {errors.berater_nr && (
                                    <p className="text-sm text-destructive">
                                        {errors.berater_nr.message}
                                    </p>
                                )}
                            </div>

                            <div className="space-y-2">
                                <Label htmlFor="mandanten_nr">Mandantennummer *</Label>
                                <Input
                                    id="mandanten_nr"
                                    placeholder="12345"
                                    {...register('mandanten_nr')}
                                />
                                {errors.mandanten_nr && (
                                    <p className="text-sm text-destructive">
                                        {errors.mandanten_nr.message}
                                    </p>
                                )}
                            </div>
                        </div>

                        <div className="space-y-2">
                            <Label htmlFor="wj_beginn">Wirtschaftsjahr-Beginn *</Label>
                            <Input id="wj_beginn" type="date" {...register('wj_beginn')} />
                            {errors.wj_beginn && (
                                <p className="text-sm text-destructive">
                                    {errors.wj_beginn.message}
                                </p>
                            )}
                            <p className="text-xs text-muted-foreground">
                                Beginn des Wirtschaftsjahres (meist 01.01.)
                            </p>
                        </div>
                    </div>

                    {/* Kontenrahmen */}
                    <div className="space-y-4">
                        <h4 className="font-medium text-sm text-muted-foreground uppercase tracking-wide">
                            Kontenrahmen
                        </h4>

                        <RadioGroup
                            value={kontenrahmen}
                            onValueChange={(value) =>
                                setValue('kontenrahmen', value as 'SKR03' | 'SKR04')
                            }
                            className="grid grid-cols-2 gap-4"
                            aria-label="Kontenrahmen auswählen"
                        >
                            <div
                                className={`flex items-start space-x-3 p-4 rounded-lg border ${
                                    kontenrahmen === 'SKR03'
                                        ? 'border-primary bg-primary/5'
                                        : 'border-muted'
                                }`}
                            >
                                <RadioGroupItem value="SKR03" id="skr03" />
                                <div className="space-y-1">
                                    <Label htmlFor="skr03" className="font-medium cursor-pointer">
                                        SKR 03
                                    </Label>
                                    <p className="text-xs text-muted-foreground">
                                        Prozessorientiert - Industrie, Handel, Handwerk
                                    </p>
                                </div>
                            </div>

                            <div
                                className={`flex items-start space-x-3 p-4 rounded-lg border ${
                                    kontenrahmen === 'SKR04'
                                        ? 'border-primary bg-primary/5'
                                        : 'border-muted'
                                }`}
                            >
                                <RadioGroupItem value="SKR04" id="skr04" />
                                <div className="space-y-1">
                                    <Label htmlFor="skr04" className="font-medium cursor-pointer">
                                        SKR 04
                                    </Label>
                                    <p className="text-xs text-muted-foreground">
                                        Abschlussorientiert - Bilanzierende Unternehmen
                                    </p>
                                </div>
                            </div>
                        </RadioGroup>
                        {errors.kontenrahmen && (
                            <p className="text-sm text-destructive">
                                {errors.kontenrahmen.message}
                            </p>
                        )}
                    </div>

                    {/* Erweiterte Einstellungen (Collapsible) */}
                    <Collapsible>
                        <CollapsibleTrigger asChild>
                            <Button
                                variant="ghost"
                                type="button"
                                className="w-full justify-between"
                                aria-label="Erweiterte Einstellungen ein- oder ausblenden"
                            >
                                <span>Erweiterte Einstellungen</span>
                                <ChevronDown className="h-4 w-4" />
                            </Button>
                        </CollapsibleTrigger>
                        <CollapsibleContent className="space-y-4 pt-4">
                            {/* Standardkonten Eingang */}
                            <div className="space-y-2">
                                <h5 className="text-sm font-medium">Eingangsrechnungen</h5>
                                <div className="grid grid-cols-2 gap-4">
                                    <div className="space-y-2">
                                        <Label htmlFor="incoming_expense_account">
                                            Aufwandskonto
                                        </Label>
                                        <Input
                                            id="incoming_expense_account"
                                            placeholder={kontenrahmen === 'SKR03' ? '4200' : '5200'}
                                            {...register('incoming_expense_account')}
                                        />
                                        {errors.incoming_expense_account && (
                                            <p className="text-sm text-destructive">
                                                {errors.incoming_expense_account.message}
                                            </p>
                                        )}
                                    </div>
                                    <div className="space-y-2">
                                        <Label htmlFor="incoming_creditor_account">
                                            Kreditorenkonto
                                        </Label>
                                        <Input
                                            id="incoming_creditor_account"
                                            placeholder="70000"
                                            {...register('incoming_creditor_account')}
                                        />
                                        {errors.incoming_creditor_account && (
                                            <p className="text-sm text-destructive">
                                                {errors.incoming_creditor_account.message}
                                            </p>
                                        )}
                                    </div>
                                </div>
                            </div>

                            {/* Standardkonten Ausgang */}
                            <div className="space-y-2">
                                <h5 className="text-sm font-medium">Ausgangsrechnungen</h5>
                                <div className="grid grid-cols-2 gap-4">
                                    <div className="space-y-2">
                                        <Label htmlFor="outgoing_revenue_account">Erloeskonto</Label>
                                        <Input
                                            id="outgoing_revenue_account"
                                            placeholder={kontenrahmen === 'SKR03' ? '8400' : '4400'}
                                            {...register('outgoing_revenue_account')}
                                        />
                                        {errors.outgoing_revenue_account && (
                                            <p className="text-sm text-destructive">
                                                {errors.outgoing_revenue_account.message}
                                            </p>
                                        )}
                                    </div>
                                    <div className="space-y-2">
                                        <Label htmlFor="outgoing_debtor_account">
                                            Debitorenkonto
                                        </Label>
                                        <Input
                                            id="outgoing_debtor_account"
                                            placeholder="10000"
                                            {...register('outgoing_debtor_account')}
                                        />
                                        {errors.outgoing_debtor_account && (
                                            <p className="text-sm text-destructive">
                                                {errors.outgoing_debtor_account.message}
                                            </p>
                                        )}
                                    </div>
                                </div>
                            </div>

                            {/* Sammelkonten */}
                            <div className="space-y-2">
                                <h5 className="text-sm font-medium">Sammelkonten</h5>
                                <div className="grid grid-cols-2 gap-4">
                                    <div className="space-y-2">
                                        <Label htmlFor="sammelkonto_kreditoren">
                                            Sammelkonto Kreditoren
                                        </Label>
                                        <Input
                                            id="sammelkonto_kreditoren"
                                            {...register('sammelkonto_kreditoren')}
                                        />
                                        {errors.sammelkonto_kreditoren && (
                                            <p className="text-sm text-destructive">
                                                {errors.sammelkonto_kreditoren.message}
                                            </p>
                                        )}
                                    </div>
                                    <div className="space-y-2">
                                        <Label htmlFor="sammelkonto_debitoren">
                                            Sammelkonto Debitoren
                                        </Label>
                                        <Input
                                            id="sammelkonto_debitoren"
                                            {...register('sammelkonto_debitoren')}
                                        />
                                        {errors.sammelkonto_debitoren && (
                                            <p className="text-sm text-destructive">
                                                {errors.sammelkonto_debitoren.message}
                                            </p>
                                        )}
                                    </div>
                                </div>
                            </div>

                            {/* Buchungstext-Format */}
                            <div className="space-y-2">
                                <Label htmlFor="buchungstext_format">Buchungstext-Format</Label>
                                <Input
                                    id="buchungstext_format"
                                    placeholder="{invoice_number}"
                                    {...register('buchungstext_format')}
                                />
                                <p className="text-xs text-muted-foreground">
                                    Platzhalter: {'{invoice_number}'}, {'{sender}'}, {'{recipient}'}
                                </p>
                                {errors.buchungstext_format && (
                                    <p className="text-sm text-destructive">
                                        {errors.buchungstext_format.message}
                                    </p>
                                )}
                            </div>
                        </CollapsibleContent>
                    </Collapsible>

                    {/* Standard-Konfiguration Checkbox */}
                    <div className="flex items-center space-x-2">
                        <Checkbox
                            id="is_default"
                            checked={watch('is_default')}
                            onCheckedChange={(checked) => setValue('is_default', !!checked)}
                        />
                        <Label htmlFor="is_default" className="cursor-pointer">
                            Als Standard-Konfiguration verwenden
                        </Label>
                    </div>

                    <DialogFooter>
                        <Button
                            type="button"
                            variant="outline"
                            onClick={() => onOpenChange(false)}
                        >
                            Abbrechen
                        </Button>
                        <Button type="submit" disabled={isSubmitting}>
                            {isSubmitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                            {isEdit ? 'Speichern' : 'Erstellen'}
                        </Button>
                    </DialogFooter>
                </form>
            </DialogContent>
        </Dialog>
    );
}
