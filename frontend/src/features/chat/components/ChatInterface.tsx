import { useState, useRef, useEffect, useMemo } from 'react';
import { Send, Paperclip, FileText, Bot, User, Loader2, X, MessageSquare, Square } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import type { ChatMessage, SourceChunk } from '@/lib/api/chat-api';
import { useThinkingMessage } from '../hooks/use-thinking-messages';

interface ChatInterfaceProps {
    messages: ChatMessage[];
    onSendMessage: (content: string) => void;
    isThinking: boolean;
    onSourceClick?: (source: SourceChunk) => void;
    onFileUpload?: (file: File) => void;
    isUploading?: boolean;
    uploadProgress?: number;
    attachedDocument?: { id: string; name: string } | null;
    onRemoveAttachment?: () => void;
    onStop?: () => void;
    canStop?: boolean;
}

export function ChatInterface({
    messages,
    onSendMessage,
    isThinking,
    onSourceClick,
    onFileUpload,
    isUploading,
    uploadProgress,
    attachedDocument,
    onRemoveAttachment,
    onStop,
    canStop,
}: ChatInterfaceProps) {
    const [input, setInput] = useState('');
    const scrollRef = useRef<HTMLDivElement>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);

    const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (file && onFileUpload) {
            onFileUpload(file);
        }
        // Reset input so same file can be selected again
        e.target.value = '';
    };

    // Check if we're currently streaming (last message is streaming)
    const isStreaming = messages.some((m) => m.id === 'streaming');
    const isProcessing = isThinking || isStreaming;

    // Get streaming message content (if any)
    const streamingMessage = messages.find((m) => m.id === 'streaming');
    const hasStreamingContent = !!(streamingMessage?.content);

    // Check if last user message had attachment (for context-aware thinking messages)
    const lastUserMessage = useMemo(() => {
        for (let i = messages.length - 1; i >= 0; i--) {
            if (messages[i].role === 'user') return messages[i];
        }
        return null;
    }, [messages]);
    const hasRecentAttachment = !!(lastUserMessage?.attached_document || attachedDocument);

    // Kontextabhängige, rotierende Thinking-Nachricht
    const thinkingMessage = useThinkingMessage({
        hasAttachment: hasRecentAttachment,
        hasContent: hasStreamingContent,
        isStreaming,
        isThinking,
    });

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
                    {/* Welcome Screen when no messages */}
                    {messages.length === 0 && !isThinking && (
                        <div className="flex flex-col items-center justify-center py-16 text-center text-muted-foreground">
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
                                    onClick={() => onSendMessage('Fasse die letzten Rechnungen zusammen')}
                                >
                                    "Fasse die letzten Rechnungen zusammen"
                                </Button>
                                <Button
                                    variant="outline"
                                    onClick={() => onSendMessage('Welche Verträge laufen bald aus?')}
                                >
                                    "Welche Verträge laufen bald aus?"
                                </Button>
                            </div>
                        </div>
                    )}

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
                                            <span className="text-muted-foreground">
                                                {thinkingMessage}
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

                                {/* Attached Document (User messages) - Prominent styling */}
                                {msg.role === 'user' && msg.attached_document && (
                                    <Card
                                        className="flex items-center gap-3 p-2.5 mt-2 bg-background/95 border-2 border-primary/40 rounded-lg cursor-pointer hover:border-primary/60 hover:shadow-md transition-all shadow-sm"
                                        onClick={() => onSourceClick?.({
                                            chunk_id: '',
                                            document_id: msg.attached_document!.id,
                                            document_name: msg.attached_document!.name,
                                            chunk_text: '',
                                            chunk_index: 0,
                                            page_number: 1,
                                            section_type: null,
                                            similarity: 0,
                                            rerank_score: null
                                        })}
                                        role="button"
                                        aria-label={`Dokument ${msg.attached_document.name} öffnen`}
                                    >
                                        {/* Thumbnail with skeleton fallback */}
                                        <div className="w-10 h-12 rounded overflow-hidden bg-muted animate-pulse flex-shrink-0 flex items-center justify-center border">
                                            <img
                                                src={`/api/v1/documents/${msg.attached_document.id}/thumbnail`}
                                                className="w-full h-full object-cover"
                                                alt={`Anhang: ${msg.attached_document.name}`}
                                                onLoad={(e) => {
                                                    e.currentTarget.parentElement?.classList.remove('animate-pulse');
                                                }}
                                                onError={(e) => {
                                                    e.currentTarget.style.display = 'none';
                                                    e.currentTarget.parentElement?.classList.remove('animate-pulse');
                                                }}
                                            />
                                            <FileText className="h-5 w-5 text-muted-foreground" />
                                        </div>
                                        <div className="flex flex-col min-w-0">
                                            <span className="text-sm font-medium truncate max-w-[100px] md:max-w-[140px] text-foreground">
                                                {msg.attached_document.name}
                                            </span>
                                            <span className="text-[10px] text-muted-foreground">Anhang - Klicken zum Öffnen</span>
                                        </div>
                                        <FileText className="h-4 w-4 text-primary ml-auto flex-shrink-0" aria-hidden="true" />
                                    </Card>
                                )}

                                {/* Sources (Assistant only) */}
                                {msg.sources && msg.sources.length > 0 && (
                                    <div className="flex flex-wrap gap-2 mt-1">
                                        {msg.sources.map((source) => (
                                            <Card
                                                key={source.chunk_id}
                                                className="flex items-center gap-2 p-2 text-xs hover:bg-muted cursor-pointer transition-colors border-primary/20"
                                                onClick={() => {
                                                    if (onSourceClick) {
                                                        onSourceClick(source);
                                                    }
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
                                <span className="text-xs text-muted-foreground">{thinkingMessage}</span>
                            </div>
                        </div>
                    )}
                    <div ref={scrollRef} />
                </div>
            </ScrollArea>

            {/* Input Area */}
            <div className="p-4 border-t bg-background">
                {/* Attachment Badge mit Thumbnail - Prominent styling */}
                {attachedDocument && (
                    <div className="max-w-3xl mx-auto mb-3">
                        <Card
                            className="inline-flex items-center gap-3 px-4 py-3 bg-primary/5 border-2 border-primary/30 rounded-xl cursor-pointer hover:border-primary/50 hover:bg-primary/10 hover:shadow-lg transition-all shadow-md"
                            onClick={() => onSourceClick?.({
                                chunk_id: '',
                                document_id: attachedDocument.id,
                                document_name: attachedDocument.name,
                                chunk_text: '',
                                chunk_index: 0,
                                page_number: 1,
                                section_type: null,
                                similarity: 0,
                                rerank_score: null
                            })}
                            role="button"
                            aria-label={`Dokument ${attachedDocument.name} öffnen`}
                        >
                            {/* Thumbnail Preview with skeleton loading */}
                            <div className="w-12 h-16 rounded-lg overflow-hidden bg-muted animate-pulse flex-shrink-0 border-2 border-muted flex items-center justify-center shadow-inner">
                                <img
                                    src={`/api/v1/documents/${attachedDocument.id}/thumbnail`}
                                    className="w-full h-full object-cover"
                                    alt={`Vorschau: ${attachedDocument.name}`}
                                    onLoad={(e) => {
                                        e.currentTarget.parentElement?.classList.remove('animate-pulse');
                                        e.currentTarget.parentElement?.classList.add('bg-background');
                                    }}
                                    onError={(e) => {
                                        e.currentTarget.style.display = 'none';
                                        e.currentTarget.parentElement?.classList.remove('animate-pulse');
                                        e.currentTarget.parentElement?.classList.add('bg-background');
                                    }}
                                />
                                <FileText className="h-6 w-6 text-primary/60" aria-hidden="true" />
                            </div>
                            <div className="flex flex-col min-w-0">
                                <div className="flex items-center gap-2">
                                    <Badge variant="secondary" className="text-[10px] px-1.5 py-0">
                                        Anhang
                                    </Badge>
                                </div>
                                <span className="text-sm font-semibold truncate max-w-[140px] md:max-w-[200px] mt-1">
                                    {attachedDocument.name}
                                </span>
                                <span className="text-xs text-muted-foreground">Klicken zum Öffnen</span>
                            </div>
                            <Button
                                variant="outline"
                                size="sm"
                                className="h-8 w-8 p-0 hover:bg-destructive hover:text-destructive-foreground hover:border-destructive ml-4 transition-colors"
                                onClick={(e) => {
                                    e.stopPropagation();
                                    onRemoveAttachment?.();
                                }}
                                title="Anhang entfernen"
                            >
                                <X className="h-4 w-4" />
                            </Button>
                        </Card>
                    </div>
                )}
                <div className="max-w-3xl mx-auto flex gap-2">
                    {/* Hidden file input */}
                    <input
                        ref={fileInputRef}
                        type="file"
                        accept=".pdf,.png,.jpg,.jpeg,.tif,.tiff,.bmp,.gif,.webp,.heic,.heif"
                        onChange={handleFileSelect}
                        className="hidden"
                    />
                    <Button
                        variant="outline"
                        size="icon"
                        className="shrink-0 relative"
                        onClick={() => fileInputRef.current?.click()}
                        disabled={isUploading}
                        title="Dokument hochladen"
                    >
                        {isUploading ? (
                            <>
                                <Loader2 className="h-5 w-5 animate-spin" />
                                {uploadProgress !== undefined && uploadProgress > 0 && (
                                    <span className="absolute -bottom-1 -right-1 text-[10px] bg-primary text-primary-foreground rounded-full px-1 min-w-[1.25rem] text-center">
                                        {uploadProgress}%
                                    </span>
                                )}
                            </>
                        ) : (
                            <Paperclip className="h-5 w-5" />
                        )}
                    </Button>
                    <Textarea
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        onKeyDown={handleKeyDown}
                        placeholder="Stellen Sie eine Frage zu Ihren Dokumenten..."
                        className="min-h-[50px] max-h-[200px] resize-none"
                        rows={1}
                    />
                    {canStop ? (
                        <Button
                            onClick={onStop}
                            variant="destructive"
                            className="shrink-0"
                            title="Generierung stoppen"
                        >
                            <Square className="h-5 w-5 fill-current" />
                        </Button>
                    ) : (
                        <Button
                            onClick={handleSend}
                            disabled={!input.trim() || isProcessing}
                            className="shrink-0"
                            title="Nachricht senden"
                        >
                            {isProcessing ? (
                                <Loader2 className="h-5 w-5 animate-spin" />
                            ) : (
                                <Send className="h-5 w-5" />
                            )}
                        </Button>
                    )}
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
