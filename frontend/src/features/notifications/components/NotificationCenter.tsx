/**
 * Notification Center - Hauptkomponente
 *
 * Sheet/Sidebar für Benachrichtigungen
 */

import React, { useState } from 'react';
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle
} from '@/components/ui/sheet';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { Check, Trash2, AlertCircle } from 'lucide-react';
import { NotificationItem } from './NotificationItem';
import {
  useNotifications,
  useMarkAllAsRead,
  useBulkDismiss
} from '../hooks/useNotifications';
import { NotificationPriority } from '../types';
import { cn } from '@/lib/utils';

interface NotificationCenterProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function NotificationCenter({
  open,
  onOpenChange
}: NotificationCenterProps) {
  const [activeTab, setActiveTab] = useState<string>('all');
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  // Query basierend auf aktivem Tab
  const filter =
    activeTab === 'all'
      ? undefined
      : activeTab === 'critical'
        ? { priority: NotificationPriority.CRITICAL }
        : activeTab === 'warning'
          ? { priority: NotificationPriority.WARNING }
          : { priority: NotificationPriority.INFO };

  const {
    data,
    isLoading,
    isError,
    error,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage
  } = useNotifications(filter);

  const markAllAsReadMutation = useMarkAllAsRead();
  const bulkDismissMutation = useBulkDismiss();

  const notifications = data?.pages.flatMap((page) => page.items) ?? [];
  const unreadCount =
    notifications.filter((n) => !n.read).length;

  const handleMarkAllAsRead = () => {
    markAllAsReadMutation.mutate();
  };

  const handleBulkDismiss = () => {
    if (selectedIds.size === 0) return;
    bulkDismissMutation.mutate(
      { notification_ids: Array.from(selectedIds) },
      {
        onSuccess: () => {
          setSelectedIds(new Set());
        }
      }
    );
  };

  const handleScroll = (event: React.UIEvent<HTMLDivElement>) => {
    const { scrollTop, scrollHeight, clientHeight } = event.currentTarget;
    if (
      scrollHeight - scrollTop <= clientHeight * 1.5 &&
      hasNextPage &&
      !isFetchingNextPage
    ) {
      fetchNextPage();
    }
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-full sm:max-w-md p-0 flex flex-col">
        <SheetHeader className="px-6 py-4 border-b">
          <div className="flex items-center justify-between">
            <SheetTitle>Benachrichtigungen</SheetTitle>
            <div className="flex items-center gap-2">
              {selectedIds.size > 0 && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleBulkDismiss}
                  disabled={bulkDismissMutation.isPending}
                >
                  <Trash2 className="h-4 w-4 mr-2" />
                  {selectedIds.size} löschen
                </Button>
              )}
              {unreadCount > 0 && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleMarkAllAsRead}
                  disabled={markAllAsReadMutation.isPending}
                >
                  <Check className="h-4 w-4 mr-2" />
                  Alle gelesen
                </Button>
              )}
            </div>
          </div>
        </SheetHeader>

        <Tabs
          value={activeTab}
          onValueChange={setActiveTab}
          className="flex-1 flex flex-col min-h-0"
        >
          <div className="px-6 pt-4">
            <TabsList className="w-full grid grid-cols-4">
              <TabsTrigger value="all">Alle</TabsTrigger>
              <TabsTrigger value="critical">Kritisch</TabsTrigger>
              <TabsTrigger value="warning">Warnungen</TabsTrigger>
              <TabsTrigger value="info">Info</TabsTrigger>
            </TabsList>
          </div>

          <TabsContent
            value={activeTab}
            className="flex-1 min-h-0 mt-4 data-[state=active]:flex data-[state=active]:flex-col"
          >
            {isLoading ? (
              <div className="flex items-center justify-center h-full text-muted-foreground">
                Lädt...
              </div>
            ) : isError ? (
              <div className="flex flex-col items-center justify-center h-full text-destructive gap-2 px-6">
                <AlertCircle className="h-8 w-8" />
                <p className="text-sm text-center">
                  Fehler beim Laden der Benachrichtigungen
                </p>
                {error instanceof Error && (
                  <p className="text-xs text-center text-muted-foreground">
                    {error.message}
                  </p>
                )}
              </div>
            ) : notifications.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full text-muted-foreground gap-2 px-6">
                <Check className="h-12 w-12 mb-2" />
                <p className="text-sm font-medium">Keine Benachrichtigungen</p>
                <p className="text-xs text-center">
                  {activeTab === 'all'
                    ? 'Sie haben keine neuen Benachrichtigungen'
                    : `Keine ${
                        activeTab === 'critical'
                          ? 'kritischen'
                          : activeTab === 'warning'
                            ? 'Warn-'
                            : 'Info-'
                      }Benachrichtigungen`}
                </p>
              </div>
            ) : (
              <ScrollArea
                className="flex-1 px-6"
                onScrollCapture={handleScroll}
              >
                <div className="space-y-2 pb-4">
                  {notifications.map((notification) => (
                    <NotificationItem
                      key={notification.id}
                      notification={notification}
                      selected={selectedIds.has(notification.id)}
                      onSelect={(selected) => {
                        setSelectedIds((prev) => {
                          const next = new Set(prev);
                          if (selected) {
                            next.add(notification.id);
                          } else {
                            next.delete(notification.id);
                          }
                          return next;
                        });
                      }}
                      onClose={() => onOpenChange(false)}
                    />
                  ))}
                  {isFetchingNextPage && (
                    <div className="py-4 text-center text-sm text-muted-foreground">
                      Lädt weitere...
                    </div>
                  )}
                </div>
              </ScrollArea>
            )}
          </TabsContent>
        </Tabs>
      </SheetContent>
    </Sheet>
  );
}
