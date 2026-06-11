/**
 * Notification Center - Item Component
 *
 * Einzelne Benachrichtigung mit Swipe-to-dismiss
 */

import React, { useState, useRef } from 'react';
import { useNavigate } from '@tanstack/react-router';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { AlertCircle, AlertTriangle, Info, FileText, Receipt, Workflow, Trash2 } from 'lucide-react';
import {
  useMarkAsRead,
  useDeleteNotification
} from '../hooks/useNotifications';
import type { Notification } from '../types';
import { NotificationPriority, NotificationType } from '../types';

interface NotificationItemProps {
  notification: Notification;
  selected?: boolean;
  onSelect?: (selected: boolean) => void;
  onClose?: () => void;
}

export function NotificationItem({
  notification,
  selected = false,
  onSelect,
  onClose
}: NotificationItemProps) {
  const navigate = useNavigate();
  const markAsReadMutation = useMarkAsRead();
  const deleteNotificationMutation = useDeleteNotification();

  // Swipe-to-dismiss State
  const [swipeOffset, setSwipeOffset] = useState(0);
  const [isDragging, setIsDragging] = useState(false);
  const startX = useRef(0);
  const currentX = useRef(0);

  const handleClick = () => {
    if (!notification.read) {
      markAsReadMutation.mutate(notification.id);
    }

    if (notification.link) {
      navigate({ to: notification.link });
      onClose?.();
    }
  };

  const handleDelete = (e: React.MouseEvent) => {
    e.stopPropagation();
    deleteNotificationMutation.mutate(notification.id);
  };

  const handleCheckboxChange = (checked: boolean) => {
    onSelect?.(checked);
  };

  // Swipe-to-dismiss Handlers
  const handleTouchStart = (e: React.TouchEvent) => {
    startX.current = e.touches[0].clientX;
    setIsDragging(true);
  };

  const handleTouchMove = (e: React.TouchEvent) => {
    if (!isDragging) return;
    currentX.current = e.touches[0].clientX;
    const diff = currentX.current - startX.current;
    setSwipeOffset(diff);
  };

  const handleTouchEnd = () => {
    setIsDragging(false);

    if (Math.abs(swipeOffset) > 100) {
      // Schwellenwert für Dismiss
      deleteNotificationMutation.mutate(notification.id);
    }
    setSwipeOffset(0);
  };

  // Icon basierend auf Priorität und Typ
  const getIcon = () => {
    // Priorität hat Vorrang
    if (notification.priority === NotificationPriority.CRITICAL) {
      return <AlertCircle className="h-5 w-5 text-destructive" />;
    }
    if (notification.priority === NotificationPriority.WARNING) {
      return <AlertTriangle className="h-5 w-5 text-warning" />;
    }

    // Sonst nach Typ
    switch (notification.type) {
      case NotificationType.DOCUMENT:
        return <FileText className="h-5 w-5 text-blue-500" />;
      case NotificationType.INVOICE:
        return <Receipt className="h-5 w-5 text-green-500" />;
      case NotificationType.WORKFLOW:
        return <Workflow className="h-5 w-5 text-purple-500" />;
      case NotificationType.ALERT:
        return <AlertTriangle className="h-5 w-5 text-orange-500" />;
      default:
        return <Info className="h-5 w-5 text-muted-foreground" />;
    }
  };

  // Relative Zeit formatieren
  const getRelativeTime = (dateString: string) => {
    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return 'Gerade eben';
    if (diffMins < 60) return `vor ${diffMins} Min`;
    if (diffHours < 24) return `vor ${diffHours} Std`;
    if (diffDays < 7) return `vor ${diffDays} ${diffDays === 1 ? 'Tag' : 'Tagen'}`;
    return date.toLocaleDateString('de-DE', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric'
    });
  };

  return (
    <div
      className={cn(
        'relative overflow-hidden rounded-lg border transition-all',
        !notification.read && 'bg-accent/50',
        notification.link && 'cursor-pointer hover:bg-accent/70',
        selected && 'ring-2 ring-primary'
      )}
      style={{
        transform: `translateX(${swipeOffset}px)`,
        transition: isDragging ? 'none' : 'transform 0.3s ease-out'
      }}
      onTouchStart={handleTouchStart}
      onTouchMove={handleTouchMove}
      onTouchEnd={handleTouchEnd}
    >
      {/* Swipe Background */}
      {swipeOffset !== 0 && (
        <div
          className={cn(
            'absolute inset-0 flex items-center px-4',
            swipeOffset < 0 ? 'justify-end bg-destructive/20' : 'justify-start'
          )}
        >
          <Trash2
            className={cn(
              'h-5 w-5',
              Math.abs(swipeOffset) > 100
                ? 'text-destructive'
                : 'text-muted-foreground'
            )}
          />
        </div>
      )}

      <div
        className="flex items-start gap-3 p-4"
        onClick={notification.link ? handleClick : undefined}
      >
        {/* Checkbox für Auswahl */}
        {onSelect && (
          <Checkbox
            checked={selected}
            onCheckedChange={handleCheckboxChange}
            onClick={(e) => e.stopPropagation()}
          />
        )}

        {/* Icon */}
        <div className="mt-0.5">{getIcon()}</div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-2">
            <h4
              className={cn(
                'text-sm font-medium line-clamp-1',
                !notification.read && 'font-semibold'
              )}
            >
              {notification.title}
            </h4>
            {!notification.read && (
              <div className="h-2 w-2 rounded-full bg-primary flex-shrink-0 mt-1.5" />
            )}
          </div>

          <p className="text-sm text-muted-foreground line-clamp-2 mt-1">
            {notification.message}
          </p>

          <div className="flex items-center justify-between mt-2">
            <span className="text-xs text-muted-foreground">
              {getRelativeTime(notification.created_at)}
            </span>

            {/* Delete Button */}
            <Button
              variant="ghost"
              size="sm"
              className="h-7 px-2 -mr-2"
              onClick={handleDelete}
              disabled={deleteNotificationMutation.isPending}
            >
              <Trash2 className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
