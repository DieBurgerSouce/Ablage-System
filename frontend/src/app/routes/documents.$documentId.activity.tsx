/**
 * Document Activity Route
 *
 * Route für die Aktivitätshistorie eines Dokuments.
 */

import { useState, useCallback, useMemo } from 'react';
import { createFileRoute, Link } from '@tanstack/react-router';
import { ArrowLeft, History, Loader2 } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { Button } from '@/components/ui/button';
import { documentsService } from '@/lib/api/services/documents';
import {
  ActivityTimeline,
  ActivityFilterBar,
  useDocumentTimelineInfinite,
  type ActivitySource,
} from '@/features/documents/activity';

export const Route = createFileRoute('/documents/$documentId/activity')({
  component: DocumentActivityPage,
});

function DocumentActivityPage() {
  const { documentId } = Route.useParams();

  // Filter State
  const [search, setSearch] = useState('');
  const [source, setSource] = useState<ActivitySource | 'all'>('all');
  const [activityType, setActivityType] = useState('all');
  const [dateFrom, setDateFrom] = useState<Date | undefined>();
  const [dateUntil, setDateUntil] = useState<Date | undefined>();

  // Document Info
  const { data: document, isLoading: docLoading } = useQuery({
    queryKey: ['document', documentId],
    queryFn: () => documentsService.getById(documentId),
  });

  // Timeline Query with filters
  const {
    data: timelineData,
    isLoading: timelineLoading,
    isFetchingNextPage,
    hasNextPage,
    fetchNextPage,
  } = useDocumentTimelineInfinite(documentId, {
    activityType: activityType !== 'all' ? activityType : undefined,
    limit: 20,
  });

  // Flatten pages to activities
  const activities = useMemo(() => {
    if (!timelineData?.pages) return [];
    return timelineData.pages.flatMap((page) => page.items);
  }, [timelineData]);

  // Client-side filtering for search and source
  const filteredActivities = useMemo(() => {
    let result = activities;

    // Source filter
    if (source !== 'all') {
      result = result.filter((a) => a.source === source);
    }

    // Search filter
    if (search) {
      const searchLower = search.toLowerCase();
      result = result.filter(
        (a) =>
          a.title.toLowerCase().includes(searchLower) ||
          a.description?.toLowerCase().includes(searchLower) ||
          a.actorName?.toLowerCase().includes(searchLower)
      );
    }

    // Date filters
    if (dateFrom) {
      result = result.filter((a) => new Date(a.createdAt) >= dateFrom);
    }
    if (dateUntil) {
      const until = new Date(dateUntil);
      until.setHours(23, 59, 59, 999);
      result = result.filter((a) => new Date(a.createdAt) <= until);
    }

    return result;
  }, [activities, source, search, dateFrom, dateUntil]);

  const handleClearFilters = useCallback(() => {
    setSearch('');
    setSource('all');
    setActivityType('all');
    setDateFrom(undefined);
    setDateUntil(undefined);
  }, []);

  const handleLoadMore = useCallback(() => {
    if (hasNextPage && !isFetchingNextPage) {
      fetchNextPage();
    }
  }, [hasNextPage, isFetchingNextPage, fetchNextPage]);

  if (docLoading) {
    return (
      <div className="h-full flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!document) {
    return (
      <div className="container py-8 max-w-4xl">
        <div className="text-center text-muted-foreground">
          Dokument nicht gefunden.
        </div>
      </div>
    );
  }

  return (
    <div className="container py-8 max-w-4xl">
      {/* Header */}
      <div className="mb-8">
        <Link to="/documents/$documentId" params={{ documentId }}>
          <Button variant="ghost" size="sm" className="mb-4">
            <ArrowLeft className="h-4 w-4 mr-2" />
            Zurück zum Dokument
          </Button>
        </Link>

        <div className="flex items-center gap-3">
          <div className="p-2 bg-primary/10 rounded-lg">
            <History className="h-6 w-6 text-primary" />
          </div>
          <div>
            <h1 className="text-2xl font-bold">Aktivitätshistorie</h1>
            <p className="text-muted-foreground truncate max-w-md">
              {document.title || document.name}
            </p>
          </div>
        </div>
      </div>

      {/* Filter Bar */}
      <div className="mb-6">
        <ActivityFilterBar
          search={search}
          onSearchChange={setSearch}
          source={source}
          onSourceChange={setSource}
          activityType={activityType}
          onActivityTypeChange={setActivityType}
          dateFrom={dateFrom}
          onDateFromChange={setDateFrom}
          dateUntil={dateUntil}
          onDateUntilChange={setDateUntil}
          onClearFilters={handleClearFilters}
        />
      </div>

      {/* Timeline */}
      <ActivityTimeline
        activities={filteredActivities}
        isLoading={timelineLoading}
        hasMore={hasNextPage}
        onLoadMore={handleLoadMore}
        isLoadingMore={isFetchingNextPage}
        showTarget={false}
        title={`Aktivitäten (${filteredActivities.length})`}
        emptyMessage="Keine Aktivitäten für dieses Dokument gefunden"
      />
    </div>
  );
}
