/**
 * ValidationQueueDashboard
 *
 * Enterprise-Grade Validierungs-Queue Dashboard.
 * Zeigt die Warteschlange mit Filtern, Batch-Operationen und Quick-Stats.
 *
 * Layout:
 * - Stats Cards oben (Ausstehend, Heute geprüft, Kritisch, Approval Rate)
 * - Tabs: Warteschlange | Meine Items | Batch | Regeln | Statistiken
 * - Filter-Panel links, Tabelle rechts
 * - Batch-Actions-Bar unten bei Selektion
 */

import { useState, useMemo, useCallback } from 'react';
import { useNavigate } from '@tanstack/react-router';
import { logger } from '@/lib/logger';
import {
  CheckCircle,
  Clock,
  AlertTriangle,
  Filter,
  RefreshCw,
  Search,
  ChevronLeft,
  ChevronRight,
  Users,
  BarChart3,
  Settings2,
  ListChecks,
  UserCheck,
  XCircle,
  ArrowUpDown,
  MoreHorizontal,
  Eye,
  UserPlus,
  Trash2,
  WifiOff,
  RotateCcw,
} from 'lucide-react';
import { toast } from 'sonner';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { useOnlineStatus } from '@/lib/hooks/use-online-status';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { usePermissions } from '@/lib/auth/hooks/use-permissions';
import {
  useValidationQueue,
  useQueueStats,
  useMyAssignedItems,
  useApproveQueueItem,
  useRejectQueueItem,
  useBatchApprove,
  useBatchReject,
  useBatchAssign,
  useDeleteQueueItem,
  useAnalyticsOverview,
} from '../hooks/use-validation-queue';
import {
  ValidationStatus,
  SampleSource,
  VALIDATION_STATUS_LABELS,
  SAMPLE_SOURCE_LABELS,
  getValidationStatusColor,
  getConfidenceColor,
  getPriorityColor,
} from '../types/validation-queue.types';
import type { ValidationQueueItem, ValidationQueueFilters } from '../types/validation-queue.types';
import { RejectReasonDialog } from './RejectReasonDialog';
import { BulkApproveDialog } from './BulkApproveDialog';
import { AssignEditorDialog } from './AssignEditorDialog';
import type { RejectionCategory } from '../types/validation-queue.types';
import { RulesManager } from './RulesManager';
import { AnalyticsDashboard } from './AnalyticsDashboard';

const PAGE_SIZE = 20;

const DOCUMENT_TYPES = [
  { value: 'all', label: 'Alle Typen' },
  { value: 'invoice', label: 'Rechnungen' },
  { value: 'delivery_note', label: 'Lieferscheine' },
  { value: 'contract', label: 'Verträge' },
  { value: 'letter', label: 'Briefe' },
  { value: 'order', label: 'Bestellungen' },
  { value: 'receipt', label: 'Kassenbelege' },
];

const STATUS_OPTIONS = [
  { value: 'all', label: 'Alle Status' },
  { value: ValidationStatus.PENDING, label: VALIDATION_STATUS_LABELS[ValidationStatus.PENDING] },
  { value: ValidationStatus.IN_PROGRESS, label: VALIDATION_STATUS_LABELS[ValidationStatus.IN_PROGRESS] },
  { value: ValidationStatus.APPROVED, label: VALIDATION_STATUS_LABELS[ValidationStatus.APPROVED] },
  { value: ValidationStatus.REJECTED, label: VALIDATION_STATUS_LABELS[ValidationStatus.REJECTED] },
];

const SOURCE_OPTIONS = [
  { value: 'all', label: 'Alle Quellen' },
  { value: SampleSource.AUTOMATIC, label: SAMPLE_SOURCE_LABELS[SampleSource.AUTOMATIC] },
  { value: SampleSource.RULE_BASED, label: SAMPLE_SOURCE_LABELS[SampleSource.RULE_BASED] },
  { value: SampleSource.LOW_CONFIDENCE, label: SAMPLE_SOURCE_LABELS[SampleSource.LOW_CONFIDENCE] },
  { value: SampleSource.MANUAL, label: SAMPLE_SOURCE_LABELS[SampleSource.MANUAL] },
];

const SORT_OPTIONS = [
  { value: 'created_at:desc', label: 'Neueste zuerst' },
  { value: 'created_at:asc', label: 'Älteste zuerst' },
  { value: 'priority:desc', label: 'Höchste Priorität' },
  { value: 'priority:asc', label: 'Niedrigste Priorität' },
  { value: 'avg_field_confidence:asc', label: 'Niedrigste Konfidenz' },
  { value: 'avg_field_confidence:desc', label: 'Höchste Konfidenz' },
];

/**
 * Inner Dashboard Component - wrapped with ErrorBoundary
 */
function ValidationQueueDashboardInner() {
  const navigate = useNavigate();
  const { isAdmin, canAccess } = usePermissions();

  // Online Status Detection
  const { isOnline, offlineSince } = useOnlineStatus({
    onOffline: () => {
      toast.error('Verbindung verloren. Einige Funktionen sind eingeschränkt.');
    },
    onOnline: () => {
      toast.success('Verbindung wiederhergestellt.');
    },
  });

  // State
  const [activeTab, setActiveTab] = useState('queue');
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('pending');
  const [documentTypeFilter, setDocumentTypeFilter] = useState('all');
  const [sourceFilter, setSourceFilter] = useState('all');
  const [sortOption, setSortOption] = useState('created_at:desc');
  const [page, setPage] = useState(0);
  const [selectedItems, setSelectedItems] = useState<string[]>([]);

  // Dialog States
  const [rejectDialogOpen, setRejectDialogOpen] = useState(false);
  const [rejectDialogItem, setRejectDialogItem] = useState<string | null>(null);
  const [bulkApproveDialogOpen, setBulkApproveDialogOpen] = useState(false);
  const [assignDialogOpen, setAssignDialogOpen] = useState(false);

  // Parse sort option
  const [sortBy, sortOrder] = sortOption.split(':') as [string, 'asc' | 'desc'];

  // Build filters
  const filters: ValidationQueueFilters & { sort_by?: string; sort_order?: string } = {
    status: statusFilter === 'all' ? undefined : (statusFilter as ValidationStatus),
    document_type: documentTypeFilter === 'all' ? undefined : documentTypeFilter,
    sample_source: sourceFilter === 'all' ? undefined : (sourceFilter as SampleSource),
    search: searchQuery.trim() || undefined, // Multi-Feld-Suche (document_name, document_type, notes)
    sort_by: sortBy,
    sort_order: sortOrder,
  };

  // Queries
  const {
    data: queueData,
    isLoading,
    error,
    refetch,
  } = useValidationQueue({
    ...filters,
    limit: PAGE_SIZE,
    offset: page * PAGE_SIZE,
  });

  const { data: statsData, isLoading: isLoadingStats } = useQueueStats();
  const { data: analyticsData } = useAnalyticsOverview();
  // Lazy Loading: Nur laden wenn "my-items" Tab aktiv ist
  const { data: myItemsData, isLoading: isLoadingMyItems } = useMyAssignedItems(
    statusFilter === 'all' ? undefined : (statusFilter as ValidationStatus),
    50,
    0,
    activeTab === 'my-items' // Nur laden wenn Tab aktiv
  );

  // Mutations
  const approveItem = useApproveQueueItem();
  const rejectItem = useRejectQueueItem();
  const deleteItem = useDeleteQueueItem();
  const batchApprove = useBatchApprove();
  const batchReject = useBatchReject();
  const batchAssign = useBatchAssign();

  // Handlers - all wrapped with useCallback for performance
  const handleSearch = useCallback((e: React.FormEvent) => {
    e.preventDefault();
    refetch();
  }, [refetch]);

  const handleFilterChange = useCallback(() => {
    setPage(0);
    setSelectedItems([]);
  }, []);

  const handleResetFilters = useCallback(() => {
    setSearchQuery('');
    setStatusFilter('pending');
    setDocumentTypeFilter('all');
    setSourceFilter('all');
    setSortOption('created_at:desc');
    setPage(0);
    setSelectedItems([]);
    toast.info('Filter zurückgesetzt');
  }, []);

  const handleOpenItem = useCallback((itemId: string) => {
    navigate({ to: `/validation-queue/${itemId}` });
  }, [navigate]);

  const handleApprove = useCallback(async (itemId: string) => {
    try {
      await approveItem.mutateAsync({ itemId });
      toast.success('Dokument genehmigt');
    } catch {
      toast.error('Fehler beim Genehmigen');
    }
  }, [approveItem]);

  const handleReject = useCallback((itemId: string) => {
    setRejectDialogItem(itemId);
    setRejectDialogOpen(true);
  }, []);

  const handleRejectConfirm = useCallback(async (reason: string, category?: RejectionCategory) => {
    const targetId = rejectDialogItem;
    if (targetId) {
      // Einzel-Ablehnung
      try {
        await rejectItem.mutateAsync({
          itemId: targetId,
          data: { reason, rejection_category: category },
        });
        toast.success('Dokument abgelehnt');
        setRejectDialogOpen(false);
        setRejectDialogItem(null);
      } catch {
        toast.error('Fehler beim Ablehnen');
      }
    } else if (selectedItems.length > 0) {
      // Batch-Ablehnung
      try {
        const result = await batchReject.mutateAsync({
          item_ids: selectedItems,
          reason,
          rejection_category: category,
        });
        toast.success(`${result.success_count} Dokumente abgelehnt`);
        if (result.failure_count > 0) {
          toast.warning(`${result.failure_count} konnten nicht abgelehnt werden`);
        }
        setRejectDialogOpen(false);
        setSelectedItems([]);
      } catch {
        toast.error('Fehler beim Batch-Ablehnen');
      }
    }
  }, [rejectDialogItem, selectedItems, rejectItem, batchReject]);

  const handleDelete = useCallback(async (itemId: string) => {
    if (window.confirm('Dieses Item wirklich löschen?')) {
      try {
        await deleteItem.mutateAsync(itemId);
        toast.success('Item gelöscht');
      } catch {
        toast.error('Fehler beim Löschen');
      }
    }
  }, [deleteItem]);

  const handleBatchApproveClick = useCallback(() => {
    if (selectedItems.length === 0) return;
    setBulkApproveDialogOpen(true);
  }, [selectedItems.length]);

  const handleBatchApproveConfirm = useCallback(async (notes?: string, applyCorrections?: boolean) => {
    try {
      const result = await batchApprove.mutateAsync({
        item_ids: selectedItems,
        notes,
      });
      toast.success(`${result.success_count} Dokumente genehmigt`);
      if (result.failure_count > 0) {
        toast.warning(`${result.failure_count} konnten nicht genehmigt werden`);
      }
      setBulkApproveDialogOpen(false);
      setSelectedItems([]);
    } catch {
      toast.error('Fehler beim Batch-Genehmigen');
    }
  }, [batchApprove, selectedItems]);

  const handleBatchRejectClick = useCallback(() => {
    if (selectedItems.length === 0) return;
    setRejectDialogItem(null); // null = Batch-Modus
    setRejectDialogOpen(true);
  }, [selectedItems.length]);

  const handleAssignClick = useCallback(() => {
    if (selectedItems.length === 0) return;
    setAssignDialogOpen(true);
  }, [selectedItems.length]);

  const handleAssignConfirm = useCallback(async (editorId: string) => {
    if (selectedItems.length === 0) return;
    try {
      const result = await batchAssign.mutateAsync({
        item_ids: selectedItems,
        editor_id: editorId,
      });
      toast.success(`${result.success_count} Dokumente zugewiesen`);
      if (result.failure_count > 0) {
        toast.warning(`${result.failure_count} konnten nicht zugewiesen werden`);
      }
      setAssignDialogOpen(false);
      setSelectedItems([]);
    } catch {
      toast.error('Fehler beim Zuweisen');
    }
  }, [batchAssign, selectedItems]);

  const handleSelectAll = useCallback((checked: boolean) => {
    if (checked && queueData?.items) {
      setSelectedItems(queueData.items.map((item) => item.id));
    } else {
      setSelectedItems([]);
    }
  }, [queueData?.items]);

  const handleSelectItem = useCallback((itemId: string, checked: boolean) => {
    if (checked) {
      setSelectedItems((prev) => [...prev, itemId]);
    } else {
      setSelectedItems((prev) => prev.filter((id) => id !== itemId));
    }
  }, []);

  // Pagination
  const totalPages = queueData ? Math.ceil(queueData.total / PAGE_SIZE) : 0;
  const canGoPrevious = page > 0;
  const canGoNext = page < totalPages - 1;

  // Stats Cards Data
  const stats = useMemo(() => {
    const s = statsData || {};
    const a = analyticsData || {};
    return {
      pending: s.pending || 0,
      inProgress: s.in_progress || 0,
      todayValidated: a.items_validated_today || 0,
      approvalRate: a.approval_rate ? `${Math.round(a.approval_rate * 100)}%` : '-',
    };
  }, [statsData, analyticsData]);

  // Dynamisches aria-label für Select-All Checkbox
  const selectAllLabel = useMemo(() => {
    if (!queueData?.items.length) return 'Keine Dokumente zum Auswählen';
    if (selectedItems.length === queueData.items.length) {
      return `Alle ${queueData.items.length} Dokumente abwählen`;
    }
    return `Alle ${queueData.items.length} Dokumente auswählen`;
  }, [selectedItems.length, queueData?.items.length]);

  // Aktueller Filter-Status für Screen Reader
  const currentFilterDescription = useMemo(() => {
    const parts: string[] = [];
    if (statusFilter !== 'all') {
      parts.push(`Status: ${VALIDATION_STATUS_LABELS[statusFilter as ValidationStatus]}`);
    }
    if (documentTypeFilter !== 'all') {
      const type = DOCUMENT_TYPES.find(t => t.value === documentTypeFilter);
      parts.push(`Typ: ${type?.label || documentTypeFilter}`);
    }
    if (sourceFilter !== 'all') {
      parts.push(`Quelle: ${SAMPLE_SOURCE_LABELS[sourceFilter as SampleSource]}`);
    }
    return parts.length > 0 ? parts.join(', ') : 'Keine Filter aktiv';
  }, [statusFilter, documentTypeFilter, sourceFilter]);

  // Prüfen ob Filter von Defaults abweichen (für Reset-Button Sichtbarkeit)
  const hasActiveFilters = useMemo(() => {
    return (
      searchQuery !== '' ||
      statusFilter !== 'pending' ||
      documentTypeFilter !== 'all' ||
      sourceFilter !== 'all' ||
      sortOption !== 'created_at:desc'
    );
  }, [searchQuery, statusFilter, documentTypeFilter, sourceFilter, sortOption]);

  return (
    <div className="space-y-6">
      {/* Skip-Links für Accessibility */}
      <div className="sr-only focus-within:not-sr-only focus-within:absolute focus-within:z-50 focus-within:top-0 focus-within:left-0 focus-within:bg-background focus-within:p-4">
        <a
          href="#validation-filters"
          className="focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 rounded px-4 py-2 bg-primary text-primary-foreground"
        >
          Zu den Filtern springen
        </a>
        <a
          href="#validation-table"
          className="ml-2 focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 rounded px-4 py-2 bg-primary text-primary-foreground"
        >
          Zur Tabelle springen
        </a>
      </div>

      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Validierung</h1>
          <p className="text-muted-foreground">
            OCR-Ergebnisse prüfen und Datenextraktion validieren
          </p>
        </div>
        <Button
          onClick={() => refetch()}
          disabled={isLoading}
          variant="outline"
          aria-label="Warteschlange aktualisieren"
        >
          <RefreshCw className={`w-4 h-4 mr-2 ${isLoading ? 'animate-spin' : ''}`} aria-hidden="true" />
          Aktualisieren
        </Button>
      </div>

      {/* Stats Cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Ausstehend</CardTitle>
            <Clock className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            {isLoadingStats ? (
              <Skeleton className="h-8 w-16" />
            ) : (
              <div className="text-2xl font-bold">{stats.pending}</div>
            )}
            <p className="text-xs text-muted-foreground">Dokumente warten auf Prüfung</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">In Bearbeitung</CardTitle>
            <Users className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            {isLoadingStats ? (
              <Skeleton className="h-8 w-16" />
            ) : (
              <div className="text-2xl font-bold">{stats.inProgress}</div>
            )}
            <p className="text-xs text-muted-foreground">Aktiv bearbeitete Items</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Heute geprüft</CardTitle>
            <CheckCircle className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            {isLoadingStats ? (
              <Skeleton className="h-8 w-16" />
            ) : (
              <div className="text-2xl font-bold">{stats.todayValidated}</div>
            )}
            <p className="text-xs text-muted-foreground">Validierungen heute</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Genehmigungsrate</CardTitle>
            <BarChart3 className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            {isLoadingStats ? (
              <Skeleton className="h-8 w-16" />
            ) : (
              <div className="text-2xl font-bold">{stats.approvalRate}</div>
            )}
            <p className="text-xs text-muted-foreground">Durchschnittliche Quote</p>
          </CardContent>
        </Card>
      </div>

      {/* Main Content with Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="queue" className="gap-2">
            <ListChecks className="w-4 h-4" />
            Warteschlange
          </TabsTrigger>
          <TabsTrigger value="my-items" className="gap-2">
            <UserCheck className="w-4 h-4" />
            Meine Items
          </TabsTrigger>
          {canAccess.validationManage && (
            <>
              <TabsTrigger value="rules" className="gap-2">
                <Settings2 className="w-4 h-4" />
                Regeln
              </TabsTrigger>
              <TabsTrigger value="analytics" className="gap-2">
                <BarChart3 className="w-4 h-4" />
                Statistiken
              </TabsTrigger>
            </>
          )}
        </TabsList>

        <TabsContent value="queue" className="space-y-4">
          {/* Screen Reader: Aktueller Filter-Status */}
          <div className="sr-only" aria-live="polite" aria-atomic="true">
            Aktuelle Filter: {currentFilterDescription}.
            {queueData && `${queueData.total} Dokumente gefunden.`}
          </div>

          {/* Filters */}
          <div
            id="validation-filters"
            className="flex flex-col lg:flex-row gap-4 items-start lg:items-center justify-between"
            role="region"
            aria-label="Filter und Sortierung"
          >
            <div className="flex flex-wrap items-center gap-2">
              <form onSubmit={handleSearch} className="flex items-center gap-2" role="search" aria-label="Dokumente durchsuchen">
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" aria-hidden="true" />
                  <label htmlFor="search-docs" className="sr-only">
                    Dokumente durchsuchen
                  </label>
                  <Input
                    id="search-docs"
                    placeholder="Dokument suchen..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="pl-9 w-[200px]"
                    aria-label="Suchbegriff eingeben"
                  />
                </div>
              </form>

              <div className="flex items-center gap-2">
                <label htmlFor="status-filter" className="sr-only">
                  Nach Status filtern
                </label>
                <Select
                  value={statusFilter}
                  onValueChange={(v) => {
                    setStatusFilter(v);
                    handleFilterChange();
                  }}
                >
                  <SelectTrigger id="status-filter" className="w-[140px]" aria-label="Status-Filter">
                    <SelectValue placeholder="Status" />
                  </SelectTrigger>
                  <SelectContent>
                    {STATUS_OPTIONS.map((option) => (
                      <SelectItem key={option.value} value={option.value}>
                        {option.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="flex items-center gap-2">
                <label htmlFor="doctype-filter" className="sr-only">
                  Nach Dokumenttyp filtern
                </label>
                <Select
                  value={documentTypeFilter}
                  onValueChange={(v) => {
                    setDocumentTypeFilter(v);
                    handleFilterChange();
                  }}
                >
                  <SelectTrigger id="doctype-filter" className="w-[140px]" aria-label="Dokumenttyp-Filter">
                    <SelectValue placeholder="Dokumenttyp" />
                  </SelectTrigger>
                  <SelectContent>
                    {DOCUMENT_TYPES.map((type) => (
                      <SelectItem key={type.value} value={type.value}>
                        {type.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="flex items-center gap-2">
                <label htmlFor="source-filter" className="sr-only">
                  Nach Quelle filtern
                </label>
                <Select
                  value={sourceFilter}
                  onValueChange={(v) => {
                    setSourceFilter(v);
                    handleFilterChange();
                  }}
                >
                  <SelectTrigger id="source-filter" className="w-[140px]" aria-label="Quellen-Filter">
                    <SelectValue placeholder="Quelle" />
                  </SelectTrigger>
                  <SelectContent>
                    {SOURCE_OPTIONS.map((option) => (
                      <SelectItem key={option.value} value={option.value}>
                        {option.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <label htmlFor="sort-option" className="sr-only">
                Sortierung wählen
              </label>
              <Select value={sortOption} onValueChange={setSortOption}>
                <SelectTrigger id="sort-option" className="w-[180px]" aria-label="Sortierung">
                  <ArrowUpDown className="w-4 h-4 mr-2" aria-hidden="true" />
                  <SelectValue placeholder="Sortierung" />
                </SelectTrigger>
                <SelectContent>
                  {SORT_OPTIONS.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>

              {/* Filter Reset Button - nur anzeigen wenn Filter aktiv */}
              {hasActiveFilters && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleResetFilters}
                  aria-label="Alle Filter zurücksetzen"
                  className="text-muted-foreground hover:text-foreground"
                >
                  <RotateCcw className="w-4 h-4 mr-2" aria-hidden="true" />
                  Zurücksetzen
                </Button>
              )}
            </div>
          </div>

          {/* Results Info */}
          <div className="flex items-center justify-between text-sm text-muted-foreground">
            <div>
              {queueData && (
                <span>
                  {queueData.total} Dokumente
                  {statusFilter !== 'all' && (
                    <Badge variant="secondary" className="ml-2">
                      {VALIDATION_STATUS_LABELS[statusFilter as ValidationStatus]}
                    </Badge>
                  )}
                </span>
              )}
            </div>
            <div>
              {queueData && totalPages > 1 && (
                <span>
                  Seite {page + 1} von {totalPages}
                </span>
              )}
            </div>
          </div>

          {/* Error State */}
          {error && (
            <div
              className="bg-destructive/10 border border-destructive/20 rounded-lg p-4 text-destructive"
              role="alert"
              aria-live="assertive"
            >
              <p className="font-medium">Fehler beim Laden der Daten</p>
              <p className="text-sm mt-1">{(error as Error).message}</p>
              <Button variant="outline" size="sm" onClick={() => refetch()} className="mt-2">
                Erneut versuchen
              </Button>
            </div>
          )}

          {/* Loading State */}
          {isLoading && (
            <div className="space-y-2" role="status" aria-label="Lade Dokumente">
              <span className="sr-only">Lade Validierungs-Warteschlange...</span>
              {Array.from({ length: 5 }).map((_, i) => (
                <Skeleton key={i} className="h-16 w-full" />
              ))}
            </div>
          )}

          {/* Empty State */}
          {!isLoading && !error && queueData?.items.length === 0 && (
            <div
              className="text-center py-12 bg-muted/30 rounded-lg"
              role="status"
              aria-label="Keine Dokumente gefunden"
            >
              <CheckCircle className="w-12 h-12 mx-auto text-muted-foreground mb-4" aria-hidden="true" />
              <h3 className="text-lg font-medium mb-2">Keine Dokumente gefunden</h3>
              <p className="text-muted-foreground mb-4">
                {statusFilter === 'pending'
                  ? 'Alle Dokumente wurden validiert. Gut gemacht!'
                  : 'Keine Dokumente entsprechen den gewählten Filtern.'}
              </p>
              {statusFilter !== 'all' && (
                <Button variant="outline" onClick={() => setStatusFilter('all')}>
                  Alle Status anzeigen
                </Button>
              )}
            </div>
          )}

          {/* Queue Table */}
          {!isLoading && !error && queueData && queueData.items.length > 0 && (
            <>
              <div id="validation-table" className="rounded-md border" role="region" aria-label="Validierungs-Warteschlange">
                <Table aria-label={`Validierungs-Warteschlange mit ${queueData.total} Dokumenten. ${currentFilterDescription}`}>
                  <caption className="sr-only">
                    Validierungs-Warteschlange: {queueData.total} Dokumente.
                    {statusFilter !== 'all' && ` Gefiltert nach: ${VALIDATION_STATUS_LABELS[statusFilter as ValidationStatus]}.`}
                    Seite {page + 1} von {totalPages || 1}.
                  </caption>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-[40px]">
                        <Checkbox
                          checked={
                            selectedItems.length === queueData.items.length &&
                            queueData.items.length > 0
                          }
                          onCheckedChange={handleSelectAll}
                          aria-label={selectAllLabel}
                        />
                      </TableHead>
                      <TableHead>Dokument</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Quelle</TableHead>
                      <TableHead>Konfidenz</TableHead>
                      <TableHead>Priorität</TableHead>
                      <TableHead>Erstellt</TableHead>
                      <TableHead className="w-[80px]">Aktionen</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {queueData.items.map((item) => (
                      <TableRow
                        key={item.id}
                        className="cursor-pointer hover:bg-muted/50"
                        onClick={() => handleOpenItem(item.id)}
                      >
                        <TableCell onClick={(e) => e.stopPropagation()}>
                          <Checkbox
                            checked={selectedItems.includes(item.id)}
                            onCheckedChange={(checked) =>
                              handleSelectItem(item.id, checked as boolean)
                            }
                            aria-label={`${item.document_name || `Dokument ${item.document_id.slice(0, 8)}`} auswählen`}
                          />
                        </TableCell>
                        <TableCell>
                          <div>
                            <div className="font-medium">
                              {item.document_name || `Dokument ${item.document_id.slice(0, 8)}`}
                            </div>
                            <div className="text-sm text-muted-foreground">
                              {item.document_type || 'Unbekannt'}
                            </div>
                          </div>
                        </TableCell>
                        <TableCell>
                          <Badge variant={getValidationStatusColor(item.status)}>
                            {VALIDATION_STATUS_LABELS[item.status]}
                          </Badge>
                        </TableCell>
                        <TableCell>
                          <span className="text-sm">
                            {SAMPLE_SOURCE_LABELS[item.sample_source as SampleSource]}
                          </span>
                        </TableCell>
                        <TableCell>
                          {item.avg_field_confidence !== null ? (
                            <span
                              className={`font-medium ${getConfidenceColor(item.avg_field_confidence)}`}
                            >
                              {Math.round(item.avg_field_confidence * 100)}%
                            </span>
                          ) : (
                            <span className="text-muted-foreground">-</span>
                          )}
                        </TableCell>
                        <TableCell>
                          <span className={`font-medium ${getPriorityColor(item.priority)}`}>
                            {item.priority}
                          </span>
                        </TableCell>
                        <TableCell>
                          <span className="text-sm text-muted-foreground">
                            {new Date(item.created_at).toLocaleDateString('de-DE')}
                          </span>
                        </TableCell>
                        <TableCell onClick={(e) => e.stopPropagation()}>
                          <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                              <Button
                                variant="ghost"
                                size="icon"
                                aria-label={`Aktionen für ${item.document_name || `Dokument ${item.document_id.slice(0, 8)}`}`}
                              >
                                <MoreHorizontal className="w-4 h-4" aria-hidden="true" />
                              </Button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align="end">
                              <DropdownMenuItem onClick={() => handleOpenItem(item.id)}>
                                <Eye className="w-4 h-4 mr-2" />
                                Öffnen
                              </DropdownMenuItem>
                              {item.status === ValidationStatus.PENDING && (
                                <>
                                  <DropdownMenuItem onClick={() => handleApprove(item.id)}>
                                    <CheckCircle className="w-4 h-4 mr-2" />
                                    Genehmigen
                                  </DropdownMenuItem>
                                  <DropdownMenuItem onClick={() => handleReject(item.id)}>
                                    <XCircle className="w-4 h-4 mr-2" />
                                    Ablehnen
                                  </DropdownMenuItem>
                                </>
                              )}
                              {canAccess.validationManage && (
                                <>
                                  <DropdownMenuSeparator />
                                  <DropdownMenuItem onClick={() => handleDelete(item.id)}>
                                    <Trash2 className="w-4 h-4 mr-2" />
                                    Löschen
                                  </DropdownMenuItem>
                                </>
                              )}
                            </DropdownMenuContent>
                          </DropdownMenu>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>

              {/* Pagination */}
              {totalPages > 1 && (
                <div className="flex items-center justify-center gap-4 pt-4">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setPage((p) => p - 1)}
                    disabled={!canGoPrevious}
                    aria-label="Vorherige Seite"
                  >
                    <ChevronLeft className="w-4 h-4 mr-1" aria-hidden="true" />
                    Zurück
                  </Button>
                  <span className="text-sm text-muted-foreground" aria-live="polite">
                    Seite {page + 1} von {totalPages}
                  </span>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setPage((p) => p + 1)}
                    disabled={!canGoNext}
                    aria-label="Nächste Seite"
                  >
                    Weiter
                    <ChevronRight className="w-4 h-4 ml-1" aria-hidden="true" />
                  </Button>
                </div>
              )}
            </>
          )}

          {/* Batch Actions Bar */}
          {selectedItems.length > 0 && (
            <div
              className="fixed bottom-4 left-1/2 -translate-x-1/2 bg-background border rounded-lg shadow-lg p-4 flex items-center gap-4 z-50"
              role="toolbar"
              aria-label="Batch-Aktionen"
            >
              <span className="text-sm font-medium" aria-live="polite">
                {selectedItems.length} ausgewählt
              </span>
              <div className="flex items-center gap-2" role="group" aria-label="Aktionen für ausgewählte Dokumente">
                <Button
                  size="sm"
                  onClick={handleBatchApproveClick}
                  disabled={batchApprove.isPending}
                  aria-label={`${selectedItems.length} Dokumente genehmigen`}
                >
                  <CheckCircle className="w-4 h-4 mr-2" aria-hidden="true" />
                  Alle genehmigen
                </Button>
                <Button
                  size="sm"
                  variant="destructive"
                  onClick={handleBatchRejectClick}
                  disabled={batchReject.isPending}
                  aria-label={`${selectedItems.length} Dokumente ablehnen`}
                >
                  <XCircle className="w-4 h-4 mr-2" aria-hidden="true" />
                  Alle ablehnen
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={handleAssignClick}
                  aria-label={`${selectedItems.length} Dokumente zuweisen`}
                >
                  <UserPlus className="w-4 h-4 mr-2" aria-hidden="true" />
                  Zuweisen
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => setSelectedItems([])}
                  aria-label="Auswahl aufheben"
                >
                  Abbrechen
                </Button>
              </div>
            </div>
          )}
        </TabsContent>

        <TabsContent value="my-items" className="space-y-4">
          {/* Loading State */}
          {isLoadingMyItems && (
            <div className="space-y-2" role="status" aria-label="Lade meine Items">
              <span className="sr-only">Lade zugewiesene Items...</span>
              {Array.from({ length: 5 }).map((_, i) => (
                <Skeleton key={i} className="h-16 w-full" />
              ))}
            </div>
          )}

          {/* Empty State */}
          {!isLoadingMyItems && (!myItemsData?.items || myItemsData.items.length === 0) && (
            <div
              className="text-center py-12 bg-muted/30 rounded-lg"
              role="status"
              aria-label="Keine zugewiesenen Items"
            >
              <UserCheck className="w-12 h-12 mx-auto text-muted-foreground mb-4" aria-hidden="true" />
              <h3 className="text-lg font-medium mb-2">Keine Items zugewiesen</h3>
              <p className="text-muted-foreground mb-4">
                Sie haben derzeit keine Dokumente zur Validierung zugewiesen.
              </p>
              <Button variant="outline" onClick={() => setActiveTab('queue')}>
                Zur Warteschlange
              </Button>
            </div>
          )}

          {/* My Items Table */}
          {!isLoadingMyItems && myItemsData?.items && myItemsData.items.length > 0 && (
            <>
              <div className="flex items-center justify-between text-sm text-muted-foreground mb-4">
                <span>{myItemsData.total} zugewiesene Dokumente</span>
              </div>

              <div className="rounded-md border" role="region" aria-label="Meine zugewiesenen Items">
                <Table aria-label={`Meine zugewiesenen Items: ${myItemsData.total} Dokumente`}>
                  <caption className="sr-only">
                    Ihre zugewiesenen Dokumente zur Validierung.
                  </caption>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Dokument</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Priorität</TableHead>
                      <TableHead>Konfidenz</TableHead>
                      <TableHead>Zugewiesen am</TableHead>
                      <TableHead className="w-[100px]">Aktionen</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {myItemsData.items.map((item) => (
                      <TableRow
                        key={item.id}
                        className="cursor-pointer hover:bg-muted/50"
                        onClick={() => handleOpenItem(item.id)}
                      >
                        <TableCell>
                          <div>
                            <div className="font-medium">
                              {item.document_name || `Dokument ${item.document_id.slice(0, 8)}`}
                            </div>
                            <div className="text-sm text-muted-foreground">
                              {item.document_type || 'Unbekannt'}
                            </div>
                          </div>
                        </TableCell>
                        <TableCell>
                          <Badge variant={getValidationStatusColor(item.status)}>
                            {VALIDATION_STATUS_LABELS[item.status]}
                          </Badge>
                        </TableCell>
                        <TableCell>
                          <span className={`font-medium ${getPriorityColor(item.priority)}`}>
                            {item.priority}
                          </span>
                        </TableCell>
                        <TableCell>
                          {item.avg_field_confidence !== null ? (
                            <span
                              className={`font-medium ${getConfidenceColor(item.avg_field_confidence)}`}
                            >
                              {Math.round(item.avg_field_confidence * 100)}%
                            </span>
                          ) : (
                            <span className="text-muted-foreground">-</span>
                          )}
                        </TableCell>
                        <TableCell>
                          <span className="text-sm text-muted-foreground">
                            {item.assigned_at
                              ? new Date(item.assigned_at).toLocaleDateString('de-DE')
                              : '-'}
                          </span>
                        </TableCell>
                        <TableCell onClick={(e) => e.stopPropagation()}>
                          <div className="flex items-center gap-1">
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => handleOpenItem(item.id)}
                              aria-label={`${item.document_name || 'Dokument'} öffnen`}
                            >
                              <Eye className="w-4 h-4" aria-hidden="true" />
                            </Button>
                            {item.status === 'pending' || item.status === 'in_progress' ? (
                              <>
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => handleApprove(item.id)}
                                  className="text-green-600 hover:text-green-700"
                                  aria-label={`${item.document_name || 'Dokument'} genehmigen`}
                                >
                                  <CheckCircle className="w-4 h-4" aria-hidden="true" />
                                </Button>
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => handleReject(item.id)}
                                  className="text-red-600 hover:text-red-700"
                                  aria-label={`${item.document_name || 'Dokument'} ablehnen`}
                                >
                                  <XCircle className="w-4 h-4" aria-hidden="true" />
                                </Button>
                              </>
                            ) : null}
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </>
          )}
        </TabsContent>

        {canAccess.validationManage && (
          <>
            <TabsContent value="rules" className="space-y-4">
              <RulesManager />
            </TabsContent>

            <TabsContent value="analytics" className="space-y-4">
              <AnalyticsDashboard />
            </TabsContent>
          </>
        )}
      </Tabs>

      {/* Dialoge */}
      <RejectReasonDialog
        open={rejectDialogOpen}
        onOpenChange={setRejectDialogOpen}
        onConfirm={handleRejectConfirm}
        isLoading={rejectItem.isPending || batchReject.isPending}
        itemCount={rejectDialogItem ? 1 : selectedItems.length}
        documentName={
          rejectDialogItem
            ? queueData?.items.find((i) => i.id === rejectDialogItem)?.document_name
            : undefined
        }
      />

      <BulkApproveDialog
        open={bulkApproveDialogOpen}
        onOpenChange={setBulkApproveDialogOpen}
        onConfirm={handleBatchApproveConfirm}
        isLoading={batchApprove.isPending}
        items={
          queueData?.items.filter((item) => selectedItems.includes(item.id)) || []
        }
      />

      <AssignEditorDialog
        open={assignDialogOpen}
        onOpenChange={setAssignDialogOpen}
        onConfirm={handleAssignConfirm}
        isLoading={batchAssign.isPending}
        itemCount={selectedItems.length}
      />

      {/* Offline Banner */}
      {!isOnline && (
        <div
          className="fixed bottom-0 left-0 right-0 bg-yellow-600 text-white px-4 py-3 flex items-center justify-center gap-3 z-50"
          role="alert"
          aria-live="assertive"
        >
          <WifiOff className="w-5 h-5" aria-hidden="true" />
          <span className="font-medium">
            Offline - Einige Funktionen sind nicht verfügbar.
            {offlineSince && (
              <span className="ml-2 text-yellow-200">
                (Seit {new Date(offlineSince).toLocaleTimeString('de-DE')})
              </span>
            )}
          </span>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => window.location.reload()}
            className="ml-4"
          >
            Seite neu laden
          </Button>
        </div>
      )}
    </div>
  );
}

/**
 * ValidationQueueDashboard - Exported with ErrorBoundary wrapper
 * Provides graceful error handling for the entire dashboard.
 */
export function ValidationQueueDashboard() {
  return (
    <ErrorBoundary
      errorTitle="Fehler in der Validierungs-Warteschlange"
      errorDescription="Das Dashboard konnte nicht geladen werden. Bitte versuchen Sie es erneut."
      onError={(details) => {
        logger.error('ValidationQueueDashboard Fehler', details.error, { component: 'ValidationQueueDashboard', timestamp: details.timestamp });
      }}
    >
      <ValidationQueueDashboardInner />
    </ErrorBoundary>
  );
}

export default ValidationQueueDashboard;
