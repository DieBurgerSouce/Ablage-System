/**
 * Active Jobs Tab
 *
 * Live-Tabelle mit allen aktiven Jobs (processing + queued).
 * Mit Bulk-Aktionen, Filterung und Sortierung.
 *
 * Accessibility Features:
 * - ARIA live region for status updates
 * - Keyboard navigation for table rows
 * - Screen reader-friendly labels
 * - Focus management for modals
 */

import { useState, useMemo, useCallback, useEffect } from 'react';
import { Ban, CheckCircle2, ChevronDown, ChevronUp, Clock, FileText, Loader2, MoreHorizontal, Pause, Play, RefreshCw, Search, Skull, XCircle, Zap } from 'lucide-react';
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
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { Progress } from '@/components/ui/progress';
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
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';

import { useJobsList } from '../../hooks/use-jobs-query';
import {
  useCancelJob,
  useRetryJob,
  usePauseJob,
  useResumeJob,
  useForceKillJob,
  useBulkCancelJobs,
  useBulkChangePriority,
} from '../../hooks/use-job-mutations';
import { useJobPermissions } from '../../hooks/use-job-permissions';
import { JOB_STATUS_CONFIG, JOB_TYPE_CONFIG, type Job, type JobStatus } from '../../types/job-types';
import { JobDetailModal, BulkActionDialog, PriorityChangeModal } from '../modals';
import { isHighPriority } from '../../constants/thresholds';

// ==================== Helper Functions ====================

function formatRelativeTime(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffSecs = Math.floor(diffMs / 1000);
  const diffMins = Math.floor(diffSecs / 60);
  const diffHours = Math.floor(diffMins / 60);

  if (diffSecs < 60) return `vor ${diffSecs}s`;
  if (diffMins < 60) return `vor ${diffMins}min`;
  if (diffHours < 24) return `vor ${diffHours}h`;
  return date.toLocaleDateString('de-DE');
}

function getStatusIcon(status: JobStatus) {
  const icons = {
    pending: <Clock className="h-4 w-4" />,
    queued: <Clock className="h-4 w-4" />,
    processing: <Loader2 className="h-4 w-4 animate-spin" />,
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

export function ActiveJobsTab() {
  const [selectedJobs, setSelectedJobs] = useState<string[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [typeFilter, setTypeFilter] = useState<string>('all');
  const [sortBy, setSortBy] = useState<'created_at' | 'priority'>('created_at');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');
  const [detailJobId, setDetailJobId] = useState<string | null>(null);
  const [bulkCancelOpen, setBulkCancelOpen] = useState(false);
  const [priorityModalOpen, setPriorityModalOpen] = useState(false);

  const permissions = useJobPermissions();

  // Query für aktive Jobs
  const { data, isLoading, refetch } = useJobsList({
    page: 1,
    perPage: 100,
    filters: {
      status: statusFilter !== 'all' ? (statusFilter as JobStatus) : undefined,
      jobType: typeFilter !== 'all' ? (typeFilter as Job['jobType']) : undefined,
    },
    sortBy,
    sortOrder,
  });

  // Mutations
  const cancelJob = useCancelJob();
  const retryJob = useRetryJob();
  const pauseJob = usePauseJob();
  const resumeJob = useResumeJob();
  const forceKillJob = useForceKillJob();
  const bulkCancelJobs = useBulkCancelJobs();
  const bulkChangePriority = useBulkChangePriority();

  // Filter Jobs lokal nach Suchbegriff
  const filteredJobs = useMemo(() => {
    if (!data?.jobs) return [];
    if (!searchQuery) return data.jobs;

    const query = searchQuery.toLowerCase();
    return data.jobs.filter(
      (job) =>
        job.id.toLowerCase().includes(query) ||
        job.documentFilename?.toLowerCase().includes(query) ||
        job.userEmail?.toLowerCase().includes(query) ||
        job.jobType.toLowerCase().includes(query)
    );
  }, [data?.jobs, searchQuery]);

  // Aktive Jobs (nicht abgeschlossen)
  const activeJobs = useMemo(() => {
    return filteredJobs.filter(
      (job) => job.status === 'processing' || job.status === 'queued' || job.status === 'pending'
    );
  }, [filteredJobs]);

  // Sync selection state with data - remove selected jobs that no longer exist
  useEffect(() => {
    if (selectedJobs.length > 0 && activeJobs.length > 0) {
      const activeJobIds = new Set(activeJobs.map((job) => job.id));
      const validSelectedJobs = selectedJobs.filter((id) => activeJobIds.has(id));

      // Only update if there are stale selections
      if (validSelectedJobs.length !== selectedJobs.length) {
        setSelectedJobs(validSelectedJobs);
      }
    }
  }, [activeJobs, selectedJobs]);

  // Handlers
  const handleSelectAll = (checked: boolean) => {
    if (checked) {
      setSelectedJobs(activeJobs.map((job) => job.id));
    } else {
      setSelectedJobs([]);
    }
  };

  const handleSelectJob = (jobId: string, checked: boolean) => {
    if (checked) {
      setSelectedJobs((prev) => [...prev, jobId]);
    } else {
      setSelectedJobs((prev) => prev.filter((id) => id !== jobId));
    }
  };

  const handleBulkCancel = async (): Promise<{ success: number; failed: number }> => {
    return new Promise((resolve, reject) => {
      bulkCancelJobs.mutate(
        { jobIds: selectedJobs },
        {
          onSuccess: (data) => {
            setSelectedJobs([]);
            resolve({ success: data?.cancelledCount ?? selectedJobs.length, failed: 0 });
          },
          onError: (error) => {
            reject(error);
          },
        }
      );
    });
  };

  const handleBulkPriorityChange = async (newPriority: number): Promise<void> => {
    return new Promise((resolve, reject) => {
      bulkChangePriority.mutate(
        { jobIds: selectedJobs, priority: newPriority },
        {
          onSuccess: () => {
            setSelectedJobs([]);
            resolve();
          },
          onError: (error) => {
            reject(error);
          },
        }
      );
    });
  };

  const toggleSort = (column: 'created_at' | 'priority') => {
    if (sortBy === column) {
      setSortOrder((prev) => (prev === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortBy(column);
      setSortOrder('desc');
    }
  };

  const isAllSelected = activeJobs.length > 0 && selectedJobs.length === activeJobs.length;
  const isSomeSelected = selectedJobs.length > 0 && selectedJobs.length < activeJobs.length;

  // Keyboard navigation handler for table rows
  const handleRowKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTableRowElement>, jobId: string) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        setDetailJobId(jobId);
      }
    },
    []
  );

  return (
    <div className="space-y-4" role="region" aria-label="Aktive Jobs Verwaltung">
      {/* Screen reader live region for status updates */}
      <div
        role="status"
        aria-live="polite"
        aria-atomic="true"
        className="sr-only"
      >
        {activeJobs.length} aktive Jobs geladen
        {selectedJobs.length > 0 && `, ${selectedJobs.length} ausgewählt`}
      </div>

      {/* Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex flex-wrap items-center gap-2">
          {/* Suche - Fix 8: aria-label für WCAG 2.1 AA */}
          <div className="relative">
            <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" aria-hidden="true" />
            <Input
              placeholder="Suche nach ID, Dokument, User..."
              aria-label="Jobs durchsuchen nach ID, Dokument oder Benutzer"
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
              <SelectItem value="processing">In Bearbeitung</SelectItem>
              <SelectItem value="queued">In Warteschlange</SelectItem>
              <SelectItem value="pending">Wartend</SelectItem>
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
        </div>

        <div className="flex items-center gap-2">
          {/* Bulk Actions */}
          {selectedJobs.length > 0 && permissions.canBulkActions && (
            <>
              <Button
                variant="destructive"
                size="sm"
                onClick={() => setBulkCancelOpen(true)}
                disabled={bulkCancelJobs.isPending}
              >
                {bulkCancelJobs.isPending ? (
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                ) : (
                  <XCircle className="h-4 w-4 mr-2" />
                )}
                {selectedJobs.length} abbrechen
              </Button>

              {permissions.canChangePriority && (
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => setPriorityModalOpen(true)}
                  disabled={bulkChangePriority.isPending}
                >
                  {bulkChangePriority.isPending ? (
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  ) : (
                    <Zap className="h-4 w-4 mr-2" />
                  )}
                  Priorität ändern
                </Button>
              )}
            </>
          )}

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
                {permissions.canBulkActions && (
                  <TableHead className="w-[50px]">
                    <Checkbox
                      checked={isAllSelected}
                      onCheckedChange={handleSelectAll}
                      aria-label="Alle auswählen"
                    />
                  </TableHead>
                )}
                <TableHead>Status</TableHead>
                <TableHead>Job-Typ</TableHead>
                <TableHead>Dokument / Beschreibung</TableHead>
                <TableHead>Benutzer</TableHead>
                <TableHead
                  className="cursor-pointer hover:text-foreground"
                  onClick={() => toggleSort('priority')}
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      toggleSort('priority');
                    }
                  }}
                  aria-sort={
                    sortBy === 'priority'
                      ? sortOrder === 'asc'
                        ? 'ascending'
                        : 'descending'
                      : 'none'
                  }
                  role="columnheader"
                >
                  <div className="flex items-center gap-1">
                    Priorität
                    {sortBy === 'priority' &&
                      (sortOrder === 'asc' ? (
                        <ChevronUp className="h-4 w-4" aria-hidden="true" />
                      ) : (
                        <ChevronDown className="h-4 w-4" aria-hidden="true" />
                      ))}
                    <span className="sr-only">
                      {sortBy === 'priority'
                        ? sortOrder === 'asc'
                          ? ', aufsteigend sortiert'
                          : ', absteigend sortiert'
                        : ', Klicken zum Sortieren'}
                    </span>
                  </div>
                </TableHead>
                <TableHead>Fortschritt</TableHead>
                <TableHead
                  className="cursor-pointer hover:text-foreground"
                  onClick={() => toggleSort('created_at')}
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      toggleSort('created_at');
                    }
                  }}
                  aria-sort={
                    sortBy === 'created_at'
                      ? sortOrder === 'asc'
                        ? 'ascending'
                        : 'descending'
                      : 'none'
                  }
                  role="columnheader"
                >
                  <div className="flex items-center gap-1">
                    Gestartet
                    {sortBy === 'created_at' &&
                      (sortOrder === 'asc' ? (
                        <ChevronUp className="h-4 w-4" aria-hidden="true" />
                      ) : (
                        <ChevronDown className="h-4 w-4" aria-hidden="true" />
                      ))}
                    <span className="sr-only">
                      {sortBy === 'created_at'
                        ? sortOrder === 'asc'
                          ? ', aufsteigend sortiert'
                          : ', absteigend sortiert'
                        : ', Klicken zum Sortieren'}
                    </span>
                  </div>
                </TableHead>
                <TableHead className="w-[50px]"></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? (
                // Loading State
                [...Array(5)].map((_, i) => (
                  <TableRow key={i}>
                    {permissions.canBulkActions && (
                      <TableCell>
                        <Skeleton className="h-4 w-4" />
                      </TableCell>
                    )}
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
                      <Skeleton className="h-6 w-12" />
                    </TableCell>
                    <TableCell>
                      <Skeleton className="h-4 w-24" />
                    </TableCell>
                    <TableCell>
                      <Skeleton className="h-4 w-16" />
                    </TableCell>
                    <TableCell>
                      <Skeleton className="h-8 w-8" />
                    </TableCell>
                  </TableRow>
                ))
              ) : activeJobs.length === 0 ? (
                // Empty State
                <TableRow>
                  <TableCell colSpan={permissions.canBulkActions ? 9 : 8} className="h-32">
                    <div className="flex flex-col items-center justify-center text-center">
                      <CheckCircle2 className="h-12 w-12 text-muted-foreground/50 mb-2" />
                      <p className="text-lg font-medium">Keine aktiven Jobs</p>
                      <p className="text-sm text-muted-foreground">
                        Alle Jobs sind abgeschlossen oder es wurden keine gefunden.
                      </p>
                    </div>
                  </TableCell>
                </TableRow>
              ) : (
                // Job Rows
                activeJobs.map((job) => {
                  const statusConfig = JOB_STATUS_CONFIG[job.status];
                  const typeConfig = JOB_TYPE_CONFIG[job.jobType];
                  const isSelected = selectedJobs.includes(job.id);

                  return (
                    <TableRow
                      key={job.id}
                      className={isSelected ? 'bg-muted/50' : undefined}
                      onClick={() => setDetailJobId(job.id)}
                      onKeyDown={(e) => handleRowKeyDown(e, job.id)}
                      tabIndex={0}
                      role="row"
                      aria-selected={isSelected}
                      aria-label={`Job ${job.documentFilename || job.id}, Status: ${statusConfig?.label || job.status}, Typ: ${typeConfig?.label || job.jobType}`}
                    >
                      {permissions.canBulkActions && (
                        <TableCell onClick={(e) => e.stopPropagation()}>
                          <Checkbox
                            checked={isSelected}
                            onCheckedChange={(checked) =>
                              handleSelectJob(job.id, checked as boolean)
                            }
                            aria-label={`Job ${job.id} auswählen`}
                          />
                        </TableCell>
                      )}

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
                        <Badge
                          variant={isHighPriority(job.priority) ? 'destructive' : 'secondary'}
                        >
                          {job.priority}
                        </Badge>
                      </TableCell>

                      <TableCell>
                        {job.progress !== undefined ? (
                          <div className="flex items-center gap-2 min-w-[100px]">
                            <Progress
                              value={job.progress}
                              className="h-2 flex-1"
                              aria-label={`Fortschritt ${job.progress.toFixed(0)} Prozent`}
                              aria-valuenow={job.progress}
                              aria-valuemin={0}
                              aria-valuemax={100}
                            />
                            <span
                              className="text-xs text-muted-foreground w-10"
                              aria-hidden="true"
                            >
                              {job.progress.toFixed(0)}%
                            </span>
                          </div>
                        ) : (
                          <span className="text-sm text-muted-foreground">-</span>
                        )}
                      </TableCell>

                      <TableCell>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <span className="text-sm text-muted-foreground cursor-help">
                              {job.startedAt
                                ? formatRelativeTime(job.startedAt)
                                : formatRelativeTime(job.createdAt)}
                            </span>
                          </TooltipTrigger>
                          <TooltipContent>
                            {new Date(job.startedAt || job.createdAt).toLocaleString('de-DE')}
                          </TooltipContent>
                        </Tooltip>
                      </TableCell>

                      <TableCell onClick={(e) => e.stopPropagation()}>
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button
                              variant="ghost"
                              size="icon"
                              aria-label={`Aktionen für Job ${job.documentFilename || job.id}`}
                            >
                              <MoreHorizontal className="h-4 w-4" aria-hidden="true" />
                              <span className="sr-only">Aktionen öffnen</span>
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            <DropdownMenuLabel>Aktionen</DropdownMenuLabel>
                            <DropdownMenuSeparator />

                            {permissions.canManage && (
                              <DropdownMenuItem
                                onClick={() => cancelJob.mutate({ jobId: job.id })}
                                className="text-destructive"
                              >
                                <XCircle className="h-4 w-4 mr-2" />
                                Abbrechen
                              </DropdownMenuItem>
                            )}

                            {permissions.canPauseResume && job.status === 'processing' && (
                              <DropdownMenuItem onClick={() => pauseJob.mutate(job.id)}>
                                <Pause className="h-4 w-4 mr-2" />
                                Pausieren
                              </DropdownMenuItem>
                            )}

                            {permissions.canPauseResume && job.isPaused && (
                              <DropdownMenuItem onClick={() => resumeJob.mutate(job.id)}>
                                <Play className="h-4 w-4 mr-2" />
                                Fortsetzen
                              </DropdownMenuItem>
                            )}

                            {permissions.canForceKill && job.status === 'processing' && (
                              <>
                                <DropdownMenuSeparator />
                                <DropdownMenuItem
                                  onClick={() => forceKillJob.mutate(job.id)}
                                  className="text-destructive"
                                >
                                  <Skull className="h-4 w-4 mr-2" />
                                  Force Kill
                                </DropdownMenuItem>
                              </>
                            )}
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

      {/* Summary */}
      {!isLoading && (
        <div className="flex items-center justify-between text-sm text-muted-foreground">
          <span>
            {activeJobs.length} aktive Jobs
            {selectedJobs.length > 0 && ` (${selectedJobs.length} ausgewählt)`}
          </span>
          <span>Automatische Aktualisierung alle 5 Sekunden</span>
        </div>
      )}

      {/* Bulk Cancel Dialog - Enterprise Version */}
      <BulkActionDialog
        open={bulkCancelOpen}
        onOpenChange={setBulkCancelOpen}
        actionType="cancel"
        selectedCount={selectedJobs.length}
        onConfirm={handleBulkCancel}
        isLoading={bulkCancelJobs.isPending}
      />

      {/* Priority Change Modal */}
      <PriorityChangeModal
        open={priorityModalOpen}
        onOpenChange={setPriorityModalOpen}
        jobCount={selectedJobs.length}
        onConfirm={handleBulkPriorityChange}
        isLoading={bulkChangePriority.isPending}
      />

      {/* Detail Modal */}
      <JobDetailModal
        jobId={detailJobId}
        open={!!detailJobId}
        onOpenChange={(open) => !open && setDetailJobId(null)}
      />
    </div>
  );
}

export default ActiveJobsTab;
