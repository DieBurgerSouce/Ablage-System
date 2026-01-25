/**
 * Backup Validation Panel
 *
 * Zeigt Backup-Integritäts-Checks und Validierungsergebnisse.
 */

import { useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Alert, AlertDescription } from '@/components/ui/alert';
import {
  CheckCircle2,
  XCircle,
  Shield,
  RefreshCw,
  AlertTriangle,
  FileCheck,
  Lock,
  Calendar,
} from 'lucide-react';
import { format } from 'date-fns';
import { de } from 'date-fns/locale';
import type { Backup } from '../api';

interface BackupValidationPanelProps {
  backups: Backup[];
  isLoading: boolean;
  onValidate: (backupName: string) => void;
  onValidateAll: () => void;
  isValidating: boolean;
}

const formatDate = (dateStr: string) => {
  try {
    return format(new Date(dateStr), 'dd.MM.yyyy HH:mm', { locale: de });
  } catch {
    return dateStr;
  }
};

const formatSize = (bytes: number) => {
  const gb = bytes / (1024 * 1024 * 1024);
  return `${gb.toFixed(2)} GB`;
};

const getTypeBadge = (typ: Backup['typ']) => {
  const typeConfig: Record<
    Backup['typ'],
    { label: string; variant: 'default' | 'secondary' | 'outline' }
  > = {
    full: { label: 'Vollsicherung', variant: 'default' },
    incremental: { label: 'Inkrementell', variant: 'secondary' },
    differential: { label: 'Differentiell', variant: 'outline' },
  };

  const config = typeConfig[typ];
  return <Badge variant={config.variant}>{config.label}</Badge>;
};

const getValidationBadge = (backup: Backup) => {
  if (!backup.validiert) {
    return (
      <Badge variant="outline" className="gap-1">
        <AlertTriangle className="h-3 w-3" />
        Nicht validiert
      </Badge>
    );
  }

  if (backup.validation_status === 'success') {
    return (
      <Badge variant="default" className="gap-1 bg-green-600">
        <CheckCircle2 className="h-3 w-3" />
        Gültig
      </Badge>
    );
  }

  if (backup.validation_status === 'failed') {
    return (
      <Badge variant="destructive" className="gap-1">
        <XCircle className="h-3 w-3" />
        Fehlerhaft
      </Badge>
    );
  }

  return (
    <Badge variant="secondary" className="gap-1">
      <RefreshCw className="h-3 w-3 animate-spin" />
      Validierung läuft
    </Badge>
  );
};

export function BackupValidationPanel({
  backups,
  isLoading,
  onValidate,
  onValidateAll,
  isValidating,
}: BackupValidationPanelProps) {
  const [validatingBackup, setValidatingBackup] = useState<string | null>(null);

  const handleValidate = async (backupName: string) => {
    setValidatingBackup(backupName);
    await onValidate(backupName);
    setValidatingBackup(null);
  };

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <Skeleton className="h-6 w-48 mb-2" />
          <Skeleton className="h-4 w-72" />
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </div>
        </CardContent>
      </Card>
    );
  }

  const validBackups = backups.filter((b) => b.validation_status === 'success').length;
  const failedBackups = backups.filter((b) => b.validation_status === 'failed').length;
  const unvalidatedBackups = backups.filter((b) => !b.validiert).length;
  const encryptedBackups = backups.filter((b) => b.verschluesselt).length;

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle>Backup-Integritäts-Checks</CardTitle>
            <CardDescription>
              Validierung und Integritätsprüfung aller Backups
            </CardDescription>
          </div>
          <Button onClick={onValidateAll} disabled={isValidating}>
            {isValidating ? (
              <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
            ) : (
              <Shield className="h-4 w-4 mr-2" />
            )}
            Alle validieren
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Statistics */}
        <div className="grid grid-cols-4 gap-4">
          <div className="p-3 rounded-lg bg-muted">
            <div className="flex items-center gap-2 text-sm text-muted-foreground mb-1">
              <FileCheck className="h-4 w-4" />
              Gesamt
            </div>
            <div className="text-2xl font-bold">{backups.length}</div>
          </div>

          <div className="p-3 rounded-lg bg-green-50 dark:bg-green-950">
            <div className="flex items-center gap-2 text-sm text-green-700 dark:text-green-400 mb-1">
              <CheckCircle2 className="h-4 w-4" />
              Gültig
            </div>
            <div className="text-2xl font-bold text-green-700 dark:text-green-400">
              {validBackups}
            </div>
          </div>

          <div className="p-3 rounded-lg bg-red-50 dark:bg-red-950">
            <div className="flex items-center gap-2 text-sm text-red-700 dark:text-red-400 mb-1">
              <XCircle className="h-4 w-4" />
              Fehlerhaft
            </div>
            <div className="text-2xl font-bold text-red-700 dark:text-red-400">
              {failedBackups}
            </div>
          </div>

          <div className="p-3 rounded-lg bg-yellow-50 dark:bg-yellow-950">
            <div className="flex items-center gap-2 text-sm text-yellow-700 dark:text-yellow-400 mb-1">
              <AlertTriangle className="h-4 w-4" />
              Unvalidiert
            </div>
            <div className="text-2xl font-bold text-yellow-700 dark:text-yellow-400">
              {unvalidatedBackups}
            </div>
          </div>
        </div>

        {/* Encryption Status */}
        <Alert>
          <Lock className="h-4 w-4" />
          <AlertDescription>
            {encryptedBackups} von {backups.length} Backups sind verschlüsselt (
            {backups.length > 0 ? ((encryptedBackups / backups.length) * 100).toFixed(0) : 0}%)
          </AlertDescription>
        </Alert>

        {/* Backups Table */}
        {backups.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
            <FileCheck className="h-12 w-12 mb-4 opacity-50" />
            <p>Keine Backups gefunden</p>
          </div>
        ) : (
          <div className="border rounded-lg">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Typ</TableHead>
                  <TableHead>Größe</TableHead>
                  <TableHead>Erstellt</TableHead>
                  <TableHead>Verschlüsselt</TableHead>
                  <TableHead>Validierung</TableHead>
                  <TableHead>Letzte Prüfung</TableHead>
                  <TableHead></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {backups.map((backup) => (
                  <TableRow key={backup.name}>
                    <TableCell className="font-mono text-sm">{backup.name}</TableCell>
                    <TableCell>{getTypeBadge(backup.typ)}</TableCell>
                    <TableCell className="font-mono text-sm">
                      {formatSize(backup.groesse)}
                    </TableCell>
                    <TableCell className="font-mono text-sm">
                      {formatDate(backup.erstellt)}
                    </TableCell>
                    <TableCell>
                      {backup.verschluesselt ? (
                        <Badge variant="default" className="gap-1">
                          <Lock className="h-3 w-3" />
                          Ja
                        </Badge>
                      ) : (
                        <Badge variant="outline" className="gap-1">
                          <XCircle className="h-3 w-3" />
                          Nein
                        </Badge>
                      )}
                    </TableCell>
                    <TableCell>{getValidationBadge(backup)}</TableCell>
                    <TableCell className="font-mono text-sm text-muted-foreground">
                      {backup.validiert_am ? formatDate(backup.validiert_am) : '-'}
                    </TableCell>
                    <TableCell>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleValidate(backup.name)}
                        disabled={validatingBackup === backup.name}
                      >
                        {validatingBackup === backup.name ? (
                          <RefreshCw className="h-4 w-4 animate-spin" />
                        ) : (
                          <Shield className="h-4 w-4" />
                        )}
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
