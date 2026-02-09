/**
 * ActivityFeed - Echtzeit-Aktivitaetsverlauf
 *
 * Features:
 * - Zeitstempel + Benutzer + Aktion Eintraege
 * - Aktionstypen: "hat Dokument hochgeladen", "hat Kommentar hinzugefuegt", etc.
 * - Auto-Scroll zum neuesten Eintrag
 * - Max 50 Eintraege mit "Aeltere laden" Button
 * - Filter nach Aktionstyp
 * - WebSocket-Updates fuer neue Aktivitaeten
 */

import { useState, useRef, useEffect, useCallback, useMemo } from 'react';
import {
  Upload,
  MessageSquare,
  Eye,
  Download,
  Tag,
  Share2,
  CheckCircle,
  AlertCircle,
  FileText,
  Clock,
  Filter,
  ChevronDown,
} from 'lucide-react';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { cn } from '@/lib/utils';
import { formatDistanceToNow } from 'date-fns';
import { de } from 'date-fns/locale';
import type { Activity, ActivityType } from '../types/collaboration.types';
import { useRealtimeEvent, type RealtimeEvent } from '@/lib/websocket';

// ==================== Activity Config ====================

const ACTIVITY_CONFIG: Record<
  ActivityType,
  { icon: typeof Upload; label: string; color: string }
> = {
  document_created: {
    icon: Upload,
    label: 'hat Dokument hochgeladen',
    color: 'text-green-500',
  },
  document_updated: {
    icon: FileText,
    label: 'hat Dokument aktualisiert',
    color: 'text-blue-500',
  },
  document_viewed: {
    icon: Eye,
    label: 'hat Dokument angesehen',
    color: 'text-gray-500',
  },
  document_downloaded: {
    icon: Download,
    label: 'hat Dokument heruntergeladen',
    color: 'text-purple-500',
  },
  comment_added: {
    icon: MessageSquare,
    label: 'hat Kommentar hinzugefuegt',
    color: 'text-amber-500',
  },
  comment_replied: {
    icon: MessageSquare,
    label: 'hat auf Kommentar geantwortet',
    color: 'text-amber-500',
  },
  status_changed: {
    icon: CheckCircle,
    label: 'hat Status geaendert',
    color: 'text-emerald-500',
  },
  tags_changed: {
    icon: Tag,
    label: 'hat Tags geaendert',
    color: 'text-orange-500',
  },
  metadata_updated: {
    icon: AlertCircle,
    label: 'hat Metadaten aktualisiert',
    color: 'text-slate-500',
  },
  document_shared: {
    icon: Share2,
    label: 'hat Dokument geteilt',
    color: 'text-indigo-500',
  },
};

const FILTER_OPTIONS: { value: ActivityType | 'all'; label: string }[] = [
  { value: 'all', label: 'Alle Aktivitaeten' },
  { value: 'document_created', label: 'Hochgeladen' },
  { value: 'document_updated', label: 'Aktualisiert' },
  { value: 'comment_added', label: 'Kommentare' },
  { value: 'status_changed', label: 'Statusaenderungen' },
  { value: 'document_shared', label: 'Geteilt' },
];

// ==================== Helpers ====================

function getInitials(name: string): string {
  const parts = name.split(/\s+/);
  if (parts.length >= 2) {
    return (parts[0][0] + parts[1][0]).toUpperCase();
  }
  return name.slice(0, 2).toUpperCase();
}

// ==================== Sub-Components ====================

interface ActivityEntryProps {
  activity: Activity;
}

function ActivityEntry({ activity }: ActivityEntryProps) {
  const config = ACTIVITY_CONFIG[activity.type] ?? {
    icon: FileText,
    label: activity.description || 'Unbekannte Aktion',
    color: 'text-gray-500',
  };
  const Icon = config.icon;

  const timeAgo = formatDistanceToNow(new Date(activity.createdAt), {
    addSuffix: true,
    locale: de,
  });

  return (
    <div className="flex items-start gap-3 py-2.5 px-3 hover:bg-accent/30 rounded-md transition-colors">
      {/* Avatar */}
      <Avatar className="h-7 w-7 flex-shrink-0 mt-0.5">
        {activity.userAvatar ? (
          <AvatarImage src={activity.userAvatar} alt={activity.userName} />
        ) : null}
        <AvatarFallback className="text-[10px]">
          {getInitials(activity.userName)}
        </AvatarFallback>
      </Avatar>

      {/* Content */}
      <div className="flex-1 min-w-0">
        <p className="text-sm">
          <span className="font-medium">{activity.userName}</span>{' '}
          <span className="text-muted-foreground">{config.label}</span>
        </p>
        {activity.description && activity.description !== config.label && (
          <p className="text-xs text-muted-foreground mt-0.5 truncate">
            {activity.description}
          </p>
        )}
      </div>

      {/* Icon + Time */}
      <div className="flex flex-col items-end gap-1 flex-shrink-0">
        <Icon className={cn('h-3.5 w-3.5', config.color)} aria-hidden="true" />
        <span className="text-[10px] text-muted-foreground whitespace-nowrap">
          {timeAgo}
        </span>
      </div>
    </div>
  );
}

// ==================== Main Component ====================

interface ActivityFeedProps {
  /** Initiale Aktivitaeten */
  activities?: Activity[];
  /** Maximale Eintraege im Feed */
  maxEntries?: number;
  /** Callback zum Laden aelterer Eintraege */
  onLoadMore?: () => void;
  /** Gibt es weitere Eintraege */
  hasMore?: boolean;
  /** Laede-Status */
  isLoading?: boolean;
  /** Hoehe des Scroll-Bereichs */
  height?: string;
  className?: string;
}

export function ActivityFeed({
  activities: initialActivities = [],
  maxEntries = 50,
  onLoadMore,
  hasMore = false,
  isLoading = false,
  height = '400px',
  className,
}: ActivityFeedProps) {
  const [activities, setActivities] = useState<Activity[]>(initialActivities);
  const [filter, setFilter] = useState<ActivityType | 'all'>('all');
  const scrollRef = useRef<HTMLDivElement>(null);
  const isAutoScrollRef = useRef(true);

  // Sync with external activities
  useEffect(() => {
    setActivities(initialActivities);
  }, [initialActivities]);

  // Subscribe to real-time events via the existing global WebSocket
  const handleRealtimeEvent = useCallback(
    (event: RealtimeEvent) => {
      // Map WebSocket events to Activity entries
      const eventTypeMap: Record<string, ActivityType> = {
        'document.uploaded': 'document_created',
        'document.updated': 'document_updated',
        'comment.created': 'comment_added',
        'comment.replied': 'comment_replied',
      };

      const activityType = eventTypeMap[event.event_type];
      if (!activityType) return;

      const newActivity: Activity = {
        id: event.event_id,
        documentId: (event.payload.document_id as string) || '',
        userId: (event.payload.user_id as string) || '',
        userName: (event.payload.user_name as string) || 'Unbekannt',
        type: activityType,
        description: (event.payload.description as string) || '',
        createdAt: event.timestamp,
      };

      setActivities((prev) => {
        const updated = [newActivity, ...prev];
        return updated.slice(0, maxEntries);
      });

      // Auto-scroll to top (newest)
      if (isAutoScrollRef.current && scrollRef.current) {
        scrollRef.current.scrollTop = 0;
      }
    },
    [maxEntries],
  );

  useRealtimeEvent('document.uploaded', handleRealtimeEvent);
  useRealtimeEvent('document.updated', handleRealtimeEvent);
  useRealtimeEvent('comment.created', handleRealtimeEvent);
  useRealtimeEvent('comment.replied', handleRealtimeEvent);

  // Filtered activities
  const filteredActivities = useMemo(
    () =>
      filter === 'all'
        ? activities
        : activities.filter((a) => a.type === filter),
    [activities, filter],
  );

  const currentFilterLabel = FILTER_OPTIONS.find((o) => o.value === filter)?.label ?? 'Alle';

  return (
    <div className={cn('flex flex-col', className)}>
      {/* Header with Filter */}
      <div className="flex items-center justify-between px-3 py-2 border-b">
        <div className="flex items-center gap-2">
          <Clock className="h-4 w-4 text-muted-foreground" />
          <h3 className="text-sm font-medium">Aktivitaeten</h3>
          {activities.length > 0 && (
            <Badge variant="secondary" className="text-[10px] px-1.5 py-0">
              {filteredActivities.length}
            </Badge>
          )}
        </div>

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="sm" className="h-7 text-xs gap-1">
              <Filter className="h-3 w-3" />
              {currentFilterLabel}
              <ChevronDown className="h-3 w-3" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            {FILTER_OPTIONS.map((option) => (
              <DropdownMenuItem
                key={option.value}
                onClick={() => setFilter(option.value)}
                className={cn(filter === option.value && 'bg-accent')}
              >
                {option.label}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      {/* Activity List */}
      <ScrollArea style={{ height }} ref={scrollRef}>
        <div className="divide-y divide-border/50">
          {filteredActivities.length === 0 && (
            <div className="flex flex-col items-center justify-center py-8 text-muted-foreground">
              <Clock className="h-8 w-8 mb-2 opacity-50" />
              <p className="text-sm">Keine Aktivitaeten vorhanden</p>
            </div>
          )}
          {filteredActivities.map((activity) => (
            <ActivityEntry key={activity.id} activity={activity} />
          ))}
        </div>

        {/* Load More */}
        {hasMore && (
          <div className="p-3 text-center">
            <Button
              variant="ghost"
              size="sm"
              className="text-xs"
              onClick={onLoadMore}
              disabled={isLoading}
            >
              {isLoading ? 'Wird geladen...' : 'Aeltere laden'}
            </Button>
          </div>
        )}
      </ScrollArea>
    </div>
  );
}

export default ActivityFeed;
