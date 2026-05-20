/**
 * ChatPanel - KI-Chat Seitenleiste (Slide-out Panel)
 *
 * Hauptkomponente des KI-Assistenten. Oeffnet sich als Sheet von rechts
 * und bietet:
 * - Session-Auswahl und -Erstellung
 * - Nachrichten-Anzeige mit Auto-Scroll
 * - Streaming-Antworten vom RAG-Backend
 * - Optionaler Dokument-/Entity-Kontext
 */

import { useState, useRef, useEffect, useCallback } from 'react';
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Bot, Plus, MessageSquare, Loader2, AlertCircle } from 'lucide-react';
import { ChatMessage } from './ChatMessage';
import { ChatInput } from './ChatInput';
import {
  useChatSessions,
  useCreateChatSession,
  useChatMessages,
  useSendMessage,
} from '../hooks/use-chat';

interface ChatPanelProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Dokument-ID fuer kontextbezogene Fragen */
  contextDocumentId?: string;
  /** Anzeige-Label fuer den aktiven Kontext */
  contextLabel?: string;
}

export function ChatPanel({
  open,
  onOpenChange,
  contextDocumentId,
  contextLabel,
}: ChatPanelProps) {
  const [activeSessionId, setActiveSessionId] = useState<string>('');

  const scrollRef = useRef<HTMLDivElement>(null);

  const { data: sessions, isLoading: sessionsLoading } = useChatSessions();
  const createSession = useCreateChatSession();
  const { data: messages, isLoading: messagesLoading } =
    useChatMessages(activeSessionId);
  const { sendStreaming, streamingContent, isStreaming, streamError } =
    useSendMessage(activeSessionId);

  // Erste Session automatisch auswaehlen
  useEffect(() => {
    if (sessions && sessions.length > 0 && !activeSessionId) {
      setActiveSessionId(sessions[0].id);
    }
  }, [sessions, activeSessionId]);

  // Auto-Scroll zum Ende bei neuen Nachrichten / Streaming
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, streamingContent]);

  const handleNewSession = useCallback(async () => {
    const session = await createSession.mutateAsync({
      title: 'Neue Unterhaltung',
      ...(contextDocumentId
        ? { context_type: 'document' as const, context_id: contextDocumentId }
        : {}),
    });
    setActiveSessionId(session.id);
  }, [createSession, contextDocumentId]);

  const handleSend = useCallback(
    (message: string) => {
      if (!activeSessionId) return;
      sendStreaming(
        message,
        contextDocumentId
          ? { context_type: 'document', context_id: contextDocumentId }
          : undefined
      );
    },
    [activeSessionId, sendStreaming, contextDocumentId]
  );

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-full sm:max-w-lg p-0 flex flex-col">
        <SheetHeader className="px-4 py-3 border-b">
          <div className="flex items-center justify-between">
            <SheetTitle className="flex items-center gap-2 text-base">
              <Bot className="h-5 w-5" />
              KI-Assistent
            </SheetTitle>
            <Button
              variant="ghost"
              size="sm"
              onClick={handleNewSession}
              disabled={createSession.isPending}
            >
              {createSession.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin mr-1" />
              ) : (
                <Plus className="h-4 w-4 mr-1" />
              )}
              Neu
            </Button>
          </div>

          {/* Session-Auswahl */}
          {sessions && sessions.length > 0 && (
            <Select
              value={activeSessionId || 'none'}
              onValueChange={(val) => {
                if (val !== 'none') setActiveSessionId(val);
              }}
            >
              <SelectTrigger className="h-8 text-xs">
                <SelectValue placeholder="Unterhaltung waehlen..." />
              </SelectTrigger>
              <SelectContent>
                {sessions.map((session) => (
                  <SelectItem key={session.id} value={session.id}>
                    <div className="flex items-center gap-2">
                      <MessageSquare className="h-3 w-3" />
                      <span className="truncate">
                        {session.title || 'Unterhaltung'}
                      </span>
                      <span className="text-muted-foreground">
                        ({session.message_count})
                      </span>
                    </div>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </SheetHeader>

        {/* Nachrichten-Bereich */}
        <div className="flex-1 min-h-0 overflow-hidden">
          {sessionsLoading ? (
            <div className="flex items-center justify-center h-full text-muted-foreground">
              <Loader2 className="h-5 w-5 animate-spin mr-2" />
              Lade Sessions...
            </div>
          ) : !activeSessionId ? (
            <div className="flex flex-col items-center justify-center h-full text-muted-foreground gap-3 px-6">
              <Bot className="h-12 w-12 opacity-50" />
              <p className="text-sm font-medium">
                Willkommen beim KI-Assistenten
              </p>
              <p className="text-xs text-center">
                Stellen Sie Fragen zu Ihren Dokumenten. Der Assistent
                durchsucht Ihre Ablage und gibt fundierte Antworten.
              </p>
              <Button
                variant="outline"
                size="sm"
                onClick={handleNewSession}
              >
                <Plus className="h-4 w-4 mr-2" />
                Neue Unterhaltung starten
              </Button>
            </div>
          ) : messagesLoading ? (
            <div className="flex items-center justify-center h-full text-muted-foreground">
              <Loader2 className="h-5 w-5 animate-spin mr-2" />
              Lade Nachrichten...
            </div>
          ) : (
            <ScrollArea className="h-full">
              <div className="p-4 space-y-4" ref={scrollRef}>
                {(!messages || messages.length === 0) && !isStreaming && (
                  <div className="text-center py-8 text-muted-foreground text-sm">
                    <Bot className="h-8 w-8 mx-auto mb-2 opacity-50" />
                    Stellen Sie Ihre erste Frage...
                  </div>
                )}

                {messages?.map((msg) => (
                  <ChatMessage key={msg.id} message={msg} />
                ))}

                {/* Streaming-Nachricht */}
                {isStreaming && streamingContent && (
                  <ChatMessage
                    message={{
                      id: 'streaming',
                      session_id: activeSessionId,
                      role: 'assistant',
                      content: '',
                      created_at: new Date().toISOString(),
                    }}
                    isStreaming
                    streamingContent={streamingContent}
                  />
                )}

                {/* Streaming-Fehler */}
                {streamError && (
                  <div className="flex items-center gap-2 text-sm text-destructive bg-destructive/10 rounded-lg px-3 py-2">
                    <AlertCircle className="h-4 w-4 shrink-0" />
                    <span>{streamError}</span>
                  </div>
                )}
              </div>
            </ScrollArea>
          )}
        </div>

        {/* Eingabefeld */}
        {activeSessionId && (
          <ChatInput
            onSend={handleSend}
            isLoading={isStreaming}
            contextLabel={contextLabel}
            disabled={!activeSessionId}
          />
        )}
      </SheetContent>
    </Sheet>
  );
}
