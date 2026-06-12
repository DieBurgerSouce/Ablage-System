/**
 * MentionsBadge - Bell-Icon mit Unread-Count für Mentions
 *
 * Features:
 * - Bell-Icon mit Badge
 * - Unread Count aus useMentions Hook
 * - Click öffnet Mentions-Dropdown oder navigiert zu Mentions-Seite
 * - Pulsing Animation bei neuen Mentions
 */

import { useState } from 'react';
import { Bell } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { cn } from '@/lib/utils';
import { formatDistanceToNow } from 'date-fns';
import { de } from 'date-fns/locale';
import { useMentions, useMarkMentionAsRead } from '../hooks/useMentions';
import { Link } from '@tanstack/react-router';

// ==================== Helpers ====================

function getInitials(name: string): string {
  const parts = name.split(/\s+/);
  if (parts.length >= 2) {
    return (parts[0][0] + parts[1][0]).toUpperCase();
  }
  return name.slice(0, 2).toUpperCase();
}

// ==================== Sub-Components ====================

function MentionItem({
  mention,
  onMarkAsRead,
}: {
  mention: any;
  onMarkAsRead: (id: string) => void;
}) {
  const timeAgo = formatDistanceToNow(new Date(mention.mentioned_at), {
    addSuffix: true,
    locale: de,
  });

  return (
    <Link
      to="/documents/$documentId"
      params={{ documentId: mention.document_id }}
      className="block p-3 hover:bg-accent/50 transition-colors border-b last:border-0"
      onClick={() => {
        if (!mention.is_read) {
          onMarkAsRead(mention.id);
        }
      }}
    >
      <div className="flex gap-3">
        <Avatar className="h-8 w-8 flex-shrink-0">
          {mention.mentioned_by_user_avatar ? (
            <AvatarImage
              src={mention.mentioned_by_user_avatar}
              alt={mention.mentioned_by_user_name}
            />
          ) : null}
          <AvatarFallback className="text-[10px]">
            {getInitials(mention.mentioned_by_user_name)}
          </AvatarFallback>
        </Avatar>

        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium mb-0.5">{mention.mentioned_by_user_name}</p>
          <p className="text-xs text-muted-foreground mb-1">
            hat Sie in <span className="font-medium">{mention.document_name}</span> erwähnt
          </p>
          <p className="text-xs text-muted-foreground line-clamp-2 mb-1">
            "{mention.comment_text}"
          </p>
          <span className="text-[10px] text-muted-foreground">{timeAgo}</span>
        </div>

        {!mention.is_read && (
          <div className="flex-shrink-0">
            <div className="h-2 w-2 rounded-full bg-blue-500" />
          </div>
        )}
      </div>
    </Link>
  );
}

// ==================== Main Component ====================

interface MentionsBadgeProps {
  /** Zeige Dropdown-Vorschau */
  showPreview?: boolean;
  /** Maximale Mentions in Dropdown */
  previewLimit?: number;
  className?: string;
}

export function MentionsBadge({
  showPreview = true,
  previewLimit = 5,
  className,
}: MentionsBadgeProps) {
  const [open, setOpen] = useState(false);
  const { data, isLoading } = useMentions(true);
  const markAsRead = useMarkMentionAsRead();

  const unreadCount = data?.unread_count ?? 0;
  const mentions = data?.mentions ?? [];
  const previewMentions = mentions.slice(0, previewLimit);
  const hasMore = mentions.length > previewLimit;

  const handleMarkAsRead = (mentionId: string) => {
    markAsRead.mutate(mentionId);
  };

  if (!showPreview) {
    // Simple Badge ohne Dropdown
    return (
      <Link to="/activity" className={cn('relative', className)}>
        <Button variant="ghost" size="icon" className="relative">
          <Bell className="h-5 w-5" />
          {unreadCount > 0 && (
            <Badge
              variant="destructive"
              className="absolute -top-1 -right-1 h-5 w-5 flex items-center justify-center p-0 text-[10px]"
            >
              {unreadCount > 9 ? '9+' : unreadCount}
            </Badge>
          )}
        </Button>
      </Link>
    );
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="ghost" size="icon" className={cn('relative', className)}>
          <Bell className="h-5 w-5" />
          {unreadCount > 0 && (
            <>
              <Badge
                variant="destructive"
                className="absolute -top-1 -right-1 h-5 w-5 flex items-center justify-center p-0 text-[10px]"
              >
                {unreadCount > 9 ? '9+' : unreadCount}
              </Badge>
              {/* Pulsing animation */}
              <span className="absolute -top-1 -right-1 h-5 w-5 rounded-full bg-destructive animate-ping opacity-75" />
            </>
          )}
        </Button>
      </PopoverTrigger>

      <PopoverContent align="end" className="w-96 p-0">
        <div className="border-b px-4 py-3">
          <h3 className="font-medium text-sm">Erwähnungen</h3>
          {unreadCount > 0 && (
            <p className="text-xs text-muted-foreground mt-0.5">
              {unreadCount} ungelesen{unreadCount > 1 ? 'e' : ''}
            </p>
          )}
        </div>

        {isLoading ? (
          <div className="p-8 text-center text-sm text-muted-foreground">Wird geladen...</div>
        ) : mentions.length === 0 ? (
          <div className="p-8 text-center text-sm text-muted-foreground">
            Keine neuen Erwähnungen
          </div>
        ) : (
          <>
            <ScrollArea className="max-h-96">
              {previewMentions.map((mention) => (
                <MentionItem
                  key={mention.id}
                  mention={mention}
                  onMarkAsRead={handleMarkAsRead}
                />
              ))}
            </ScrollArea>

            {hasMore && (
              <div className="border-t p-2 text-center">
                <Link to="/activity">
                  <Button variant="ghost" size="sm" className="text-xs w-full">
                    Alle {mentions.length} Erwähnungen anzeigen
                  </Button>
                </Link>
              </div>
            )}
          </>
        )}
      </PopoverContent>
    </Popover>
  );
}

export default MentionsBadge;
