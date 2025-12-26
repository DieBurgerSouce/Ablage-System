/**
 * Create Payment Dialog
 * Dialog zum Erstellen neuer SEPA-Zahlungen
 */

import { useState } from 'react';
import { Loader2 } from 'lucide-react';
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
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select';
import { useToast } from '@/components/ui/use-toast';
import { useAccounts, useCreatePayment } from '@/features/banking/hooks/use-banking-queries';

// IBAN Validierung (vereinfacht)
const ibanRegex = /^[A-Z]{2}\d{2}[A-Z0-9]{4,30}$/;

interface PaymentFormData {
    bank_account_id: string;
    beneficiary_name: string;
    beneficiary_iban: string;
    beneficiary_bic: string;
    amount: number;
    currency: string;
    reference: string;
    execution_date: string;
}

interface CreatePaymentDialogProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    linkedDocumentId?: string;
    prefillData?: Partial<PaymentFormData>;
}

export function CreatePaymentDialog({
    open,
    onOpenChange,
    linkedDocumentId,
    prefillData,
}: CreatePaymentDialogProps) {
    const { toast } = useToast();
    const { data: accounts } = useAccounts();
    const createPayment = useCreatePayment();

    const [formData, setFormData] = useState<PaymentFormData>({
        bank_account_id: '',
        beneficiary_name: prefillData?.beneficiary_name ?? '',
        beneficiary_iban: prefillData?.beneficiary_iban ?? '',
        beneficiary_bic: '',
        amount: prefillData?.amount ?? 0,
        currency: 'EUR',
        reference: prefillData?.reference ?? '',
        execution_date: '',
    });

    const [errors, setErrors] = useState<Partial<Record<keyof PaymentFormData, string>>>({});

    const validate = (): boolean => {
        const newErrors: Partial<Record<keyof PaymentFormData, string>> = {};

        if (!formData.bank_account_id) {
            newErrors.bank_account_id = 'Bitte Quellkonto waehlen';
        }
        if (!formData.beneficiary_name || formData.beneficiary_name.length > 70) {
            newErrors.beneficiary_name = 'Name des Empfaengers erforderlich (max. 70 Zeichen)';
        }
        const cleanIban = formData.beneficiary_iban.replace(/\s/g, '').toUpperCase();
        if (!ibanRegex.test(cleanIban)) {
            newErrors.beneficiary_iban = 'Ungueltige IBAN';
        }
        if (formData.amount <= 0) {
            newErrors.amount = 'Betrag muss positiv sein';
        }

        setErrors(newErrors);
        return Object.keys(newErrors).length === 0;
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();

        if (!validate()) return;

        try {
            await createPayment.mutateAsync({
                ...formData,
                beneficiary_iban: formData.beneficiary_iban.replace(/\s/g, '').toUpperCase(),
                document_id: linkedDocumentId,
            });
            toast({
                title: 'Zahlung erstellt',
                description: 'Die Zahlungsanweisung wurde erfolgreich erstellt.',
            });
            onOpenChange(false);
            resetForm();
        } catch (err) {
            toast({
                title: 'Fehler',
                description: err instanceof Error ? err.message : 'Zahlung konnte nicht erstellt werden.',
                variant: 'destructive',
            });
        }
    };

    const resetForm = () => {
        setFormData({
            bank_account_id: '',
            beneficiary_name: prefillData?.beneficiary_name ?? '',
            beneficiary_iban: prefillData?.beneficiary_iban ?? '',
            beneficiary_bic: '',
            amount: prefillData?.amount ?? 0,
            currency: 'EUR',
            reference: prefillData?.reference ?? '',
            execution_date: '',
        });
        setErrors({});
    };

    const handleClose = () => {
        onOpenChange(false);
        resetForm();
    };

    const updateField = <K extends keyof PaymentFormData>(field: K, value: PaymentFormData[K]) => {
        setFormData((prev) => ({ ...prev, [field]: value }));
        if (errors[field]) {
            setErrors((prev) => ({ ...prev, [field]: undefined }));
        }
    };

    return (
        <Dialog open={open} onOpenChange={handleClose}>
            <DialogContent className="max-w-lg">
                <DialogHeader>
                    <DialogTitle>Neue SEPA-Zahlung</DialogTitle>
                    <DialogDescription>
                        Erstellen Sie eine neue Zahlungsanweisung.
                    </DialogDescription>
                </DialogHeader>

                <form onSubmit={handleSubmit} className="space-y-4">
                    {/* Source Account */}
                    <div className="space-y-2">
                        <Label htmlFor="bank_account_id">Quellkonto</Label>
                        <Select
                            value={formData.bank_account_id}
                            onValueChange={(v) => updateField('bank_account_id', v)}
                        >
                            <SelectTrigger>
                                <SelectValue placeholder="Konto waehlen..." />
                            </SelectTrigger>
                            <SelectContent>
                                {accounts?.map((account) => (
                                    <SelectItem key={account.id} value={account.id}>
                                        {account.account_name} ({account.iban.slice(-4)})
                                    </SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                        {errors.bank_account_id && (
                            <p className="text-sm text-destructive">{errors.bank_account_id}</p>
                        )}
                    </div>

                    {/* Recipient Name */}
                    <div className="space-y-2">
                        <Label htmlFor="beneficiary_name">Empfaenger</Label>
                        <Input
                            id="beneficiary_name"
                            placeholder="Name des Empfaengers"
                            value={formData.beneficiary_name}
                            onChange={(e) => updateField('beneficiary_name', e.target.value)}
                        />
                        {errors.beneficiary_name && (
                            <p className="text-sm text-destructive">{errors.beneficiary_name}</p>
                        )}
                    </div>

                    {/* IBAN and BIC */}
                    <div className="grid gap-4 md:grid-cols-2">
                        <div className="space-y-2">
                            <Label htmlFor="beneficiary_iban">IBAN</Label>
                            <Input
                                id="beneficiary_iban"
                                placeholder="DE89 3704 0044 0532 0130 00"
                                className="font-mono"
                                value={formData.beneficiary_iban}
                                onChange={(e) => updateField('beneficiary_iban', e.target.value)}
                            />
                            {errors.beneficiary_iban && (
                                <p className="text-sm text-destructive">{errors.beneficiary_iban}</p>
                            )}
                        </div>

                        <div className="space-y-2">
                            <Label htmlFor="beneficiary_bic">BIC (optional)</Label>
                            <Input
                                id="beneficiary_bic"
                                placeholder="COBADEFFXXX"
                                className="font-mono"
                                value={formData.beneficiary_bic}
                                onChange={(e) => updateField('beneficiary_bic', e.target.value)}
                            />
                        </div>
                    </div>

                    {/* Amount and Currency */}
                    <div className="grid gap-4 md:grid-cols-2">
                        <div className="space-y-2">
                            <Label htmlFor="amount">Betrag</Label>
                            <Input
                                id="amount"
                                type="number"
                                step="0.01"
                                min="0.01"
                                placeholder="0.00"
                                value={formData.amount || ''}
                                onChange={(e) => updateField('amount', parseFloat(e.target.value) || 0)}
                            />
                            {errors.amount && (
                                <p className="text-sm text-destructive">{errors.amount}</p>
                            )}
                        </div>

                        <div className="space-y-2">
                            <Label htmlFor="currency">Waehrung</Label>
                            <Select
                                value={formData.currency}
                                onValueChange={(v) => updateField('currency', v)}
                            >
                                <SelectTrigger>
                                    <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="EUR">EUR</SelectItem>
                                    <SelectItem value="CHF">CHF</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>
                    </div>

                    {/* Reference */}
                    <div className="space-y-2">
                        <Label htmlFor="reference">Verwendungszweck</Label>
                        <Textarea
                            id="reference"
                            placeholder="Rechnungsnummer, Kundennummer, etc."
                            className="resize-none"
                            rows={2}
                            value={formData.reference}
                            onChange={(e) => updateField('reference', e.target.value)}
                        />
                    </div>

                    {/* Execution Date */}
                    <div className="space-y-2">
                        <Label htmlFor="execution_date">Ausfuehrungsdatum (optional)</Label>
                        <Input
                            id="execution_date"
                            type="date"
                            value={formData.execution_date}
                            onChange={(e) => updateField('execution_date', e.target.value)}
                        />
                    </div>

                    <DialogFooter>
                        <Button type="button" variant="outline" onClick={handleClose}>
                            Abbrechen
                        </Button>
                        <Button type="submit" disabled={createPayment.isPending}>
                            {createPayment.isPending ? (
                                <>
                                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                    Erstelle...
                                </>
                            ) : (
                                'Zahlung erstellen'
                            )}
                        </Button>
                    </DialogFooter>
                </form>
            </DialogContent>
        </Dialog>
    );
}
