/**
 * DATEV Vendor-Mapping Dialog
 *
 * Formular zum Erstellen und Bearbeiten von Lieferanten-Kontenzuordnungen.
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
import { useToast } from '@/components/ui/use-toast';
import { Loader2 } from 'lucide-react';
import {
    vendorMappingSchema,
    type VendorMappingFormData,
} from '@/features/datev/utils/validation';
import {
    useCreateVendorMapping,
    useUpdateVendorMapping,
} from '@/features/datev/hooks/use-datev-queries';
import type { DATEVVendorMappingResponse } from '@/lib/api/services/datev';

interface VendorMappingDialogProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    configId: string;
    mapping?: DATEVVendorMappingResponse | null;
}

export function VendorMappingDialog({
    open,
    onOpenChange,
    configId,
    mapping,
}: VendorMappingDialogProps) {
    const isEdit = !!mapping;
    const { toast } = useToast();

    const createMapping = useCreateVendorMapping();
    const updateMapping = useUpdateVendorMapping();

    const {
        register,
        handleSubmit,
        reset,
        watch,
        clearErrors,
        formState: { errors, isSubmitting },
    } = useForm<VendorMappingFormData>({
        resolver: zodResolver(vendorMappingSchema),
        defaultValues: {
            vendor_name: '',
            vendor_vat_id: '',
            vendor_iban: '',
            business_entity_id: '',
            expense_account: '',
            creditor_account: '',
            cost_center: '',
            cost_object: '',
        },
    });

    // Live Error Clearing: Fehler löschen wenn Nutzer Feld korrigiert
    useEffect(() => {
        const subscription = watch((_, { name }) => {
            if (name && errors[name as keyof typeof errors]) {
                clearErrors(name as keyof VendorMappingFormData);
            }
        });
        return () => subscription.unsubscribe();
    }, [watch, clearErrors, errors]);

    // Bei Bearbeitung: Formular mit vorhandenen Daten fuellen
    useEffect(() => {
        if (mapping) {
            reset({
                vendor_name: mapping.vendor_name || '',
                vendor_vat_id: mapping.vendor_vat_id || '',
                vendor_iban: mapping.vendor_iban || '',
                business_entity_id: mapping.business_entity_id || '',
                expense_account: mapping.expense_account,
                creditor_account: mapping.creditor_account || '',
                cost_center: mapping.cost_center || '',
                cost_object: mapping.cost_object || '',
            });
        } else {
            reset({
                vendor_name: '',
                vendor_vat_id: '',
                vendor_iban: '',
                business_entity_id: '',
                expense_account: '',
                creditor_account: '',
                cost_center: '',
                cost_object: '',
            });
        }
    }, [mapping, reset]);

    const onSubmit = async (data: VendorMappingFormData) => {
        try {
            // Leere Strings zu undefined konvertieren
            const cleanData = {
                expense_account: data.expense_account,
                vendor_name: data.vendor_name || undefined,
                vendor_vat_id: data.vendor_vat_id || undefined,
                vendor_iban: data.vendor_iban || undefined,
                business_entity_id: data.business_entity_id || undefined,
                creditor_account: data.creditor_account || undefined,
                cost_center: data.cost_center || undefined,
                cost_object: data.cost_object || undefined,
            };

            const vendorIdentifier = data.vendor_name || data.vendor_vat_id || data.vendor_iban || 'Lieferant';

            if (isEdit && mapping) {
                await updateMapping.mutateAsync({
                    configId,
                    mappingId: mapping.id,
                    data: cleanData,
                });
                toast({
                    title: 'Zuordnung aktualisiert',
                    description: `Die Zuordnung für ${vendorIdentifier} wurde aktualisiert.`,
                });
            } else {
                await createMapping.mutateAsync({
                    configId,
                    data: cleanData,
                });
                toast({
                    title: 'Zuordnung erstellt',
                    description: `Neue Zuordnung für ${vendorIdentifier} wurde erstellt.`,
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

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="max-w-lg">
                <DialogHeader>
                    <DialogTitle>
                        {isEdit ? 'Lieferanten-Zuordnung bearbeiten' : 'Neue Lieferanten-Zuordnung'}
                    </DialogTitle>
                    <DialogDescription>
                        Ordnen Sie einem Lieferanten spezifische Konten zu. Mindestens ein
                        Identifikationsmerkmal (Name, USt-IdNr oder IBAN) ist erforderlich.
                    </DialogDescription>
                </DialogHeader>

                <form onSubmit={handleSubmit(onSubmit)} className="space-y-6">
                    {/* Identifikation */}
                    <div className="space-y-4">
                        <h4 className="font-medium text-sm text-muted-foreground uppercase tracking-wide">
                            Lieferanten-Identifikation
                        </h4>

                        <div className="space-y-2">
                            <Label htmlFor="vendor_name">Firmenname</Label>
                            <Input
                                id="vendor_name"
                                placeholder="Musterfirma GmbH"
                                {...register('vendor_name')}
                            />
                            {errors.vendor_name && (
                                <p className="text-sm text-destructive">
                                    {errors.vendor_name.message}
                                </p>
                            )}
                            <p className="text-xs text-muted-foreground">
                                Wird case-insensitiv gematcht (Groß-/Kleinschreibung egal)
                            </p>
                        </div>

                        <div className="grid grid-cols-2 gap-4">
                            <div className="space-y-2">
                                <Label htmlFor="vendor_vat_id">USt-IdNr</Label>
                                <Input
                                    id="vendor_vat_id"
                                    placeholder="DE123456789"
                                    {...register('vendor_vat_id')}
                                />
                                {errors.vendor_vat_id && (
                                    <p className="text-sm text-destructive">
                                        {errors.vendor_vat_id.message}
                                    </p>
                                )}
                            </div>

                            <div className="space-y-2">
                                <Label htmlFor="vendor_iban">IBAN</Label>
                                <Input
                                    id="vendor_iban"
                                    placeholder="DE89 3704 0044 0532 0130 00"
                                    {...register('vendor_iban')}
                                />
                                {errors.vendor_iban && (
                                    <p className="text-sm text-destructive">
                                        {errors.vendor_iban.message}
                                    </p>
                                )}
                            </div>
                        </div>
                    </div>

                    {/* Kontozuordnung */}
                    <div className="space-y-4">
                        <h4 className="font-medium text-sm text-muted-foreground uppercase tracking-wide">
                            Kontozuordnung
                        </h4>

                        <div className="grid grid-cols-2 gap-4">
                            <div className="space-y-2">
                                <Label htmlFor="expense_account">Aufwandskonto *</Label>
                                <Input
                                    id="expense_account"
                                    placeholder="4200"
                                    {...register('expense_account')}
                                />
                                {errors.expense_account && (
                                    <p className="text-sm text-destructive">
                                        {errors.expense_account.message}
                                    </p>
                                )}
                                <p className="text-xs text-muted-foreground">
                                    Sachkonto für diesen Lieferanten
                                </p>
                            </div>

                            <div className="space-y-2">
                                <Label htmlFor="creditor_account">Kreditorenkonto</Label>
                                <Input
                                    id="creditor_account"
                                    placeholder="70001"
                                    {...register('creditor_account')}
                                />
                                {errors.creditor_account && (
                                    <p className="text-sm text-destructive">
                                        {errors.creditor_account.message}
                                    </p>
                                )}
                                <p className="text-xs text-muted-foreground">
                                    Personenkonto (optional)
                                </p>
                            </div>
                        </div>
                    </div>

                    {/* Kostenrechnung */}
                    <div className="space-y-4">
                        <h4 className="font-medium text-sm text-muted-foreground uppercase tracking-wide">
                            Kostenrechnung (optional)
                        </h4>

                        <div className="grid grid-cols-2 gap-4">
                            <div className="space-y-2">
                                <Label htmlFor="cost_center">Kostenstelle</Label>
                                <Input
                                    id="cost_center"
                                    placeholder="KST001"
                                    {...register('cost_center')}
                                />
                                {errors.cost_center && (
                                    <p className="text-sm text-destructive">
                                        {errors.cost_center.message}
                                    </p>
                                )}
                            </div>

                            <div className="space-y-2">
                                <Label htmlFor="cost_object">Kostentraeger</Label>
                                <Input
                                    id="cost_object"
                                    placeholder="KTR001"
                                    {...register('cost_object')}
                                />
                                {errors.cost_object && (
                                    <p className="text-sm text-destructive">
                                        {errors.cost_object.message}
                                    </p>
                                )}
                            </div>
                        </div>
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
