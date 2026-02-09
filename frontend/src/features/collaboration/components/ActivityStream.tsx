/**
 * ActivityStream - Aktivitätsverlauf für Dokumente
 *
 * Zeigt chronologisch alle Aktivitäten zu einem Dokument:
 * - Erstellung, Bearbeitung, Downloads
 * - Statusänderungen
 * - Kommentare
 * - Tag-Änderungen
 */

import { Loader2, History, FileText, MessageSquare, Tag, Settings, Download, Eye, Share2, CheckCircle } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { Badge } from '@/components/ui/badge';
import { useActivity } from '../hooks/use-activity';
import type { ActivityType } from '../types/collaboration.types';
import { formatDistanceToNow } from 'date-fns';
import { de } from 'date-fns/locale';
import { cn } from '@/lib/utils';

interface ActivityStreamProps {
  documentId: string;
  className?: string;
}

function getInitials(name: string): string {
  return name
    .split(' ')
    .map((n) => n[0])
    .join('')
    .toUpperCase()
    .slice(0, 2);
}

const ACTIVITY_ICONS: Record<ActivityType, React.ElementType> = {
  document_created: FileText,
  document_updated: Settings,
  document_viewed: Eye,
  document_downloaded: Download,
  comment_added: MessageSquare,
  comment_replied: MessageSquare,
  status_changed: CheckCircle,
  tags_changed: Tag,
  metadata_updated: Settings,
  document_shared: Share2,
};

const ACTIVITY_COLORS: Record<ActivityType, string> = {
  document_created: 'bg-green-500/10 text-green-600',
  document_updated: 'bg-blue-500/10 text-blue-600',
  document_viewed: 'bg-gray-500/10 text-gray-600',
  document_downloaded: 'bg-purple-500/10 text-purple-600',
  comment_added: 'bg-amber-500/10 text-amber-600',
  comment_replied: 'bg-amber-500/10 text-amber-600',
  status_changed: 'bg-cyan-500/10 text-cyan-600',
  tags_changed: 'bg-pink-500/10 text-pink-600',
  metadata_updated: 'bg-indigo-500/10 text-indigo-600',
  document_shared: 'bg-orange-500/10 text-orange-600',
};

export function ActivityStream({ documentId, className }: ActivityStreamProps) {
  const { data, isLoading, error, isError } = useActivity(documentId);

  // Loading state
  if (isLoading) {
    return (
      <Card className={className}>
        <CardContent className="py-8">
          <div className="flex items-center justify-center gap-3 text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin" />
            <span>Lade Aktivitäten...</span>
          </div>
        </CardContent>
      </Card>
    );
  }

  // Error state
  if (isError) {
    return (
      <Card className={className}>
        <CardContent className="py-8">
          <div className="text-center text-destructive">
            <p>Aktivitäten konnten nicht geladen werden.</p>
            <p className="text-xs mt-1">{(error as Error)?.message}</p>
          </div>
        </CardContent>
      </Card>
    );
  }

  const activities = data?.activities || [];

  return (
    <Card className={className}>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-lg">
          <History className="h-5 w-5" />
          Aktivitätsverlauf
          {data?.total ? (
            <span className="text-sm font-normal text-muted-foreground">
              ({data.total})
            </span>
          ) : null}
        </CardTitle>
      </CardHeader>

      <CardContent>
        {activities.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            <History className="h-12 w-12 mx-auto mb-4 opacity-50" />
            <p>Keine Aktivitäten vorhanden.</p>
          </div>
        ) : (
          <div className="relative">
            {/* Timeline line */}
            <div className="absolute left-[18px] top-0 bottom-0 w-px bg-border" />

            <div className="space-y-6">
              {activities.map((activity, _index) => {
                const Icon = ACTIVITY_ICONS[activity.type] || FileText;
                const colorClass = ACTIVITY_COLORS[activity.type] || 'bg-muted text-muted-foreground';
                const timeAgo = formatDistanceToNow(new Date(activity.createdAt), {
                  addSuffix: true,
                  locale: de,
                });

                return (
                  <div key={activity.id} className="relative flex gap-4">
                    {/* Icon */}
                    <div
                      className={cn(
                        'relative z-10 flex h-9 w-9 items-center justify-center rounded-full border bg-background',
                        colorClass
                      )}
                    >
                      <Icon className="h-4 w-4" />
                    </div>

                    {/* Content */}
                    <div className="flex-1 min-w-0 pt-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        {activity.userName !== 'System' && (
                          <Avatar className="h-5 w-5">
                            <AvatarImage src={activity.userAvatar} alt={activity.userName} />
                            <AvatarFallback className="text-[8px]">
                              {getInitials(activity.userName)}
                            </AvatarFallback>
                          </Avatar>
                        )}
                        <span className="font-medium text-sm">
                          {activity.userName}
                        </span>
                        <span className="text-sm text-muted-foreground">
                          {activity.description}
                        </span>
                      </div>

                      {/* Metadata */}
                      {activity.metadata && (
                        <div className="mt-1">
                          {activity.type === 'tags_changed' && activity.metadata.addedTags && (
                            <div className="flex gap-1 flex-wrap">
                              {(activity.metadata.addedTags as string[]).map((tag) => (
                                <Badge key={tag} variant="secondary" className="text-xs">
                                  {tag}
                                </Badge>
                              ))}
                            </div>
                          )}
                          {activity.type === 'metadata_updated' && activity.metadata.oldValue && (
                            <div className="text-xs text-muted-foreground">
                              <span className="line-through">{activity.metadata.oldValue as string}</span>
                              {' → '}
                              <span className="font-medium">{activity.metadata.newValue as string}</span>
                            </div>
                          )}
                        </div>
                      )}

                      {/* Timestamp */}
                      <div className="text-xs text-muted-foreground mt-1">
                        {timeAgo}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default ActivityStream;
