/**
 * EntityTimeline Component
 *
 * Zeigt eine chronologische Timeline der Aktivitäten eines Geschäftspartners.
 * Verwendet React Query für Datenabruf.
 */

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from '@tanstack/react-router';
import { Clock, FileText, Filter, RefreshCw } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import {
    DropdownMenu,
    DropdownMenuCheckboxItem,
    DropdownMenuContent,
    DropdownMenuLabel,
    DropdownMenuSeparator,
    DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { TimelineEvent } from './TimelineEvent';
import {
    fetchEntityTimeline,
    relationshipsQueryKeys,
    type TimelineEventType,
} from '../api/relationships-api';

// ==================== Types ====================

interface EntityTimelineProps {
    entityId: string;
    entityName?: string;
    compact?: boolean;
    showHeader?: boolean;
    maxEvents?: number;
}

// ==================== Event Type Labels ====================

const EVENT_TYPE_LABELS: Record<TimelineEventType, string> = {
    document_linked: 'Dokumente',
    entity_created: 'Erstellt',
    entity_updated: 'Aktualisiert',
};

// ==================== Loading Skeleton ====================

function TimelineSkeleton() {
    return (
        <div className="space-y-4">
            {[1, 2, 3].map((i) => (
                <div key={i} className="flex gap-4">
                    <Skeleton className="h-10 w-10 rounded-full shrink-0" />
                    <div className="flex-1 space-y-2">
                        <Skeleton className="h-4 w-32" />
                        <Skeleton className="h-16 w-full rounded-lg" />
                    </div>
                </div>
            ))}
        </div>
    );
}

// ==================== Empty State ====================

function TimelineEmpty() {
    return (
        <div className="flex flex-col items-center justify-center py-12 text-center">
            <Clock className="h-12 w-12 text-muted-foreground mb-4" />
            <p className="text-muted-foreground">
                Keine Aktivitäten gefunden
            </p>
            <p className="text-sm text-muted-foreground/70 mt-1">
                Hier erscheinen zukünftige Aktivitäten dieses Geschäftspartners.
            </p>
        </div>
    );
}

// ==================== Main Component ====================

export function EntityTimeline({
    entityId,
    entityName,
    compact = false,
    showHeader = true,
    maxEvents = 50,
}: EntityTimelineProps) {
    const navigate = useNavigate();
    const [selectedTypes, setSelectedTypes] = useState<TimelineEventType[]>([]);

    // Fetch timeline data
    const {
        data,
        isLoading,
        isError,
        error,
        refetch,
        isFetching,
    } = useQuery({
        queryKey: relationshipsQueryKeys.entityTimeline(entityId),
        queryFn: () => fetchEntityTimeline({
            entityId,
            limit: maxEvents,
            eventTypes: selectedTypes.length > 0 ? selectedTypes : undefined,
        }),
        enabled: !!entityId,
    });

    // Handle filter toggle
    const toggleEventType = (type: TimelineEventType) => {
        setSelectedTypes((prev) =>
            prev.includes(type)
                ? prev.filter((t) => t !== type)
                : [...prev, type]
        );
    };

    // Handle document click
    const handleEventClick = (documentId: string | undefined) => {
        if (documentId) {
            navigate({ to: '/viewer/$documentId', params: { documentId } });
        }
    };

    // Filter events
    const filteredEvents = data?.events.filter((event) =>
        selectedTypes.length === 0 || selectedTypes.includes(event.eventType)
    ) ?? [];

    // Count by type
    const eventCounts = data?.events.reduce(
        (acc, event) => {
            acc[event.eventType] = (acc[event.eventType] || 0) + 1;
            return acc;
        },
        {} as Record<TimelineEventType, number>
    ) ?? {};

    return (
        <Card className={compact ? 'border-0 shadow-none' : undefined}>
            {showHeader && !compact && (
                <CardHeader className="pb-3">
                    <div className="flex items-start justify-between">
                        <div>
                            <CardTitle className="text-lg flex items-center gap-2">
                                <Clock className="h-5 w-5" />
                                Aktivitäten
                            </CardTitle>
                            <CardDescription>
                                {entityName
                                    ? `Timeline für ${entityName}`
                                    : 'Chronologische Übersicht der Aktivitäten'}
                            </CardDescription>
                        </div>

                        <div className="flex items-center gap-2">
                            {/* Filter Dropdown */}
                            <DropdownMenu>
                                <DropdownMenuTrigger asChild>
                                    <Button variant="outline" size="sm" className="gap-2">
                                        <Filter className="h-4 w-4" />
                                        Filter
                                        {selectedTypes.length > 0 && (
                                            <Badge variant="secondary" className="ml-1 h-5 px-1.5">
                                                {selectedTypes.length}
                                            </Badge>
                                        )}
                                    </Button>
                                </DropdownMenuTrigger>
                                <DropdownMenuContent align="end" className="w-48">
                                    <DropdownMenuLabel>Event-Typen</DropdownMenuLabel>
                                    <DropdownMenuSeparator />
                                    {(Object.keys(EVENT_TYPE_LABELS) as TimelineEventType[]).map((type) => (
                                        <DropdownMenuCheckboxItem
                                            key={type}
                                            checked={selectedTypes.includes(type)}
                                            onCheckedChange={() => toggleEventType(type)}
                                        >
                                            <span className="flex-1">{EVENT_TYPE_LABELS[type]}</span>
                                            <span className="text-muted-foreground text-xs">
                                                {eventCounts[type] || 0}
                                            </span>
                                        </DropdownMenuCheckboxItem>
                                    ))}
                                </DropdownMenuContent>
                            </DropdownMenu>

                            {/* Refresh Button */}
                            <Button
                                variant="ghost"
                                size="icon"
                                onClick={() => refetch()}
                                disabled={isFetching}
                            >
                                <RefreshCw className={`h-4 w-4 ${isFetching ? 'animate-spin' : ''}`} />
                            </Button>
                        </div>
                    </div>

                    {/* Stats Summary */}
                    {data && (
                        <div className="flex gap-2 mt-3">
                            <Badge variant="outline" className="gap-1">
                                <FileText className="h-3 w-3" />
                                {eventCounts.document_linked || 0} Dokumente
                            </Badge>
                            <Badge variant="outline">
                                {data.total} Ereignisse gesamt
                            </Badge>
                        </div>
                    )}
                </CardHeader>
            )}

            <CardContent className={compact ? 'p-0' : undefined}>
                {isLoading ? (
                    <TimelineSkeleton />
                ) : isError ? (
                    <div className="flex flex-col items-center justify-center py-8 text-center">
                        <p className="text-destructive mb-2">
                            Fehler beim Laden der Timeline
                        </p>
                        <p className="text-sm text-muted-foreground mb-4">
                            {error instanceof Error ? error.message : 'Unbekannter Fehler'}
                        </p>
                        <Button variant="outline" size="sm" onClick={() => refetch()}>
                            Erneut versuchen
                        </Button>
                    </div>
                ) : filteredEvents.length === 0 ? (
                    <TimelineEmpty />
                ) : (
                    <div className="relative">
                        {filteredEvents.map((event, index) => (
                            <TimelineEvent
                                key={event.id}
                                event={event}
                                isLast={index === filteredEvents.length - 1}
                                onClick={
                                    event.metadata?.documentId
                                        ? () => handleEventClick(event.metadata?.documentId)
                                        : undefined
                                }
                            />
                        ))}
                    </div>
                )}

                {/* Load More (optional) */}
                {data && filteredEvents.length >= maxEvents && (
                    <div className="flex justify-center pt-4">
                        <Button variant="outline" size="sm" disabled>
                            Alle {data.total} Ereignisse geladen
                        </Button>
                    </div>
                )}
            </CardContent>
        </Card>
    );
}

export default EntityTimeline;
