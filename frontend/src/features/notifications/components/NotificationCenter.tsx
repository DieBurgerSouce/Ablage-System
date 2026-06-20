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
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger
} from '@/components/ui/dropdown-menu';
import { Check, Trash2, AlertCircle, Clock, ChevronDown, ChevronUp, History } from 'lucide-react';
import { UnifiedErrorBoundary } from '@/components/errors/UnifiedErrorBoundary';
import { NotificationItem } from './NotificationItem';
import {
  useNotifications,
  useMarkAllAsRead,
  useBulkDismiss,
  useGroupedNotifications,
  useSnoozeNotification
} from '../hooks/useNotifications';
import { NotificationPriority } from '../types';
import type { Notification } from '../types';

interface NotificationCenterProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/**
 * NotificationCenter mit lokaler ErrorBoundary (B5):
 * Ein Fehler in diesem Widget darf NIE wieder die gesamte App in den
 * Root-ErrorBoundary reissen - der Schaden bleibt auf das Widget begrenzt.
 */
export function NotificationCenter(props: NotificationCenterProps) {
  return (
    <UnifiedErrorBoundary
      variant="inline"
      context="general"
      errorTitle="Benachrichtigungen nicht verfügbar"
      errorDescription="Das Benachrichtigungs-Center konnte nicht geladen werden. Die übrige Anwendung funktioniert weiterhin."
    >
      <NotificationCenterInner {...props} />
    </UnifiedErrorBoundary>
  );
}

function NotificationCenterInner({
  open,
  onOpenChange
}: NotificationCenterProps) {
  const [activeTab, setActiveTab] = useState<string>('all');
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set());
  const [showHistory, setShowHistory] = useState(false);

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
  const snoozeMutation = useSnoozeNotification();

  // Defensiv (B5): Eine unerwartete Seiten-/Eintrags-Form darf hier nie
  // einen TypeError ausloesen - kaputte Eintraege werden verworfen.
  const allNotifications = (data?.pages ?? [])
    .flatMap((page) => (Array.isArray(page?.items) ? page.items : []))
    .filter((n): n is Notification => Boolean(n) && typeof n === 'object');

  // Gesnoozede Benachrichtigungen filtern
  const now = new Date();
  const notifications = allNotifications.filter((n) => {
    if (n.snoozed_until && new Date(n.snoozed_until) > now) {
      return false;
    }
    return true;
  });

  // Prioritaets-Tabs clientseitig filtern: GET /notifications/ unterstuetzt
  // keinen priority-Parameter (nur /notifications/system tut das).
  const priorityFiltered = filter?.priority
    ? notifications.filter((n) => n.priority === filter.priority)
    : notifications;

  // Verlaufsfilter: nur letzte 7 Tage
  const filteredNotifications = showHistory
    ? priorityFiltered
    : priorityFiltered.filter((n) => {
        const created = new Date(n.created_at);
        if (Number.isNaN(created.getTime())) {
          // Unbekanntes Datum nie still verstecken
          return true;
        }
        const sevenDaysAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
        return created >= sevenDaysAgo;
      });

  const groupedNotifications = useGroupedNotifications(filteredNotifications);
  const unreadCount =
    filteredNotifications.filter((n) => !n.read).length;

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

  const handleSnooze = (notificationId: string, duration: string) => {
    const snoozeUntil = new Date();
    switch (duration) {
      case '1h':
        snoozeUntil.setHours(snoozeUntil.getHours() + 1);
        break;
      case 'tomorrow':
        snoozeUntil.setDate(snoozeUntil.getDate() + 1);
        snoozeUntil.setHours(9, 0, 0, 0);
        break;
      case 'next_week':
        snoozeUntil.setDate(snoozeUntil.getDate() + 7);
        snoozeUntil.setHours(9, 0, 0, 0);
        break;
    }
    snoozeMutation.mutate({ id: notificationId, until: snoozeUntil.toISOString() });
  };

  const toggleGroup = (groupKey: string) => {
    setExpandedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(groupKey)) {
        next.delete(groupKey);
      } else {
        next.add(groupKey);
      }
      return next;
    });
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
          <div className="px-6 pt-4 space-y-3">
            <TabsList className="w-full grid grid-cols-4">
              <TabsTrigger value="all">Alle</TabsTrigger>
              <TabsTrigger value="critical">Kritisch</TabsTrigger>
              <TabsTrigger value="warning">Warnungen</TabsTrigger>
              <TabsTrigger value="info">Info</TabsTrigger>
            </TabsList>
            <div className="flex items-center justify-end">
              <Button
                variant={showHistory ? 'secondary' : 'ghost'}
                size="sm"
                onClick={() => setShowHistory(!showHistory)}
                className="h-7 text-xs"
              >
                <History className="h-3.5 w-3.5 mr-1.5" />
                {showHistory ? 'Letzte 7 Tage' : 'Alle anzeigen'}
              </Button>
            </div>
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
            ) : filteredNotifications.length === 0 ? (
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
                  {groupedNotifications.map((group) => (
                    <div key={group.group_key} className="space-y-1">
                      {/* Gruppenkopf mit Zaehler */}
                      {group.count > 1 && (
                        <button
                          type="button"
                          className="flex items-center gap-2 w-full text-left px-2 py-1 text-xs text-muted-foreground hover:text-foreground transition-colors rounded"
                          onClick={() => toggleGroup(group.group_key)}
                        >
                          {expandedGroups.has(group.group_key) ? (
                            <ChevronUp className="h-3 w-3" />
                          ) : (
                            <ChevronDown className="h-3 w-3" />
                          )}
                          <span className="font-medium">
                            {group.count} zusammengehoerige Benachrichtigungen
                          </span>
                        </button>
                      )}

                      {/* Erste (neueste) Benachrichtigung immer anzeigen */}
                      <div className="flex items-start gap-1">
                        <div className="flex-1 min-w-0">
                          <NotificationItem
                            key={group.latest.id}
                            notification={group.latest}
                            selected={selectedIds.has(group.latest.id)}
                            onSelect={(selected) => {
                              setSelectedIds((prev) => {
                                const next = new Set(prev);
                                if (selected) {
                                  next.add(group.latest.id);
                                } else {
                                  next.delete(group.latest.id);
                                }
                                return next;
                              });
                            }}
                            onClose={() => onOpenChange(false)}
                          />
                        </div>
                        {/* Snooze-Dropdown */}
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button
                              variant="ghost"
                              size="sm"
                              className="h-8 w-8 p-0 mt-3 flex-shrink-0"
                              title="Spaeter erinnern"
                            >
                              <Clock className="h-3.5 w-3.5" />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            <DropdownMenuItem
                              onClick={() => handleSnooze(group.latest.id, '1h')}
                            >
                              <Clock className="h-4 w-4 mr-2" />
                              1 Stunde
                            </DropdownMenuItem>
                            <DropdownMenuItem
                              onClick={() => handleSnooze(group.latest.id, 'tomorrow')}
                            >
                              <Clock className="h-4 w-4 mr-2" />
                              Morgen
                            </DropdownMenuItem>
                            <DropdownMenuItem
                              onClick={() => handleSnooze(group.latest.id, 'next_week')}
                            >
                              <Clock className="h-4 w-4 mr-2" />
                              Naechste Woche
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </div>

                      {/* Weitere Benachrichtigungen in der Gruppe (aufklappbar) */}
                      {group.count > 1 &&
                        expandedGroups.has(group.group_key) &&
                        group.notifications.slice(1).map((notification) => (
                          <div key={notification.id} className="flex items-start gap-1 ml-4">
                            <div className="flex-1 min-w-0">
                              <NotificationItem
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
                            </div>
                            <DropdownMenu>
                              <DropdownMenuTrigger asChild>
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  className="h-8 w-8 p-0 mt-3 flex-shrink-0"
                                  title="Spaeter erinnern"
                                >
                                  <Clock className="h-3.5 w-3.5" />
                                </Button>
                              </DropdownMenuTrigger>
                              <DropdownMenuContent align="end">
                                <DropdownMenuItem
                                  onClick={() => handleSnooze(notification.id, '1h')}
                                >
                                  <Clock className="h-4 w-4 mr-2" />
                                  1 Stunde
                                </DropdownMenuItem>
                                <DropdownMenuItem
                                  onClick={() => handleSnooze(notification.id, 'tomorrow')}
                                >
                                  <Clock className="h-4 w-4 mr-2" />
                                  Morgen
                                </DropdownMenuItem>
                                <DropdownMenuItem
                                  onClick={() => handleSnooze(notification.id, 'next_week')}
                                >
                                  <Clock className="h-4 w-4 mr-2" />
                                  Naechste Woche
                                </DropdownMenuItem>
                              </DropdownMenuContent>
                            </DropdownMenu>
                          </div>
                        ))}

                      {/* "X weitere" Hinweis wenn nicht aufgeklappt */}
                      {group.count > 1 && !expandedGroups.has(group.group_key) && (
                        <button
                          type="button"
                          className="text-xs text-muted-foreground hover:text-foreground ml-6 py-1 transition-colors"
                          onClick={() => toggleGroup(group.group_key)}
                        >
                          {group.count - 1} weitere
                        </button>
                      )}
                    </div>
                  ))}
                  {isFetchingNextPage && (
                    <div className="py-4 text-center text-sm text-muted-foreground">
                      Laedt weitere...
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
