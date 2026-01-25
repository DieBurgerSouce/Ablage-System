/**
 * Backup Status Card
 *
 * Zeigt den aktuellen Status des Backup-Systems.
 */

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Alert, AlertDescription } from '@/components/ui/alert';
import {
  HardDrive,
  Shield,
  CheckCircle2,
  XCircle,
  Clock,
  Database,
  AlertTriangle,
} from 'lucide-react';
import { format } from 'date-fns';
import { de } from 'date-fns/locale';
import type { BackupStatus } from '../api';

interface BackupStatusCardProps {
  status?: BackupStatus;
  isLoading: boolean;
}

const formatDate = (dateStr?: string) => {
  if (!dateStr) return '-';
  try {
    return format(new Date(dateStr), 'dd.MM.yyyy HH:mm', { locale: de });
  } catch {
    return dateStr;
  }
};

const formatSize = (gb?: number) => {
  if (gb === undefined) return '-';
  return `${gb.toFixed(2)} GB`;
};

export function BackupStatusCard({ status, isLoading }: BackupStatusCardProps) {
  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <Skeleton className="h-6 w-48 mb-2" />
          <Skeleton className="h-4 w-72" />
        </CardHeader>
        <CardContent className="space-y-4">
          <Skeleton className="h-20 w-full" />
          <Skeleton className="h-20 w-full" />
        </CardContent>
      </Card>
    );
  }

  if (!status) {
    return (
      <Card>
        <CardContent className="pt-6">
          <Alert variant="destructive">
            <XCircle className="h-4 w-4" />
            <AlertDescription>Backup-Status konnte nicht geladen werden</AlertDescription>
          </Alert>
        </CardContent>
      </Card>
    );
  }

  const isHealthy = status.service_aktiv && status.encryption_aktiv;
  const storageUsagePercent = status.verfuegbarer_speicherplatz_gb && status.gesamt_backup_groesse_gb
    ? (status.gesamt_backup_groesse_gb / (status.verfuegbarer_speicherplatz_gb + status.gesamt_backup_groesse_gb)) * 100
    : 0;
  const isStorageCritical = storageUsagePercent > 80;

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            <Database className="h-5 w-5" />
            System-Status
          </CardTitle>
          <Badge variant={isHealthy ? 'default' : 'destructive'} className="gap-1">
            {isHealthy ? (
              <>
                <CheckCircle2 className="h-3 w-3" />
                Gesund
              </>
            ) : (
              <>
                <XCircle className="h-3 w-3" />
                Problem
              </>
            )}
          </Badge>
        </div>
        <CardDescription>Aktueller Status des Backup-Systems</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Service Status */}
        <div className="grid grid-cols-2 gap-4">
          <div className="flex items-center gap-3 p-3 rounded-lg bg-muted">
            <div
              className={`p-2 rounded-lg ${
                status.service_aktiv ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
              }`}
            >
              {status.service_aktiv ? (
                <CheckCircle2 className="h-4 w-4" />
              ) : (
                <XCircle className="h-4 w-4" />
              )}
            </div>
            <div>
              <div className="text-sm text-muted-foreground">Backup-Service</div>
              <div className="font-medium">
                {status.service_aktiv ? 'Aktiv' : 'Inaktiv'}
              </div>
            </div>
          </div>

          <div className="flex items-center gap-3 p-3 rounded-lg bg-muted">
            <div
              className={`p-2 rounded-lg ${
                status.encryption_aktiv
                  ? 'bg-green-100 text-green-700'
                  : 'bg-yellow-100 text-yellow-700'
              }`}
            >
              <Shield className="h-4 w-4" />
            </div>
            <div>
              <div className="text-sm text-muted-foreground">Verschlüsselung</div>
              <div className="font-medium">
                {status.encryption_aktiv ? 'Aktiviert' : 'Deaktiviert'}
              </div>
            </div>
          </div>
        </div>

        {/* Backup Timing */}
        <div className="space-y-3">
          <div className="flex items-center justify-between p-3 rounded-lg bg-muted">
            <div className="flex items-center gap-2">
              <Clock className="h-4 w-4 text-muted-foreground" />
              <span className="text-sm">Letzte Vollsicherung</span>
            </div>
            <span className="font-mono text-sm">
              {formatDate(status.letzte_vollsicherung)}
            </span>
          </div>

          {status.naechste_geplante_sicherung && (
            <div className="flex items-center justify-between p-3 rounded-lg bg-muted">
              <div className="flex items-center gap-2">
                <Clock className="h-4 w-4 text-muted-foreground" />
                <span className="text-sm">Nächste geplante Sicherung</span>
              </div>
              <span className="font-mono text-sm">
                {formatDate(status.naechste_geplante_sicherung)}
              </span>
            </div>
          )}
        </div>

        {/* Storage Info */}
        <div className="space-y-2">
          <div className="flex items-center justify-between text-sm">
            <div className="flex items-center gap-2">
              <HardDrive className="h-4 w-4 text-muted-foreground" />
              <span>Speichernutzung</span>
            </div>
            <span className="font-mono">
              {formatSize(status.gesamt_backup_groesse_gb)} von{' '}
              {formatSize(
                (status.verfuegbarer_speicherplatz_gb ?? 0) +
                  (status.gesamt_backup_groesse_gb ?? 0)
              )}
            </span>
          </div>

          {/* Storage Usage Bar */}
          <div className="h-2 bg-muted rounded-full overflow-hidden">
            <div
              className={`h-full transition-all ${
                isStorageCritical ? 'bg-red-500' : 'bg-blue-500'
              }`}
              style={{ width: `${Math.min(storageUsagePercent, 100)}%` }}
            />
          </div>

          {isStorageCritical && (
            <Alert variant="destructive">
              <AlertTriangle className="h-4 w-4" />
              <AlertDescription>
                Speicherplatz wird knapp. Bitte alte Backups archivieren.
              </AlertDescription>
            </Alert>
          )}
        </div>

        {/* Storage Path */}
        <div className="pt-3 border-t">
          <div className="text-sm text-muted-foreground mb-1">Speicherpfad</div>
          <code className="text-xs bg-muted px-2 py-1 rounded block break-all">
            {status.storage_pfad}
          </code>
        </div>
      </CardContent>
    </Card>
  );
}
