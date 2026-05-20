/**
 * EmailConfigList Component
 *
 * Zeigt Liste aller Email-Import-Konfigurationen mit Status und Aktionen.
 */

import { useState } from 'react';
import { formatDistanceToNow } from 'date-fns';
import { de } from 'date-fns/locale';
import {
  Mail,
  RefreshCw,
  Settings,
  Trash2,
  Play,
  CheckCircle,
  XCircle,
  AlertCircle,
  Loader2,
  Plus,
} from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
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
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { useToast } from '@/components/ui/use-toast';

import {
  useEmailConfigs,
  useDeleteEmailConfig,
  useTestEmailConnection,
  useTriggerEmailSync,
} from '../hooks/use-import-queries';
import type { EmailConfigListItem, ConnectionStatus } from '../types/import-types';

// ==================== Status Badge ====================

interface ConnectionStatusBadgeProps {
  status: ConnectionStatus;
}

function ConnectionStatusBadge({ status }: ConnectionStatusBadgeProps) {
  const statusConfig = {
    connected: {
      label: 'Verbunden',
      variant: 'default' as const,
      icon: CheckCircle,
      className: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200',
    },
    disconnected: {
      label: 'Getrennt',
      variant: 'secondary' as const,
      icon: XCircle,
      className: 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200',
    },
    error: {
      label: 'Fehler',
      variant: 'destructive' as const,
      icon: AlertCircle,
      className: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200',
    },
    unknown: {
      label: 'Unbekannt',
      variant: 'outline' as const,
      icon: AlertCircle,
      className: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200',
    },
  };

  const config = statusConfig[status] || statusConfig.unknown;
  const Icon = config.icon;

  return (
    <Badge variant={config.variant} className={config.className}>
      <Icon className="mr-1 h-3 w-3" />
      {config.label}
    </Badge>
  );
}

// ==================== Main Component ====================

interface EmailConfigListProps {
  onCreateNew?: () => void;
  onEdit?: (configId: string) => void;
}

export function EmailConfigList({ onCreateNew, onEdit }: EmailConfigListProps) {
  const { toast } = useToast();
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);

  // Queries
  const { data: configs, isLoading, error, refetch } = useEmailConfigs();

  // Mutations
  const deleteConfig = useDeleteEmailConfig();
  const testConnection = useTestEmailConnection();
  const triggerSync = useTriggerEmailSync();

  // Handlers
  const handleTestConnection = async (configId: string, configName: string) => {
    try {
      const result = await testConnection.mutateAsync(configId);
      toast({
        title: result.success ? 'Verbindung erfolgreich' : 'Verbindung fehlgeschlagen',
        description: result.message,
        variant: result.success ? 'default' : 'destructive',
      });
    } catch (err) {
      toast({
        title: 'Fehler beim Verbindungstest',
        description: err instanceof Error ? err.message : 'Unbekannter Fehler',
        variant: 'destructive',
      });
    }
  };

  const handleTriggerSync = async (configId: string, configName: string) => {
    try {
      await triggerSync.mutateAsync(configId);
      toast({
        title: 'Synchronisierung gestartet',
        description: `Email-Sync für "${configName}" wurde gestartet.`,
      });
    } catch (err) {
      toast({
        title: 'Fehler beim Starten der Synchronisierung',
        description: err instanceof Error ? err.message : 'Unbekannter Fehler',
        variant: 'destructive',
      });
    }
  };

  const handleDelete = async (configId: string) => {
    try {
      await deleteConfig.mutateAsync(configId);
      toast({
        title: 'Konfiguration gelöscht',
        description: 'Die Email-Konfiguration wurde erfolgreich gelöscht.',
      });
      setDeleteConfirmId(null);
    } catch (err) {
      toast({
        title: 'Fehler beim Löschen',
        description: err instanceof Error ? err.message : 'Unbekannter Fehler',
        variant: 'destructive',
      });
    }
  };

  // Loading State
  if (isLoading) {
    return (
      <Card>
        <CardContent className="flex items-center justify-center py-8">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          <span className="ml-2 text-muted-foreground">Lade Email-Konfigurationen...</span>
        </CardContent>
      </Card>
    );
  }

  // Error State
  if (error) {
    return (
      <Card>
        <CardContent className="flex flex-col items-center justify-center py-8 text-destructive">
          <AlertCircle className="h-8 w-8 mb-2" />
          <p>Fehler beim Laden der Konfigurationen</p>
          <Button variant="outline" size="sm" className="mt-4" onClick={() => refetch()}>
            Erneut versuchen
          </Button>
        </CardContent>
      </Card>
    );
  }

  // Empty State
  if (!configs || configs.length === 0) {
    return (
      <Card>
        <CardContent className="flex flex-col items-center justify-center py-12">
          <Mail className="h-12 w-12 text-muted-foreground mb-4" />
          <h3 className="text-lg font-medium mb-2">Keine Email-Konfigurationen</h3>
          <p className="text-muted-foreground text-center mb-4">
            Erstellen Sie eine neue Konfiguration, um Emails automatisch zu importieren.
          </p>
          {onCreateNew && (
            <Button onClick={onCreateNew}>
              <Plus className="mr-2 h-4 w-4" />
              Neue Konfiguration
            </Button>
          )}
        </CardContent>
      </Card>
    );
  }

  return (
    <>
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <div>
            <CardTitle className="flex items-center gap-2">
              <Mail className="h-5 w-5" />
              Email-Import-Konfigurationen
            </CardTitle>
            <CardDescription>
              {configs.length} Konfiguration{configs.length !== 1 ? 'en' : ''} eingerichtet
            </CardDescription>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={() => refetch()}>
              <RefreshCw className="h-4 w-4" />
            </Button>
            {onCreateNew && (
              <Button onClick={onCreateNew}>
                <Plus className="mr-2 h-4 w-4" />
                Neu
              </Button>
            )}
          </div>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Server</TableHead>
                <TableHead>Ordner</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Letzte Sync</TableHead>
                <TableHead className="text-right">Dokumente</TableHead>
                <TableHead className="w-[150px]">Aktionen</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {configs.map((config) => (
                <TableRow key={config.id}>
                  <TableCell className="font-medium">
                    <div className="flex items-center gap-2">
                      {config.name}
                      {!config.isActive && (
                        <Badge variant="secondary" className="text-xs">
                          Inaktiv
                        </Badge>
                      )}
                    </div>
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {config.imapServer}
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {config.imapFolder}
                  </TableCell>
                  <TableCell>
                    <ConnectionStatusBadge status={config.connectionStatus} />
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {config.lastSyncAt
                      ? formatDistanceToNow(new Date(config.lastSyncAt), {
                          addSuffix: true,
                          locale: de,
                        })
                      : 'Nie'}
                  </TableCell>
                  <TableCell className="text-right font-mono">
                    {config.totalDocumentsCreated.toLocaleString('de-DE')}
                  </TableCell>
                  <TableCell>
                    <TooltipProvider>
                      <div className="flex items-center gap-1">
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <Button
                              variant="ghost"
                              size="icon"
                              onClick={() => handleTestConnection(config.id, config.name)}
                              disabled={testConnection.isPending}
                            >
                              {testConnection.isPending ? (
                                <Loader2 className="h-4 w-4 animate-spin" />
                              ) : (
                                <CheckCircle className="h-4 w-4" />
                              )}
                            </Button>
                          </TooltipTrigger>
                          <TooltipContent>Verbindung testen</TooltipContent>
                        </Tooltip>

                        <Tooltip>
                          <TooltipTrigger asChild>
                            <Button
                              variant="ghost"
                              size="icon"
                              onClick={() => handleTriggerSync(config.id, config.name)}
                              disabled={triggerSync.isPending || !config.isActive}
                            >
                              {triggerSync.isPending ? (
                                <Loader2 className="h-4 w-4 animate-spin" />
                              ) : (
                                <Play className="h-4 w-4" />
                              )}
                            </Button>
                          </TooltipTrigger>
                          <TooltipContent>Sync starten</TooltipContent>
                        </Tooltip>

                        <Tooltip>
                          <TooltipTrigger asChild>
                            <Button
                              variant="ghost"
                              size="icon"
                              onClick={() => onEdit?.(config.id)}
                            >
                              <Settings className="h-4 w-4" />
                            </Button>
                          </TooltipTrigger>
                          <TooltipContent>Bearbeiten</TooltipContent>
                        </Tooltip>

                        <Tooltip>
                          <TooltipTrigger asChild>
                            <Button
                              variant="ghost"
                              size="icon"
                              className="text-destructive hover:text-destructive"
                              onClick={() => setDeleteConfirmId(config.id)}
                            >
                              <Trash2 className="h-4 w-4" />
                            </Button>
                          </TooltipTrigger>
                          <TooltipContent>Löschen</TooltipContent>
                        </Tooltip>
                      </div>
                    </TooltipProvider>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* Delete Confirmation Dialog */}
      <AlertDialog
        open={deleteConfirmId !== null}
        onOpenChange={(open) => !open && setDeleteConfirmId(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Konfiguration löschen?</AlertDialogTitle>
            <AlertDialogDescription>
              Diese Aktion kann nicht rückgängig gemacht werden. Die Konfiguration
              und alle zugehörigen Einstellungen werden dauerhaft gelöscht.
              Bereits importierte Dokumente bleiben erhalten.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Abbrechen</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => deleteConfirmId && handleDelete(deleteConfirmId)}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {deleteConfig.isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Trash2 className="mr-2 h-4 w-4" />
              )}
              Löschen
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
