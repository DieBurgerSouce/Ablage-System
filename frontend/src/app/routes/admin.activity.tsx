/**
 * Admin Activity Route
 *
 * Company-weite Aktivitätsansicht für Admins.
 */

import { useState, useCallback, useMemo } from 'react';
import { createFileRoute } from '@tanstack/react-router';
import { History, Shield } from 'lucide-react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import {
  ActivityTimeline,
  ActivityFilterBar,
  ActivityStats,
  useCompanyTimelineInfinite,
  useActivityStatistics,
  type ActivitySource,
} from '@/features/documents/activity';

export const Route = createFileRoute('/admin/activity')({
  component: AdminActivityPage,
});

function AdminActivityPage() {
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
  } = useCompanyTimelineInfinite({
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
      <div className="flex items-center gap-3 mb-6">
        <div className="p-2 bg-primary/10 rounded-lg">
          <History className="h-6 w-6 text-primary" />
        </div>
        <div>
          <h1 className="text-2xl font-bold">Company-Aktivitäten</h1>
          <p className="text-muted-foreground">
            Überblick über alle Aktivitäten in Ihrer Organisation
          </p>
        </div>
      </div>

      {/* Admin Notice */}
      <Alert className="mb-6">
        <Shield className="h-4 w-4" />
        <AlertTitle>Administrator-Ansicht</AlertTitle>
        <AlertDescription>
          Sie sehen alle Aktivitäten der gesamten Company. Diese Daten sind vertraulich.
        </AlertDescription>
      </Alert>

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
            title={`Alle Aktivitäten (${activities.length})`}
            emptyMessage="Keine Aktivitäten gefunden"
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
              Keine Statistiken verfügbar
            </div>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}
