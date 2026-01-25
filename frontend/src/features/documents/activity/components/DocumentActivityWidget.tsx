/**
 * DocumentActivityWidget Component
 *
 * Kompakte Activity-Ansicht fuer Integration in Dokumentenansichten.
 */

import { useMemo } from 'react';
import { Link } from '@tanstack/react-router';
import { History, ChevronRight, Loader2 } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { useDocumentTimeline } from '../hooks';
import type { Activity } from '../types';
import { ActivityItem } from './ActivityItem';

interface DocumentActivityWidgetProps {
  documentId: string;
  maxItems?: number;
  maxHeight?: string;
  showViewAll?: boolean;
  className?: string;
}

export function DocumentActivityWidget({
  documentId,
  maxItems = 5,
  maxHeight = 'max-h-[400px]',
  showViewAll = true,
  className,
}: DocumentActivityWidgetProps) {
  const { data, isLoading, error } = useDocumentTimeline(documentId, {
    limit: maxItems,
  });

  const activities = useMemo(() => data?.items || [], [data]);

  if (isLoading) {
    return (
      <Card className={className}>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-sm font-medium">
            <History className="h-4 w-4" />
            Aktivitaeten
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-center py-8">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card className={className}>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-sm font-medium">
            <History className="h-4 w-4" />
            Aktivitaeten
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground text-center py-4">
            Aktivitaeten konnten nicht geladen werden.
          </p>
        </CardContent>
      </Card>
    );
  }

  if (activities.length === 0) {
    return (
      <Card className={className}>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-sm font-medium">
            <History className="h-4 w-4" />
            Aktivitaeten
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground text-center py-4">
            Noch keine Aktivitaeten
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className={className}>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2 text-sm font-medium">
            <History className="h-4 w-4" />
            Aktivitaeten ({activities.length})
          </CardTitle>
          {showViewAll && (
            <Link
              to="/documents/$documentId/activity"
              params={{ documentId }}
            >
              <Button variant="ghost" size="sm" className="h-7 px-2">
                Alle
                <ChevronRight className="h-4 w-4 ml-1" />
              </Button>
            </Link>
          )}
        </div>
      </CardHeader>
      <CardContent className="pt-0">
        <ScrollArea className={maxHeight}>
          <div className="space-y-0 pr-4">
            {activities.map((activity, index) => (
              <ActivityItem
                key={activity.id}
                activity={activity}
                showTarget={false}
                isLast={index === activities.length - 1}
              />
            ))}
          </div>
        </ScrollArea>

        {data?.hasMore && showViewAll && (
          <div className="mt-4 pt-4 border-t">
            <Link
              to="/documents/$documentId/activity"
              params={{ documentId }}
              className="block"
            >
              <Button variant="outline" size="sm" className="w-full">
                Alle Aktivitaeten anzeigen
                <ChevronRight className="h-4 w-4 ml-1" />
              </Button>
            </Link>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
