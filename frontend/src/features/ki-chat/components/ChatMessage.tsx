/**
 * ChatMessage - Einzelne Nachricht im KI-Chat Panel
 *
 * Zeigt User- und Assistant-Nachrichten mit Quellen-Badges,
 * Streaming-Cursor und Zeitstempel an.
 */

import { FileText, ExternalLink } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import type { ChatMessage as ChatMessageType } from '../types/chat-types';

interface ChatMessageProps {
  message: ChatMessageType;
  isStreaming?: boolean;
  streamingContent?: string;
}

export function ChatMessage({
  message,
  isStreaming,
  streamingContent,
}: ChatMessageProps) {
  const isUser = message.role === 'user';
  const content = isStreaming ? streamingContent : message.content;

  return (
    <div
      className={cn('flex gap-3', isUser ? 'justify-end' : 'justify-start')}
    >
      <div
        className={cn(
          'max-w-[85%] rounded-lg px-4 py-3',
          isUser ? 'bg-primary text-primary-foreground' : 'bg-muted'
        )}
      >
        {/* Nachrichteninhalt */}
        <div className="text-sm whitespace-pre-wrap break-words">
          {content}
        </div>

        {/* Streaming-Cursor */}
        {isStreaming && (
          <span className="inline-block w-2 h-4 bg-current animate-pulse ml-0.5" />
        )}

        {/* Quellen-Badges */}
        {message.sources && message.sources.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {message.sources.map((source) => (
              <Badge
                key={`${source.document_id}-${source.chunk_index}`}
                variant="secondary"
                className="text-xs cursor-pointer hover:bg-secondary/80 gap-1"
                onClick={() => {
                  window.location.href = `/documents/${source.document_id}`;
                }}
              >
                <FileText className="h-3 w-3" />
                <span className="max-w-[100px] truncate">
                  {source.chunk_text.slice(0, 30)}...
                </span>
                {source.page_number && (
                  <span className="text-muted-foreground">
                    S.{source.page_number}
                  </span>
                )}
                <span className="text-muted-foreground">
                  {Math.round(source.similarity * 100)}%
                </span>
                <ExternalLink className="h-3 w-3" />
              </Badge>
            ))}
          </div>
        )}

        {/* Zeitstempel */}
        <div
          className={cn(
            'text-[10px] mt-1',
            isUser
              ? 'text-primary-foreground/60'
              : 'text-muted-foreground'
          )}
        >
          {new Date(message.created_at).toLocaleTimeString('de-DE', {
            hour: '2-digit',
            minute: '2-digit',
          })}
        </div>
      </div>
    </div>
  );
}
