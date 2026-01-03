/**
 * ERP Connections Admin Page
 *
 * Hauptseite fuer ERP-Verbindungsverwaltung.
 */

import { useState } from 'react';
import {
  Plus,
  RefreshCw,
  Settings,
  Trash2,
  Play,
  AlertTriangle,
  CheckCircle,
  XCircle,
  Clock,
  Loader2,
} from 'lucide-react';

import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
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
  useERPConnections,
  useDeleteConnection,
  useTestConnection,
  useTriggerSync,
  useERPStats,
} from '../hooks/useERP';
import type { ERPConnection, ERPConnectionStatus } from '../types';
import { ERPConnectionDialog } from './ERPConnectionDialog';
import { ERPStatsCards } from './ERPStatsCards';

// =============================================================================
// Status Badge Component
// =============================================================================

function ConnectionStatusBadge({ status }: { status: ERPConnectionStatus }) {
  const variants: Record<ERPConnectionStatus, { variant: 'default' | 'secondary' | 'destructive' | 'outline'; icon: React.ReactNode }> = {
    connected: { variant: 'default', icon: <CheckCircle className="h-3 w-3" /> },
    disconnected: { variant: 'secondary', icon: <XCircle className="h-3 w-3" /> },
    error: { variant: 'destructive', icon: <AlertTriangle className="h-3 w-3" /> },
    authenticating: { variant: 'outline', icon: <Loader2 className="h-3 w-3 animate-spin" /> },
    rate_limited: { variant: 'destructive', icon: <Clock className="h-3 w-3" /> },
  };

  const labels: Record<ERPConnectionStatus, string> = {
    connected: 'Verbunden',
    disconnected: 'Getrennt',
    error: 'Fehler',
    authenticating: 'Authentifizierung',
    rate_limited: 'Rate-Limit',
  };

  const { variant, icon } = variants[status];

  return (
    <Badge variant={variant} className="gap-1">
      {icon}
      {labels[status]}
    </Badge>
  );
}

// =============================================================================
// ERP Type Badge
// =============================================================================

function ERPTypeBadge({ type }: { type: string }) {
  const colors: Record<string, string> = {
    odoo: 'bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200',
    lexware: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200',
    sap_b1: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200',
    custom: 'bg-gray-100 text-gray-800 dark:bg-gray-900 dark:text-gray-200',
  };

  const labels: Record<string, string> = {
    odoo: 'Odoo',
    lexware: 'Lexware',
    sap_b1: 'SAP B1',
    custom: 'Custom',
  };

  return (
    <span className={`inline-flex items-center px-2 py-1 rounded text-xs font-medium ${colors[type] || colors.custom}`}>
      {labels[type] || type}
    </span>
  );
}

// =============================================================================
// Main Component
// =============================================================================

export function ERPConnectionsPage() {
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingConnection, setEditingConnection] = useState<ERPConnection | null>(null);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [connectionToDelete, setConnectionToDelete] = useState<ERPConnection | null>(null);

  const { data: connections, isLoading, refetch } = useERPConnections();
  const { data: stats } = useERPStats();
  const deleteConnection = useDeleteConnection();
  const testConnection = useTestConnection();
  const triggerSync = useTriggerSync();

  const handleEdit = (connection: ERPConnection) => {
    setEditingConnection(connection);
    setDialogOpen(true);
  };

  const handleDelete = (connection: ERPConnection) => {
    setConnectionToDelete(connection);
    setDeleteDialogOpen(true);
  };

  const confirmDelete = async () => {
    if (connectionToDelete) {
      await deleteConnection.mutateAsync(connectionToDelete.id);
      setDeleteDialogOpen(false);
      setConnectionToDelete(null);
    }
  };

  const handleTest = (connectionId: string) => {
    testConnection.mutate(connectionId);
  };

  const handleSync = (connectionId: string, syncType: 'full' | 'delta') => {
    triggerSync.mutate({ connectionId, syncType });
  };

  const formatDate = (dateString: string | null) => {
    if (!dateString) return '-';
    return new Date(dateString).toLocaleString('de-DE', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">ERP-Integrationen</h1>
          <p className="text-muted-foreground">
            Verwalten Sie Ihre ERP-Systemverbindungen und Synchronisation
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => refetch()}>
            <RefreshCw className="h-4 w-4 mr-2" />
            Aktualisieren
          </Button>
          <Button onClick={() => {
            setEditingConnection(null);
            setDialogOpen(true);
          }}>
            <Plus className="h-4 w-4 mr-2" />
            Neue Verbindung
          </Button>
        </div>
      </div>

      {/* Stats Cards */}
      {stats && <ERPStatsCards stats={stats} />}

      {/* Connections Table */}
      <Card>
        <CardHeader>
          <CardTitle>ERP-Verbindungen</CardTitle>
          <CardDescription>
            Alle konfigurierten ERP-Systemverbindungen
          </CardDescription>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
          ) : !connections?.length ? (
            <div className="text-center py-8 text-muted-foreground">
              <p>Keine ERP-Verbindungen konfiguriert</p>
              <Button
                variant="link"
                onClick={() => {
                  setEditingConnection(null);
                  setDialogOpen(true);
                }}
              >
                Erste Verbindung erstellen
              </Button>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Typ</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Letzte Sync</TableHead>
                  <TableHead>Naechste Sync</TableHead>
                  <TableHead className="text-right">Aktionen</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {connections.map((connection) => (
                  <TableRow key={connection.id}>
                    <TableCell>
                      <div>
                        <div className="font-medium">{connection.name}</div>
                        <div className="text-sm text-muted-foreground">
                          {connection.url}
                        </div>
                      </div>
                    </TableCell>
                    <TableCell>
                      <ERPTypeBadge type={connection.erp_type} />
                    </TableCell>
                    <TableCell>
                      <ConnectionStatusBadge status={connection.connection_status} />
                    </TableCell>
                    <TableCell>{formatDate(connection.last_sync_at)}</TableCell>
                    <TableCell>{formatDate(connection.next_scheduled_sync)}</TableCell>
                    <TableCell className="text-right">
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="sm">
                            <Settings className="h-4 w-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem onClick={() => handleTest(connection.id)}>
                            <CheckCircle className="h-4 w-4 mr-2" />
                            Verbindung testen
                          </DropdownMenuItem>
                          <DropdownMenuItem onClick={() => handleSync(connection.id, 'delta')}>
                            <Play className="h-4 w-4 mr-2" />
                            Delta-Sync starten
                          </DropdownMenuItem>
                          <DropdownMenuItem onClick={() => handleSync(connection.id, 'full')}>
                            <RefreshCw className="h-4 w-4 mr-2" />
                            Voll-Sync starten
                          </DropdownMenuItem>
                          <DropdownMenuSeparator />
                          <DropdownMenuItem onClick={() => handleEdit(connection)}>
                            <Settings className="h-4 w-4 mr-2" />
                            Bearbeiten
                          </DropdownMenuItem>
                          <DropdownMenuItem
                            className="text-destructive"
                            onClick={() => handleDelete(connection)}
                          >
                            <Trash2 className="h-4 w-4 mr-2" />
                            Loeschen
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

      {/* Connection Dialog */}
      <ERPConnectionDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        connection={editingConnection}
      />

      {/* Delete Confirmation Dialog */}
      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Verbindung loeschen?</AlertDialogTitle>
            <AlertDialogDescription>
              Sind Sie sicher, dass Sie die Verbindung "{connectionToDelete?.name}"
              loeschen moechten? Alle zugehoerigen Sync-Historie und Konflikte werden
              ebenfalls geloescht.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Abbrechen</AlertDialogCancel>
            <AlertDialogAction
              onClick={confirmDelete}
              className="bg-destructive text-destructive-foreground"
            >
              Loeschen
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
