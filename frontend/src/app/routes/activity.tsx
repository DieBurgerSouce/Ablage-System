/**
 * My Activity Route
 *
 * Hauptseite fuer persoenliche Aktivitaeten.
 */

import { useState, useCallback, useMemo } from 'react';
import { createFileRoute } from '@tanstack/react-router';
import { History } from 'lucide-react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  ActivityTimeline,
  ActivityFilterBar,
  ActivityStats,
  useMyActivitiesInfinite,
  useActivityStatistics,
  type ActivitySource,
} from '@/features/documents/activity';

export const Route = createFileRoute('/activity')({
  component: MyActivityPage,
});

function MyActivityPage() {
  // Filter State
  const [search, setSearch] = useState('');
  const [source, setSource] = useState<ActivitySource | 'all'>('all');
  const [activityType, setActivityType] = useState('all');
  const [dateFrom, setDateFrom] = useState<Date | undefined>();
  const [dateUntil, setDateUntil] = useState<Date | undefined>();

  // API Queries
  const {
    data: timelineData,
    isLoading: timelineLoading,
    isFetchingNextPage,
    hasNextPage,
    fetchNextPage,
  } = useMyActivitiesInfinite({
    source: source !== 'all' ? source : undefined,
    activityType: activityType !== 'all' ? activityType : undefined,
    dateFrom: dateFrom?.toISOString(),
    dateUntil: dateUntil?.toISOString(),
    search: search || undefined,
    limit: 20,
  });

  const { data: stats, isLoading: statsLoading } = useActivityStatistics({
    dateFrom: dateFrom?.toISOString(),
    dateUntil: dateUntil?.toISOString(),
  });

  // Flatten pages to activities
  const activities = useMemo(() => {
    if (!timelineData?.pages) return [];
    return timelineData.pages.flatMap((page) => page.items);
  }, [timelineData]);

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

  return (
    <div className="container py-8 max-w-6xl">
      {/* Header */}
      <div className="flex items-center gap-3 mb-8">
        <div className="p-2 bg-primary/10 rounded-lg">
          <History className="h-6 w-6 text-primary" />
        </div>
        <div>
          <h1 className="text-2xl font-bold">Meine Aktivitaeten</h1>
          <p className="text-muted-foreground">
            Ueberblick ueber alle Ihre Aktionen und Ereignisse
          </p>
        </div>
      </div>

      {/* Tabs */}
      <Tabs defaultValue="timeline" className="space-y-6">
        <TabsList>
          <TabsTrigger value="timeline">Timeline</TabsTrigger>
          <TabsTrigger value="stats">Statistiken</TabsTrigger>
        </TabsList>

        {/* Timeline Tab */}
        <TabsContent value="timeline" className="space-y-6">
          {/* Filter Bar */}
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

          {/* Timeline */}
          <ActivityTimeline
            activities={activities}
            isLoading={timelineLoading}
            hasMore={hasNextPage}
            onLoadMore={handleLoadMore}
            isLoadingMore={isFetchingNextPage}
            showTarget={true}
            title={`Aktivitaeten (${activities.length})`}
            emptyMessage="Keine Aktivitaeten gefunden"
          />
        </TabsContent>

        {/* Stats Tab */}
        <TabsContent value="stats">
          {statsLoading ? (
            <div className="flex items-center justify-center py-16">
              <div className="animate-spin h-8 w-8 border-4 border-primary border-t-transparent rounded-full" />
            </div>
          ) : stats ? (
            <ActivityStats stats={stats} />
          ) : (
            <div className="text-center py-16 text-muted-foreground">
              Keine Statistiken verfuegbar
            </div>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}
