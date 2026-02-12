/**
 * ImportLogTable Component
 *
 * Zeigt Import-Logs mit Filter- und Retry-Funktionalitaet.
 */

import { useState } from 'react';
import { formatDistanceToNow, format } from 'date-fns';
import { de } from 'date-fns/locale';
import {
  FileText,
  RefreshCw,
  Mail,
  Folder,
  CheckCircle,
  XCircle,
  AlertTriangle,
  Clock,
  SkipForward,
  Copy,
  Loader2,
  ChevronDown,
  RotateCcw,
  ExternalLink,
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
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import { useToast } from '@/components/ui/use-toast';

import { useImportLogs, useRetryImport } from '../hooks/use-import-queries';
import type { ImportLogResponse, ImportStatus, SourceType, ImportLogFilter } from '../types/import-types';

// ==================== Status Badge ====================

interface StatusBadgeProps {
  status: ImportStatus;
}

function StatusBadge({ status }: StatusBadgeProps) {
  const statusConfig = {
    completed: {
      label: 'Erfolgreich',
      icon: CheckCircle,
      className: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200',
    },
    failed: {
      label: 'Fehlgeschlagen',
      icon: XCircle,
      className: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200',
    },
    pending: {
      label: 'Ausstehend',
      icon: Clock,
      className: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200',
    },
    processing: {
      label: 'Verarbeitung',
      icon: Loader2,
      className: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200',
    },
    skipped: {
      label: 'Übersprungen',
      icon: SkipForward,
      className: 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200',
    },
    duplicate: {
      label: 'Duplikat',
      icon: Copy,
      className: 'bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200',
    },
  };

  const config = statusConfig[status] || {
    label: status,
    icon: AlertTriangle,
    className: '',
  };
  const Icon = config.icon;

  return (
    <Badge variant="outline" className={config.className}>
      <Icon className={`mr-1 h-3 w-3 ${status === 'processing' ? 'animate-spin' : ''}`} />
      {config.label}
    </Badge>
  );
}

// ==================== Source Badge ====================

interface SourceBadgeProps {
  type: SourceType;
}

function SourceBadge({ type }: SourceBadgeProps) {
  const Icon = type === 'email' ? Mail : Folder;
  const label = type === 'email' ? 'Email' : 'Ordner';

  return (
    <Badge variant="secondary">
      <Icon className="mr-1 h-3 w-3" />
      {label}
    </Badge>
  );
}

// ==================== Log Row ====================

interface LogRowProps {
  log: ImportLogResponse;
  onRetry: (logId: string) => void;
  isRetrying: boolean;
}

function LogRow({ log, onRetry, isRetrying }: LogRowProps) {
  const [isOpen, setIsOpen] = useState(false);

  const displayName = log.sourceType === 'email'
    ? log.emailSubject || log.emailFrom || 'Unbekannte Email'
    : log.originalFilename || log.originalPath || 'Unbekannte Datei';

  const canRetry = log.status === 'failed' && log.retryCount < 3;

  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen}>
      <TableRow className="group">
        <TableCell>
          <CollapsibleTrigger asChild>
            <Button variant="ghost" size="sm" className="h-8 w-8 p-0">
              <ChevronDown
                className={`h-4 w-4 transition-transform ${
                  isOpen ? 'rotate-180' : ''
                }`}
              />
            </Button>
          </CollapsibleTrigger>
        </TableCell>
        <TableCell>
          <SourceBadge type={log.sourceType} />
        </TableCell>
        <TableCell className="max-w-[300px]">
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger className="block truncate text-left">
                {displayName}
              </TooltipTrigger>
              <TooltipContent side="bottom" className="max-w-md">
                <p className="break-all">{displayName}</p>
                {log.originalFilename && log.originalPath && (
                  <p className="text-xs text-muted-foreground mt-1">
                    {log.originalPath}
                  </p>
                )}
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        </TableCell>
        <TableCell>
          <StatusBadge status={log.status} />
        </TableCell>
        <TableCell className="text-muted-foreground">
          {formatDistanceToNow(new Date(log.startedAt), {
            addSuffix: true,
            locale: de,
          })}
        </TableCell>
        <TableCell className="text-right font-mono text-muted-foreground">
          {log.processingDurationMs
            ? `${(log.processingDurationMs / 1000).toFixed(1)}s`
            : '-'}
        </TableCell>
        <TableCell>
          <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
            {canRetry && (
              <TooltipProvider>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => onRetry(log.id)}
                      disabled={isRetrying}
                    >
                      {isRetrying ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <RotateCcw className="h-4 w-4" />
                      )}
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>Erneut versuchen</TooltipContent>
                </Tooltip>
              </TooltipProvider>
            )}
            {log.documentId && (
              <TooltipProvider>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button variant="ghost" size="icon" asChild>
                      <a
                        href={`/documents/${log.documentId}`}
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        <ExternalLink className="h-4 w-4" />
                      </a>
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>Dokument öffnen</TooltipContent>
                </Tooltip>
              </TooltipProvider>
            )}
          </div>
        </TableCell>
      </TableRow>

      <CollapsibleContent asChild>
        <TableRow className="bg-muted/50">
          <TableCell colSpan={7} className="p-4">
            <div className="grid gap-4 md:grid-cols-2 text-sm">
              <div className="space-y-2">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Gestartet:</span>
                  <span>{format(new Date(log.startedAt), 'dd.MM.yyyy HH:mm:ss', { locale: de })}</span>
                </div>
                {log.completedAt && (
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Abgeschlossen:</span>
                    <span>{format(new Date(log.completedAt), 'dd.MM.yyyy HH:mm:ss', { locale: de })}</span>
                  </div>
                )}
                {log.fileSize && (
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Dateigröße:</span>
                    <span>{(log.fileSize / 1024).toFixed(1)} KB</span>
                  </div>
                )}
                {log.mimeType && (
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Typ:</span>
                    <span className="font-mono">{log.mimeType}</span>
                  </div>
                )}
              </div>

              <div className="space-y-2">
                {log.retryCount > 0 && (
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Versuche:</span>
                    <span>{log.retryCount + 1}</span>
                  </div>
                )}
                {log.matchedRuleId && (
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Regel angewendet:</span>
                    <span>Ja</span>
                  </div>
                )}
                {log.documentId && (
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Dokument-ID:</span>
                    <span className="font-mono text-xs">{log.documentId}</span>
                  </div>
                )}
              </div>

              {log.errorMessage && (
                <div className="md:col-span-2 p-3 rounded-lg bg-destructive/10 text-destructive">
                  <p className="font-medium mb-1">Fehler:</p>
                  <p className="text-sm">{log.errorMessage}</p>
                  {log.errorCode && (
                    <p className="text-xs mt-1 font-mono">Code: {log.errorCode}</p>
                  )}
                </div>
              )}
            </div>
          </TableCell>
        </TableRow>
      </CollapsibleContent>
    </Collapsible>
  );
}

// ==================== Main Component ====================

interface ImportLogTableProps {
  emailConfigId?: string;
  folderConfigId?: string;
  maxItems?: number;
}

export function ImportLogTable({
  emailConfigId,
  folderConfigId,
  maxItems = 50,
}: ImportLogTableProps) {
  const { toast } = useToast();
  const [filter, setFilter] = useState<ImportLogFilter>({
    emailConfigId,
    folderConfigId,
    perPage: maxItems,
  });

  // Queries
  const { data: logs, isLoading, error, refetch } = useImportLogs(filter);

  // Mutations
  const retryImport = useRetryImport();

  // Handlers
  const handleRetry = async (logId: string) => {
    try {
      await retryImport.mutateAsync(logId);
      toast({
        title: 'Import wird wiederholt',
        description: 'Der Import wurde in die Warteschlange gestellt.',
      });
    } catch (err) {
      toast({
        title: 'Fehler',
        description: err instanceof Error ? err.message : 'Unbekannter Fehler',
        variant: 'destructive',
      });
    }
  };

  const handleSourceFilterChange = (value: string) => {
    setFilter((prev) => ({
      ...prev,
      sourceType: value === 'all' ? undefined : (value as SourceType),
    }));
  };

  const handleStatusFilterChange = (value: string) => {
    setFilter((prev) => ({
      ...prev,
      status: value === 'all' ? undefined : (value as ImportStatus),
    }));
  };

  // Loading State
  if (isLoading) {
    return (
      <Card>
        <CardContent className="flex items-center justify-center py-8">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          <span className="ml-2 text-muted-foreground">Lade Import-Logs...</span>
        </CardContent>
      </Card>
    );
  }

  // Error State
  if (error) {
    return (
      <Card>
        <CardContent className="flex flex-col items-center justify-center py-8 text-destructive">
          <AlertTriangle className="h-8 w-8 mb-2" />
          <p>Fehler beim Laden der Logs</p>
          <Button variant="outline" size="sm" className="mt-4" onClick={() => refetch()}>
            Erneut versuchen
          </Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <div>
          <CardTitle className="flex items-center gap-2">
            <FileText className="h-5 w-5" />
            Import-Protokoll
          </CardTitle>
          <CardDescription>
            {logs?.length ?? 0} Einträge
          </CardDescription>
        </div>
        <div className="flex items-center gap-2">
          <Select
            value={filter.sourceType ?? 'all'}
            onValueChange={handleSourceFilterChange}
          >
            <SelectTrigger className="w-[130px]">
              <SelectValue placeholder="Quelle" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Alle Quellen</SelectItem>
              <SelectItem value="email">Email</SelectItem>
              <SelectItem value="folder">Ordner</SelectItem>
            </SelectContent>
          </Select>

          <Select
            value={filter.status ?? 'all'}
            onValueChange={handleStatusFilterChange}
          >
            <SelectTrigger className="w-[150px]">
              <SelectValue placeholder="Status" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Alle Status</SelectItem>
              <SelectItem value="completed">Erfolgreich</SelectItem>
              <SelectItem value="failed">Fehlgeschlagen</SelectItem>
              <SelectItem value="pending">Ausstehend</SelectItem>
              <SelectItem value="processing">Verarbeitung</SelectItem>
              <SelectItem value="skipped">Übersprungen</SelectItem>
              <SelectItem value="duplicate">Duplikat</SelectItem>
            </SelectContent>
          </Select>

          <Button variant="outline" size="icon" onClick={() => refetch()}>
            <RefreshCw className="h-4 w-4" />
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {!logs || logs.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
            <FileText className="h-12 w-12 mb-4" />
            <p>Keine Import-Einträge gefunden</p>
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-[40px]" />
                <TableHead className="w-[100px]">Quelle</TableHead>
                <TableHead>Datei / Betreff</TableHead>
                <TableHead className="w-[130px]">Status</TableHead>
                <TableHead className="w-[150px]">Zeit</TableHead>
                <TableHead className="w-[100px] text-right">Dauer</TableHead>
                <TableHead className="w-[80px]" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {logs.map((log) => (
                <LogRow
                  key={log.id}
                  log={log}
                  onRetry={handleRetry}
                  isRetrying={retryImport.isPending}
                />
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
