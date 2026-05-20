/**
 * ActivityTimeline - Timeline für Dokument-Aktivitäten
 *
 * Features:
 * - Chronologische Aktivitätsliste mit Icons
 * - Zeitstempel + Benutzer + Aktion
 * - System-Events (OCR, Auto-Kategorisierung)
 * - Gruppierung nach Datum
 * - Echtzeit-Updates via WebSocket
 */

import { useMemo } from 'react';
import {
  Upload,
  FileText,
  Tag,
  CheckCircle,
  AlertCircle,
  Cpu,
  Zap,
  Clock,
  User,
} from 'lucide-react';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { cn } from '@/lib/utils';
import { format, formatDistanceToNow, isToday, isYesterday } from 'date-fns';
import { de } from 'date-fns/locale';
import type { Activity, ActivityType } from '../types/collaboration.types';

// ==================== Activity Config ====================

const ACTIVITY_CONFIG: Record<
  ActivityType,
  { icon: typeof Upload; label: string; color: string; systemEvent?: boolean }
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
    icon: User,
    label: 'hat Dokument angesehen',
    color: 'text-gray-400',
  },
  document_downloaded: {
    icon: Upload,
    label: 'hat Dokument heruntergeladen',
    color: 'text-purple-500',
  },
  comment_added: {
    icon: FileText,
    label: 'hat kommentiert',
    color: 'text-amber-500',
  },
  comment_replied: {
    icon: FileText,
    label: 'hat geantwortet',
    color: 'text-amber-500',
  },
  status_changed: {
    icon: CheckCircle,
    label: 'hat Status geändert',
    color: 'text-emerald-500',
  },
  tags_changed: {
    icon: Tag,
    label: 'hat Tags geändert',
    color: 'text-orange-500',
  },
  metadata_updated: {
    icon: AlertCircle,
    label: 'hat Metadaten aktualisiert',
    color: 'text-slate-500',
  },
  document_shared: {
    icon: Zap,
    label: 'hat Dokument geteilt',
    color: 'text-indigo-500',
  },
};

// ==================== Helpers ====================

function getInitials(name: string): string {
  const parts = name.split(/\s+/);
  if (parts.length >= 2) {
    return (parts[0][0] + parts[1][0]).toUpperCase();
  }
  return name.slice(0, 2).toUpperCase();
}

function getDateLabel(date: Date): string {
  if (isToday(date)) {
    return 'Heute';
  }
  if (isYesterday(date)) {
    return 'Gestern';
  }
  return format(date, 'dd.MM.yyyy', { locale: de });
}

// ==================== Sub-Components ====================

interface ActivityItemProps {
  activity: Activity;
  showAvatar?: boolean;
}

function ActivityItem({ activity, showAvatar = true }: ActivityItemProps) {
  const config = ACTIVITY_CONFIG[activity.type] ?? {
    icon: FileText,
    label: activity.description || 'Unbekannte Aktion',
    color: 'text-gray-500',
  };
  const Icon = config.icon;
  const isSystemEvent = activity.userId === 'system';

  const timeAgo = formatDistanceToNow(new Date(activity.createdAt), {
    addSuffix: true,
    locale: de,
  });

  return (
    <div className="flex gap-3 pb-4 relative">
      {/* Timeline Line */}
      <div className="absolute left-[15px] top-8 bottom-0 w-px bg-border" />

      {/* Icon or Avatar */}
      <div className="relative z-10">
        {showAvatar && !isSystemEvent ? (
          <Avatar className="h-8 w-8 ring-2 ring-background">
            {activity.userAvatar ? (
              <AvatarImage src={activity.userAvatar} alt={activity.userName} />
            ) : null}
            <AvatarFallback className="text-[10px]">
              {getInitials(activity.userName)}
            </AvatarFallback>
          </Avatar>
        ) : (
          <div
            className={cn(
              'h-8 w-8 rounded-full flex items-center justify-center ring-2 ring-background',
              isSystemEvent ? 'bg-muted' : 'bg-background'
            )}
          >
            <Icon className={cn('h-4 w-4', config.color)} />
          </div>
        )}
      </div>

      {/* Content */}
      <div className="flex-1 pt-0.5">
        <div className="flex items-start justify-between gap-2">
          <div className="flex-1">
            {isSystemEvent ? (
              <p className="text-sm">
                <span className="flex items-center gap-1.5">
                  <Cpu className="h-3.5 w-3.5 text-muted-foreground inline" />
                  <span className="font-medium text-muted-foreground">System</span>
                </span>
                <span className="text-muted-foreground ml-1">{config.label}</span>
              </p>
            ) : (
              <p className="text-sm">
                <span className="font-medium">{activity.userName}</span>{' '}
                <span className="text-muted-foreground">{config.label}</span>
              </p>
            )}

            {activity.description && activity.description !== config.label && (
              <p className="text-xs text-muted-foreground mt-1">{activity.description}</p>
            )}

            {/* Metadata Badge */}
            {activity.metadata && Object.keys(activity.metadata).length > 0 && (
              <div className="flex flex-wrap gap-1 mt-1.5">
                {Object.entries(activity.metadata).map(([key, value]) => (
                  <Badge key={key} variant="outline" className="text-[10px] px-1.5 py-0">
                    {key}: {String(value)}
                  </Badge>
                ))}
              </div>
            )}
          </div>

          <span className="text-[10px] text-muted-foreground whitespace-nowrap">{timeAgo}</span>
        </div>
      </div>
    </div>
  );
}

// ==================== Main Component ====================

interface ActivityTimelineProps {
  /** Aktivitäten (chronologisch sortiert) */
  activities: Activity[];
  /** Zeige Avatare */
  showAvatars?: boolean;
  /** Gruppierung nach Datum */
  groupByDate?: boolean;
  /** Höhe des Scroll-Bereichs */
  height?: string;
  /** Leere-State Nachricht */
  emptyMessage?: string;
  className?: string;
}

export function ActivityTimeline({
  activities,
  showAvatars = true,
  groupByDate = true,
  height = '500px',
  emptyMessage = 'Keine Aktivitäten vorhanden',
  className,
}: ActivityTimelineProps) {
  // Gruppierung nach Datum
  const groupedActivities = useMemo(() => {
    if (!groupByDate) {
      return { all: activities };
    }

    const groups: Record<string, Activity[]> = {};
    activities.forEach((activity) => {
      const date = new Date(activity.createdAt);
      const label = getDateLabel(date);
      if (!groups[label]) {
        groups[label] = [];
      }
      groups[label].push(activity);
    });
    return groups;
  }, [activities, groupByDate]);

  const dateKeys = Object.keys(groupedActivities);

  return (
    <div className={cn('flex flex-col border rounded-lg', className)}>
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-3 border-b bg-muted/30">
        <Clock className="h-4 w-4 text-muted-foreground" />
        <h3 className="text-sm font-medium">Aktivitätsverlauf</h3>
        {activities.length > 0 && (
          <Badge variant="secondary" className="text-[10px] px-1.5 py-0 ml-auto">
            {activities.length}
          </Badge>
        )}
      </div>

      {/* Timeline */}
      <ScrollArea style={{ height }}>
        <div className="p-4">
          {activities.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
              <Clock className="h-12 w-12 mb-3 opacity-20" />
              <p className="text-sm">{emptyMessage}</p>
            </div>
          ) : (
            <div className="space-y-6">
              {dateKeys.map((dateLabel) => (
                <div key={dateLabel}>
                  {groupByDate && (
                    <div className="flex items-center gap-2 mb-3">
                      <span className="text-xs font-medium text-muted-foreground">
                        {dateLabel}
                      </span>
                      <div className="flex-1 h-px bg-border" />
                    </div>
                  )}
                  <div className="space-y-0">
                    {groupedActivities[dateLabel].map((activity) => (
                      <ActivityItem
                        key={activity.id}
                        activity={activity}
                        showAvatar={showAvatars}
                      />
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </ScrollArea>
    </div>
  );
}

export default ActivityTimeline;
