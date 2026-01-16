/**
 * Chat Interface Component
 *
 * Main chat interface with WebSocket connection,
 * message list, and input.
 */

import { useEffect, useRef, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
    MessageSquare,
    Wifi,
    WifiOff,
    AlertCircle,
    Loader2,
    Trash2,
    RefreshCw,
    FileText,
    Bot,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
    Alert,
    AlertDescription,
    AlertTitle,
} from '@/components/ui/alert';
import {
    Tooltip,
    TooltipContent,
    TooltipProvider,
    TooltipTrigger,
} from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';
import { logger } from '@/lib/logger';
import { useChatWebSocket } from '../hooks/use-chat-websocket';
import { useChatStatus } from '../hooks/use-chat';
import { ChatMessage } from './ChatMessage';
import { ChatInput } from './ChatInput';
import type { ConnectionStatus } from '../types/chat-types';

interface ChatInterfaceProps {
    sessionId?: string;
    onSessionChange?: (sessionId: string) => void;
    onSourceClick?: (documentId: string) => void;
    className?: string;
}

export function ChatInterface({
    sessionId: initialSessionId,
    onSessionChange,
    onSourceClick,
    className,
}: ChatInterfaceProps) {
    const messagesEndRef = useRef<HTMLDivElement>(null);

    // Chat status
    const { data: chatStatus, isLoading: statusLoading } = useChatStatus();

    // WebSocket connection
    const {
        status,
        sessionId,
        error,
        messages,
        isStreaming,
        contextDocuments,
        statusMessage,
        connect,
        disconnect,
        sendMessage,
        clearHistory,
    } = useChatWebSocket({
        sessionId: initialSessionId,
        autoConnect: true,
        onConnected: (sid) => {
            onSessionChange?.(sid);
        },
        onError: (err) => {
            logger.error('Chat-Fehler', err);
        },
    });

    // Auto-scroll to bottom
    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages, isStreaming]);

    // Handle send
    const handleSend = useCallback(
        (content: string) => {
            sendMessage(content);
        },
        [sendMessage]
    );

    // Handle reconnect
    const handleReconnect = useCallback(() => {
        connect(sessionId || undefined);
    }, [connect, sessionId]);

    // Handle clear
    const handleClear = useCallback(() => {
        if (window.confirm('Chat-Verlauf wirklich löschen?')) {
            clearHistory();
        }
    }, [clearHistory]);

    // Connection status indicator
    const getStatusInfo = (
        status: ConnectionStatus
    ): { icon: React.ReactNode; label: string; color: string } => {
        switch (status) {
            case 'connected':
                return {
                    icon: <Wifi className="h-4 w-4" />,
                    label: 'Verbunden',
                    color: 'text-green-500',
                };
            case 'connecting':
                return {
                    icon: <Loader2 className="h-4 w-4 animate-spin" />,
                    label: 'Verbinde...',
                    color: 'text-yellow-500',
                };
            case 'disconnected':
                return {
                    icon: <WifiOff className="h-4 w-4" />,
                    label: 'Getrennt',
                    color: 'text-muted-foreground',
                };
            case 'error':
                return {
                    icon: <AlertCircle className="h-4 w-4" />,
                    label: 'Fehler',
                    color: 'text-destructive',
                };
        }
    };

    const statusInfo = getStatusInfo(status);

    return (
        <div
            className={cn(
                'flex flex-col h-full border rounded-lg bg-background',
                className
            )}
        >
            {/* Header */}
            <div className="flex items-center justify-between p-4 border-b">
                <div className="flex items-center gap-3">
                    <div className="p-2 rounded-full bg-primary/10">
                        <MessageSquare className="h-5 w-5 text-primary" />
                    </div>
                    <div>
                        <h3 className="font-semibold">Dokumenten-Chat</h3>
                        <div className="flex items-center gap-2 text-sm text-muted-foreground">
                            <span className={statusInfo.color}>
                                {statusInfo.icon}
                            </span>
                            <span>{statusInfo.label}</span>
                            {chatStatus?.llm_enabled && chatStatus.llm_model && (
                                <Badge variant="secondary" className="text-xs">
                                    <Bot className="h-3 w-3 mr-1" />
                                    {chatStatus.llm_model}
                                </Badge>
                            )}
                        </div>
                    </div>
                </div>

                <div className="flex items-center gap-2">
                    {/* Context Documents Indicator */}
                    {contextDocuments.length > 0 && (
                        <TooltipProvider>
                            <Tooltip>
                                <TooltipTrigger asChild>
                                    <Badge variant="outline" className="gap-1">
                                        <FileText className="h-3 w-3" />
                                        {contextDocuments.length} Dokumente
                                    </Badge>
                                </TooltipTrigger>
                                <TooltipContent>
                                    <div className="space-y-1">
                                        {contextDocuments.map((doc, i) => (
                                            <div key={i} className="text-sm">
                                                {doc.filename} ({Math.round(doc.similarity * 100)}%)
                                            </div>
                                        ))}
                                    </div>
                                </TooltipContent>
                            </Tooltip>
                        </TooltipProvider>
                    )}

                    {/* Clear History */}
                    <TooltipProvider>
                        <Tooltip>
                            <TooltipTrigger asChild>
                                <Button
                                    variant="ghost"
                                    size="icon"
                                    onClick={handleClear}
                                    disabled={status !== 'connected' || messages.length === 0}
                                >
                                    <Trash2 className="h-4 w-4" />
                                </Button>
                            </TooltipTrigger>
                            <TooltipContent>Verlauf löschen</TooltipContent>
                        </Tooltip>
                    </TooltipProvider>

                    {/* Reconnect */}
                    {(status === 'disconnected' || status === 'error') && (
                        <Button
                            variant="outline"
                            size="sm"
                            onClick={handleReconnect}
                            className="gap-1"
                        >
                            <RefreshCw className="h-4 w-4" />
                            Verbinden
                        </Button>
                    )}
                </div>
            </div>

            {/* Error Alert */}
            <AnimatePresence>
                {error && (
                    <motion.div
                        initial={{ opacity: 0, height: 0 }}
                        animate={{ opacity: 1, height: 'auto' }}
                        exit={{ opacity: 0, height: 0 }}
                        className="px-4 pt-4"
                    >
                        <Alert variant="destructive">
                            <AlertCircle className="h-4 w-4" />
                            <AlertTitle>Fehler</AlertTitle>
                            <AlertDescription>{error}</AlertDescription>
                        </Alert>
                    </motion.div>
                )}
            </AnimatePresence>

            {/* Messages */}
            <ScrollArea className="flex-1 px-2">
                <div className="py-4">
                    {/* Empty State */}
                    {messages.length === 0 && status === 'connected' && (
                        <div className="flex flex-col items-center justify-center h-64 text-center text-muted-foreground">
                            <Bot className="h-12 w-12 mb-4 opacity-50" />
                            <p className="text-lg font-medium">
                                Willkommen im Dokumenten-Chat
                            </p>
                            <p className="text-sm max-w-md mt-2">
                                Stelle Fragen zu deinen Dokumenten. Ich durchsuche
                                deine Ablage und gebe dir kontextbasierte Antworten.
                            </p>
                            {!chatStatus?.llm_enabled && (
                                <Badge variant="secondary" className="mt-4">
                                    LLM nicht aktiviert - Nur Kontext-Vorschau
                                </Badge>
                            )}
                        </div>
                    )}

                    {/* Message List */}
                    <AnimatePresence initial={false}>
                        {messages
                            .filter((m) => m.role !== 'system')
                            .map((message) => (
                                <ChatMessage
                                    key={message.id}
                                    message={message}
                                    onSourceClick={onSourceClick}
                                />
                            ))}
                    </AnimatePresence>

                    {/* Status Message */}
                    {statusMessage && (
                        <motion.div
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 1 }}
                            className="flex items-center gap-2 px-4 py-2 text-sm text-muted-foreground"
                        >
                            <Loader2 className="h-4 w-4 animate-spin" />
                            {statusMessage}
                        </motion.div>
                    )}

                    {/* Scroll anchor */}
                    <div ref={messagesEndRef} />
                </div>
            </ScrollArea>

            {/* Input */}
            <ChatInput
                onSend={handleSend}
                disabled={status !== 'connected'}
                isLoading={isStreaming}
                placeholder={
                    status === 'connected'
                        ? 'Stelle eine Frage zu deinen Dokumenten...'
                        : 'Verbinde zuerst...'
                }
            />
        </div>
    );
}

export default ChatInterface;
