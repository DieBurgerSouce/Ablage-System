/**
 * DATEV Lieferanten-Zuordnungen Seite
 *
 * Verwaltet Vendor-spezifische Kontenzuordnungen.
 */

import { useState, useRef } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
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
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select';
import { Plus, MoreHorizontal, Pencil, Trash2, AlertCircle, Users } from 'lucide-react';
import {
    useConfigs,
    useVendorMappings,
    useDeleteVendorMapping,
} from '@/features/datev/hooks/use-datev-queries';
import { formatVatId, formatIban, truncateText } from '@/features/datev/utils';
import { VendorMappingDialog } from './VendorMappingDialog';
import type { DATEVVendorMappingResponse } from '@/lib/api/services/datev';

export function VendorsPage() {
    const { data: configs, isLoading: configsLoading } = useConfigs();
    const [selectedConfigId, setSelectedConfigId] = useState<string>('');

    // Automatisch erste Konfiguration auswählen wenn vorhanden
    const effectiveConfigId =
        selectedConfigId || (configs && configs.length > 0 ? configs[0].id : '');

    const {
        data: mappings,
        isLoading: mappingsLoading,
        error: mappingsError,
    } = useVendorMappings(effectiveConfigId, !!effectiveConfigId);

    const deleteMapping = useDeleteVendorMapping();

    const [dialogOpen, setDialogOpen] = useState(false);
    const [editingMapping, setEditingMapping] = useState<DATEVVendorMappingResponse | null>(null);
    const [deleteConfirm, setDeleteConfirm] = useState<DATEVVendorMappingResponse | null>(null);

    // Refs für Focus Management nach Dialog-Schliessung
    const createButtonRef = useRef<HTMLButtonElement>(null);
    const lastTriggerRef = useRef<'create' | 'edit'>('create');

    const handleCreate = () => {
        if (dialogOpen) return; // Race Condition Guard
        lastTriggerRef.current = 'create';
        setEditingMapping(null);
        setDialogOpen(true);
    };

    const handleEdit = (mapping: DATEVVendorMappingResponse) => {
        if (dialogOpen) return; // Race Condition Guard
        lastTriggerRef.current = 'edit';
        setEditingMapping(mapping);
        setDialogOpen(true);
    };

    // Focus Management: Focus zurück zum Trigger-Button nach Dialog-Close
    const handleDialogClose = (open: boolean) => {
        setDialogOpen(open);
        if (!open && lastTriggerRef.current === 'create') {
            setTimeout(() => createButtonRef.current?.focus(), 0);
        }
    };

    const handleDelete = async () => {
        if (deleteConfirm && effectiveConfigId) {
            try {
                await deleteMapping.mutateAsync({
                    configId: effectiveConfigId,
                    mappingId: deleteConfirm.id,
                });
                setDeleteConfirm(null);
            } catch {
                // Error wird von TanStack Query behandelt - Dialog bleibt offen
            }
        }
    };

    // Keine Konfigurationen vorhanden
    if (!configsLoading && (!configs || configs.length === 0)) {
        return (
            <Alert>
                <AlertCircle className="h-4 w-4" />
                <AlertTitle>Keine Konfiguration vorhanden</AlertTitle>
                <AlertDescription>
                    Bevor Sie Lieferanten-Zuordnungen erstellen können, müssen Sie zuerst eine
                    DATEV-Konfiguration anlegen.
                </AlertDescription>
            </Alert>
        );
    }

    return (
        <div className="space-y-6">
            {/* Header mit Konfigurationsauswahl */}
            <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
                <div>
                    <h2 className="text-xl font-semibold">Lieferanten-Zuordnungen</h2>
                    <p className="text-sm text-muted-foreground">
                        Weisen Sie Lieferanten spezifische Buchungskonten zu.
                    </p>
                </div>

                <div className="flex items-center gap-4">
                    {/* Konfigurationsauswahl */}
                    <div className="flex items-center gap-2">
                        <span className="text-sm text-muted-foreground">Konfiguration:</span>
                        {configsLoading ? (
                            <Skeleton className="h-10 w-48" />
                        ) : (
                            <Select
                                value={effectiveConfigId}
                                onValueChange={setSelectedConfigId}
                            >
                                <SelectTrigger
                                    className="w-48"
                                    aria-label="DATEV-Konfiguration für Vendor-Mappings auswählen"
                                >
                                    <SelectValue placeholder="Konfiguration wählen" />
                                </SelectTrigger>
                                <SelectContent>
                                    {configs?.map((config) => (
                                        <SelectItem key={config.id} value={config.id}>
                                            {config.berater_nr} / {config.mandanten_nr}
                                            {config.is_default && ' (Standard)'}
                                        </SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        )}
                    </div>

                    <Button
                        ref={createButtonRef}
                        onClick={handleCreate}
                        disabled={!effectiveConfigId || configsLoading}
                    >
                        <Plus className="mr-2 h-4 w-4" />
                        Neue Zuordnung
                    </Button>
                </div>
            </div>

            {/* Zuordnungsliste */}
            <Card>
                <CardHeader>
                    <CardTitle className="text-base">Vendor-Mappings</CardTitle>
                    <CardDescription>
                        {mappingsLoading
                            ? 'Lade...'
                            : `${mappings?.length || 0} Zuordnung${(mappings?.length || 0) !== 1 ? 'en' : ''}`}
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    {mappingsLoading ? (
                        <div className="space-y-3">
                            {[1, 2, 3].map((i) => (
                                <Skeleton key={i} className="h-16 w-full" />
                            ))}
                        </div>
                    ) : mappingsError ? (
                        <div className="text-center py-10 text-muted-foreground">
                            Fehler beim Laden der Zuordnungen.
                        </div>
                    ) : !mappings || mappings.length === 0 ? (
                        <div className="text-center py-10">
                            <Users className="h-12 w-12 mx-auto text-muted-foreground/50 mb-4" />
                            <h3 className="text-lg font-medium mb-2">Keine Zuordnungen vorhanden</h3>
                            <p className="text-sm text-muted-foreground mb-4">
                                Erstellen Sie Zuordnungen, um Lieferanten automatisch den richtigen
                                Konten zuzuweisen.
                            </p>
                            <Button onClick={handleCreate}>
                                <Plus className="mr-2 h-4 w-4" />
                                Erste Zuordnung erstellen
                            </Button>
                        </div>
                    ) : (
                        <Table>
                            <TableHeader>
                                <TableRow>
                                    <TableHead>Lieferant</TableHead>
                                    <TableHead>USt-IdNr</TableHead>
                                    <TableHead>IBAN</TableHead>
                                    <TableHead>Aufwandskonto</TableHead>
                                    <TableHead>Kreditorenkonto</TableHead>
                                    <TableHead>Kostenstelle</TableHead>
                                    <TableHead className="w-[70px]"></TableHead>
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {mappings.map((mapping) => (
                                    <TableRow key={mapping.id}>
                                        <TableCell className="font-medium">
                                            {truncateText(mapping.vendor_name, 30)}
                                        </TableCell>
                                        <TableCell className="font-mono text-sm">
                                            {formatVatId(mapping.vendor_vat_id)}
                                        </TableCell>
                                        <TableCell className="font-mono text-sm">
                                            {mapping.vendor_iban
                                                ? truncateText(formatIban(mapping.vendor_iban), 20)
                                                : '–'}
                                        </TableCell>
                                        <TableCell className="font-mono">
                                            {mapping.expense_account}
                                        </TableCell>
                                        <TableCell className="font-mono">
                                            {mapping.creditor_account || '–'}
                                        </TableCell>
                                        <TableCell>{mapping.cost_center || '–'}</TableCell>
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
                                                        onClick={() => handleEdit(mapping)}
                                                    >
                                                        <Pencil className="mr-2 h-4 w-4" />
                                                        Bearbeiten
                                                    </DropdownMenuItem>
                                                    <DropdownMenuItem
                                                        onClick={() => setDeleteConfirm(mapping)}
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

            {/* Vendor-Mapping Dialog */}
            {effectiveConfigId && (
                <VendorMappingDialog
                    open={dialogOpen}
                    onOpenChange={handleDialogClose}
                    configId={effectiveConfigId}
                    mapping={editingMapping}
                />
            )}

            {/* Loesch-Bestätigung */}
            <AlertDialog open={!!deleteConfirm} onOpenChange={() => setDeleteConfirm(null)}>
                <AlertDialogContent>
                    <AlertDialogHeader>
                        <AlertDialogTitle>Zuordnung löschen?</AlertDialogTitle>
                        <AlertDialogDescription>
                            Möchten Sie die Zuordnung für{' '}
                            {deleteConfirm?.vendor_name || deleteConfirm?.vendor_vat_id || 'diesen Lieferanten'}{' '}
                            wirklich löschen? Diese Aktion kann nicht rückgängig gemacht werden.
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
