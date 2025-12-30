/**
 * NotificationBell - Benachrichtigungs-Glocke in der Header-Leiste
 *
 * Zeigt ungelesene Benachrichtigungen an und ermoeglicht:
 * - Dropdown mit Benachrichtigungsliste
 * - Als gelesen markieren
 * - Alle als gelesen markieren
 * - Navigation zu Dokumenten
 */

import { useState, useCallback } from 'react';
import { Bell, Check, CheckCheck, MessageSquare, AtSign, Share2, CheckCircle, XCircle, ClipboardList, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import {
  useNotifications,
  useMarkAsRead,
  useMarkAllAsRead,
} from '@/features/collaboration/hooks/use-notifications';
import type { NotificationType } from '@/features/collaboration/types/collaboration.types';
import { formatDistanceToNow } from 'date-fns';
import { de } from 'date-fns/locale';
import { cn } from '@/lib/utils';
import { useNavigate } from '@tanstack/react-router';

function getInitials(name: string): string {
  return name
    .split(' ')
    .map((n) => n[0])
    .join('')
    .toUpperCase()
    .slice(0, 2);
}

const NOTIFICATION_ICONS: Record<NotificationType, React.ElementType> = {
  mention: AtSign,
  comment_reply: MessageSquare,
  document_shared: Share2,
  task_assigned: ClipboardList,
  document_approved: CheckCircle,
  document_rejected: XCircle,
};

const NOTIFICATION_COLORS: Record<NotificationType, string> = {
  mention: 'text-blue-500',
  comment_reply: 'text-amber-500',
  document_shared: 'text-purple-500',
  task_assigned: 'text-orange-500',
  document_approved: 'text-green-500',
  document_rejected: 'text-red-500',
};

export function NotificationBell() {
  const navigate = useNavigate();
  const { data, isLoading } = useNotifications();
  const markAsReadMutation = useMarkAsRead();
  const markAllAsReadMutation = useMarkAllAsRead();
  const [open, setOpen] = useState(false);

  const unreadCount = data?.unreadCount || 0;
  const notifications = data?.notifications || [];

  const handleMarkAllRead = useCallback(() => {
    markAllAsReadMutation.mutate();
  }, [markAllAsReadMutation]);

  const handleNotificationClick = useCallback(
    (notificationId: string, actionUrl?: string, isRead?: boolean) => {
      if (!isRead) {
        markAsReadMutation.mutate(notificationId);
      }
      if (actionUrl) {
        setOpen(false);
        navigate({ to: actionUrl });
      }
    },
    [markAsReadMutation, navigate]
  );

  return (
    <DropdownMenu open={open} onOpenChange={setOpen}>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" className="relative">
          <Bell className="h-5 w-5" />
          {unreadCount > 0 && (
            <Badge
              variant="destructive"
              className="absolute -top-1 -right-1 h-5 min-w-[20px] px-1 flex items-center justify-center text-[10px]"
            >
              {unreadCount > 9 ? '9+' : unreadCount}
            </Badge>
          )}
          <span className="sr-only">
            {unreadCount} ungelesene Benachrichtigungen
          </span>
        </Button>
      </DropdownMenuTrigger>

      <DropdownMenuContent align="end" className="w-80">
        <DropdownMenuLabel className="flex items-center justify-between">
          <span>Benachrichtigungen</span>
          {unreadCount > 0 && (
            <Button
              variant="ghost"
              size="sm"
              className="h-auto py-1 px-2 text-xs"
              onClick={handleMarkAllRead}
              disabled={markAllAsReadMutation.isPending}
            >
              {markAllAsReadMutation.isPending ? (
                <Loader2 className="h-3 w-3 animate-spin mr-1" />
              ) : (
                <CheckCheck className="h-3 w-3 mr-1" />
              )}
              Alle gelesen
            </Button>
          )}
        </DropdownMenuLabel>
        <DropdownMenuSeparator />

        {isLoading ? (
          <div className="py-8 flex items-center justify-center text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin" />
          </div>
        ) : notifications.length === 0 ? (
          <div className="py-8 text-center text-muted-foreground">
            <Bell className="h-10 w-10 mx-auto mb-2 opacity-50" />
            <p className="text-sm">Keine Benachrichtigungen</p>
          </div>
        ) : (
          <ScrollArea className="h-[320px]">
            <DropdownMenuGroup>
              {notifications.map((notification) => {
                const Icon = NOTIFICATION_ICONS[notification.type] || Bell;
                const iconColor = NOTIFICATION_COLORS[notification.type] || 'text-muted-foreground';
                const timeAgo = formatDistanceToNow(new Date(notification.createdAt), {
                  addSuffix: true,
                  locale: de,
                });

                return (
                  <DropdownMenuItem
                    key={notification.id}
                    className={cn(
                      'flex items-start gap-3 p-3 cursor-pointer',
                      !notification.isRead && 'bg-accent/50'
                    )}
                    onClick={() =>
                      handleNotificationClick(
                        notification.id,
                        notification.actionUrl,
                        notification.isRead
                      )
                    }
                  >
                    {/* Avatar */}
                    <Avatar className="h-8 w-8 shrink-0">
                      <AvatarImage
                        src={notification.fromUserAvatar}
                        alt={notification.fromUserName}
                      />
                      <AvatarFallback className="text-xs">
                        {getInitials(notification.fromUserName)}
                      </AvatarFallback>
                    </Avatar>

                    {/* Content */}
                    <div className="flex-1 min-w-0 space-y-1">
                      <div className="flex items-center gap-2">
                        <Icon className={cn('h-3.5 w-3.5', iconColor)} />
                        <span className="font-medium text-xs">{notification.title}</span>
                        {!notification.isRead && (
                          <span className="h-2 w-2 rounded-full bg-primary shrink-0" />
                        )}
                      </div>
                      <p className="text-xs text-muted-foreground line-clamp-2">
                        {notification.message}
                      </p>
                      {notification.documentName && (
                        <p className="text-xs text-primary truncate">
                          {notification.documentName}
                        </p>
                      )}
                      <p className="text-[10px] text-muted-foreground">{timeAgo}</p>
                    </div>
                  </DropdownMenuItem>
                );
              })}
            </DropdownMenuGroup>
          </ScrollArea>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export default NotificationBell;
