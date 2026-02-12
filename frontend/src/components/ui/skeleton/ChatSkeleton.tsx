/**
 * ChatSkeleton - Loading-State für den Chat-Bereich
 *
 * Nutzt SkeletonList mit variant="avatar" für Nachrichten
 * und einen Skeleton-Input-Bereich am unteren Rand.
 */

import * as React from 'react';
import { Skeleton } from '@/components/ui/skeleton';
import { SkeletonList } from './SkeletonList';
import { cn } from '@/lib/utils';

export interface ChatSkeletonProps {
  /** Anzahl der Nachrichten-Platzhalter */
  messages?: number;
  /** Input-Bereich anzeigen */
  showInput?: boolean;
  /** Zusätzliche CSS-Klassen */
  className?: string;
}

export const ChatSkeleton = React.memo(function ChatSkeleton({
  messages = 4,
  showInput = true,
  className,
}: ChatSkeletonProps) {
  return (
    <div className={cn('flex flex-col h-full', className)}>
      {/* Nachrichten-Bereich */}
      <div className="flex-1 p-4">
        <SkeletonList
          items={messages}
          variant="avatar"
          showDividers
        />
      </div>

      {/* Eingabe-Bereich */}
      {showInput && (
        <div className="border-t p-4 space-y-2">
          <div className="flex items-center gap-2">
            <Skeleton className="h-10 flex-1 rounded-md" />
            <Skeleton className="h-10 w-10 rounded-md shrink-0" />
          </div>
        </div>
      )}
    </div>
  );
});

ChatSkeleton.displayName = 'ChatSkeleton';

export default ChatSkeleton;
