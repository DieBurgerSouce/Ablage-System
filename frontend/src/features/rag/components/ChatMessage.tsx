/**
 * Chat Message Component
 *
 * Renders a single chat message with sources and styling.
 */

import { memo } from 'react';
import { motion } from 'framer-motion';
import { User, Bot, FileText, ExternalLink, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
    Tooltip,
    TooltipContent,
    TooltipProvider,
    TooltipTrigger,
} from '@/components/ui/tooltip';
import type { ChatMessage as ChatMessageType } from '../types/chat-types';
import { formatTimestamp, formatSimilarity } from '../types/chat-types';
import { ChatActionCard } from './ChatActionCard';
import { DailyAgendaCard } from './DailyAgendaCard';
import { ComparisonChart } from './ComparisonChart';
import { SkontoCard } from './SkontoCard';

interface ChatMessageProps {
    message: ChatMessageType;
    onSourceClick?: (documentId: string) => void;
    onConfirmAction?: (actionId: string) => void;
    onRejectAction?: (actionId: string) => void;
    confirmingActionId?: string | null;
}

export const ChatMessage = memo(function ChatMessage({
    message,
    onSourceClick,
    onConfirmAction,
    onRejectAction,
    confirmingActionId,
}: ChatMessageProps) {
    const isUser = message.role === 'user';
    const isAssistant = message.role === 'assistant';
    const isStreaming = message.isStreaming;

    return (
        <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.2 }}
            className={cn(
                'flex gap-3 p-4',
                isUser ? 'flex-row-reverse' : 'flex-row'
            )}
        >
            {/* Avatar */}
            <div
                className={cn(
                    'flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center',
                    isUser
                        ? 'bg-primary text-primary-foreground'
                        : 'bg-muted'
                )}
            >
                {isUser ? (
                    <User className="h-4 w-4" />
                ) : (
                    <Bot className="h-4 w-4" />
                )}
            </div>

            {/* Message Content */}
            <div
                className={cn(
                    'flex flex-col gap-2 max-w-[80%]',
                    isUser ? 'items-end' : 'items-start'
                )}
            >
                {/* Message Bubble */}
                <div
                    className={cn(
                        'rounded-lg px-4 py-2',
                        isUser
                            ? 'bg-primary text-primary-foreground'
                            : 'bg-muted',
                        isStreaming && 'animate-pulse'
                    )}
                >
                    {/* Message Text */}
                    <div className="whitespace-pre-wrap break-words">
                        {message.content || (
                            <span className="flex items-center gap-2 text-muted-foreground">
                                <Loader2 className="h-4 w-4 animate-spin" />
                                Generiere Antwort...
                            </span>
                        )}
                    </div>

                    {/* Streaming Cursor */}
                    {isStreaming && message.content && (
                        <span className="inline-block w-2 h-4 ml-1 bg-current animate-pulse" />
                    )}
                </div>

                {/* Sources */}
                {isAssistant && message.sources && message.sources.length > 0 && (
                    <div className="flex flex-wrap gap-2 mt-1">
                        <TooltipProvider>
                            {message.sources.map((source, index) => (
                                <Tooltip key={source.document_id}>
                                    <TooltipTrigger asChild>
                                        <Button
                                            variant="outline"
                                            size="sm"
                                            className="h-7 text-xs gap-1"
                                            onClick={() =>
                                                onSourceClick?.(source.document_id)
                                            }
                                        >
                                            <FileText className="h-3 w-3" />
                                            <span className="max-w-[120px] truncate">
                                                {source.filename}
                                            </span>
                                            <Badge
                                                variant="secondary"
                                                className="ml-1 text-[10px] px-1"
                                            >
                                                {formatSimilarity(source.similarity)}
                                            </Badge>
                                            <ExternalLink className="h-3 w-3 ml-1" />
                                        </Button>
                                    </TooltipTrigger>
                                    <TooltipContent>
                                        <p className="font-medium">{source.filename}</p>
                                        <p className="text-xs text-muted-foreground">
                                            Relevanz: {formatSimilarity(source.similarity)}
                                        </p>
                                    </TooltipContent>
                                </Tooltip>
                            ))}
                        </TooltipProvider>
                    </div>
                )}

                {/* Actions */}
                {isAssistant && message.actions && message.actions.length > 0 && (
                    <div className="flex flex-col gap-3 mt-2 w-full max-w-md">
                        {message.actions.map((action) => {
                            if (action.result_type === 'agenda' && action.agenda_items) {
                                return (
                                    <DailyAgendaCard
                                        key={action.action_id}
                                        items={action.agenda_items}
                                    />
                                );
                            }
                            if (action.result_type === 'comparison' && action.comparison_data) {
                                return (
                                    <ComparisonChart
                                        key={action.action_id}
                                        data={action.comparison_data}
                                    />
                                );
                            }
                            if (action.result_type === 'skonto' && action.skonto_items) {
                                return (
                                    <SkontoCard
                                        key={action.action_id}
                                        items={action.skonto_items}
                                    />
                                );
                            }
                            return (
                                <ChatActionCard
                                    key={action.action_id}
                                    action={action}
                                    onConfirm={onConfirmAction || (() => {})}
                                    onReject={onRejectAction || (() => {})}
                                    isConfirming={confirmingActionId === action.action_id}
                                />
                            );
                        })}
                    </div>
                )}

                {/* Timestamp */}
                <span className="text-xs text-muted-foreground">
                    {formatTimestamp(message.timestamp)}
                </span>
            </div>
        </motion.div>
    );
});

export default ChatMessage;
