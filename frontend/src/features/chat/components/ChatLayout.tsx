import { useState, useEffect, useCallback, useRef } from 'react';
import { Plus, MessageSquare, Search, Menu } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { ScrollArea } from '@/components/ui/scroll-area';
import { cn } from '@/lib/utils';
import { ChatInterface } from './ChatInterface';
import { DocumentPreviewModal } from './DocumentPreviewModal';
import { chatApi } from '@/lib/api/chat-api';
import { documentsService } from '@/lib/api/services/documents';
import { useToast } from '@/components/ui/use-toast';
import type { ChatSession, ChatMessage, SourceChunk } from '@/lib/api/chat-api';

/**
 * Formatiert ein Datum als relative Zeit (z.B. "vor 23 Stunden", "vor 3 Tagen")
 */
function formatRelativeTime(dateString: string | null): string {
    if (!dateString) return 'Noch keine Nachricht';

    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMinutes = Math.floor(diffMs / (1000 * 60));
    const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

    if (diffMinutes < 1) return 'Gerade eben';
    if (diffMinutes < 60) return `vor ${diffMinutes} ${diffMinutes === 1 ? 'Minute' : 'Minuten'}`;
    if (diffHours < 24) return `vor ${diffHours} ${diffHours === 1 ? 'Stunde' : 'Stunden'}`;
    if (diffDays < 7) return `vor ${diffDays} ${diffDays === 1 ? 'Tag' : 'Tagen'}`;
    if (diffDays < 30) {
        const weeks = Math.floor(diffDays / 7);
        return `vor ${weeks} ${weeks === 1 ? 'Woche' : 'Wochen'}`;
    }
    if (diffDays < 365) {
        const months = Math.floor(diffDays / 30);
        return `vor ${months} ${months === 1 ? 'Monat' : 'Monaten'}`;
    }
    const years = Math.floor(diffDays / 365);
    return `vor ${years} ${years === 1 ? 'Jahr' : 'Jahren'}`;
}

export function ChatLayout() {
    const { toast } = useToast();
    const [sessions, setSessions] = useState<ChatSession[]>([]);
    const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
    const [messages, setMessages] = useState<ChatMessage[]>([]);
    const [isThinking, setIsThinking] = useState(false);
    const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);

    // Streaming state
    const [streamingContent, setStreamingContent] = useState<string>('');
    const [streamingSources, setStreamingSources] = useState<SourceChunk[]>([]);
    const [isStreaming, setIsStreaming] = useState(false);

    // Document preview modal state
    const [previewSource, setPreviewSource] = useState<SourceChunk | null>(null);

    // Document upload state
    const [isUploading, setIsUploading] = useState(false);
    const [uploadProgress, setUploadProgress] = useState(0);
    const [attachedDocument, setAttachedDocument] = useState<{
        id: string;
        name: string;
    } | null>(null);

    // Ref für Sources - löst React Closure-Problem
    const sourcesRef = useRef<SourceChunk[]>([]);
    // Flag um zu verhindern, dass Messages nach Streaming neu geladen werden
    const skipNextSessionLoad = useRef(false);
    // AbortController für Streaming-Abbruch
    const abortControllerRef = useRef<AbortController | null>(null);

    // Load Sessions
    useEffect(() => {
        chatApi.getSessions().then(setSessions).catch(console.error);
    }, []);

    // Load Messages when session changes
    useEffect(() => {
        if (activeSessionId) {
            // Skip reload wenn gerade eine Message mit Sources hinzugefügt wurde
            if (skipNextSessionLoad.current) {
                skipNextSessionLoad.current = false;
                return;
            }
            setMessages([]); // Clear previous messages
            chatApi
                .getSession(activeSessionId)
                .then((session) => {
                    setMessages(session.messages || []);
                })
                .catch(console.error);
        }
    }, [activeSessionId]);

    const handleSendMessage = useCallback(
        async (content: string) => {
            // Create new AbortController for this request
            abortControllerRef.current = new AbortController();

            setIsThinking(true);
            setIsStreaming(true);
            setStreamingContent('');
            setStreamingSources([]);
            sourcesRef.current = []; // Reset ref

            // Capture attachment before clearing (for context)
            const currentAttachment = attachedDocument;

            // Optimistic update - add user message immediately
            // Include attached_document so it shows in the UI immediately
            const tempUserMsg: ChatMessage = {
                id: crypto.randomUUID(),
                session_id: activeSessionId || '',
                role: 'user',
                content: content,
                created_at: new Date().toISOString(),
                attached_document: currentAttachment
                    ? { id: currentAttachment.id, name: currentAttachment.name }
                    : undefined,
            };
            setMessages((prev) => [...prev, tempUserMsg]);

            // Clear attachment after capturing
            if (currentAttachment) {
                setAttachedDocument(null);
            }

            // Variable to track content for abort handling
            let fullContent = '';

            try {
                await chatApi.sendMessageStream(content, activeSessionId || undefined, {
                    // Document context wenn Attachment vorhanden
                    contextType: currentAttachment ? 'document' : undefined,
                    contextId: currentAttachment?.id,
                    signal: abortControllerRef.current.signal,
                    onChunk: (chunk) => {
                        fullContent += chunk;
                        setStreamingContent(fullContent);
                    },
                    onSource: (source) => {
                        // Ref UND State aktualisieren - Ref für Callback, State für UI
                        sourcesRef.current = [...sourcesRef.current, source];
                        setStreamingSources((prev) => [...prev, source]);
                    },
                    onDone: (sessionId, messageId) => {
                        // Verwende Ref statt State (Closure-Problem gelöst!)
                        const finalSources = [...sourcesRef.current];

                        // Create final assistant message
                        const assistantMsg: ChatMessage = {
                            id: messageId || crypto.randomUUID(),
                            session_id: sessionId,
                            role: 'assistant',
                            content: fullContent,
                            created_at: new Date().toISOString(),
                            sources: finalSources,
                        };

                        // Add to messages and clear streaming state
                        setMessages((prev) => [...prev, assistantMsg]);
                        setStreamingContent('');
                        setStreamingSources([]);
                        sourcesRef.current = [];
                        setIsStreaming(false);
                        setIsThinking(false);
                        abortControllerRef.current = null;

                        // If new session was created, update state
                        if (!activeSessionId || sessionId !== activeSessionId) {
                            // Skip das automatische Neuladen der Messages (würde Sources verlieren)
                            skipNextSessionLoad.current = true;
                            setActiveSessionId(sessionId);
                            chatApi.getSessions().then(setSessions).catch(console.error);
                        }
                    },
                    onAbort: () => {
                        // Streaming wurde abgebrochen - behalte bisherigen Content
                        const finalSources = [...sourcesRef.current];

                        if (fullContent.trim()) {
                            // Füge abgebrochene Nachricht hinzu mit bisherigem Inhalt
                            const abortedMsg: ChatMessage = {
                                id: crypto.randomUUID(),
                                session_id: activeSessionId || '',
                                role: 'assistant',
                                content: fullContent + '\n\n*[Generierung gestoppt]*',
                                created_at: new Date().toISOString(),
                                sources: finalSources,
                            };
                            setMessages((prev) => [...prev, abortedMsg]);
                        }

                        setStreamingContent('');
                        setStreamingSources([]);
                        sourcesRef.current = [];
                        setIsStreaming(false);
                        setIsThinking(false);
                        abortControllerRef.current = null;
                    },
                    onError: (error) => {
                        console.error('Streaming error:', error);
                        abortControllerRef.current = null;
                        // Fallback to non-streaming
                        handleSendMessageFallback(content, tempUserMsg.id);
                    },
                });
            } catch (error) {
                console.error('Chat error:', error);
                abortControllerRef.current = null;
                // Fallback to non-streaming on connection error
                handleSendMessageFallback(content, tempUserMsg.id);
            }
        },
        [activeSessionId, attachedDocument]
    );

    // Fallback to non-streaming if streaming fails
    const handleSendMessageFallback = async (content: string, tempMsgId: string) => {
        try {
            const { session_id, response } = await chatApi.sendMessage(
                content,
                activeSessionId || undefined
            );

            if (!activeSessionId || session_id !== activeSessionId) {
                setActiveSessionId(session_id);
                chatApi.getSessions().then(setSessions).catch(console.error);
            }

            setMessages((prev) => [...prev, response]);
        } catch (fallbackError) {
            console.error('Fallback error:', fallbackError);
            // Remove optimistic update on error
            setMessages((prev) => prev.filter((m) => m.id !== tempMsgId));
        } finally {
            setStreamingContent('');
            setStreamingSources([]);
            setIsStreaming(false);
            setIsThinking(false);
        }
    };

    const handleNewChat = () => {
        setActiveSessionId(null);
        setMessages([]);
        setStreamingContent('');
        setStreamingSources([]);
        setAttachedDocument(null);
        setIsMobileMenuOpen(false);
    };

    const handleSourceClick = useCallback((source: SourceChunk) => {
        // Open document preview modal instead of navigating
        setPreviewSource(source);
    }, []);

    const handleFileUpload = useCallback(
        async (file: File) => {
            setIsUploading(true);
            setUploadProgress(0);

            try {
                const document = await documentsService.upload(
                    file,
                    { ocrBackend: 'auto' },
                    (progress) => setUploadProgress(progress)
                );

                toast({
                    title: 'Dokument hochgeladen',
                    description: `${document.name} - Du kannst jetzt Fragen dazu stellen.`,
                });

                // Dokument als Attachment speichern (nicht automatisch senden)
                setAttachedDocument({ id: document.id, name: document.name });
            } catch (error) {
                const errorMessage =
                    error instanceof Error ? error.message : 'Unbekannter Fehler';
                toast({
                    title: 'Upload fehlgeschlagen',
                    description: errorMessage,
                    variant: 'destructive',
                });
            } finally {
                setIsUploading(false);
                setUploadProgress(0);
            }
        },
        [toast]
    );

    const handleRemoveAttachment = useCallback(() => {
        setAttachedDocument(null);
    }, []);

    const handleStop = useCallback(() => {
        if (abortControllerRef.current) {
            abortControllerRef.current.abort();
        }
    }, []);

    // Combine messages with streaming message for display
    const displayMessages = isStreaming
        ? [
              ...messages,
              {
                  id: 'streaming',
                  session_id: activeSessionId || '',
                  role: 'assistant' as const,
                  content: streamingContent,
                  created_at: new Date().toISOString(),
                  sources: streamingSources,
                  is_thinking: streamingContent.length === 0,
              },
          ]
        : messages;

    const SidebarContent = () => (
        <div className="flex flex-col h-full">
            <div className="p-4 border-b">
                <Button
                    onClick={handleNewChat}
                    className="w-full justify-start gap-2"
                    variant="default"
                >
                    <Plus className="h-4 w-4" /> Neuer Chat
                </Button>
            </div>
            <div className="p-4">
                <div className="relative">
                    <Search className="absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
                    <Input placeholder="Chats durchsuchen..." className="pl-8" />
                </div>
            </div>
            <ScrollArea className="flex-1">
                <div className="p-2 space-y-1">
                    {sessions.map((session) => (
                        <Button
                            key={session.id}
                            variant={activeSessionId === session.id ? 'secondary' : 'ghost'}
                            className={cn(
                                'w-full justify-start text-left h-auto py-3 px-4',
                                activeSessionId === session.id && 'bg-secondary'
                            )}
                            onClick={() => {
                                setAttachedDocument(null);
                                setActiveSessionId(session.id);
                                setIsMobileMenuOpen(false);
                            }}
                        >
                            <MessageSquare className="h-4 w-4 mr-3 shrink-0 text-muted-foreground" />
                            <div className="overflow-hidden">
                                <div className="font-medium truncate">
                                    {session.title || 'Neue Unterhaltung'}
                                </div>
                                <div className="text-xs text-muted-foreground truncate">
                                    {formatRelativeTime(session.last_message_at)}
                                </div>
                            </div>
                        </Button>
                    ))}
                </div>
            </ScrollArea>
        </div>
    );

    return (
        <div className="flex h-[calc(100vh-4rem)] bg-background relative">
            {/* Sidebar */}
            <aside
                className={cn(
                    'w-80 flex-col border-r bg-muted/10 absolute md:relative h-full z-20 bg-background transition-transform duration-200 ease-in-out',
                    isMobileMenuOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'
                )}
            >
                <SidebarContent />
            </aside>

            {/* Overlay for mobile */}
            {isMobileMenuOpen && (
                <div
                    className="fixed inset-0 bg-black/50 z-10 md:hidden"
                    onClick={() => setIsMobileMenuOpen(false)}
                />
            )}

            {/* Main Chat Area */}
            <main className="flex-1 flex flex-col min-w-0">
                {/* Mobile Header */}
                <div className="md:hidden p-4 border-b flex items-center gap-4">
                    <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => setIsMobileMenuOpen(true)}
                    >
                        <Menu className="h-5 w-5" />
                    </Button>
                    <span className="font-semibold">Chat</span>
                </div>

                <ChatInterface
                    messages={displayMessages}
                    onSendMessage={handleSendMessage}
                    isThinking={isThinking && !isStreaming}
                    onSourceClick={handleSourceClick}
                    onFileUpload={handleFileUpload}
                    isUploading={isUploading}
                    uploadProgress={uploadProgress}
                    attachedDocument={attachedDocument}
                    onRemoveAttachment={handleRemoveAttachment}
                    onStop={handleStop}
                    canStop={isStreaming}
                />
            </main>

            {/* Document Preview Modal */}
            <DocumentPreviewModal
                documentId={previewSource?.document_id ?? null}
                open={!!previewSource}
                onOpenChange={(open) => !open && setPreviewSource(null)}
                documentName={previewSource?.document_name}
                pageNumber={previewSource?.page_number}
            />
        </div>
    );
}
