/**
 * Presence Indicator fuer Chat Real-time Collaboration.
 *
 * Zeigt an:
 * - Online-Benutzer mit Avataren
 * - Typing-Indikatoren
 * - Connection-Status
 */

import { useMemo } from 'react';
import {
    Tooltip,
    TooltipContent,
    TooltipProvider,
    TooltipTrigger,
} from '@/components/ui/tooltip';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import { Wifi, WifiOff, Loader2 } from 'lucide-react';
import type { WSPresenceUser } from '@/lib/api/chat-api';

// ============================================================================
// TYPES
// ============================================================================

interface PresenceIndicatorProps {
    /** Online-Benutzer */
    users: WSPresenceUser[];
    /** Verbindungsstatus */
    isConnected: boolean;
    /** Max angezeigte Avatare */
    maxAvatars?: number;
    /** Kompakte Ansicht */
    compact?: boolean;
    /** Eigene User-ID (zum Ausblenden) */
    currentUserId?: string;
}

// ============================================================================
// HELPERS
// ============================================================================

function getInitials(name: string): string {
    const parts = name.split(/\s+/);
    if (parts.length >= 2) {
        return (parts[0][0] + parts[1][0]).toUpperCase();
    }
    return name.slice(0, 2).toUpperCase();
}

function getAvatarColor(userId: string): string {
    // Konsistente Farbe basierend auf User-ID
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

// ============================================================================
// SUB-COMPONENTS
// ============================================================================

interface UserAvatarProps {
    user: WSPresenceUser;
    size?: 'sm' | 'md' | 'lg';
    showTyping?: boolean;
}

function UserAvatar({ user, size = 'md', showTyping = true }: UserAvatarProps) {
    const sizeClasses = {
        sm: 'h-6 w-6 text-[10px]',
        md: 'h-8 w-8 text-xs',
        lg: 'h-10 w-10 text-sm',
    };

    return (
        <TooltipProvider>
            <Tooltip>
                <TooltipTrigger asChild>
                    <div className="relative">
                        <div
                            className={cn(
                                'rounded-full flex items-center justify-center text-white font-medium',
                                sizeClasses[size],
                                getAvatarColor(user.user_id)
                            )}
                        >
                            {getInitials(user.username)}
                        </div>
                        {/* Online-Indikator */}
                        <span className="absolute bottom-0 right-0 block h-2 w-2 rounded-full bg-green-400 ring-2 ring-background" />
                        {/* Typing-Animation */}
                        {showTyping && user.is_typing && (
                            <span className="absolute -bottom-1 -right-1 flex h-4 w-4 items-center justify-center">
                                <TypingAnimation />
                            </span>
                        )}
                    </div>
                </TooltipTrigger>
                <TooltipContent>
                    <p className="font-medium">{user.username}</p>
                    {user.is_typing && (
                        <p className="text-xs text-muted-foreground">tippt gerade...</p>
                    )}
                </TooltipContent>
            </Tooltip>
        </TooltipProvider>
    );
}

function TypingAnimation() {
    return (
        <div className="flex items-center space-x-0.5">
            <span className="h-1 w-1 rounded-full bg-primary animate-bounce [animation-delay:-0.3s]" />
            <span className="h-1 w-1 rounded-full bg-primary animate-bounce [animation-delay:-0.15s]" />
            <span className="h-1 w-1 rounded-full bg-primary animate-bounce" />
        </div>
    );
}

interface ConnectionStatusProps {
    isConnected: boolean;
}

function ConnectionStatus({ isConnected }: ConnectionStatusProps) {
    return (
        <TooltipProvider>
            <Tooltip>
                <TooltipTrigger asChild>
                    <div
                        className={cn(
                            'flex items-center gap-1 px-2 py-1 rounded-md text-xs',
                            isConnected
                                ? 'bg-green-500/10 text-green-500'
                                : 'bg-red-500/10 text-red-500'
                        )}
                    >
                        {isConnected ? (
                            <Wifi className="h-3 w-3" />
                        ) : (
                            <WifiOff className="h-3 w-3" />
                        )}
                    </div>
                </TooltipTrigger>
                <TooltipContent>
                    {isConnected ? 'Verbunden' : 'Nicht verbunden'}
                </TooltipContent>
            </Tooltip>
        </TooltipProvider>
    );
}

// ============================================================================
// MAIN COMPONENT
// ============================================================================

export function PresenceIndicator({
    users,
    isConnected,
    maxAvatars = 4,
    compact = false,
    currentUserId,
}: PresenceIndicatorProps) {
    // Filtere eigenen User aus und sortiere (tippende User zuerst)
    const filteredUsers = useMemo(() => {
        return users
            .filter((u) => u.user_id !== currentUserId)
            .sort((a, b) => {
                if (a.is_typing && !b.is_typing) return -1;
                if (!a.is_typing && b.is_typing) return 1;
                return 0;
            });
    }, [users, currentUserId]);

    const displayedUsers = filteredUsers.slice(0, maxAvatars);
    const hiddenCount = filteredUsers.length - displayedUsers.length;

    // Typing Users (fuer separate Anzeige)
    const typingUsers = filteredUsers.filter((u) => u.is_typing);

    if (compact) {
        return (
            <div className="flex items-center gap-2">
                <ConnectionStatus isConnected={isConnected} />
                {filteredUsers.length > 0 && (
                    <Badge variant="secondary" className="text-xs">
                        {filteredUsers.length} online
                    </Badge>
                )}
            </div>
        );
    }

    return (
        <div className="flex items-center gap-3">
            {/* Connection Status */}
            <ConnectionStatus isConnected={isConnected} />

            {/* Online Users */}
            {filteredUsers.length > 0 && (
                <div className="flex items-center">
                    {/* Avatar Stack */}
                    <div className="flex -space-x-2">
                        {displayedUsers.map((user) => (
                            <UserAvatar key={user.user_id} user={user} size="sm" />
                        ))}
                        {hiddenCount > 0 && (
                            <TooltipProvider>
                                <Tooltip>
                                    <TooltipTrigger asChild>
                                        <div className="h-6 w-6 rounded-full bg-muted flex items-center justify-center text-[10px] font-medium ring-2 ring-background">
                                            +{hiddenCount}
                                        </div>
                                    </TooltipTrigger>
                                    <TooltipContent>
                                        <p>
                                            {hiddenCount} weitere{' '}
                                            {hiddenCount === 1 ? 'Benutzer' : 'Benutzer'}
                                        </p>
                                    </TooltipContent>
                                </Tooltip>
                            </TooltipProvider>
                        )}
                    </div>

                    {/* Online Count Badge */}
                    <Badge variant="outline" className="ml-2 text-xs">
                        {filteredUsers.length} online
                    </Badge>
                </div>
            )}

            {/* Typing Indicator (separate) */}
            {typingUsers.length > 0 && (
                <div className="flex items-center gap-1 text-xs text-muted-foreground">
                    <Loader2 className="h-3 w-3 animate-spin" />
                    <span>
                        {typingUsers.length === 1
                            ? `${typingUsers[0].username} tippt...`
                            : `${typingUsers.length} Benutzer tippen...`}
                    </span>
                </div>
            )}
        </div>
    );
}

// ============================================================================
// TYPING INDICATOR STANDALONE
// ============================================================================

interface TypingIndicatorProps {
    /** Tippende Benutzer */
    typingUsers: Array<{ user_id: string; username: string }>;
    /** Kompakte Variante (nur Animation) */
    compact?: boolean;
}

export function TypingIndicator({ typingUsers, compact = false }: TypingIndicatorProps) {
    if (typingUsers.length === 0) return null;

    if (compact) {
        return (
            <div className="flex items-center gap-1 p-2">
                <TypingAnimation />
            </div>
        );
    }

    const displayText =
        typingUsers.length === 1
            ? `${typingUsers[0].username} tippt...`
            : typingUsers.length === 2
              ? `${typingUsers[0].username} und ${typingUsers[1].username} tippen...`
              : `${typingUsers[0].username} und ${typingUsers.length - 1} weitere tippen...`;

    return (
        <div className="flex items-center gap-2 px-4 py-2 text-sm text-muted-foreground">
            <div className="flex items-center space-x-1">
                <span className="h-2 w-2 rounded-full bg-muted-foreground/50 animate-bounce [animation-delay:-0.3s]" />
                <span className="h-2 w-2 rounded-full bg-muted-foreground/50 animate-bounce [animation-delay:-0.15s]" />
                <span className="h-2 w-2 rounded-full bg-muted-foreground/50 animate-bounce" />
            </div>
            <span>{displayText}</span>
        </div>
    );
}

export default PresenceIndicator;
