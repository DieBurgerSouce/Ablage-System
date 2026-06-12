/**
 * Document Graph & Timeline Route
 *
 * Interaktive Visualisierung von Dokumenten-Beziehungen (Chains)
 * und chronologischem Verlauf (Lineage/Events).
 */

import { createFileRoute } from '@tanstack/react-router';
import { useState, useCallback } from 'react';
import { Network } from 'lucide-react';

import { ErrorBoundary } from '@/components/ErrorBoundary';

import {
  DocumentGraphView,
  DocumentTimelineView,
  GraphFilters,
} from '@/features/document-graph';
import {
  useEntityChains,
  useDocumentTimeline,
} from '@/features/document-graph/hooks/use-document-graph-queries';
import type { GraphFilterState } from '@/features/document-graph/types/document-graph-types';

export const Route = createFileRoute('/document-graph')({
  component: DocumentGraphPage,
});

function DocumentGraphPage() {
  // Filter state
  const [filters, setFilters] = useState<GraphFilterState>({
    entityId: null,
    entityType: 'all',
    timeRange: '90d',
    documentTypes: [],
    viewMode: 'graph',
  });

  // Selected document for timeline
  const [selectedDocumentId, setSelectedDocumentId] = useState<string | null>(null);

  // Fetch chains (all by default, or filtered by entity)
  const {
    data: chainsData,
    isLoading: chainsLoading,
    error: chainsError,
  } = useEntityChains(filters.entityId || '', 50);

  // Fetch timeline for selected document
  const {
    data: timelineData,
    isLoading: timelineLoading,
  } = useDocumentTimeline(selectedDocumentId);

  const handleFiltersChange = useCallback(
    (partial: Partial<GraphFilterState>) => {
      setFilters((prev) => ({ ...prev, ...partial }));
    },
    []
  );

  const handleDocumentClick = useCallback((documentId: string) => {
    setSelectedDocumentId(documentId);
  }, []);

  // Get chains list, filtered by time range and document types
  const chains = chainsData?.chains ?? [];

  return (
    <ErrorBoundary
      errorTitle="Fehler im Dokumenten-Graph"
      errorDescription="Der Dokumenten-Graph konnte nicht geladen werden. Bitte versuchen Sie es erneut."
    >
      <div className="p-8 space-y-6">
        {/* Header */}
        <div>
          <h1 className="text-3xl font-bold flex items-center gap-2">
            <Network className="h-8 w-8 text-primary" />
            Dokumenten-Graph
          </h1>
          <p className="text-muted-foreground mt-1">
            Visualisierung von Dokumenten-Beziehungen und chronologischem Verlauf
          </p>
        </div>

        {/* Filters */}
        <GraphFilters filters={filters} onFiltersChange={handleFiltersChange} />

        {/* Main Content */}
        {filters.viewMode === 'graph' ? (
          <div className="h-[600px] border rounded-lg overflow-hidden bg-background">
            <DocumentGraphView
              chains={chains}
              isLoading={chainsLoading}
              error={chainsError as Error | null}
              onDocumentClick={handleDocumentClick}
            />
          </div>
        ) : (
          <DocumentTimelineView
            events={timelineData?.events ?? []}
            isLoading={timelineLoading}
            documentTitle={
              selectedDocumentId
                ? `Dokument ${selectedDocumentId.slice(0, 8)}...`
                : undefined
            }
          />
        )}

        {/* Timeline below graph when document is selected */}
        {filters.viewMode === 'graph' && selectedDocumentId && (
          <DocumentTimelineView
            events={timelineData?.events ?? []}
            isLoading={timelineLoading}
            documentTitle={`Dokument ${selectedDocumentId.slice(0, 8)}...`}
          />
        )}
      </div>
    </ErrorBoundary>
  );
}
