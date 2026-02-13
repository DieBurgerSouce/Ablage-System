/**
 * PresenceIndicator - Kompakte Anzeige aktiver Betrachter
 *
 * Features:
 * - Avatar-Stack (max 3 sichtbar)
 * - "+N viewing" Overflow-Badge
 * - Tooltip mit Namen
 * - Kompakte Variante für Header/Toolbar
 */

import { useMemo } from 'react';
import { Eye } from 'lucide-react';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';
import type { PresenceUser } from '../hooks/usePresence';

// ==================== Helpers ====================

function getInitials(name: string): string {
  const parts = name.split(/\s+/);
  if (parts.length >= 2) {
    return (parts[0][0] + parts[1][0]).toUpperCase();
  }
  return name.slice(0, 2).toUpperCase();
}

function getAvatarColor(userId: string): string {
  const colors = [
    'bg-blue-500',
    'bg-green-500',
    'bg-purple-500',
    'bg-orange-500',
    'bg-pink-500',
    'bg-teal-500',
    'bg-indigo-500',
    'bg-rose-500',
  ];
  const hash = userId.split('').reduce((acc, char) => acc + char.charCodeAt(0), 0);
  return colors[hash % colors.length];
}

// ==================== Sub-Components ====================

interface PresenceAvatarProps {
  user: PresenceUser;
  size?: 'sm' | 'md';
}

function PresenceAvatar({ user, size = 'sm' }: PresenceAvatarProps) {
  const sizeClass = size === 'sm' ? 'h-6 w-6' : 'h-7 w-7';
  const textClass = size === 'sm' ? 'text-[9px]' : 'text-[10px]';

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <Avatar className={cn(sizeClass, 'ring-2 ring-background cursor-default')}>
            {user.user_avatar ? (
              <AvatarImage src={user.user_avatar} alt={user.user_name} />
            ) : null}
            <AvatarFallback
              className={cn(textClass, 'text-white font-medium', getAvatarColor(user.user_id))}
            >
              {getInitials(user.user_name)}
            </AvatarFallback>
          </Avatar>
        </TooltipTrigger>
        <TooltipContent side="bottom">
          <p className="font-medium text-sm">{user.user_name}</p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

// ==================== Main Component ====================

interface PresenceIndicatorProps {
  /** Präsenz-User aus usePresence Hook */
  viewers: PresenceUser[];
  /** Eigene User-ID (wird ausgeblendet) */
  currentUserId?: string;
  /** Maximale Anzahl sichtbarer Avatare */
  maxVisible?: number;
  /** Größe der Avatare */
  size?: 'sm' | 'md';
  /** Zeige "viewing" Text */
  showText?: boolean;
  className?: string;
}

export function PresenceIndicator({
  viewers,
  currentUserId,
  maxVisible = 3,
  size = 'sm',
  showText = true,
  className,
}: PresenceIndicatorProps) {
  // Eigenen User ausfiltern
  const filteredViewers = useMemo(
    () => viewers.filter((v) => v.user_id !== currentUserId),
    [viewers, currentUserId]
  );

  const displayedViewers = filteredViewers.slice(0, maxVisible);
  const overflowCount = filteredViewers.length - displayedViewers.length;

  if (filteredViewers.length === 0) {
    return null;
  }

  return (
    <div className={cn('flex items-center gap-2', className)}>
      {/* Avatar Stack */}
      <div className="flex -space-x-2">
        {displayedViewers.map((viewer) => (
          <PresenceAvatar key={viewer.user_id} user={viewer} size={size} />
        ))}
        {overflowCount > 0 && (
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <div
                  className={cn(
                    'rounded-full bg-muted flex items-center justify-center font-medium ring-2 ring-background cursor-default',
                    size === 'sm' ? 'h-6 w-6 text-[9px]' : 'h-7 w-7 text-[10px]'
                  )}
                >
                  +{overflowCount}
                </div>
              </TooltipTrigger>
              <TooltipContent side="bottom">
                <div className="space-y-0.5 max-h-48 overflow-auto">
                  {filteredViewers.slice(maxVisible).map((viewer) => (
                    <p key={viewer.user_id} className="text-sm">
                      {viewer.user_name}
                    </p>
                  ))}
                </div>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        )}
      </div>

      {/* Text */}
      {showText && (
        <div className="flex items-center gap-1 text-xs text-muted-foreground">
          <Eye className="h-3 w-3" />
          <span>viewing</span>
        </div>
      )}
    </div>
  );
}

export default PresenceIndicator;
