/**
 * AuditLogTable Component
 *
 * Enterprise Audit-Log Viewer mit Filter, Pagination und Export.
 */

import { useState, useMemo } from 'react';
import { formatDistanceToNow, format } from 'date-fns';
import { de } from 'date-fns/locale';
import {
  FileText,
  RefreshCw,
  Download,
  CheckCircle,
  XCircle,
  AlertTriangle,
  User,
  Globe,
  Clock,
  ChevronDown,
  Search,
  Loader2,
  Filter,
  X,
  FileJson,
  FileSpreadsheet,
} from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
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
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
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
import { Skeleton } from '@/components/ui/skeleton';
import { useToast } from '@/components/ui/use-toast';

import {
  useAuditLogs,
  useExportAuditLogs,
  type AuditLogView,
  type AuditQueryParams,
  type AuditLogFilters,
} from './audit-api';

// ==================== Action Badge ====================

interface ActionBadgeProps {
  action: string;
}

function ActionBadge({ action }: ActionBadgeProps) {
  // Group actions by category
  const getActionCategory = (act: string): { color: string; label: string } => {
    if (act.includes('login') || act.includes('logout') || act.includes('auth')) {
      return { color: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200', label: 'Auth' };
    }
    if (act.includes('create') || act.includes('upload')) {
      return { color: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200', label: 'Erstellen' };
    }
    if (act.includes('update') || act.includes('edit')) {
      return { color: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200', label: 'Bearbeiten' };
    }
    if (act.includes('delete') || act.includes('remove')) {
      return { color: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200', label: 'Löschen' };
    }
    if (act.includes('export') || act.includes('download')) {
      return { color: 'bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200', label: 'Export' };
    }
    return { color: 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200', label: 'Sonstige' };
  };

  const category = getActionCategory(action);

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger>
          <Badge variant="outline" className={category.color}>
            {action.replace(/_/g, ' ').split(' ').slice(0, 2).join(' ')}
          </Badge>
        </TooltipTrigger>
        <TooltipContent>
          <p className="font-mono">{action}</p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

// ==================== Success Badge ====================

interface SuccessBadgeProps {
  success: boolean;
  errorMessage?: string | null;
}

function SuccessBadge({ success, errorMessage }: SuccessBadgeProps) {
  if (success) {
    return (
      <Badge variant="outline" className="bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200">
        <CheckCircle className="mr-1 h-3 w-3" />
        Erfolgreich
      </Badge>
    );
  }

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger>
          <Badge variant="outline" className="bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200">
            <XCircle className="mr-1 h-3 w-3" />
            Fehlgeschlagen
          </Badge>
        </TooltipTrigger>
        {errorMessage && (
          <TooltipContent side="bottom" className="max-w-sm">
            <p className="text-sm">{errorMessage}</p>
          </TooltipContent>
        )}
      </Tooltip>
    </TooltipProvider>
  );
}

// ==================== Log Row ====================

interface LogRowProps {
  log: AuditLogView;
}

function LogRow({ log }: LogRowProps) {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen}>
      <TableRow className="group">
        <TableCell>
          <CollapsibleTrigger asChild>
            <Button variant="ghost" size="sm" className="h-8 w-8 p-0">
              <ChevronDown
                className={`h-4 w-4 transition-transform ${isOpen ? 'rotate-180' : ''}`}
              />
            </Button>
          </CollapsibleTrigger>
        </TableCell>
        <TableCell className="text-muted-foreground text-xs font-mono">
          {format(new Date(log.created_at), 'dd.MM.yy HH:mm', { locale: de })}
        </TableCell>
        <TableCell>
          <div className="flex items-center gap-2">
            <User className="h-4 w-4 text-muted-foreground" />
            <span className="truncate max-w-[150px]">
              {log.user_email ?? 'System'}
            </span>
          </div>
        </TableCell>
        <TableCell>
          <ActionBadge action={log.action} />
        </TableCell>
        <TableCell>
          {log.resource_type && (
            <Badge variant="secondary">{log.resource_type}</Badge>
          )}
        </TableCell>
        <TableCell>
          <SuccessBadge success={log.success} errorMessage={log.error_message} />
        </TableCell>
        <TableCell className="text-muted-foreground text-xs">
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger className="flex items-center gap-1">
                <Globe className="h-3 w-3" />
                {log.ip_address?.split(',')[0] ?? '-'}
              </TooltipTrigger>
              <TooltipContent>
                <p>{log.ip_address ?? 'Keine IP'}</p>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        </TableCell>
      </TableRow>

      <CollapsibleContent asChild>
        <TableRow className="bg-muted/50 hover:bg-muted/50">
          <TableCell colSpan={7} className="p-4">
            <div className="grid gap-4 md:grid-cols-3 text-sm">
              {/* Zeitstempel & Benutzer */}
              <div className="space-y-2">
                <h4 className="font-medium text-muted-foreground">Details</h4>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Zeitpunkt:</span>
                  <span>{format(new Date(log.created_at), 'dd.MM.yyyy HH:mm:ss', { locale: de })}</span>
                </div>
                {log.user_email && (
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Benutzer:</span>
                    <span>{log.user_email}</span>
                  </div>
                )}
                {log.user_id && (
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">User-ID:</span>
                    <span className="font-mono text-xs">{log.user_id}</span>
                  </div>
                )}
              </div>

              {/* Request-Info */}
              <div className="space-y-2">
                <h4 className="font-medium text-muted-foreground">Request</h4>
                {log.request_method && (
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Methode:</span>
                    <Badge variant="outline">{log.request_method}</Badge>
                  </div>
                )}
                {log.request_path && (
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Pfad:</span>
                    <span className="font-mono text-xs truncate max-w-[180px]">{log.request_path}</span>
                  </div>
                )}
                {log.ip_address && (
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">IP-Adresse:</span>
                    <span className="font-mono text-xs">{log.ip_address}</span>
                  </div>
                )}
              </div>

              {/* Ressource & Metadaten */}
              <div className="space-y-2">
                <h4 className="font-medium text-muted-foreground">Ressource</h4>
                {log.resource_type && (
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Typ:</span>
                    <span>{log.resource_type}</span>
                  </div>
                )}
                {log.resource_id && (
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">ID:</span>
                    <span className="font-mono text-xs">{log.resource_id}</span>
                  </div>
                )}
                {log.metadata && Object.keys(log.metadata).length > 0 && (
                  <div>
                    <span className="text-muted-foreground">Metadaten:</span>
                    <pre className="mt-1 p-2 rounded bg-muted text-xs overflow-auto max-h-32">
                      {JSON.stringify(log.metadata, null, 2)}
                    </pre>
                  </div>
                )}
              </div>

              {/* Fehlermeldung */}
              {log.error_message && (
                <div className="md:col-span-3 p-3 rounded-lg bg-destructive/10 text-destructive">
                  <p className="font-medium mb-1">Fehlermeldung:</p>
                  <p className="text-sm">{log.error_message}</p>
                </div>
              )}

              {/* User Agent */}
              {log.user_agent && (
                <div className="md:col-span-3">
                  <span className="text-muted-foreground text-xs">User Agent: </span>
                  <span className="font-mono text-xs">{log.user_agent}</span>
                </div>
              )}
            </div>
          </TableCell>
        </TableRow>
      </CollapsibleContent>
    </Collapsible>
  );
}

// ==================== Skeleton ====================

function TableSkeleton() {
  return (
    <div className="space-y-2">
      {Array.from({ length: 10 }).map((_, i) => (
        <div key={i} className="flex items-center gap-4 p-3">
          <Skeleton className="h-8 w-8 rounded" />
          <Skeleton className="h-4 w-24" />
          <Skeleton className="h-4 w-32" />
          <Skeleton className="h-6 w-24 rounded-full" />
          <Skeleton className="h-6 w-20 rounded-full" />
          <Skeleton className="h-6 w-24 rounded-full" />
          <Skeleton className="h-4 w-20" />
        </div>
      ))}
    </div>
  );
}

// ==================== Filter Popover ====================

interface FilterPopoverProps {
  filters: AuditLogFilters;
  onFiltersChange: (filters: AuditLogFilters) => void;
}

function FilterPopover({ filters, onFiltersChange }: FilterPopoverProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [localFilters, setLocalFilters] = useState<AuditLogFilters>(filters);

  const activeFilterCount = useMemo(() => {
    let count = 0;
    if (filters.action) count++;
    if (filters.resource_type) count++;
    if (filters.success !== undefined) count++;
    if (filters.from_date) count++;
    if (filters.to_date) count++;
    if (filters.ip_address) count++;
    return count;
  }, [filters]);

  const handleApply = () => {
    onFiltersChange(localFilters);
    setIsOpen(false);
  };

  const handleReset = () => {
    const emptyFilters: AuditLogFilters = {};
    setLocalFilters(emptyFilters);
    onFiltersChange(emptyFilters);
    setIsOpen(false);
  };

  return (
    <Popover open={isOpen} onOpenChange={setIsOpen}>
      <PopoverTrigger asChild>
        <Button variant="outline" size="sm" className="h-9">
          <Filter className="h-4 w-4 mr-2" />
          Filter
          {activeFilterCount > 0 && (
            <Badge variant="secondary" className="ml-2 h-5 px-1.5">
              {activeFilterCount}
            </Badge>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-80" align="end">
        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="filter-action">Aktion</Label>
            <Input
              id="filter-action"
              placeholder="z.B. login, document_upload"
              value={localFilters.action ?? ''}
              onChange={(e) => setLocalFilters({ ...localFilters, action: e.target.value || undefined })}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="filter-resource">Ressourcentyp</Label>
            <Input
              id="filter-resource"
              placeholder="z.B. document, user"
              value={localFilters.resource_type ?? ''}
              onChange={(e) => setLocalFilters({ ...localFilters, resource_type: e.target.value || undefined })}
            />
          </div>

          <div className="space-y-2">
            <Label>Status</Label>
            <Select
              value={localFilters.success === undefined ? 'all' : localFilters.success ? 'success' : 'error'}
              onValueChange={(val) => setLocalFilters({
                ...localFilters,
                success: val === 'all' ? undefined : val === 'success',
              })}
            >
              <SelectTrigger>
                <SelectValue placeholder="Alle" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Alle</SelectItem>
                <SelectItem value="success">Erfolgreich</SelectItem>
                <SelectItem value="error">Fehlgeschlagen</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="grid grid-cols-2 gap-2">
            <div className="space-y-2">
              <Label htmlFor="filter-from">Von</Label>
              <Input
                id="filter-from"
                type="date"
                value={localFilters.from_date?.split('T')[0] ?? ''}
                onChange={(e) => setLocalFilters({
                  ...localFilters,
                  from_date: e.target.value ? `${e.target.value}T00:00:00Z` : undefined,
                })}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="filter-to">Bis</Label>
              <Input
                id="filter-to"
                type="date"
                value={localFilters.to_date?.split('T')[0] ?? ''}
                onChange={(e) => setLocalFilters({
                  ...localFilters,
                  to_date: e.target.value ? `${e.target.value}T23:59:59Z` : undefined,
                })}
              />
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="filter-ip">IP-Adresse</Label>
            <Input
              id="filter-ip"
              placeholder="z.B. 192.168.1.1"
              value={localFilters.ip_address ?? ''}
              onChange={(e) => setLocalFilters({ ...localFilters, ip_address: e.target.value || undefined })}
            />
          </div>

          <div className="flex justify-between pt-2">
            <Button variant="ghost" size="sm" onClick={handleReset}>
              Zurücksetzen
            </Button>
            <Button size="sm" onClick={handleApply}>
              Anwenden
            </Button>
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
}

// ==================== Main Component ====================

interface AuditLogTableProps {
  userId?: string;
  maxItems?: number;
}

export function AuditLogTable({ userId, maxItems = 50 }: AuditLogTableProps) {
  const { toast } = useToast();
  const [params, setParams] = useState<AuditQueryParams>({
    page: 1,
    per_page: maxItems,
    user_id: userId,
    sort_by: 'created_at',
    sort_order: 'desc',
  });

  // Queries
  const { data, isLoading, error, refetch, isFetching } = useAuditLogs(params);

  // Mutations
  const exportMutation = useExportAuditLogs();

  // Handlers
  const handleFiltersChange = (newFilters: AuditLogFilters) => {
    setParams((prev) => ({
      ...prev,
      ...newFilters,
      page: 1, // Reset to first page on filter change
    }));
  };

  const handleExport = async (format: 'csv' | 'json') => {
    try {
      await exportMutation.mutateAsync({
        format,
        filters: {
          user_id: params.user_id,
          action: params.action,
          resource_type: params.resource_type,
          success: params.success,
          from_date: params.from_date,
          to_date: params.to_date,
        },
      });
      toast({
        title: 'Export erfolgreich',
        description: `Audit-Logs wurden als ${format.toUpperCase()} exportiert.`,
      });
    } catch (err) {
      toast({
        title: 'Export fehlgeschlagen',
        description: err instanceof Error ? err.message : 'Unbekannter Fehler',
        variant: 'destructive',
      });
    }
  };

  const handlePageChange = (newPage: number) => {
    setParams((prev) => ({ ...prev, page: newPage }));
  };

  // Error State
  if (error) {
    return (
      <Card>
        <CardContent className="flex flex-col items-center justify-center py-8 text-destructive">
          <AlertTriangle className="h-8 w-8 mb-2" />
          <p>Fehler beim Laden der Audit-Logs</p>
          <Button variant="outline" size="sm" className="mt-4" onClick={() => refetch()}>
            Erneut versuchen
          </Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between flex-wrap gap-4">
        <div>
          <CardTitle className="flex items-center gap-2">
            <FileText className="h-5 w-5" />
            Audit-Protokoll
          </CardTitle>
          <CardDescription>
            {isLoading ? 'Laden...' : `${data?.total ?? 0} Einträge`}
          </CardDescription>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          {/* Search */}
          <div className="relative">
            <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Aktion suchen..."
              className="pl-8 w-[200px] h-9"
              value={params.action ?? ''}
              onChange={(e) => setParams((prev) => ({ ...prev, action: e.target.value || undefined, page: 1 }))}
            />
          </div>

          {/* Filters */}
          <FilterPopover
            filters={{
              action: params.action,
              resource_type: params.resource_type,
              success: params.success,
              from_date: params.from_date,
              to_date: params.to_date,
              ip_address: params.ip_address,
            }}
            onFiltersChange={handleFiltersChange}
          />

          {/* Export */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" size="sm" className="h-9" disabled={exportMutation.isPending}>
                {exportMutation.isPending ? (
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                ) : (
                  <Download className="h-4 w-4 mr-2" />
                )}
                Export
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={() => handleExport('csv')}>
                <FileSpreadsheet className="h-4 w-4 mr-2" />
                Als CSV
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => handleExport('json')}>
                <FileJson className="h-4 w-4 mr-2" />
                Als JSON
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>

          {/* Refresh */}
          <Button
            variant="outline"
            size="icon"
            className="h-9 w-9"
            onClick={() => refetch()}
            disabled={isFetching}
            aria-label="Aktualisieren"
          >
            <RefreshCw className={`h-4 w-4 ${isFetching ? 'animate-spin' : ''}`} />
          </Button>
        </div>
      </CardHeader>

      <CardContent>
        {isLoading ? (
          <TableSkeleton />
        ) : !data || data.logs.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
            <FileText className="h-12 w-12 mb-4" />
            <p>Keine Audit-Einträge gefunden</p>
          </div>
        ) : (
          <>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[40px]" />
                  <TableHead className="w-[110px]">Zeit</TableHead>
                  <TableHead className="w-[180px]">Benutzer</TableHead>
                  <TableHead className="w-[150px]">Aktion</TableHead>
                  <TableHead className="w-[120px]">Ressource</TableHead>
                  <TableHead className="w-[120px]">Status</TableHead>
                  <TableHead className="w-[100px]">IP</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.logs.map((log) => (
                  <LogRow key={log.id} log={log} />
                ))}
              </TableBody>
            </Table>

            {/* Pagination */}
            {data.total_pages > 1 && (
              <div className="flex items-center justify-between mt-4 pt-4 border-t">
                <div className="text-sm text-muted-foreground">
                  Seite {data.page} von {data.total_pages}
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handlePageChange(data.page - 1)}
                    disabled={data.page <= 1}
                  >
                    Zurück
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handlePageChange(data.page + 1)}
                    disabled={data.page >= data.total_pages}
                  >
                    Weiter
                  </Button>
                </div>
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}

export default AuditLogTable;
