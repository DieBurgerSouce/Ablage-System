/**
 * Notification Center - Bell Icon Component
 *
 * Bell Icon für Header mit Badge und Animation
 */

import { useState, useEffect } from 'react';
import { Bell } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import { useUnreadCount } from '../hooks/useNotifications';
import { NotificationCenter } from './NotificationCenter';

export function NotificationBell() {
  const [isOpen, setIsOpen] = useState(false);
  const [shouldAnimate, setShouldAnimate] = useState(false);
  const { data: unreadCount = 0, isLoading } = useUnreadCount();

  // Animation bei neuen Benachrichtigungen
  useEffect(() => {
    if (unreadCount > 0 && !isOpen) {
      setShouldAnimate(true);
      const timer = setTimeout(() => setShouldAnimate(false), 1000);
      return () => clearTimeout(timer);
    }
  }, [unreadCount, isOpen]);

  const handleClick = () => {
    setIsOpen(true);
    setShouldAnimate(false);
  };

  return (
    <>
      <Button
        variant="ghost"
        size="icon"
        className="relative"
        onClick={handleClick}
        aria-label={`Benachrichtigungen${unreadCount > 0 ? ` (${unreadCount} ungelesen)` : ''}`}
      >
        <Bell
          className={cn(
            'h-5 w-5',
            shouldAnimate &&
              'animate-[wiggle_0.5s_ease-in-out] text-primary'
          )}
        />
        {!isLoading && unreadCount > 0 && (
          <Badge
            variant="destructive"
            className={cn(
              'absolute -top-1 -right-1 h-5 min-w-[20px] flex items-center justify-center px-1 text-xs font-semibold',
              unreadCount > 99 && 'min-w-[24px]',
              shouldAnimate && 'animate-pulse'
            )}
          >
            {unreadCount > 99 ? '99+' : unreadCount}
          </Badge>
        )}
      </Button>

      <NotificationCenter open={isOpen} onOpenChange={setIsOpen} />
    </>
  );
}
