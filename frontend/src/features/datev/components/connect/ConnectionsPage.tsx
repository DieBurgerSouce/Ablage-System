/**
 * DATEV Connect - Verbindungs-Verwaltung
 *
 * Listet alle DATEVconnect Verbindungen auf und ermöglicht OAuth2-Anbindung.
 */

import { useState } from 'react';
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
    DropdownMenuSeparator,
    DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
    Plus,
    MoreHorizontal,
    Pencil,
    Trash2,
    Link2,
    Link2Off,
    RefreshCw,
    TestTube,
    CheckCircle,
    XCircle,
    Clock,
    AlertTriangle,
} from 'lucide-react';
import { useToast } from '@/components/ui/use-toast';
import {
    useConnections,
    useDeleteConnection,
    useStartOAuth2,
    useRevokeConnection,
    useTestConnection,
    useRefreshOAuth2Token,
} from '@/features/datev/hooks/use-datev-connect-queries';
import {
    formatConnectionStatus,
    getConnectionStatusVariant,
    type DATEVConnectionResponse,
    type DATEVConnectionStatus,
} from '@/lib/api/services/datev-connect';
import { ConnectionDialog } from './ConnectionDialog';

export function ConnectionsPage() {
    const { data: connections, isLoading, error } = useConnections();
    const deleteConnection = useDeleteConnection();
    const startOAuth2 = useStartOAuth2();
    const revokeConnection = useRevokeConnection();
    const testConnection = useTestConnection();
    const refreshToken = useRefreshOAuth2Token();
    const { toast } = useToast();

    const [dialogOpen, setDialogOpen] = useState(false);
    const [editingConnection, setEditingConnection] = useState<DATEVConnectionResponse | null>(null);
    const [deleteConfirm, setDeleteConfirm] = useState<DATEVConnectionResponse | null>(null);
    const [revokeConfirm, setRevokeConfirm] = useState<DATEVConnectionResponse | null>(null);

    const handleCreate = () => {
        setEditingConnection(null);
        setDialogOpen(true);
    };

    const handleEdit = (connection: DATEVConnectionResponse) => {
        setEditingConnection(connection);
        setDialogOpen(true);
    };

    const handleDelete = async () => {
        if (deleteConfirm) {
            try {
                await deleteConnection.mutateAsync(deleteConfirm.id);
                setDeleteConfirm(null);
                toast({
                    title: 'Verbindung gelöscht',
                    description: 'Die DATEV-Verbindung wurde erfolgreich entfernt.',
                });
            } catch {
                toast({
                    title: 'Löschen fehlgeschlagen',
                    description: 'Die Verbindung konnte nicht gelöscht werden.',
                    variant: 'destructive',
                });
            }
        }
    };

    const handleConnect = async (connection: DATEVConnectionResponse) => {
        try {
            await startOAuth2.mutateAsync(connection.id);
            // Redirect erfolgt automatisch in der Mutation
        } catch {
            toast({
                title: 'Verbindung fehlgeschlagen',
                description: 'Die OAuth2-Autorisierung konnte nicht gestartet werden.',
                variant: 'destructive',
            });
        }
    };

    const handleRevoke = async () => {
        if (revokeConfirm) {
            try {
                await revokeConnection.mutateAsync(revokeConfirm.id);
                setRevokeConfirm(null);
                toast({
                    title: 'Verbindung getrennt',
                    description: 'Die DATEV-Verbindung wurde widerrufen.',
                });
            } catch {
                toast({
                    title: 'Trennen fehlgeschlagen',
                    description: 'Die Verbindung konnte nicht getrennt werden.',
                    variant: 'destructive',
                });
            }
        }
    };

    const handleTest = async (connection: DATEVConnectionResponse) => {
        try {
            const result = await testConnection.mutateAsync(connection.id);
            toast({
                title: result.success ? 'Verbindung erfolgreich' : 'Verbindung fehlgeschlagen',
                description: result.message,
                variant: result.success ? 'default' : 'destructive',
            });
        } catch {
            toast({
                title: 'Test fehlgeschlagen',
                description: 'Der Verbindungstest konnte nicht durchgeführt werden.',
                variant: 'destructive',
            });
        }
    };

    const handleRefreshToken = async (connection: DATEVConnectionResponse) => {
        try {
            await refreshToken.mutateAsync(connection.id);
            toast({
                title: 'Token aktualisiert',
                description: 'Das OAuth2-Token wurde erfolgreich erneuert.',
            });
        } catch {
            toast({
                title: 'Token-Aktualisierung fehlgeschlagen',
                description: 'Das Token konnte nicht erneuert werden. Bitte verbinden Sie sich erneut.',
                variant: 'destructive',
            });
        }
    };

    const getStatusIcon = (status: DATEVConnectionStatus) => {
        switch (status) {
            case 'connected':
                return <CheckCircle className="h-4 w-4 text-green-600" />;
            case 'pending':
                return <Clock className="h-4 w-4 text-yellow-600" />;
            case 'expired':
                return <AlertTriangle className="h-4 w-4 text-orange-600" />;
            case 'error':
            case 'revoked':
                return <XCircle className="h-4 w-4 text-red-600" />;
            default:
                return null;
        }
    };

    if (error) {
        return (
            <Card>
                <CardContent className="py-10 text-center text-muted-foreground">
                    Fehler beim Laden der Verbindungen.
                </CardContent>
            </Card>
        );
    }

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
                <div>
                    <h2 className="text-xl font-semibold">DATEVconnect Verbindungen</h2>
                    <p className="text-sm text-muted-foreground">
                        Verwalten Sie Ihre Verbindungen zur DATEVconnect API.
                    </p>
                </div>
                <Button onClick={handleCreate}>
                    <Plus className="mr-2 h-4 w-4" />
                    Neue Verbindung
                </Button>
            </div>

            {/* Verbindungsliste */}
            <Card>
                <CardHeader>
                    <CardTitle className="text-base">Alle Verbindungen</CardTitle>
                    <CardDescription>
                        {isLoading
                            ? 'Lade...'
                            : `${connections?.length || 0} Verbindung${(connections?.length || 0) !== 1 ? 'en' : ''}`}
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    {isLoading ? (
                        <div className="space-y-3">
                            {[1, 2, 3].map((i) => (
                                <Skeleton key={i} className="h-16 w-full" />
                            ))}
                        </div>
                    ) : !connections || connections.length === 0 ? (
                        <div className="text-center py-10">
                            <Link2 className="h-12 w-12 mx-auto text-muted-foreground/50 mb-4" />
                            <h3 className="text-lg font-medium mb-2">
                                Keine Verbindungen vorhanden
                            </h3>
                            <p className="text-sm text-muted-foreground mb-4">
                                Erstellen Sie Ihre erste DATEVconnect Verbindung, um
                                Buchungen direkt mit DATEV zu synchronisieren.
                            </p>
                            <Button onClick={handleCreate}>
                                <Plus className="mr-2 h-4 w-4" />
                                Erste Verbindung erstellen
                            </Button>
                        </div>
                    ) : (
                        <Table>
                            <TableHeader>
                                <TableRow>
                                    <TableHead>Name</TableHead>
                                    <TableHead>Mandant</TableHead>
                                    <TableHead>Berater</TableHead>
                                    <TableHead>Kontenrahmen</TableHead>
                                    <TableHead>Status</TableHead>
                                    <TableHead>Letzter Sync</TableHead>
                                    <TableHead className="w-[70px]"></TableHead>
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {connections.map((conn) => (
                                    <TableRow key={conn.id}>
                                        <TableCell className="font-medium">
                                            {conn.name}
                                        </TableCell>
                                        <TableCell className="font-mono">
                                            {conn.mandant_nr}
                                        </TableCell>
                                        <TableCell className="font-mono">
                                            {conn.berater_nr}
                                        </TableCell>
                                        <TableCell>
                                            <Badge variant="outline">{conn.kontenrahmen}</Badge>
                                        </TableCell>
                                        <TableCell>
                                            <div className="flex items-center gap-2">
                                                {getStatusIcon(conn.status)}
                                                <Badge variant={getConnectionStatusVariant(conn.status)}>
                                                    {formatConnectionStatus(conn.status)}
                                                </Badge>
                                            </div>
                                        </TableCell>
                                        <TableCell className="text-muted-foreground">
                                            {conn.last_sync_at
                                                ? new Date(conn.last_sync_at).toLocaleString('de-DE')
                                                : '–'}
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
                                                    {conn.status === 'pending' && (
                                                        <DropdownMenuItem
                                                            onClick={() => handleConnect(conn)}
                                                        >
                                                            <Link2 className="mr-2 h-4 w-4" />
                                                            Mit DATEV verbinden
                                                        </DropdownMenuItem>
                                                    )}
                                                    {conn.status === 'expired' && (
                                                        <DropdownMenuItem
                                                            onClick={() => handleRefreshToken(conn)}
                                                        >
                                                            <RefreshCw className="mr-2 h-4 w-4" />
                                                            Token erneuern
                                                        </DropdownMenuItem>
                                                    )}
                                                    {conn.status === 'connected' && (
                                                        <>
                                                            <DropdownMenuItem
                                                                onClick={() => handleTest(conn)}
                                                            >
                                                                <TestTube className="mr-2 h-4 w-4" />
                                                                Verbindung testen
                                                            </DropdownMenuItem>
                                                            <DropdownMenuItem
                                                                onClick={() => setRevokeConfirm(conn)}
                                                                className="text-orange-600"
                                                            >
                                                                <Link2Off className="mr-2 h-4 w-4" />
                                                                Verbindung trennen
                                                            </DropdownMenuItem>
                                                            <DropdownMenuSeparator />
                                                        </>
                                                    )}
                                                    <DropdownMenuItem onClick={() => handleEdit(conn)}>
                                                        <Pencil className="mr-2 h-4 w-4" />
                                                        Bearbeiten
                                                    </DropdownMenuItem>
                                                    <DropdownMenuItem
                                                        onClick={() => setDeleteConfirm(conn)}
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

            {/* Verbindungs-Dialog */}
            <ConnectionDialog
                open={dialogOpen}
                onOpenChange={setDialogOpen}
                connection={editingConnection}
            />

            {/* Loesch-Bestätigung */}
            <AlertDialog open={!!deleteConfirm} onOpenChange={() => setDeleteConfirm(null)}>
                <AlertDialogContent>
                    <AlertDialogHeader>
                        <AlertDialogTitle>Verbindung löschen?</AlertDialogTitle>
                        <AlertDialogDescription>
                            Möchten Sie die Verbindung "{deleteConfirm?.name}" wirklich löschen?
                            Diese Aktion kann nicht rückgängig gemacht werden.
                            Alle zugehörigen Buchungen und Sync-Daten werden ebenfalls entfernt.
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

            {/* Widerrufs-Bestätigung */}
            <AlertDialog open={!!revokeConfirm} onOpenChange={() => setRevokeConfirm(null)}>
                <AlertDialogContent>
                    <AlertDialogHeader>
                        <AlertDialogTitle>Verbindung trennen?</AlertDialogTitle>
                        <AlertDialogDescription>
                            Möchten Sie die Verbindung "{revokeConfirm?.name}" wirklich trennen?
                            Sie müssen sich anschließend erneut mit DATEV verbinden,
                            um Synchronisierungen durchzuführen.
                        </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                        <AlertDialogCancel>Abbrechen</AlertDialogCancel>
                        <AlertDialogAction
                            onClick={handleRevoke}
                            className="bg-orange-600 text-white hover:bg-orange-700"
                        >
                            Verbindung trennen
                        </AlertDialogAction>
                    </AlertDialogFooter>
                </AlertDialogContent>
            </AlertDialog>
        </div>
    );
}
