/**
 * ActivityTimeline Component
 *
 * Vertikale Timeline-Komponente fuer Aktivitaeten.
 */

import { useMemo } from 'react';
import { Loader2, History } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { cn } from '@/lib/utils';
import type { Activity } from '../types';
import { ActivityItem } from './ActivityItem';

interface ActivityTimelineProps {
  activities: Activity[];
  isLoading?: boolean;
  hasMore?: boolean;
  onLoadMore?: () => void;
  isLoadingMore?: boolean;
  showTarget?: boolean;
  maxHeight?: string;
  title?: string;
  emptyMessage?: string;
  className?: string;
}

// Gruppiert Aktivitaeten nach Datum
function groupActivitiesByDate(activities: Activity[]): Map<string, Activity[]> {
  const groups = new Map<string, Activity[]>();

  for (const activity of activities) {
    const date = new Date(activity.createdAt);
    const today = new Date();
    const yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);

    let dateKey: string;

    if (date.toDateString() === today.toDateString()) {
      dateKey = 'Heute';
    } else if (date.toDateString() === yesterday.toDateString()) {
      dateKey = 'Gestern';
    } else {
      dateKey = date.toLocaleDateString('de-DE', {
        weekday: 'long',
        day: '2-digit',
        month: 'long',
        year: 'numeric',
      });
    }

    if (!groups.has(dateKey)) {
      groups.set(dateKey, []);
    }
    groups.get(dateKey)!.push(activity);
  }

  return groups;
}

export function ActivityTimeline({
  activities,
  isLoading = false,
  hasMore = false,
  onLoadMore,
  isLoadingMore = false,
  showTarget = true,
  maxHeight,
  title = 'Aktivitaeten',
  emptyMessage = 'Keine Aktivitaeten vorhanden',
  className,
}: ActivityTimelineProps) {
  const groupedActivities = useMemo(
    () => groupActivitiesByDate(activities),
    [activities]
  );

  if (isLoading) {
    return (
      <Card className={className}>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <History className="h-5 w-5" />
            {title}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-center py-8">
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          </div>
        </CardContent>
      </Card>
    );
  }

  if (activities.length === 0) {
    return (
      <Card className={className}>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <History className="h-5 w-5" />
            {title}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col items-center justify-center py-8 text-center">
            <History className="h-12 w-12 text-muted-foreground/30 mb-4" />
            <p className="text-muted-foreground">{emptyMessage}</p>
          </div>
        </CardContent>
      </Card>
    );
  }

  const content = (
    <div className="space-y-6">
      {Array.from(groupedActivities.entries()).map(([dateLabel, dateActivities]) => (
        <div key={dateLabel}>
          {/* Date Header */}
          <div className="sticky top-0 z-20 bg-background/95 backdrop-blur-sm py-2 mb-4">
            <h3 className="text-sm font-medium text-muted-foreground">{dateLabel}</h3>
          </div>

          {/* Activities for this date */}
          <div className="space-y-0">
            {dateActivities.map((activity, index) => (
              <ActivityItem
                key={activity.id}
                activity={activity}
                showTarget={showTarget}
                isLast={index === dateActivities.length - 1}
              />
            ))}
          </div>
        </div>
      ))}

      {/* Load More Button */}
      {hasMore && onLoadMore && (
        <div className="flex justify-center pt-4">
          <Button
            variant="outline"
            onClick={onLoadMore}
            disabled={isLoadingMore}
          >
            {isLoadingMore ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin mr-2" />
                Wird geladen...
              </>
            ) : (
              'Mehr laden'
            )}
          </Button>
        </div>
      )}
    </div>
  );

  return (
    <Card className={className}>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <History className="h-5 w-5" />
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent>
        {maxHeight ? (
          <ScrollArea className={cn('pr-4', maxHeight)}>
            {content}
          </ScrollArea>
        ) : (
          content
        )}
      </CardContent>
    </Card>
  );
}
