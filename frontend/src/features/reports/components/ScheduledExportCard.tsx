/**
 * ScheduledExportCard Component
 *
 * Zeigt einen geplanten Export mit Zeitplan, Format, Status und Toggle.
 */

import {
  Calendar,
  Clock,
  FileDown,
  Loader2,
  MoreVertical,
  Pause,
  Play,
  Trash2,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { formatDistanceToNow, format } from 'date-fns';
import { de } from 'date-fns/locale';
import type { ScheduledExport } from '../api/report-builder-api';

interface ScheduledExportCardProps {
  exportItem: ScheduledExport;
  onToggle: (exportId: string, active: boolean) => void;
  onRunNow: (exportId: string) => void;
  onDelete: (exportId: string) => void;
  isToggling?: boolean;
  isRunning?: boolean;
}

const formatLabels: Record<string, string> = {
  json: 'JSON',
  csv: 'CSV',
  zip: 'ZIP',
  excel: 'Excel',
  pdf: 'PDF',
};

const exportTypeLabels: Record<string, string> = {
  documents: 'Dokumente',
  invoices: 'Rechnungen',
  datev: 'DATEV',
  training: 'Training',
};

const statusColors: Record<string, string> = {
  success: 'bg-green-500/10 text-green-600',
  failed: 'bg-red-500/10 text-red-600',
  running: 'bg-blue-500/10 text-blue-600',
};

function cronToGerman(cron: string): string {
  const parts = cron.split(' ');
  if (parts.length < 5) return cron;

  const [minute, hour, dayOfMonth, , dayOfWeek] = parts;

  if (dayOfWeek === '*' && dayOfMonth === '*') {
    return `Taeglich um ${hour.padStart(2, '0')}:${minute.padStart(2, '0')}`;
  }

  if (dayOfWeek === '1' && dayOfMonth === '*') {
    return `Woechentlich (Mo) um ${hour.padStart(2, '0')}:${minute.padStart(2, '0')}`;
  }

  if (dayOfWeek === '5' && dayOfMonth === '*') {
    return `Woechentlich (Fr) um ${hour.padStart(2, '0')}:${minute.padStart(2, '0')}`;
  }

  if (dayOfWeek === '1-5' && dayOfMonth === '*') {
    return `Werktags um ${hour.padStart(2, '0')}:${minute.padStart(2, '0')}`;
  }

  if (dayOfMonth === '1' && dayOfWeek === '*') {
    return `Monatlich (1.) um ${hour.padStart(2, '0')}:${minute.padStart(2, '0')}`;
  }

  return `Zeitplan: ${cron}`;
}

export function ScheduledExportCard({
  exportItem,
  onToggle,
  onRunNow,
  onDelete,
  isToggling = false,
  isRunning = false,
}: ScheduledExportCardProps) {
  return (
    <Card className={!exportItem.is_active ? 'opacity-60' : undefined}>
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between">
          <div className="flex-1 min-w-0">
            <CardTitle className="text-base truncate">
              {exportItem.name}
            </CardTitle>
            {exportItem.description && (
              <p className="text-sm text-muted-foreground mt-1 line-clamp-1">
                {exportItem.description}
              </p>
            )}
          </div>
          <div className="flex items-center gap-2">
            <Switch
              checked={exportItem.is_active}
              onCheckedChange={(checked) => onToggle(exportItem.id, checked)}
              disabled={isToggling}
              aria-label={exportItem.is_active ? 'Export deaktivieren' : 'Export aktivieren'}
            />
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="icon" className="h-8 w-8">
                  <MoreVertical className="h-4 w-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem
                  onClick={() => onRunNow(exportItem.id)}
                  disabled={isRunning}
                >
                  {isRunning ? (
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  ) : (
                    <Play className="h-4 w-4 mr-2" />
                  )}
                  Jetzt ausfuehren
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  onClick={() => onDelete(exportItem.id)}
                  className="text-destructive focus:text-destructive"
                >
                  <Trash2 className="h-4 w-4 mr-2" />
                  Loeschen
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          {/* Zeitplan */}
          <div className="flex items-center gap-2 text-sm">
            <Calendar className="h-4 w-4 text-muted-foreground shrink-0" />
            <span>{cronToGerman(exportItem.cron_expression)}</span>
          </div>

          {/* Badges */}
          <div className="flex flex-wrap gap-2">
            <Badge variant="outline">
              {exportTypeLabels[exportItem.export_type] || exportItem.export_type}
            </Badge>
            <Badge variant="secondary">
              <FileDown className="h-3 w-3 mr-1" />
              {formatLabels[exportItem.export_format] || exportItem.export_format.toUpperCase()}
            </Badge>
            {exportItem.is_active ? (
              <Badge variant="secondary" className="bg-green-500/10 text-green-600">
                Aktiv
              </Badge>
            ) : (
              <Badge variant="secondary" className="bg-gray-500/10 text-gray-600">
                <Pause className="h-3 w-3 mr-1" />
                Pausiert
              </Badge>
            )}
            {exportItem.last_run_status && (
              <Badge
                variant="secondary"
                className={statusColors[exportItem.last_run_status] || ''}
              >
                {exportItem.last_run_status === 'success'
                  ? 'Erfolgreich'
                  : exportItem.last_run_status === 'failed'
                    ? 'Fehlgeschlagen'
                    : exportItem.last_run_status}
              </Badge>
            )}
          </div>

          {/* Letzte / Naechste Ausfuehrung */}
          <div className="flex items-center justify-between text-xs text-muted-foreground pt-2 border-t">
            {exportItem.last_run_at ? (
              <span className="flex items-center gap-1">
                <Clock className="h-3 w-3" />
                Zuletzt:{' '}
                {formatDistanceToNow(new Date(exportItem.last_run_at), {
                  addSuffix: true,
                  locale: de,
                })}
              </span>
            ) : (
              <span className="flex items-center gap-1">
                <Clock className="h-3 w-3" />
                Noch nicht ausgefuehrt
              </span>
            )}
            {exportItem.next_run_at && exportItem.is_active && (
              <span>
                Naechste:{' '}
                {format(new Date(exportItem.next_run_at), 'dd.MM. HH:mm', {
                  locale: de,
                })}
              </span>
            )}
          </div>

          {/* Ausfuehrungen zaehler */}
          {exportItem.run_count > 0 && (
            <div className="text-xs text-muted-foreground">
              {exportItem.run_count} Ausfuehrung{exportItem.run_count !== 1 ? 'en' : ''} insgesamt
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
