/**
 * FolderConfigList Component
 *
 * Zeigt Liste aller Ordner-Import-Konfigurationen mit Status und Aktionen.
 */

import { useState } from 'react';
import { formatDistanceToNow } from 'date-fns';
import { de } from 'date-fns/locale';
import {
  Folder,
  RefreshCw,
  Settings,
  Trash2,
  Play,
  Pause,
  CheckCircle,
  XCircle,
  AlertCircle,
  Loader2,
  Plus,
  FolderOpen,
  Eye,
  EyeOff,
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
  useFolderConfigs,
  useDeleteFolderConfig,
  useTriggerFolderPoll,
} from '../hooks/use-import-queries';
import type { FolderConfigListItem } from '../types/import-types';

// ==================== Status Badge ====================

interface WatchStatusBadgeProps {
  isWatching: boolean;
  isActive: boolean;
}

function WatchStatusBadge({ isWatching, isActive }: WatchStatusBadgeProps) {
  if (!isActive) {
    return (
      <Badge variant="secondary" className="bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200">
        <EyeOff className="mr-1 h-3 w-3" />
        Inaktiv
      </Badge>
    );
  }

  if (isWatching) {
    return (
      <Badge variant="default" className="bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200">
        <Eye className="mr-1 h-3 w-3" />
        Überwacht
      </Badge>
    );
  }

  return (
    <Badge variant="outline" className="bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200">
      <AlertCircle className="mr-1 h-3 w-3" />
      Gestoppt
    </Badge>
  );
}

// ==================== Main Component ====================

interface FolderConfigListProps {
  onCreateNew?: () => void;
  onEdit?: (configId: string) => void;
}

export function FolderConfigList({ onCreateNew, onEdit }: FolderConfigListProps) {
  const { toast } = useToast();
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);

  // Queries
  const { data: configs, isLoading, error, refetch } = useFolderConfigs();

  // Mutations
  const deleteConfig = useDeleteFolderConfig();
  const triggerScan = useTriggerFolderPoll();

  // Handlers
  const handleTriggerScan = async (configId: string, configName: string) => {
    try {
      await triggerScan.mutateAsync(configId);
      toast({
        title: 'Ordner-Scan gestartet',
        description: `Der Scan für "${configName}" wurde gestartet.`,
      });
    } catch (err) {
      toast({
        title: 'Fehler beim Starten des Scans',
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
        description: 'Die Ordner-Konfiguration wurde erfolgreich gelöscht.',
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
          <span className="ml-2 text-muted-foreground">Lade Ordner-Konfigurationen...</span>
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
          <Folder className="h-12 w-12 text-muted-foreground mb-4" />
          <h3 className="text-lg font-medium mb-2">Keine Ordner-Konfigurationen</h3>
          <p className="text-muted-foreground text-center mb-4">
            Erstellen Sie eine neue Konfiguration, um Ordner automatisch zu überwachen.
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
              <FolderOpen className="h-5 w-5" />
              Ordner-Import-Konfigurationen
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
                <TableHead>Pfad</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Letzter Scan</TableHead>
                <TableHead className="text-right">Dokumente</TableHead>
                <TableHead className="w-[120px]">Aktionen</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {configs.map((config) => (
                <TableRow key={config.id}>
                  <TableCell className="font-medium">
                    <div className="flex items-center gap-2">
                      {config.name}
                      {config.includeSubfolders && (
                        <Badge variant="outline" className="text-xs">
                          Unterordner
                        </Badge>
                      )}
                    </div>
                  </TableCell>
                  <TableCell className="text-muted-foreground font-mono text-sm max-w-[200px] truncate">
                    <TooltipProvider>
                      <Tooltip>
                        <TooltipTrigger className="truncate block">
                          {config.folderPath}
                        </TooltipTrigger>
                        <TooltipContent side="bottom" className="max-w-md">
                          <p className="break-all">{config.folderPath}</p>
                        </TooltipContent>
                      </Tooltip>
                    </TooltipProvider>
                  </TableCell>
                  <TableCell>
                    <WatchStatusBadge
                      isWatching={config.isWatching}
                      isActive={config.isActive}
                    />
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {config.lastScanAt
                      ? formatDistanceToNow(new Date(config.lastScanAt), {
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
                              onClick={() => handleTriggerScan(config.id, config.name)}
                              disabled={triggerScan.isPending || !config.isActive}
                            >
                              {triggerScan.isPending ? (
                                <Loader2 className="h-4 w-4 animate-spin" />
                              ) : (
                                <Play className="h-4 w-4" />
                              )}
                            </Button>
                          </TooltipTrigger>
                          <TooltipContent>Scan starten</TooltipContent>
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
