import { useState, useEffect, useCallback } from 'react';
import { Plus, MessageSquare, Search, Menu } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { ScrollArea } from '@/components/ui/scroll-area';
import { cn } from '@/lib/utils';
import { ChatInterface } from './ChatInterface';
import { chatApi } from '@/lib/api/chat-api';
import type { ChatSession, ChatMessage, SourceChunk } from '@/lib/api/chat-api';

export function ChatLayout() {
    const [sessions, setSessions] = useState<ChatSession[]>([]);
    const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
    const [messages, setMessages] = useState<ChatMessage[]>([]);
    const [isThinking, setIsThinking] = useState(false);
    const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);

    // Streaming state
    const [streamingContent, setStreamingContent] = useState<string>('');
    const [streamingSources, setStreamingSources] = useState<SourceChunk[]>([]);
    const [isStreaming, setIsStreaming] = useState(false);

    // Load Sessions
    useEffect(() => {
        chatApi.getSessions().then(setSessions).catch(console.error);
    }, []);

    // Load Messages when session changes
    useEffect(() => {
        if (activeSessionId) {
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
            setIsThinking(true);
            setIsStreaming(true);
            setStreamingContent('');
            setStreamingSources([]);

            // Optimistic update - add user message immediately
            const tempUserMsg: ChatMessage = {
                id: crypto.randomUUID(),
                session_id: activeSessionId || '',
                role: 'user',
                content,
                created_at: new Date().toISOString(),
            };
            setMessages((prev) => [...prev, tempUserMsg]);

            try {
                let fullContent = '';

                await chatApi.sendMessageStream(content, activeSessionId || undefined, {
                    onChunk: (chunk) => {
                        fullContent += chunk;
                        setStreamingContent(fullContent);
                    },
                    onSource: (source) => {
                        setStreamingSources((prev) => [...prev, source]);
                    },
                    onDone: (sessionId, messageId) => {
                        // Create final assistant message
                        const assistantMsg: ChatMessage = {
                            id: messageId || crypto.randomUUID(),
                            session_id: sessionId,
                            role: 'assistant',
                            content: fullContent,
                            created_at: new Date().toISOString(),
                            sources: streamingSources,
                        };

                        // Add to messages and clear streaming state
                        setMessages((prev) => [...prev, assistantMsg]);
                        setStreamingContent('');
                        setStreamingSources([]);
                        setIsStreaming(false);
                        setIsThinking(false);

                        // If new session was created, update state
                        if (!activeSessionId || sessionId !== activeSessionId) {
                            setActiveSessionId(sessionId);
                            chatApi.getSessions().then(setSessions).catch(console.error);
                        }
                    },
                    onError: (error) => {
                        console.error('Streaming error:', error);
                        // Fallback to non-streaming
                        handleSendMessageFallback(content, tempUserMsg.id);
                    },
                });
            } catch (error) {
                console.error('Chat error:', error);
                // Fallback to non-streaming on connection error
                handleSendMessageFallback(content, tempUserMsg.id);
            }
        },
        [activeSessionId, streamingSources]
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
        setIsMobileMenuOpen(false);
    };

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
                                    {session.preview}
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

                {activeSessionId || messages.length > 0 || isStreaming ? (
                    <ChatInterface
                        messages={displayMessages}
                        onSendMessage={handleSendMessage}
                        isThinking={isThinking && !isStreaming}
                    />
                ) : (
                    <div className="flex-1 flex flex-col items-center justify-center p-8 text-center text-muted-foreground">
                        <div className="bg-muted/50 p-6 rounded-full mb-6">
                            <MessageSquare className="h-12 w-12 text-primary/50" />
                        </div>
                        <h3 className="text-xl font-semibold mb-2 text-foreground">
                            Willkommen beim Dokumenten-Chat
                        </h3>
                        <p className="max-w-md mb-8">
                            Stellen Sie Fragen zu Ihren Dokumenten, lassen Sie sich
                            Zusammenfassungen erstellen oder suchen Sie nach spezifischen
                            Informationen.
                        </p>
                        <div className="grid gap-2 w-full max-w-sm">
                            <Button
                                variant="outline"
                                onClick={() =>
                                    handleSendMessage('Fasse die letzten Rechnungen zusammen')
                                }
                            >
                                "Fasse die letzten Rechnungen zusammen"
                            </Button>
                            <Button
                                variant="outline"
                                onClick={() =>
                                    handleSendMessage('Welche Verträge laufen bald aus?')
                                }
                            >
                                "Welche Verträge laufen bald aus?"
                            </Button>
                        </div>
                    </div>
                )}
            </main>
        </div>
    );
}
