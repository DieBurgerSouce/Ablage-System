import { useState, useRef, useEffect } from 'react';
import { Send, Paperclip, FileText, Bot, User, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import type { ChatMessage } from '@/lib/api/chat-api';

interface ChatInterfaceProps {
    messages: ChatMessage[];
    onSendMessage: (content: string) => void;
    isThinking: boolean;
}

export function ChatInterface({ messages, onSendMessage, isThinking }: ChatInterfaceProps) {
    const [input, setInput] = useState('');
    const scrollRef = useRef<HTMLDivElement>(null);

    // Check if we're currently streaming (last message is streaming)
    const isStreaming = messages.some((m) => m.id === 'streaming');
    const isProcessing = isThinking || isStreaming;

    // Auto-scroll to bottom
    useEffect(() => {
        if (scrollRef.current) {
            scrollRef.current.scrollIntoView({ behavior: 'smooth' });
        }
    }, [messages, isThinking]);

    const handleSend = () => {
        if (!input.trim()) return;
        onSendMessage(input);
        setInput('');
    };

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSend();
        }
    };

    return (
        <div className="flex flex-col h-full">
            {/* Messages Area */}
            <ScrollArea className="flex-1 p-4">
                <div className="space-y-6 max-w-3xl mx-auto">
                    {messages.map((msg) => (
                        <div
                            key={msg.id}
                            className={cn(
                                "flex gap-4",
                                msg.role === 'user' ? "flex-row-reverse" : "flex-row"
                            )}
                        >
                            {/* Avatar Placeholder */}
                            <div className={cn(
                                "h-8 w-8 mt-1 rounded-full flex items-center justify-center shrink-0",
                                msg.role === 'assistant' ? "bg-primary text-primary-foreground" : "bg-muted"
                            )}>
                                {msg.role === 'assistant' ? <Bot className="h-5 w-5" /> : <User className="h-5 w-5" />}
                            </div>

                            {/* Message Content */}
                            <div className={cn(
                                "flex flex-col gap-2 max-w-[80%]",
                                msg.role === 'user' ? "items-end" : "items-start"
                            )}>
                                <div className={cn(
                                    "rounded-lg p-4 text-sm whitespace-pre-wrap",
                                    msg.role === 'user'
                                        ? "bg-primary text-primary-foreground"
                                        : "bg-muted/50 border"
                                )}>
                                    {/* Show loading indicator for streaming message with no content yet */}
                                    {msg.is_thinking && !msg.content ? (
                                        <div className="flex items-center gap-2">
                                            <Loader2 className="h-4 w-4 animate-spin" />
                                            <span className="text-muted-foreground animate-pulse">
                                                Suche in Dokumenten...
                                            </span>
                                        </div>
                                    ) : (
                                        <>
                                            {msg.content}
                                            {/* Show cursor while streaming */}
                                            {msg.id === 'streaming' && msg.content && (
                                                <span className="inline-block w-2 h-4 ml-1 bg-primary animate-pulse" />
                                            )}
                                        </>
                                    )}
                                </div>

                                {/* Sources (Assistant only) */}
                                {msg.sources && msg.sources.length > 0 && (
                                    <div className="flex flex-wrap gap-2 mt-1">
                                        {msg.sources.map((source) => (
                                            <Card
                                                key={source.chunk_id}
                                                className="flex items-center gap-2 p-2 text-xs hover:bg-muted cursor-pointer transition-colors border-primary/20"
                                                onClick={() => {
                                                    // Navigate to document or show preview
                                                    const docName = source.document_name || `Dokument ${source.document_id.slice(0, 8)}`;
                                                    const page = source.page_number || 1;
                                                    console.log('Source clicked:', source);
                                                    alert(`Zeige Quelle: ${docName} (Seite ${page})`);
                                                }}
                                            >
                                                <FileText className="h-3 w-3 text-primary" />
                                                <span className="truncate max-w-[150px]">
                                                    {source.document_name || `Dok. ${source.document_id.slice(0, 8)}`}
                                                </span>
                                                {source.page_number && (
                                                    <Badge variant="secondary" className="text-[10px] h-4 px-1">
                                                        S. {source.page_number}
                                                    </Badge>
                                                )}
                                                <Badge variant="outline" className="text-[10px] h-4 px-1">
                                                    {Math.round(source.similarity * 100)}%
                                                </Badge>
                                            </Card>
                                        ))}
                                    </div>
                                )}

                                <span className="text-[10px] text-muted-foreground">
                                    {new Date(msg.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                                </span>
                            </div>
                        </div>
                    ))}

                    {/* Thinking Indicator */}
                    {isThinking && (
                        <div className="flex gap-4">
                            <div className="h-8 w-8 mt-1 rounded-full bg-primary text-primary-foreground flex items-center justify-center shrink-0">
                                <Bot className="h-5 w-5" />
                            </div>
                            <div className="bg-muted/50 border rounded-lg p-4 flex items-center gap-2">
                                <span className="relative flex h-2 w-2">
                                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary opacity-75"></span>
                                    <span className="relative inline-flex rounded-full h-2 w-2 bg-primary"></span>
                                </span>
                                <span className="text-xs text-muted-foreground animate-pulse">Analysiere Dokumente...</span>
                            </div>
                        </div>
                    )}
                    <div ref={scrollRef} />
                </div>
            </ScrollArea>

            {/* Input Area */}
            <div className="p-4 border-t bg-background">
                <div className="max-w-3xl mx-auto flex gap-2">
                    <Button variant="outline" size="icon" className="shrink-0">
                        <Paperclip className="h-5 w-5" />
                    </Button>
                    <Textarea
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        onKeyDown={handleKeyDown}
                        placeholder="Stellen Sie eine Frage zu Ihren Dokumenten..."
                        className="min-h-[50px] max-h-[200px] resize-none"
                        rows={1}
                    />
                    <Button onClick={handleSend} disabled={!input.trim() || isProcessing} className="shrink-0">
                        {isProcessing ? (
                            <Loader2 className="h-5 w-5 animate-spin" />
                        ) : (
                            <Send className="h-5 w-5" />
                        )}
                    </Button>
                </div>
                <div className="max-w-3xl mx-auto mt-2 text-center">
                    <p className="text-[10px] text-muted-foreground">
                        KI kann Fehler machen. Bitte überprüfen Sie wichtige Informationen in den Originaldokumenten.
                    </p>
                </div>
            </div>
        </div>
    );
}
