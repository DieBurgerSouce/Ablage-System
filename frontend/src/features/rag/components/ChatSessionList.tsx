/**
 * Chat Session List Component
 *
 * Sidebar for managing multiple chat sessions.
 */

import { useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
    Plus,
    MessageSquare,
    Trash2,
    Clock,
    Loader2,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
    AlertDialog,
    AlertDialogAction,
    AlertDialogCancel,
    AlertDialogContent,
    AlertDialogDescription,
    AlertDialogFooter,
    AlertDialogHeader,
    AlertDialogTitle,
    AlertDialogTrigger,
} from '@/components/ui/alert-dialog';
import { cn } from '@/lib/utils';
import {
    useChatSessions,
    useCreateSession,
    useDeleteSession,
} from '../hooks/use-chat';
import type { ChatSession } from '../types/chat-types';
import { formatTimestamp } from '../types/chat-types';

interface ChatSessionListProps {
    activeSessionId: string | null;
    onSessionSelect: (sessionId: string) => void;
    className?: string;
}

export function ChatSessionList({
    activeSessionId,
    onSessionSelect,
    className,
}: ChatSessionListProps) {
    const { data: sessionsData, isLoading, refetch } = useChatSessions();
    const createSession = useCreateSession();
    const deleteSession = useDeleteSession();

    const handleNewSession = useCallback(async () => {
        try {
            const session = await createSession.mutateAsync();
            onSessionSelect(session.id);
        } catch (error) {
            console.error('Failed to create session:', error);
        }
    }, [createSession, onSessionSelect]);

    const handleDeleteSession = useCallback(
        async (sessionId: string) => {
            try {
                await deleteSession.mutateAsync(sessionId);
                if (activeSessionId === sessionId) {
                    // Select another session or create new
                    const remaining = sessionsData?.sessions.filter(
                        (s) => s.id !== sessionId
                    );
                    if (remaining && remaining.length > 0) {
                        onSessionSelect(remaining[0].id);
                    } else {
                        handleNewSession();
                    }
                }
            } catch (error) {
                console.error('Failed to delete session:', error);
            }
        },
        [
            deleteSession,
            activeSessionId,
            sessionsData,
            onSessionSelect,
            handleNewSession,
        ]
    );

    return (
        <div className={cn('flex flex-col h-full', className)}>
            {/* Header */}
            <div className="flex items-center justify-between p-4 border-b">
                <h3 className="font-semibold">Chat-Sessions</h3>
                <Button
                    variant="outline"
                    size="sm"
                    onClick={handleNewSession}
                    disabled={createSession.isPending}
                    className="gap-1"
                >
                    {createSession.isPending ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                        <Plus className="h-4 w-4" />
                    )}
                    Neu
                </Button>
            </div>

            {/* Session List */}
            <ScrollArea className="flex-1">
                <div className="p-2 space-y-1">
                    {isLoading && (
                        <div className="flex items-center justify-center py-8">
                            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                        </div>
                    )}

                    {!isLoading && (!sessionsData || sessionsData.sessions.length === 0) && (
                        <div className="text-center py-8 text-muted-foreground">
                            <MessageSquare className="h-8 w-8 mx-auto mb-2 opacity-50" />
                            <p className="text-sm">Keine Sessions</p>
                            <Button
                                variant="link"
                                size="sm"
                                onClick={handleNewSession}
                                className="mt-2"
                            >
                                Neue Session starten
                            </Button>
                        </div>
                    )}

                    <AnimatePresence initial={false}>
                        {sessionsData?.sessions.map((session) => (
                            <SessionItem
                                key={session.id}
                                session={session}
                                isActive={session.id === activeSessionId}
                                onSelect={() => onSessionSelect(session.id)}
                                onDelete={() => handleDeleteSession(session.id)}
                                isDeleting={
                                    deleteSession.isPending &&
                                    deleteSession.variables === session.id
                                }
                            />
                        ))}
                    </AnimatePresence>
                </div>
            </ScrollArea>

            {/* Footer */}
            <div className="p-2 border-t text-xs text-muted-foreground text-center">
                {sessionsData?.total ?? 0} Session(s)
            </div>
        </div>
    );
}

// ==================== Session Item ====================

interface SessionItemProps {
    session: ChatSession;
    isActive: boolean;
    onSelect: () => void;
    onDelete: () => void;
    isDeleting: boolean;
}

function SessionItem({
    session,
    isActive,
    onSelect,
    onDelete,
    isDeleting,
}: SessionItemProps) {
    return (
        <motion.div
            initial={{ opacity: 0, x: -10 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -10 }}
            className={cn(
                'group flex items-center gap-2 p-2 rounded-md cursor-pointer transition-colors',
                isActive
                    ? 'bg-primary/10 border border-primary/20'
                    : 'hover:bg-muted'
            )}
            onClick={onSelect}
        >
            <MessageSquare
                className={cn(
                    'h-4 w-4 flex-shrink-0',
                    isActive ? 'text-primary' : 'text-muted-foreground'
                )}
            />

            <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                    <span
                        className={cn(
                            'text-sm font-medium truncate',
                            isActive && 'text-primary'
                        )}
                    >
                        Session
                    </span>
                    <span className="text-xs text-muted-foreground">
                        ({session.message_count} Nachrichten)
                    </span>
                </div>
                <div className="flex items-center gap-1 text-xs text-muted-foreground">
                    <Clock className="h-3 w-3" />
                    {formatTimestamp(session.updated_at)}
                </div>
            </div>

            <AlertDialog>
                <AlertDialogTrigger asChild>
                    <Button
                        variant="ghost"
                        size="icon"
                        className={cn(
                            'h-7 w-7 opacity-0 group-hover:opacity-100 transition-opacity',
                            'hover:bg-destructive/10 hover:text-destructive'
                        )}
                        onClick={(e) => e.stopPropagation()}
                        disabled={isDeleting}
                    >
                        {isDeleting ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                            <Trash2 className="h-4 w-4" />
                        )}
                    </Button>
                </AlertDialogTrigger>
                <AlertDialogContent onClick={(e) => e.stopPropagation()}>
                    <AlertDialogHeader>
                        <AlertDialogTitle>Session löschen?</AlertDialogTitle>
                        <AlertDialogDescription>
                            Diese Aktion kann nicht rückgängig gemacht werden.
                            Der gesamte Chat-Verlauf dieser Session wird gelöscht.
                        </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                        <AlertDialogCancel>Abbrechen</AlertDialogCancel>
                        <AlertDialogAction
                            onClick={onDelete}
                            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                        >
                            Löschen
                        </AlertDialogAction>
                    </AlertDialogFooter>
                </AlertDialogContent>
            </AlertDialog>
        </motion.div>
    );
}

export default ChatSessionList;
