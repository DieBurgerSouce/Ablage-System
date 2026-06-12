/**
 * ValidationDashboard
 *
 * Enterprise-Level Validierungs-Queue Dashboard.
 * Zeigt Training-Samples mit echten Daten, Filterung und Pagination.
 */

import { useState, useCallback } from 'react';
import { CheckCircle, Filter, RefreshCw, Search, ChevronLeft, ChevronRight } from 'lucide-react';
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
import { ValidationCard } from './ValidationCard';
import { ValidationStats } from './ValidationStats';
import { useTrainingSamples, useTrainingStats } from '../hooks/use-validation-queries';
import { TrainingSampleStatus, SAMPLE_STATUS_LABELS } from '../types';
import type { ListSamplesParams } from '../api/validation-api';

const PAGE_SIZE = 12;

const DOCUMENT_TYPES = [
  { value: 'all', label: 'Alle Typen' },
  { value: 'invoice', label: 'Rechnungen' },
  { value: 'delivery_note', label: 'Lieferscheine' },
  { value: 'contract', label: 'Verträge' },
  { value: 'letter', label: 'Briefe' },
  { value: 'order', label: 'Bestellungen' },
];

const SORT_OPTIONS = [
  { value: 'business_priority:desc', label: 'Priorität' },
  { value: 'created_at:desc', label: 'Neueste zuerst' },
  { value: 'created_at:asc', label: 'Älteste zuerst' },
  { value: 'difficulty:desc', label: 'Schwierigkeit' },
  { value: 'document_type:asc', label: 'Dokumenttyp' },
];

const STATUS_OPTIONS = [
  { value: 'all', label: 'Alle Status' },
  { value: TrainingSampleStatus.PENDING, label: SAMPLE_STATUS_LABELS[TrainingSampleStatus.PENDING] },
  { value: TrainingSampleStatus.IN_PROGRESS, label: SAMPLE_STATUS_LABELS[TrainingSampleStatus.IN_PROGRESS] },
  { value: TrainingSampleStatus.ANNOTATED, label: SAMPLE_STATUS_LABELS[TrainingSampleStatus.ANNOTATED] },
  { value: TrainingSampleStatus.VERIFIED, label: SAMPLE_STATUS_LABELS[TrainingSampleStatus.VERIFIED] },
  { value: TrainingSampleStatus.REJECTED, label: SAMPLE_STATUS_LABELS[TrainingSampleStatus.REJECTED] },
];

export function ValidationDashboard() {
  // Filter State
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('pending');
  const [documentTypeFilter, setDocumentTypeFilter] = useState('all');
  const [sortBy, setSortBy] = useState('created_at:desc');
  const [page, setPage] = useState(0);

  // Parse sort value into sort_by and sort_order
  const [sortField, sortOrder] = sortBy.split(':') as [string, 'asc' | 'desc'];

  // Build query params
  const queryParams: ListSamplesParams = {
    status: statusFilter === 'all' ? undefined : (statusFilter as TrainingSampleStatus),
    document_type: documentTypeFilter === 'all' ? undefined : documentTypeFilter,
    search: searchQuery || undefined,
    sort_by: sortField as ListSamplesParams['sort_by'],
    sort_order: sortOrder,
    limit: PAGE_SIZE,
    offset: page * PAGE_SIZE,
  };

  // Queries
  const { data: samplesData, isLoading, error, refetch } = useTrainingSamples(queryParams);
  const { data: statsData, isLoading: isLoadingStats } = useTrainingStats();

  // Handlers
  const handleSearch = useCallback((e: React.FormEvent) => {
    e.preventDefault();
    setPage(0); // Reset to first page on search
    // Query wird automatisch durch queryParams aktualisiert
  }, []);

  const handleFilterChange = useCallback(() => {
    setPage(0); // Reset to first page on filter change
  }, []);

  const handleStatusChange = (value: string) => {
    setStatusFilter(value);
    handleFilterChange();
  };

  const handleDocumentTypeChange = (value: string) => {
    setDocumentTypeFilter(value);
    handleFilterChange();
  };

  const handleSortChange = (value: string) => {
    setSortBy(value);
    setPage(0); // Reset to first page on sort change
  };

  const handleRefresh = () => {
    refetch();
  };

  // Pagination
  const totalPages = samplesData ? Math.ceil(samplesData.total / PAGE_SIZE) : 0;
  const canGoPrevious = page > 0;
  const canGoNext = page < totalPages - 1;

  return (
    <div className="space-y-6">
      {/* Stats Overview */}
      <ValidationStats
        stats={statsData?.overview}
        isLoading={isLoadingStats}
      />

      {/* Filters */}
      <div className="flex flex-col lg:flex-row gap-4 items-start lg:items-center justify-between">
        {/* Search & Filter */}
        <div className="flex flex-col sm:flex-row items-start sm:items-center gap-2 w-full lg:w-auto">
          <form onSubmit={handleSearch} className="flex items-center gap-2 w-full sm:w-auto">
            <div className="relative flex-1 sm:flex-initial">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <Input
                placeholder="Dokumente suchen..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-9 w-full sm:w-[300px]"
              />
            </div>
            <Button type="submit" variant="outline" size="icon">
              <Filter className="w-4 h-4" />
            </Button>
          </form>
          <Button
            variant="outline"
            size="icon"
            onClick={handleRefresh}
            disabled={isLoading}
          >
            <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
          </Button>
        </div>

        {/* Dropdowns */}
        <div className="flex flex-wrap items-center gap-2 w-full lg:w-auto">
          <Select value={statusFilter} onValueChange={handleStatusChange}>
            <SelectTrigger className="w-[150px]">
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

          <Select value={documentTypeFilter} onValueChange={handleDocumentTypeChange}>
            <SelectTrigger className="w-[160px]">
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

          <Select value={sortBy} onValueChange={handleSortChange}>
            <SelectTrigger className="w-[160px]">
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
        </div>
      </div>

      {/* Results Info */}
      <div className="flex items-center justify-between text-sm text-muted-foreground">
        <div>
          {samplesData && (
            <span>
              {samplesData.total} Dokumente gefunden
              {statusFilter !== 'all' && (
                <Badge variant="secondary" className="ml-2">
                  {SAMPLE_STATUS_LABELS[statusFilter as TrainingSampleStatus] || statusFilter}
                </Badge>
              )}
            </span>
          )}
        </div>
        <div>
          {samplesData && totalPages > 1 && (
            <span>
              Seite {page + 1} von {totalPages}
            </span>
          )}
        </div>
      </div>

      {/* Error State */}
      {error && (
        <div className="bg-destructive/10 border border-destructive/20 rounded-lg p-4 text-destructive">
          <p className="font-medium">Fehler beim Laden der Daten</p>
          <p className="text-sm mt-1">{(error as Error).message}</p>
          <Button
            variant="outline"
            size="sm"
            onClick={handleRefresh}
            className="mt-2"
          >
            Erneut versuchen
          </Button>
        </div>
      )}

      {/* Loading State */}
      {isLoading && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
          {Array.from({ length: PAGE_SIZE }).map((_, i) => (
            <div key={i} className="bg-card border rounded-lg p-4 space-y-3">
              <Skeleton className="h-4 w-3/4" />
              <Skeleton className="h-3 w-1/2" />
              <Skeleton className="h-8 w-full" />
              <div className="flex gap-2">
                <Skeleton className="h-5 w-16" />
                <Skeleton className="h-5 w-16" />
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Empty State */}
      {!isLoading && !error && samplesData?.samples.length === 0 && (
        <div className="text-center py-12 bg-muted/30 rounded-lg">
          <CheckCircle className="w-12 h-12 mx-auto text-muted-foreground mb-4" />
          <h3 className="text-lg font-medium mb-2">Keine Dokumente gefunden</h3>
          <p className="text-muted-foreground mb-4">
            {statusFilter === 'pending'
              ? 'Alle Dokumente wurden validiert. Gut gemacht!'
              : 'Keine Dokumente entsprechen den gewählten Filtern.'}
          </p>
          {statusFilter !== 'all' && (
            <Button
              variant="outline"
              onClick={() => setStatusFilter('all')}
            >
              Alle Status anzeigen
            </Button>
          )}
        </div>
      )}

      {/* Grid */}
      {!isLoading && !error && samplesData && samplesData.samples.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
          {samplesData.samples.map((sample) => (
            <ValidationCard key={sample.id} sample={sample} />
          ))}
        </div>
      )}

      {/* Pagination */}
      {!isLoading && samplesData && totalPages > 1 && (
        <div className="flex items-center justify-center gap-4 pt-4">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setPage((p) => p - 1)}
            disabled={!canGoPrevious}
          >
            <ChevronLeft className="w-4 h-4 mr-1" />
            Zurück
          </Button>
          <div className="flex items-center gap-2">
            {Array.from({ length: Math.min(5, totalPages) }).map((_, i) => {
              // Show pages around current page
              let pageNum: number;
              if (totalPages <= 5) {
                pageNum = i;
              } else if (page < 3) {
                pageNum = i;
              } else if (page > totalPages - 4) {
                pageNum = totalPages - 5 + i;
              } else {
                pageNum = page - 2 + i;
              }

              return (
                <Button
                  key={pageNum}
                  variant={page === pageNum ? 'default' : 'outline'}
                  size="sm"
                  onClick={() => setPage(pageNum)}
                  className="w-8 h-8 p-0"
                >
                  {pageNum + 1}
                </Button>
              );
            })}
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setPage((p) => p + 1)}
            disabled={!canGoNext}
          >
            Weiter
            <ChevronRight className="w-4 h-4 ml-1" />
          </Button>
        </div>
      )}
    </div>
  );
}
