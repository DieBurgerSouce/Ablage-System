/**
 * ActivityItem Component
 *
 * Einzelner Eintrag in der Activity Timeline.
 */

import { useMemo } from 'react';
import { Link } from '@tanstack/react-router';
import {
  FileText,
  Upload,
  Eye,
  Download,
  Edit,
  Trash,
  Archive,
  RotateCcw,
  Share2,
  FolderInput,
  Scan,
  CheckCircle,
  XCircle,
  Clock,
  Check,
  X,
  MessageCircle,
  Tag,
  UserPlus,
  UserMinus,
  Shield,
  Users,
  Settings,
  Mail,
  Activity,
} from 'lucide-react';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import type { Activity, ActivityColor } from '../types';
import { ACTIVITY_SOURCE_LABELS, getActivityTypeLabel } from '../types';

interface ActivityItemProps {
  activity: Activity;
  showTarget?: boolean;
  isLast?: boolean;
}

// Icon-Mapping für Activity-Typen
const ACTIVITY_ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  'file-plus': FileText,
  upload: Upload,
  eye: Eye,
  download: Download,
  edit: Edit,
  trash: Trash,
  archive: Archive,
  'rotate-ccw': RotateCcw,
  'share-2': Share2,
  'folder-input': FolderInput,
  scan: Scan,
  'check-circle': CheckCircle,
  'x-circle': XCircle,
  clock: Clock,
  check: Check,
  x: X,
  'message-circle': MessageCircle,
  tag: Tag,
  'user-plus': UserPlus,
  'user-minus': UserMinus,
  shield: Shield,
  users: Users,
  settings: Settings,
  mail: Mail,
  activity: Activity,
};

// Farb-Klassen für den Timeline-Punkt
const COLOR_CLASSES: Record<ActivityColor | 'default', string> = {
  green: 'bg-green-500',
  red: 'bg-red-500',
  yellow: 'bg-yellow-500',
  blue: 'bg-blue-500',
  purple: 'bg-purple-500',
  gray: 'bg-gray-400',
  default: 'bg-gray-400',
};

const ICON_COLOR_CLASSES: Record<ActivityColor | 'default', string> = {
  green: 'text-green-600 dark:text-green-400',
  red: 'text-red-600 dark:text-red-400',
  yellow: 'text-yellow-600 dark:text-yellow-400',
  blue: 'text-blue-600 dark:text-blue-400',
  purple: 'text-purple-600 dark:text-purple-400',
  gray: 'text-gray-500',
  default: 'text-gray-500',
};

function formatRelativeTime(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMinutes = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMinutes < 1) {
    return 'Gerade eben';
  } else if (diffMinutes < 60) {
    return `vor ${diffMinutes} ${diffMinutes === 1 ? 'Minute' : 'Minuten'}`;
  } else if (diffHours < 24) {
    return `vor ${diffHours} ${diffHours === 1 ? 'Stunde' : 'Stunden'}`;
  } else if (diffDays < 7) {
    return `vor ${diffDays} ${diffDays === 1 ? 'Tag' : 'Tagen'}`;
  } else {
    return date.toLocaleDateString('de-DE', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  }
}

function getInitials(name: string | null | undefined): string {
  if (!name) return '?';
  return name
    .split(' ')
    .map((part) => part[0])
    .join('')
    .toUpperCase()
    .slice(0, 2);
}

export function ActivityItem({ activity, showTarget = true, isLast = false }: ActivityItemProps) {
  const Icon = useMemo(() => {
    if (activity.icon && ACTIVITY_ICONS[activity.icon]) {
      return ACTIVITY_ICONS[activity.icon];
    }
    return Activity;
  }, [activity.icon]);

  const color: ActivityColor | 'default' = activity.color || 'default';
  const dotColorClass = COLOR_CLASSES[color];
  const iconColorClass = ICON_COLOR_CLASSES[color];

  const title = getActivityTypeLabel(activity.activityType);
  const relativeTime = formatRelativeTime(activity.createdAt);

  return (
    <div className="relative flex gap-4 pb-6">
      {/* Timeline Line */}
      {!isLast && (
        <div className="absolute left-[19px] top-10 bottom-0 w-0.5 bg-border" />
      )}

      {/* Timeline Dot */}
      <div
        className={cn(
          'relative z-10 flex h-10 w-10 items-center justify-center rounded-full border-4 border-background',
          dotColorClass
        )}
      >
        <Icon className="h-4 w-4 text-white" />
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0 pt-0.5">
        {/* Header */}
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center gap-2 min-w-0">
            {/* Actor Avatar */}
            {activity.actorName && (
              <Avatar className="h-6 w-6">
                <AvatarFallback className="text-xs">
                  {getInitials(activity.actorName)}
                </AvatarFallback>
              </Avatar>
            )}

            {/* Actor Name + Title */}
            <div className="flex flex-wrap items-baseline gap-1 min-w-0">
              {activity.actorName && (
                <span className="font-medium text-sm truncate">{activity.actorName}</span>
              )}
              <span className={cn('text-sm', iconColorClass)}>{title}</span>
            </div>
          </div>

          {/* Time */}
          <span className="text-xs text-muted-foreground whitespace-nowrap">
            {relativeTime}
          </span>
        </div>

        {/* Target */}
        {showTarget && activity.targetName && (
          <div className="mt-1 flex items-center gap-2">
            {activity.targetType === 'document' && activity.targetId ? (
              <Link
                to="/documents/$documentId"
                params={{ documentId: activity.targetId }}
                className="text-sm text-primary hover:underline truncate"
              >
                {activity.targetName}
              </Link>
            ) : (
              <span className="text-sm text-muted-foreground truncate">
                {activity.targetName}
              </span>
            )}
          </div>
        )}

        {/* Description */}
        {activity.description && (
          <p className="mt-1 text-sm text-muted-foreground line-clamp-2">
            {activity.description}
          </p>
        )}

        {/* Metadata Badges */}
        <div className="mt-2 flex flex-wrap gap-2">
          {/* Source Badge */}
          <Badge variant="outline" className="text-xs">
            {ACTIVITY_SOURCE_LABELS[activity.source]}
          </Badge>

          {/* Important Badge */}
          {activity.isImportant && (
            <Badge variant="destructive" className="text-xs">
              Wichtig
            </Badge>
          )}

          {/* Team Badge */}
          {activity.teamId && (
            <Badge variant="secondary" className="text-xs">
              Team
            </Badge>
          )}

          {/* Chain Badge */}
          {activity.chainId && (
            <Badge variant="secondary" className="text-xs">
              Vorgang
            </Badge>
          )}

          {/* OCR Metadata */}
          {activity.activityType === 'ocr_completed' && activity.metadata?.backend && (
            <Badge variant="outline" className="text-xs">
              {String(activity.metadata.backend)}
            </Badge>
          )}

          {activity.activityType === 'ocr_completed' && activity.metadata?.confidence && (
            <Badge
              variant="outline"
              className={cn(
                'text-xs',
                Number(activity.metadata.confidence) >= 0.9 && 'border-green-500 text-green-600',
                Number(activity.metadata.confidence) >= 0.7 &&
                  Number(activity.metadata.confidence) < 0.9 &&
                  'border-yellow-500 text-yellow-600',
                Number(activity.metadata.confidence) < 0.7 && 'border-red-500 text-red-600'
              )}
            >
              {Math.round(Number(activity.metadata.confidence) * 100)}%
            </Badge>
          )}
        </div>
      </div>
    </div>
  );
}
