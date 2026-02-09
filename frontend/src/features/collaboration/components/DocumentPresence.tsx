/**
 * DocumentPresence - Zeigt aktive Betrachter eines Dokuments
 *
 * Features:
 * - Avatar-Stack der aktiven User (max 5, "+N" fuer Overflow)
 * - Username-Tooltip bei Hover
 * - "N Personen sehen dieses Dokument" Text
 * - WebSocket-basierte Echtzeit-Updates
 */

import { useMemo } from 'react';
import { Users } from 'lucide-react';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';
import type { PresenceUser } from '../hooks/use-realtime';

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
}

function PresenceAvatar({ user }: PresenceAvatarProps) {
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <Avatar className="h-7 w-7 ring-2 ring-background">
            {user.userAvatar ? (
              <AvatarImage src={user.userAvatar} alt={user.userName} />
            ) : null}
            <AvatarFallback
              className={cn('text-[10px] text-white font-medium', getAvatarColor(user.userId))}
            >
              {getInitials(user.userName)}
            </AvatarFallback>
          </Avatar>
        </TooltipTrigger>
        <TooltipContent>
          <p className="font-medium text-sm">{user.userName}</p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

// ==================== Main Component ====================

interface DocumentPresenceProps {
  /** Praesenz-User aus dem useRealtime Hook */
  users: PresenceUser[];
  /** Eigene User-ID (wird ausgeblendet) */
  currentUserId?: string;
  /** Maximale Anzahl sichtbarer Avatare */
  maxVisible?: number;
  /** Kompakte Variante (nur Avatare, kein Text) */
  compact?: boolean;
  className?: string;
}

export function DocumentPresence({
  users,
  currentUserId,
  maxVisible = 5,
  compact = false,
  className,
}: DocumentPresenceProps) {
  // Eigenen User ausfiltern
  const filteredUsers = useMemo(
    () => users.filter((u) => u.userId !== currentUserId),
    [users, currentUserId],
  );

  const displayedUsers = filteredUsers.slice(0, maxVisible);
  const overflowCount = filteredUsers.length - displayedUsers.length;

  if (filteredUsers.length === 0) {
    return null;
  }

  const presenceText =
    filteredUsers.length === 1
      ? '1 Person sieht dieses Dokument'
      : `${filteredUsers.length} Personen sehen dieses Dokument`;

  return (
    <div className={cn('flex items-center gap-2', className)}>
      {/* Avatar Stack */}
      <div className="flex -space-x-2">
        {displayedUsers.map((user) => (
          <PresenceAvatar key={user.userId} user={user} />
        ))}
        {overflowCount > 0 && (
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <div className="h-7 w-7 rounded-full bg-muted flex items-center justify-center text-[10px] font-medium ring-2 ring-background cursor-default">
                  +{overflowCount}
                </div>
              </TooltipTrigger>
              <TooltipContent>
                <div className="space-y-0.5">
                  {filteredUsers.slice(maxVisible).map((user) => (
                    <p key={user.userId} className="text-sm">
                      {user.userName}
                    </p>
                  ))}
                </div>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        )}
      </div>

      {/* User Icon + Text */}
      {!compact && (
        <div className="flex items-center gap-1 text-xs text-muted-foreground">
          <Users className="h-3.5 w-3.5" />
          <span>{presenceText}</span>
        </div>
      )}
    </div>
  );
}

export default DocumentPresence;
