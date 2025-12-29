/**
 * Account Dialog
 * Erstellen und Bearbeiten von Bankkonten
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
import { Checkbox } from '@/components/ui/checkbox';
import { useToast } from '@/components/ui/use-toast';
import { useCreateAccount, useUpdateAccount } from '@/features/banking/hooks/use-banking-queries';
import type { BankAccount, BankAccountCreate, BankAccountUpdate } from '@/lib/api/services/banking';

interface AccountDialogProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    account: BankAccount | null;
}

interface FormData {
    account_name: string;
    iban: string;
    bic: string;
    bank_name: string;
    account_holder: string;
    account_type: 'checking' | 'savings' | 'business' | 'credit';
    currency: string;
    is_active: boolean;
}

export function AccountDialog({ open, onOpenChange, account }: AccountDialogProps) {
    const { toast } = useToast();
    const createAccount = useCreateAccount();
    const updateAccount = useUpdateAccount();

    const isEditing = !!account;

    const {
        register,
        handleSubmit,
        reset,
        setValue,
        watch,
        formState: { errors, isSubmitting },
    } = useForm<FormData>({
        defaultValues: {
            account_name: '',
            iban: '',
            bic: '',
            bank_name: '',
            account_holder: '',
            account_type: 'checking',
            currency: 'EUR',
            is_active: true,
        },
    });

    // Reset form when dialog opens/closes or account changes
    useEffect(() => {
        if (open) {
            if (account) {
                reset({
                    account_name: account.account_name,
                    iban: account.iban,
                    bic: account.bic || '',
                    bank_name: account.bank_name || '',
                    account_holder: account.account_holder || '',
                    account_type: account.account_type,
                    currency: account.currency,
                    is_active: account.is_active,
                });
            } else {
                reset({
                    account_name: '',
                    iban: '',
                    bic: '',
                    bank_name: '',
                    account_holder: '',
                    account_type: 'checking',
                    currency: 'EUR',
                    is_active: true,
                });
            }
        }
    }, [open, account, reset]);

    const onSubmit = async (data: FormData) => {
        try {
            if (isEditing && account) {
                const updateData: BankAccountUpdate = {
                    account_name: data.account_name,
                    bank_name: data.bank_name || undefined,
                    account_holder: data.account_holder || undefined,
                    account_type: data.account_type,
                    is_active: data.is_active,
                };

                await updateAccount.mutateAsync({ id: account.id, data: updateData });
                toast({
                    title: 'Konto aktualisiert',
                    description: `${data.account_name} wurde erfolgreich aktualisiert.`,
                });
            } else {
                const createData: BankAccountCreate = {
                    account_name: data.account_name,
                    iban: data.iban.replace(/\s/g, '').toUpperCase(),
                    bic: data.bic || undefined,
                    bank_name: data.bank_name || undefined,
                    account_holder: data.account_holder || undefined,
                    account_type: data.account_type,
                    currency: data.currency,
                };

                await createAccount.mutateAsync(createData);
                toast({
                    title: 'Konto erstellt',
                    description: `${data.account_name} wurde erfolgreich erstellt.`,
                });
            }

            onOpenChange(false);
        } catch (err: unknown) {
            const errorMessage = err instanceof Error ? err.message : 'Unbekannter Fehler';
            toast({
                title: 'Fehler',
                description: `Das Konto konnte nicht gespeichert werden: ${errorMessage}`,
                variant: 'destructive',
            });
        }
    };

    const accountType = watch('account_type');
    const isActive = watch('is_active');

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="sm:max-w-[500px]">
                <DialogHeader>
                    <DialogTitle>
                        {isEditing ? 'Konto bearbeiten' : 'Neues Bankkonto'}
                    </DialogTitle>
                    <DialogDescription>
                        {isEditing
                            ? 'Bearbeiten Sie die Kontodaten.'
                            : 'Geben Sie die Daten des Bankkontos ein.'}
                    </DialogDescription>
                </DialogHeader>

                <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
                    {/* Kontoname */}
                    <div className="space-y-2">
                        <Label htmlFor="account_name">Kontoname *</Label>
                        <Input
                            id="account_name"
                            placeholder="z.B. Hauptkonto Sparkasse"
                            {...register('account_name', { required: 'Kontoname ist erforderlich' })}
                        />
                        {errors.account_name && (
                            <p className="text-sm text-destructive">{errors.account_name.message}</p>
                        )}
                    </div>

                    {/* IBAN (nur bei Erstellen) */}
                    {!isEditing && (
                        <div className="space-y-2">
                            <Label htmlFor="iban">IBAN *</Label>
                            <Input
                                id="iban"
                                placeholder="DE89 3704 0044 0532 0130 00"
                                className="font-mono"
                                {...register('iban', {
                                    required: 'IBAN ist erforderlich',
                                    validate: validateIBAN,
                                })}
                            />
                            {errors.iban && (
                                <p className="text-sm text-destructive">{errors.iban.message}</p>
                            )}
                        </div>
                    )}

                    {/* BIC (nur bei Erstellen) */}
                    {!isEditing && (
                        <div className="space-y-2">
                            <Label htmlFor="bic">BIC</Label>
                            <Input
                                id="bic"
                                placeholder="COBADEFFXXX"
                                className="font-mono uppercase"
                                {...register('bic')}
                            />
                        </div>
                    )}

                    {/* Bank Name */}
                    <div className="space-y-2">
                        <Label htmlFor="bank_name">Bankname</Label>
                        <Input
                            id="bank_name"
                            placeholder="z.B. Sparkasse Koeln"
                            {...register('bank_name')}
                        />
                    </div>

                    {/* Kontoinhaber */}
                    <div className="space-y-2">
                        <Label htmlFor="account_holder">Kontoinhaber</Label>
                        <Input
                            id="account_holder"
                            placeholder="Max Mustermann GmbH"
                            {...register('account_holder')}
                        />
                    </div>

                    {/* Kontotyp */}
                    <div className="space-y-2">
                        <Label>Kontotyp</Label>
                        <Select
                            value={accountType}
                            onValueChange={(value) =>
                                setValue('account_type', value as FormData['account_type'])
                            }
                        >
                            <SelectTrigger>
                                <SelectValue placeholder="Kontotyp wählen" />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value="checking">Girokonto</SelectItem>
                                <SelectItem value="savings">Sparkonto</SelectItem>
                                <SelectItem value="business">Geschaeftskonto</SelectItem>
                                <SelectItem value="credit">Kreditkonto</SelectItem>
                            </SelectContent>
                        </Select>
                    </div>

                    {/* Waehrung (nur bei Erstellen) */}
                    {!isEditing && (
                        <div className="space-y-2">
                            <Label htmlFor="currency">Waehrung</Label>
                            <Input
                                id="currency"
                                placeholder="EUR"
                                className="uppercase"
                                maxLength={3}
                                {...register('currency')}
                            />
                        </div>
                    )}

                    {/* Aktiv (nur bei Bearbeiten) */}
                    {isEditing && (
                        <div className="flex items-center gap-2">
                            <Checkbox
                                id="is_active"
                                checked={isActive}
                                onCheckedChange={(checked) => setValue('is_active', checked === true)}
                            />
                            <Label htmlFor="is_active">Konto ist aktiv</Label>
                        </div>
                    )}

                    <DialogFooter>
                        <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                            Abbrechen
                        </Button>
                        <Button type="submit" disabled={isSubmitting}>
                            {isSubmitting
                                ? 'Speichern...'
                                : isEditing
                                  ? 'Speichern'
                                  : 'Erstellen'}
                        </Button>
                    </DialogFooter>
                </form>
            </DialogContent>
        </Dialog>
    );
}

/**
 * IBAN-Validierung (Frontend)
 */
function validateIBAN(iban: string): string | true {
    const cleaned = iban.replace(/\s/g, '').toUpperCase();

    if (cleaned.length < 15 || cleaned.length > 34) {
        return 'IBAN muss zwischen 15 und 34 Zeichen lang sein';
    }

    if (!/^[A-Z]{2}[0-9]{2}/.test(cleaned)) {
        return 'IBAN muss mit Ländercode (z.B. DE) und 2 Ziffern beginnen';
    }

    // MOD-97 Prüfung
    try {
        const rearranged = cleaned.slice(4) + cleaned.slice(0, 4);
        const numeric = rearranged.replace(/[A-Z]/g, (c) => (c.charCodeAt(0) - 55).toString());
        const checksum = BigInt(numeric) % 97n;
        if (checksum !== 1n) {
            return 'IBAN-Prüfsumme ist ungültig';
        }
    } catch {
        return 'IBAN-Format ist ungültig';
    }

    return true;
}
