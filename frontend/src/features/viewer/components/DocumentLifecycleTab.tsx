import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Loader2, AlertCircle } from 'lucide-react';
import {
  fetchDocumentLifecycle,
  fetchDocumentLifecycleStats,
  type LifecycleEvent,
} from '../api/lifecycle-api';
import { LifecycleTimeline } from './LifecycleTimeline';

interface DocumentLifecycleTabProps {
  documentId: string;
}

type FilterType = 'all' | 'import' | 'ocr' | 'assignment' | 'approval';

const FILTER_CONFIGS: Record<FilterType, { label: string; eventTypes: string[] }> = {
  all: { label: 'Alle', eventTypes: [] },
  import: { label: 'Import', eventTypes: ['IMPORT'] },
  ocr: { label: 'OCR', eventTypes: ['OCR_START', 'OCR_COMPLETE'] },
  assignment: {
    label: 'Zuordnung',
    eventTypes: ['ENTITY_LINK', 'CLASSIFICATION', 'EXTRACTION'],
  },
  approval: { label: 'Freigabe', eventTypes: ['APPROVAL', 'REJECTION'] },
};

export function DocumentLifecycleTab({ documentId }: DocumentLifecycleTabProps) {
  const [activeFilter, setActiveFilter] = useState<FilterType>('all');

  // Fetch lifecycle data
  const {
    data: lifecycleData,
    isLoading: isLoadingLifecycle,
    error: lifecycleError,
  } = useQuery({
    queryKey: ['document', documentId, 'lifecycle'],
    queryFn: () => fetchDocumentLifecycle(documentId),
  });

  // Fetch lifecycle stats
  const {
    data: statsData,
    isLoading: isLoadingStats,
    error: statsError,
  } = useQuery({
    queryKey: ['document', documentId, 'lifecycle-stats'],
    queryFn: () => fetchDocumentLifecycleStats(documentId),
  });

  const isLoading = isLoadingLifecycle || isLoadingStats;
  const error = lifecycleError || statsError;

  // Filter events based on active filter
  const filteredEvents: LifecycleEvent[] = (() => {
    if (!lifecycleData?.events) return [];
    if (activeFilter === 'all') return lifecycleData.events;

    const filterConfig = FILTER_CONFIGS[activeFilter];
    return lifecycleData.events.filter((event) =>
      filterConfig.eventTypes.includes(event.event_type)
    );
  })();

  // Loading State
  if (isLoading) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="flex flex-col items-center gap-3 text-muted-foreground">
          <Loader2 className="h-8 w-8 animate-spin" />
          <span>Lade Lebenszyklus-Daten...</span>
        </div>
      </div>
    );
  }

  // Error State
  if (error) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="flex flex-col items-center gap-3 text-destructive">
          <AlertCircle className="h-8 w-8" />
          <span>Fehler beim Laden der Lebenszyklus-Daten</span>
          <span className="text-xs text-muted-foreground">
            {error instanceof Error ? error.message : 'Unbekannter Fehler'}
          </span>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Stats Summary */}
      {statsData && (
        <div className="grid grid-cols-2 gap-4 p-4 bg-muted/30 rounded-lg border">
          <div>
            <p className="text-xs text-muted-foreground">Ereignisse gesamt</p>
            <p className="text-2xl font-bold">{statsData.total_events}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Verarbeitungsdauer</p>
            <p className="text-2xl font-bold">
              {(statsData.total_processing_duration_ms / 1000).toFixed(1)}s
            </p>
          </div>
        </div>
      )}

      {/* Filter Chips */}
      <div className="flex gap-2 flex-wrap">
        {(Object.keys(FILTER_CONFIGS) as FilterType[]).map((filterKey) => {
          const config = FILTER_CONFIGS[filterKey];
          const isActive = activeFilter === filterKey;

          return (
            <button
              key={filterKey}
              onClick={() => setActiveFilter(filterKey)}
              className={`
                px-3 py-1.5 rounded-full text-sm font-medium transition-colors
                ${
                  isActive
                    ? 'bg-primary text-primary-foreground'
                    : 'bg-muted hover:bg-muted/80 text-muted-foreground'
                }
              `}
              aria-pressed={isActive}
            >
              {config.label}
            </button>
          );
        })}
      </div>

      {/* Timeline */}
      <LifecycleTimeline events={filteredEvents} />
    </div>
  );
}
