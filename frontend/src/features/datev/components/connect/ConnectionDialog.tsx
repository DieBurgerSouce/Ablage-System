/**
 * DATEV Connect - Verbindungs-Dialog
 *
 * Dialog zum Erstellen und Bearbeiten von DATEVconnect Verbindungen.
 */

import { useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from '@/components/ui/dialog';
import {
    Form,
    FormControl,
    FormDescription,
    FormField,
    FormItem,
    FormLabel,
    FormMessage,
} from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { Loader2 } from 'lucide-react';
import { useToast } from '@/components/ui/use-toast';
import {
    useCreateConnection,
    useUpdateConnection,
} from '@/features/datev/hooks/use-datev-connect-queries';
import type { DATEVConnectionResponse } from '@/lib/api/services/datev-connect';

// =============================================================================
// VALIDATION SCHEMA
// =============================================================================

const connectionSchema = z.object({
    name: z
        .string()
        .min(1, 'Name ist erforderlich')
        .max(100, 'Name darf maximal 100 Zeichen haben'),
    mandant_nr: z
        .string()
        .min(1, 'Mandantennummer ist erforderlich')
        .regex(/^\d{1,10}$/, 'Mandantennummer muss 1-10 Ziffern enthalten'),
    berater_nr: z
        .string()
        .min(1, 'Beraternummer ist erforderlich')
        .regex(/^\d{1,10}$/, 'Beraternummer muss 1-10 Ziffern enthalten'),
    kontenrahmen: z.enum(['SKR03', 'SKR04'], {
        message: 'Kontenrahmen ist erforderlich',
    }),
    wirtschaftsjahr_beginn: z
        .number()
        .min(1, 'Monat muss zwischen 1 und 12 liegen')
        .max(12, 'Monat muss zwischen 1 und 12 liegen'),
    auto_kontierung: z.boolean(),
    auto_beleg_upload: z.boolean(),
});

type ConnectionFormData = z.infer<typeof connectionSchema>;

// =============================================================================
// COMPONENT
// =============================================================================

interface ConnectionDialogProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    connection: DATEVConnectionResponse | null;
}

export function ConnectionDialog({ open, onOpenChange, connection }: ConnectionDialogProps) {
    const createConnection = useCreateConnection();
    const updateConnection = useUpdateConnection();
    const { toast } = useToast();

    const isEditing = !!connection;
    const isLoading = createConnection.isPending || updateConnection.isPending;

    const form = useForm<ConnectionFormData>({
        resolver: zodResolver(connectionSchema),
        defaultValues: {
            name: '',
            mandant_nr: '',
            berater_nr: '',
            kontenrahmen: 'SKR03',
            wirtschaftsjahr_beginn: 1,
            auto_kontierung: false,
            auto_beleg_upload: true,
        },
    });

    // Form mit existierenden Daten fuellen
    useEffect(() => {
        if (connection) {
            form.reset({
                name: connection.name,
                mandant_nr: connection.mandant_nr,
                berater_nr: connection.berater_nr,
                kontenrahmen: connection.kontenrahmen,
                wirtschaftsjahr_beginn: connection.wirtschaftsjahr_beginn,
                auto_kontierung: connection.auto_kontierung,
                auto_beleg_upload: connection.auto_beleg_upload,
            });
        } else {
            form.reset({
                name: '',
                mandant_nr: '',
                berater_nr: '',
                kontenrahmen: 'SKR03',
                wirtschaftsjahr_beginn: 1,
                auto_kontierung: false,
                auto_beleg_upload: true,
            });
        }
    }, [connection, form]);

    const onSubmit = async (data: ConnectionFormData) => {
        try {
            if (isEditing) {
                await updateConnection.mutateAsync({
                    id: connection.id,
                    data,
                });
                toast({
                    title: 'Verbindung aktualisiert',
                    description: 'Die Verbindung wurde erfolgreich gespeichert.',
                });
            } else {
                await createConnection.mutateAsync(data);
                toast({
                    title: 'Verbindung erstellt',
                    description: 'Die neue Verbindung wurde angelegt. Verbinden Sie sich jetzt mit DATEV.',
                });
            }
            onOpenChange(false);
        } catch {
            toast({
                title: isEditing ? 'Aktualisierung fehlgeschlagen' : 'Erstellen fehlgeschlagen',
                description: 'Die Verbindung konnte nicht gespeichert werden.',
                variant: 'destructive',
            });
        }
    };

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="sm:max-w-[500px]">
                <DialogHeader>
                    <DialogTitle>
                        {isEditing ? 'Verbindung bearbeiten' : 'Neue Verbindung erstellen'}
                    </DialogTitle>
                    <DialogDescription>
                        {isEditing
                            ? 'Aktualisieren Sie die Einstellungen Ihrer DATEVconnect Verbindung.'
                            : 'Erstellen Sie eine neue Verbindung zur DATEVconnect API.'}
                    </DialogDescription>
                </DialogHeader>

                <Form {...form}>
                    <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
                        {/* Name */}
                        <FormField
                            control={form.control}
                            name="name"
                            render={({ field }) => (
                                <FormItem>
                                    <FormLabel>Verbindungsname</FormLabel>
                                    <FormControl>
                                        <Input placeholder="Hauptverbindung" {...field} />
                                    </FormControl>
                                    <FormDescription>
                                        Ein beschreibender Name für diese Verbindung.
                                    </FormDescription>
                                    <FormMessage />
                                </FormItem>
                            )}
                        />

                        {/* Berater- und Mandantennummer */}
                        <div className="grid grid-cols-2 gap-4">
                            <FormField
                                control={form.control}
                                name="berater_nr"
                                render={({ field }) => (
                                    <FormItem>
                                        <FormLabel>Beraternummer</FormLabel>
                                        <FormControl>
                                            <Input
                                                placeholder="12345"
                                                className="font-mono"
                                                {...field}
                                            />
                                        </FormControl>
                                        <FormMessage />
                                    </FormItem>
                                )}
                            />

                            <FormField
                                control={form.control}
                                name="mandant_nr"
                                render={({ field }) => (
                                    <FormItem>
                                        <FormLabel>Mandantennummer</FormLabel>
                                        <FormControl>
                                            <Input
                                                placeholder="00001"
                                                className="font-mono"
                                                {...field}
                                            />
                                        </FormControl>
                                        <FormMessage />
                                    </FormItem>
                                )}
                            />
                        </div>

                        {/* Kontenrahmen und WJ-Beginn */}
                        <div className="grid grid-cols-2 gap-4">
                            <FormField
                                control={form.control}
                                name="kontenrahmen"
                                render={({ field }) => (
                                    <FormItem>
                                        <FormLabel>Kontenrahmen</FormLabel>
                                        <Select
                                            onValueChange={field.onChange}
                                            value={field.value}
                                        >
                                            <FormControl>
                                                <SelectTrigger>
                                                    <SelectValue placeholder="Wählen..." />
                                                </SelectTrigger>
                                            </FormControl>
                                            <SelectContent>
                                                <SelectItem value="SKR03">
                                                    SKR 03 (Standard)
                                                </SelectItem>
                                                <SelectItem value="SKR04">
                                                    SKR 04 (Bilanzierend)
                                                </SelectItem>
                                            </SelectContent>
                                        </Select>
                                        <FormMessage />
                                    </FormItem>
                                )}
                            />

                            <FormField
                                control={form.control}
                                name="wirtschaftsjahr_beginn"
                                render={({ field }) => (
                                    <FormItem>
                                        <FormLabel>WJ-Beginn (Monat)</FormLabel>
                                        <FormControl>
                                            <Input
                                                type="number"
                                                min={1}
                                                max={12}
                                                {...field}
                                                onChange={(e) =>
                                                    field.onChange(parseInt(e.target.value, 10) || 1)
                                                }
                                            />
                                        </FormControl>
                                        <FormDescription>1 = Januar</FormDescription>
                                        <FormMessage />
                                    </FormItem>
                                )}
                            />
                        </div>

                        {/* Automatisierungs-Optionen */}
                        <div className="space-y-4 pt-4 border-t">
                            <FormField
                                control={form.control}
                                name="auto_kontierung"
                                render={({ field }) => (
                                    <FormItem className="flex flex-row items-center justify-between">
                                        <div className="space-y-0.5">
                                            <FormLabel>Auto-Kontierung</FormLabel>
                                            <FormDescription>
                                                Kontierungsvorschläge automatisch anwenden bei hoher Konfidenz.
                                            </FormDescription>
                                        </div>
                                        <FormControl>
                                            <Switch
                                                checked={field.value}
                                                onCheckedChange={field.onChange}
                                            />
                                        </FormControl>
                                    </FormItem>
                                )}
                            />

                            <FormField
                                control={form.control}
                                name="auto_beleg_upload"
                                render={({ field }) => (
                                    <FormItem className="flex flex-row items-center justify-between">
                                        <div className="space-y-0.5">
                                            <FormLabel>Auto-Beleg-Upload</FormLabel>
                                            <FormDescription>
                                                Belegbilder automatisch zu DATEV Unternehmen Online hochladen.
                                            </FormDescription>
                                        </div>
                                        <FormControl>
                                            <Switch
                                                checked={field.value}
                                                onCheckedChange={field.onChange}
                                            />
                                        </FormControl>
                                    </FormItem>
                                )}
                            />
                        </div>

                        <DialogFooter>
                            <Button
                                type="button"
                                variant="outline"
                                onClick={() => onOpenChange(false)}
                                disabled={isLoading}
                            >
                                Abbrechen
                            </Button>
                            <Button type="submit" disabled={isLoading}>
                                {isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                                {isEditing ? 'Speichern' : 'Erstellen'}
                            </Button>
                        </DialogFooter>
                    </form>
                </Form>
            </DialogContent>
        </Dialog>
    );
}
