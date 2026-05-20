/**
 * Job History Tab
 *
 * Historie aller abgeschlossenen und fehlgeschlagenen Jobs.
 * Mit Filterung, Pagination und Export.
 */

import { useState, useMemo } from 'react';
import {
  Ban,
  Calendar,
  CheckCircle2,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  Clock,
  Download,
  FileText,
  Filter,
  Loader2,
  MoreHorizontal,
  RefreshCw,
  RotateCcw,
  Search,
  XCircle,
} from 'lucide-react';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';

import { useJobHistory } from '../../hooks/use-jobs-query';
import { useRetryJob } from '../../hooks/use-job-mutations';
import { useJobPermissions } from '../../hooks/use-job-permissions';
import { JOB_STATUS_CONFIG, JOB_TYPE_CONFIG, type Job, type JobStatus } from '../../types/job-types';
import { JobDetailModal } from '../modals/JobDetailModal';

// ==================== Helper Functions ====================

function formatDuration(ms?: number): string {
  if (!ms) return '-';
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  if (ms < 3600000) return `${(ms / 60000).toFixed(1)}min`;
  return `${(ms / 3600000).toFixed(1)}h`;
}

function formatDateTime(dateString?: string): string {
  if (!dateString) return '-';
  return new Date(dateString).toLocaleString('de-DE', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function getStatusIcon(status: JobStatus) {
  const icons = {
    pending: <Clock className="h-4 w-4" />,
    queued: <Clock className="h-4 w-4" />,
    processing: <Loader2 className="h-4 w-4" />,
    completed: <CheckCircle2 className="h-4 w-4" />,
    failed: <XCircle className="h-4 w-4" />,
    cancelled: <Ban className="h-4 w-4" />,
  };
  return icons[status] || <Clock className="h-4 w-4" />;
}

function getStatusVariant(status: JobStatus): 'default' | 'secondary' | 'destructive' | 'outline' {
  const variants: Record<JobStatus, 'default' | 'secondary' | 'destructive' | 'outline'> = {
    pending: 'secondary',
    queued: 'secondary',
    processing: 'default',
    completed: 'outline',
    failed: 'destructive',
    cancelled: 'outline',
  };
  return variants[status] || 'default';
}

// ==================== Main Component ====================

export function JobHistoryTab() {
  const [page, setPage] = useState(1);
  const [perPage, setPerPage] = useState(20);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [typeFilter, setTypeFilter] = useState<string>('all');
  const [dateRange, setDateRange] = useState<'7d' | '30d' | '90d' | 'all'>('7d');
  const [sortBy, setSortBy] = useState<'completed_at' | 'created_at'>('completed_at');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');
  const [detailJobId, setDetailJobId] = useState<string | null>(null);

  const permissions = useJobPermissions();

  // Berechne Datumsfilter
  const dateFilters = useMemo(() => {
    const now = new Date();
    let createdFrom: string | undefined;

    switch (dateRange) {
      case '7d':
        createdFrom = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000).toISOString();
        break;
      case '30d':
        createdFrom = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000).toISOString();
        break;
      case '90d':
        createdFrom = new Date(now.getTime() - 90 * 24 * 60 * 60 * 1000).toISOString();
        break;
      default:
        createdFrom = undefined;
    }

    return { createdFrom };
  }, [dateRange]);

  // Query
  const { data, isLoading, refetch } = useJobHistory({
    page,
    perPage,
    filters: {
      status:
        statusFilter !== 'all'
          ? (statusFilter as JobStatus)
          : undefined,
      jobType: typeFilter !== 'all' ? (typeFilter as Job['jobType']) : undefined,
      createdFrom: dateFilters.createdFrom,
    },
  });

  // Mutation
  const retryJob = useRetryJob();

  // Lokale Suche
  const filteredJobs = useMemo(() => {
    if (!data?.jobs) return [];
    if (!searchQuery) return data.jobs;

    const query = searchQuery.toLowerCase();
    return data.jobs.filter(
      (job) =>
        job.id.toLowerCase().includes(query) ||
        job.documentFilename?.toLowerCase().includes(query) ||
        job.userEmail?.toLowerCase().includes(query) ||
        job.errorMessage?.toLowerCase().includes(query)
    );
  }, [data?.jobs, searchQuery]);

  // Nur abgeschlossene Jobs
  const historyJobs = useMemo(() => {
    return filteredJobs.filter(
      (job) =>
        job.status === 'completed' || job.status === 'failed' || job.status === 'cancelled'
    );
  }, [filteredJobs]);

  const toggleSort = (column: 'completed_at' | 'created_at') => {
    if (sortBy === column) {
      setSortOrder((prev) => (prev === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortBy(column);
      setSortOrder('desc');
    }
  };

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex flex-wrap items-center gap-2">
          {/* Suche */}
          <div className="relative">
            <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Suche nach ID, Dokument, Fehler..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-8 w-[250px]"
            />
          </div>

          {/* Status Filter */}
          <Select value={statusFilter} onValueChange={setStatusFilter}>
            <SelectTrigger className="w-[150px]">
              <SelectValue placeholder="Status" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Alle Status</SelectItem>
              <SelectItem value="completed">Abgeschlossen</SelectItem>
              <SelectItem value="failed">Fehlgeschlagen</SelectItem>
              <SelectItem value="cancelled">Abgebrochen</SelectItem>
            </SelectContent>
          </Select>

          {/* Type Filter */}
          <Select value={typeFilter} onValueChange={setTypeFilter}>
            <SelectTrigger className="w-[150px]">
              <SelectValue placeholder="Typ" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Alle Typen</SelectItem>
              {Object.entries(JOB_TYPE_CONFIG).map(([type, config]) => (
                <SelectItem key={type} value={type}>
                  {config.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          {/* Date Range */}
          <Select value={dateRange} onValueChange={(v) => setDateRange(v as typeof dateRange)}>
            <SelectTrigger className="w-[150px]">
              <Calendar className="h-4 w-4 mr-2" />
              <SelectValue placeholder="Zeitraum" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="7d">Letzte 7 Tage</SelectItem>
              <SelectItem value="30d">Letzte 30 Tage</SelectItem>
              <SelectItem value="90d">Letzte 90 Tage</SelectItem>
              <SelectItem value="all">Alle</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="flex items-center gap-2">
          {/* Refresh */}
          <Button variant="outline" size="sm" onClick={() => refetch()}>
            <RefreshCw className="h-4 w-4 mr-2" />
            Aktualisieren
          </Button>
        </div>
      </div>

      {/* Table */}
      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Status</TableHead>
                <TableHead>Job-Typ</TableHead>
                <TableHead>Dokument / Beschreibung</TableHead>
                <TableHead>Benutzer</TableHead>
                <TableHead>Dauer</TableHead>
                <TableHead
                  className="cursor-pointer hover:text-foreground"
                  onClick={() => toggleSort('completed_at')}
                >
                  <div className="flex items-center gap-1">
                    Abgeschlossen
                    {sortBy === 'completed_at' &&
                      (sortOrder === 'asc' ? (
                        <ChevronUp className="h-4 w-4" />
                      ) : (
                        <ChevronDown className="h-4 w-4" />
                      ))}
                  </div>
                </TableHead>
                <TableHead>Ergebnis / Fehler</TableHead>
                <TableHead className="w-[50px]"></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? (
                [...Array(5)].map((_, i) => (
                  <TableRow key={i}>
                    <TableCell>
                      <Skeleton className="h-6 w-24" />
                    </TableCell>
                    <TableCell>
                      <Skeleton className="h-6 w-16" />
                    </TableCell>
                    <TableCell>
                      <Skeleton className="h-4 w-48" />
                    </TableCell>
                    <TableCell>
                      <Skeleton className="h-4 w-32" />
                    </TableCell>
                    <TableCell>
                      <Skeleton className="h-4 w-16" />
                    </TableCell>
                    <TableCell>
                      <Skeleton className="h-4 w-24" />
                    </TableCell>
                    <TableCell>
                      <Skeleton className="h-4 w-32" />
                    </TableCell>
                    <TableCell>
                      <Skeleton className="h-8 w-8" />
                    </TableCell>
                  </TableRow>
                ))
              ) : historyJobs.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={8} className="h-32">
                    <div className="flex flex-col items-center justify-center text-center">
                      <Clock className="h-12 w-12 text-muted-foreground/50 mb-2" />
                      <p className="text-lg font-medium">Keine Historie gefunden</p>
                      <p className="text-sm text-muted-foreground">
                        Es wurden keine abgeschlossenen Jobs im gewählten Zeitraum gefunden.
                      </p>
                    </div>
                  </TableCell>
                </TableRow>
              ) : (
                historyJobs.map((job) => {
                  const statusConfig = JOB_STATUS_CONFIG[job.status];
                  const typeConfig = JOB_TYPE_CONFIG[job.jobType];

                  return (
                    <TableRow
                      key={job.id}
                      className="cursor-pointer hover:bg-muted/50"
                      onClick={() => setDetailJobId(job.id)}
                    >
                      <TableCell>
                        <Badge variant={getStatusVariant(job.status)} className="gap-1">
                          {getStatusIcon(job.status)}
                          {statusConfig?.label ?? job.status}
                        </Badge>
                      </TableCell>

                      <TableCell>
                        <Badge variant="outline">{typeConfig?.label ?? job.jobType}</Badge>
                      </TableCell>

                      <TableCell>
                        <div className="flex items-center gap-2 max-w-[200px]">
                          <FileText className="h-4 w-4 text-muted-foreground shrink-0" />
                          <span className="truncate">
                            {job.documentFilename || job.message || '-'}
                          </span>
                        </div>
                      </TableCell>

                      <TableCell>
                        <span className="text-sm text-muted-foreground">
                          {job.userEmail || '-'}
                        </span>
                      </TableCell>

                      <TableCell>
                        <span className="text-sm">{formatDuration(job.durationMs)}</span>
                      </TableCell>

                      <TableCell>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <span className="text-sm text-muted-foreground cursor-help">
                              {formatDateTime(job.completedAt)}
                            </span>
                          </TooltipTrigger>
                          <TooltipContent>
                            Erstellt: {formatDateTime(job.createdAt)}
                            <br />
                            Gestartet: {formatDateTime(job.startedAt)}
                          </TooltipContent>
                        </Tooltip>
                      </TableCell>

                      <TableCell>
                        {job.errorMessage ? (
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <span className="text-sm text-destructive truncate max-w-[200px] block cursor-help">
                                {job.errorMessage}
                              </span>
                            </TooltipTrigger>
                            <TooltipContent className="max-w-[400px]">
                              {job.errorMessage}
                            </TooltipContent>
                          </Tooltip>
                        ) : (
                          <span className="text-sm text-green-600">Erfolgreich</span>
                        )}
                      </TableCell>

                      <TableCell onClick={(e) => e.stopPropagation()}>
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button variant="ghost" size="icon">
                              <MoreHorizontal className="h-4 w-4" />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            <DropdownMenuLabel>Aktionen</DropdownMenuLabel>
                            <DropdownMenuSeparator />

                            {permissions.canManage && job.status === 'failed' && (
                              <DropdownMenuItem
                                onClick={() => retryJob.mutate({ jobId: job.id })}
                              >
                                <RotateCcw className="h-4 w-4 mr-2" />
                                Wiederholen
                              </DropdownMenuItem>
                            )}

                            <DropdownMenuItem onClick={() => setDetailJobId(job.id)}>
                              <FileText className="h-4 w-4 mr-2" />
                              Details anzeigen
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </TableCell>
                    </TableRow>
                  );
                })
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* Pagination */}
      {data && data.totalPages > 1 && (
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-sm text-muted-foreground">
              Zeige {(page - 1) * perPage + 1} - {Math.min(page * perPage, data.total)} von{' '}
              {data.total} Einträgen
            </span>

            <Select
              value={perPage.toString()}
              onValueChange={(v) => {
                setPerPage(Number(v));
                setPage(1);
              }}
            >
              <SelectTrigger className="w-[80px] h-8">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="10">10</SelectItem>
                <SelectItem value="20">20</SelectItem>
                <SelectItem value="50">50</SelectItem>
                <SelectItem value="100">100</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page <= 1}
            >
              <ChevronLeft className="h-4 w-4" />
              Zurück
            </Button>
            <span className="text-sm text-muted-foreground">
              Seite {page} von {data.totalPages}
            </span>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage((p) => Math.min(data.totalPages, p + 1))}
              disabled={page >= data.totalPages}
            >
              Weiter
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      )}

      {/* Detail Modal */}
      <JobDetailModal
        jobId={detailJobId}
        open={!!detailJobId}
        onOpenChange={(open) => !open && setDetailJobId(null)}
      />
    </div>
  );
}

export default JobHistoryTab;
