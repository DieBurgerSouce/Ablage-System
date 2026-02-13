/**
 * SmartInboxPage - Intelligenter Posteingang mit KI-Priorisierung
 *
 * Zeigt alle eingehenden Dokumente mit ML-basierter Priorisierung und Insights.
 */

import { useState, useMemo } from 'react';
import { Sparkles, RefreshCw, Lightbulb } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { useToast } from '@/components/ui/use-toast';
import { ErrorBoundary } from '@/components/ErrorBoundary';

import { InboxStatsBar } from '../components/InboxStatsBar';
import { InboxFilters } from '../components/InboxFilters';
import { InboxItemCard } from '../components/InboxItemCard';
import { InboxInsightsPanel } from '../components/InboxInsightsPanel';
import { InboxEmptyState } from '../components/InboxEmptyState';

import {
  useSmartInboxItems,
  useSmartInboxStats,
  useSmartInboxInsights,
  usePerformInboxAction,
  useSnoozeInboxItem,
  useDismissInboxItem,
  useTriggerAggregation,
  useSmartInboxRealtime,
} from '../hooks/use-smart-inbox-queries';

import type { InboxStatus, InboxCategory, InboxSortBy, InboxActionType } from '../types';

// ==================== Main Component ====================

export function SmartInboxPage() {
  const { toast } = useToast();

  // Feature 9: WebSocket-basierte Echtzeit-Updates
  useSmartInboxRealtime();

  // State
  const [statusFilter, setStatusFilter] = useState<InboxStatus | 'all'>('all');
  const [categoryFilter, setCategoryFilter] = useState<InboxCategory | 'all'>('all');
  const [sortBy, setSortBy] = useState<InboxSortBy>('mlPriority');
  const [showInsights, setShowInsights] = useState(true);
  const [offset, setOffset] = useState(0);

  // Queries
  const {
    data: itemsData,
    isLoading: itemsLoading,
    error: itemsError,
    refetch: refetchItems,
  } = useSmartInboxItems({
    status: statusFilter === 'all' ? undefined : statusFilter,
    category: categoryFilter === 'all' ? undefined : categoryFilter,
    limit: 20,
    offset,
  });

  const { data: stats, refetch: refetchStats } = useSmartInboxStats();
  const { data: insights, refetch: refetchInsights } = useSmartInboxInsights();

  // Mutations
  const performAction = usePerformInboxAction();
  const snoozeItem = useSnoozeInboxItem();
  const dismissItem = useDismissInboxItem();
  const triggerAggregation = useTriggerAggregation();

  // Extract unique categories from stats
  const availableCategories = useMemo(() => {
    if (!stats?.byCategory) return [];
    return Object.keys(stats.byCategory) as InboxCategory[];
  }, [stats]);

  // Sort items client-side
  const sortedItems = useMemo(() => {
    if (!itemsData?.items) return [];

    const items = [...itemsData.items];

    switch (sortBy) {
      case 'mlPriority':
        return items.sort((a, b) => b.mlPriority - a.mlPriority);
      case 'deadline':
        return items.sort((a, b) => {
          if (!a.deadline && !b.deadline) return 0;
          if (!a.deadline) return 1;
          if (!b.deadline) return -1;
          return new Date(a.deadline).getTime() - new Date(b.deadline).getTime();
        });
      case 'createdAt':
        return items.sort((a, b) =>
          new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime()
        );
      default:
        return items;
    }
  }, [itemsData?.items, sortBy]);

  // Handlers
  const handleRefresh = async () => {
    await Promise.all([refetchItems(), refetchStats(), refetchInsights()]);
    toast({
      title: 'Aktualisiert',
      description: 'Posteingang wurde erfolgreich aktualisiert.',
    });
  };

  const handleAggregation = async () => {
    try {
      await triggerAggregation.mutateAsync();
      toast({
        title: 'Aggregierung gestartet',
        description: 'Neue Elemente werden eingesammelt und verarbeitet.',
      });
    } catch (error) {
      toast({
        title: 'Fehler',
        description: 'Aggregierung konnte nicht gestartet werden.',
        variant: 'destructive',
      });
    }
  };

  const handleAction = async (itemId: string, action: InboxActionType) => {
    try {
      await performAction.mutateAsync({ itemId, action });
      toast({
        title: 'Aktion ausgeführt',
        description: 'Die Aktion wurde erfolgreich ausgeführt.',
      });
    } catch (error) {
      toast({
        title: 'Fehler',
        description: 'Die Aktion konnte nicht ausgeführt werden.',
        variant: 'destructive',
      });
    }
  };

  const handleSnooze = async (itemId: string, snoozeUntil: string) => {
    try {
      await snoozeItem.mutateAsync({ itemId, snoozeUntil });
      toast({
        title: 'Verschoben',
        description: 'Element wurde erfolgreich verschoben.',
      });
    } catch (error) {
      toast({
        title: 'Fehler',
        description: 'Element konnte nicht verschoben werden.',
        variant: 'destructive',
      });
    }
  };

  const handleDismiss = async (itemId: string) => {
    try {
      await dismissItem.mutateAsync(itemId);
      toast({
        title: 'Verworfen',
        description: 'Element wurde erfolgreich verworfen.',
      });
    } catch (error) {
      toast({
        title: 'Fehler',
        description: 'Element konnte nicht verworfen werden.',
        variant: 'destructive',
      });
    }
  };

  const handleLoadMore = () => {
    setOffset((prev) => prev + 20);
  };

  const hasMore = itemsData ? offset + 20 < itemsData.total : false;

  return (
    <ErrorBoundary
      errorTitle="Fehler im Smart Inbox"
      errorDescription="Der intelligente Posteingang konnte nicht geladen werden. Bitte versuchen Sie es erneut."
    >
      <div className="p-8 space-y-6">
        {/* Header */}
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="text-3xl font-bold flex items-center gap-2">
              <Sparkles className="h-8 w-8 text-primary" />
              Smart Inbox
            </h1>
            <p className="text-muted-foreground mt-1">
              Ihr intelligenter Posteingang mit KI-Priorisierung
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={handleAggregation}
              disabled={triggerAggregation.isPending}
            >
              <Sparkles className="h-4 w-4 mr-2" />
              Aggregieren
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setShowInsights(!showInsights)}
              className="hidden lg:flex"
            >
              <Lightbulb className="h-4 w-4 mr-2" />
              {showInsights ? 'Insights ausblenden' : 'Insights anzeigen'}
            </Button>
          </div>
        </div>

        {/* Stats Bar */}
        <InboxStatsBar stats={stats} isLoading={!stats} />

        {/* Filters */}
        <InboxFilters
          statusFilter={statusFilter}
          categoryFilter={categoryFilter}
          sortBy={sortBy}
          availableCategories={availableCategories}
          onStatusChange={setStatusFilter}
          onCategoryChange={setCategoryFilter}
          onSortChange={setSortBy}
          onRefresh={handleRefresh}
          isRefreshing={itemsLoading}
        />

        {/* Main Content Area */}
        <div className="grid gap-6 lg:grid-cols-3">
          {/* Items List (2/3) */}
          <div className="lg:col-span-2 space-y-4">
            {itemsError ? (
              <div className="text-center py-12 text-destructive">
                Fehler beim Laden der Elemente. Bitte versuchen Sie es erneut.
              </div>
            ) : itemsLoading && offset === 0 ? (
              <div className="text-center py-12 text-muted-foreground">
                Lade Elemente...
              </div>
            ) : sortedItems.length === 0 ? (
              <InboxEmptyState />
            ) : (
              <>
                {sortedItems.map((item) => (
                  <InboxItemCard
                    key={item.id}
                    item={item}
                    onAction={handleAction}
                    onSnooze={handleSnooze}
                    onDismiss={handleDismiss}
                  />
                ))}
                {hasMore && (
                  <div className="flex justify-center pt-4">
                    <Button
                      variant="outline"
                      onClick={handleLoadMore}
                      disabled={itemsLoading}
                    >
                      {itemsLoading ? (
                        <>
                          <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
                          Wird geladen...
                        </>
                      ) : (
                        'Mehr laden'
                      )}
                    </Button>
                  </div>
                )}
              </>
            )}
          </div>

          {/* Insights Panel (1/3) - Hidden on mobile */}
          {showInsights && (
            <div className="hidden lg:block">
              <InboxInsightsPanel insights={insights} isLoading={!insights} />
            </div>
          )}
        </div>
      </div>
    </ErrorBoundary>
  );
}

export default SmartInboxPage;
