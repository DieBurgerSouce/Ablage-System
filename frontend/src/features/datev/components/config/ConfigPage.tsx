/**
 * DATEV Konfigurations-Seite
 *
 * Listet alle Konfigurationen auf und ermöglicht Erstellen/Bearbeiten/Löschen.
 */

import { useState, useEffect, useRef } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import {
    AlertDialog,
    AlertDialogAction,
    AlertDialogCancel,
    AlertDialogContent,
    AlertDialogDescription,
    AlertDialogFooter,
    AlertDialogHeader,
    AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table';
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Plus, MoreHorizontal, Pencil, Trash2, Star, FileSpreadsheet } from 'lucide-react';
import { useToast } from '@/components/ui/use-toast';
import { useConfigs, useDeleteConfig, useUpdateConfig } from '@/features/datev/hooks/use-datev-queries';
import { formatDate, formatKontenrahmen } from '@/features/datev/utils';
import { ConfigDialog } from './ConfigDialog';
import type { DATEVConfigurationResponse } from '@/lib/api/services/datev';

export function ConfigPage() {
    const { data: configs, isLoading, error } = useConfigs();
    const deleteConfig = useDeleteConfig();
    const updateConfig = useUpdateConfig();
    const { toast } = useToast();

    const [dialogOpen, setDialogOpen] = useState(false);
    const [editingConfig, setEditingConfig] = useState<DATEVConfigurationResponse | null>(null);
    const [deleteConfirm, setDeleteConfirm] = useState<DATEVConfigurationResponse | null>(null);

    // Refs für Focus Management nach Dialog-Schließung
    const createButtonRef = useRef<HTMLButtonElement>(null);
    const lastTriggerRef = useRef<'create' | 'edit'>('create');

    // Error-Toast für fehlgeschlagene Operationen (mit Cleanup)
    useEffect(() => {
        let isMounted = true;

        if (deleteConfig.isError && isMounted) {
            toast({
                title: 'Löschen fehlgeschlagen',
                description: deleteConfig.error?.message || 'Die Konfiguration konnte nicht gelöscht werden.',
                variant: 'destructive',
            });
        }

        return () => {
            isMounted = false;
        };
    }, [deleteConfig.isError, deleteConfig.error, toast]);

    useEffect(() => {
        let isMounted = true;

        if (updateConfig.isError && isMounted) {
            toast({
                title: 'Aktualisierung fehlgeschlagen',
                description: updateConfig.error?.message || 'Die Konfiguration konnte nicht aktualisiert werden.',
                variant: 'destructive',
            });
        }

        return () => {
            isMounted = false;
        };
    }, [updateConfig.isError, updateConfig.error, toast]);

    const handleCreate = () => {
        if (dialogOpen) return; // Race Condition Guard
        lastTriggerRef.current = 'create';
        setEditingConfig(null);
        setDialogOpen(true);
    };

    const handleEdit = (config: DATEVConfigurationResponse) => {
        if (dialogOpen) return; // Race Condition Guard
        lastTriggerRef.current = 'edit';
        setEditingConfig(config);
        setDialogOpen(true);
    };

    // Focus Management: Focus zurück zum Trigger-Button nach Dialog-Close
    const handleDialogClose = (open: boolean) => {
        setDialogOpen(open);
        if (!open && lastTriggerRef.current === 'create') {
            // Focus zurück zum Create-Button
            setTimeout(() => createButtonRef.current?.focus(), 0);
        }
        // Bei Edit: Focus geht automatisch zur Tabelle zurück (akzeptables Verhalten)
    };

    const handleDelete = async () => {
        if (deleteConfirm) {
            try {
                await deleteConfig.mutateAsync(deleteConfirm.id);
                setDeleteConfirm(null);
            } catch {
                // Error wird via useEffect Toast angezeigt - Dialog bleibt offen
            }
        }
    };

    const handleSetDefault = async (config: DATEVConfigurationResponse) => {
        try {
            await updateConfig.mutateAsync({
                id: config.id,
                data: { is_default: true },
            });
        } catch {
            // Error wird via useEffect Toast angezeigt
        }
    };

    if (error) {
        return (
            <Card>
                <CardContent className="py-10 text-center text-muted-foreground">
                    Fehler beim Laden der Konfigurationen.
                </CardContent>
            </Card>
        );
    }

    return (
        <div className="space-y-6">
            {/* Header mit Erstellen-Button */}
            <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
                <div>
                    <h2 className="text-xl font-semibold">Konfigurationen</h2>
                    <p className="text-sm text-muted-foreground">
                        Verwalten Sie Ihre DATEV-Konfigurationen mit Beraternummer und
                        Kontenrahmen.
                    </p>
                </div>
                <Button ref={createButtonRef} onClick={handleCreate}>
                    <Plus className="mr-2 h-4 w-4" />
                    Neue Konfiguration
                </Button>
            </div>

            {/* Konfigurationsliste */}
            <Card>
                <CardHeader>
                    <CardTitle className="text-base">Alle Konfigurationen</CardTitle>
                    <CardDescription>
                        {isLoading
                            ? 'Lade...'
                            : `${configs?.length || 0} Konfiguration${(configs?.length || 0) !== 1 ? 'en' : ''}`}
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    {isLoading ? (
                        <div className="space-y-3">
                            {[1, 2, 3].map((i) => (
                                <Skeleton key={i} className="h-16 w-full" />
                            ))}
                        </div>
                    ) : !configs || configs.length === 0 ? (
                        <div className="text-center py-10">
                            <FileSpreadsheet className="h-12 w-12 mx-auto text-muted-foreground/50 mb-4" />
                            <h3 className="text-lg font-medium mb-2">
                                Keine Konfigurationen vorhanden
                            </h3>
                            <p className="text-sm text-muted-foreground mb-4">
                                Erstellen Sie Ihre erste DATEV-Konfiguration, um Buchungsstapel
                                exportieren zu können.
                            </p>
                            <Button onClick={handleCreate}>
                                <Plus className="mr-2 h-4 w-4" />
                                Erste Konfiguration erstellen
                            </Button>
                        </div>
                    ) : (
                        <Table>
                            <TableHeader>
                                <TableRow>
                                    <TableHead>Beraternummer</TableHead>
                                    <TableHead>Mandantennummer</TableHead>
                                    <TableHead>Kontenrahmen</TableHead>
                                    <TableHead>WJ-Beginn</TableHead>
                                    <TableHead>Status</TableHead>
                                    <TableHead className="w-[70px]"></TableHead>
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {configs.map((config) => (
                                    <TableRow key={config.id}>
                                        <TableCell className="font-mono">
                                            {config.berater_nr}
                                        </TableCell>
                                        <TableCell className="font-mono">
                                            {config.mandanten_nr}
                                        </TableCell>
                                        <TableCell>
                                            <Badge variant="outline">
                                                {formatKontenrahmen(config.kontenrahmen)}
                                            </Badge>
                                        </TableCell>
                                        <TableCell>{formatDate(config.wj_beginn)}</TableCell>
                                        <TableCell>
                                            {config.is_default && (
                                                <Badge className="bg-yellow-100 text-yellow-800 hover:bg-yellow-100">
                                                    <Star className="h-3 w-3 mr-1 fill-current" />
                                                    Standard
                                                </Badge>
                                            )}
                                        </TableCell>
                                        <TableCell>
                                            <DropdownMenu>
                                                <DropdownMenuTrigger asChild>
                                                    <Button variant="ghost" size="icon">
                                                        <MoreHorizontal className="h-4 w-4" />
                                                        <span className="sr-only">Aktionen</span>
                                                    </Button>
                                                </DropdownMenuTrigger>
                                                <DropdownMenuContent align="end">
                                                    <DropdownMenuItem
                                                        onClick={() => handleEdit(config)}
                                                    >
                                                        <Pencil className="mr-2 h-4 w-4" />
                                                        Bearbeiten
                                                    </DropdownMenuItem>
                                                    {!config.is_default && (
                                                        <DropdownMenuItem
                                                            onClick={() => handleSetDefault(config)}
                                                        >
                                                            <Star className="mr-2 h-4 w-4" />
                                                            Als Standard setzen
                                                        </DropdownMenuItem>
                                                    )}
                                                    <DropdownMenuItem
                                                        onClick={() => setDeleteConfirm(config)}
                                                        className="text-destructive focus:text-destructive"
                                                    >
                                                        <Trash2 className="mr-2 h-4 w-4" />
                                                        Löschen
                                                    </DropdownMenuItem>
                                                </DropdownMenuContent>
                                            </DropdownMenu>
                                        </TableCell>
                                    </TableRow>
                                ))}
                            </TableBody>
                        </Table>
                    )}
                </CardContent>
            </Card>

            {/* Konfigurations-Dialog */}
            <ConfigDialog
                open={dialogOpen}
                onOpenChange={handleDialogClose}
                config={editingConfig}
            />

            {/* Loesch-Bestätigung */}
            <AlertDialog open={!!deleteConfirm} onOpenChange={() => setDeleteConfirm(null)}>
                <AlertDialogContent>
                    <AlertDialogHeader>
                        <AlertDialogTitle>Konfiguration löschen?</AlertDialogTitle>
                        <AlertDialogDescription>
                            {deleteConfirm?.is_default && (
                                <span className="block mb-2 text-destructive font-medium">
                                    Achtung: Dies ist Ihre Standard-Konfiguration!
                                </span>
                            )}
                            Möchten Sie die Konfiguration für Berater {deleteConfirm?.berater_nr}{' '}
                            / Mandant {deleteConfirm?.mandanten_nr} wirklich löschen? Diese Aktion
                            kann nicht rückgängig gemacht werden.
                        </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                        <AlertDialogCancel>Abbrechen</AlertDialogCancel>
                        <AlertDialogAction
                            onClick={handleDelete}
                            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                        >
                            Löschen
                        </AlertDialogAction>
                    </AlertDialogFooter>
                </AlertDialogContent>
            </AlertDialog>
        </div>
    );
}
