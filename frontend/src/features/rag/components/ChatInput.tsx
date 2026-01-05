/**
 * Chat Input Component
 *
 * Input field with send button for chat messages.
 */

import { useState, useCallback, useRef, useEffect, KeyboardEvent } from 'react';
import { Send, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { cn } from '@/lib/utils';

interface ChatInputProps {
    onSend: (message: string) => void;
    disabled?: boolean;
    isLoading?: boolean;
    placeholder?: string;
    className?: string;
}

export function ChatInput({
    onSend,
    disabled = false,
    isLoading = false,
    placeholder = 'Stelle eine Frage zu deinen Dokumenten...',
    className,
}: ChatInputProps) {
    const [message, setMessage] = useState('');
    const textareaRef = useRef<HTMLTextAreaElement>(null);

    // Auto-resize textarea
    useEffect(() => {
        const textarea = textareaRef.current;
        if (textarea) {
            textarea.style.height = 'auto';
            textarea.style.height = `${Math.min(textarea.scrollHeight, 200)}px`;
        }
    }, [message]);

    const handleSend = useCallback(() => {
        const trimmed = message.trim();
        if (trimmed && !disabled && !isLoading) {
            onSend(trimmed);
            setMessage('');
            if (textareaRef.current) {
                textareaRef.current.style.height = 'auto';
            }
        }
    }, [message, disabled, isLoading, onSend]);

    const handleKeyDown = useCallback(
        (e: KeyboardEvent<HTMLTextAreaElement>) => {
            // Send on Enter (without Shift)
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSend();
            }
        },
        [handleSend]
    );

    const canSend = message.trim().length > 0 && !disabled && !isLoading;

    return (
        <div
            className={cn(
                'flex items-end gap-2 p-4 border-t bg-background',
                className
            )}
        >
            <Textarea
                ref={textareaRef}
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={placeholder}
                disabled={disabled || isLoading}
                className="min-h-[44px] max-h-[200px] resize-none"
                rows={1}
            />
            <Button
                onClick={handleSend}
                disabled={!canSend}
                size="icon"
                className="flex-shrink-0 h-11 w-11"
            >
                {isLoading ? (
                    <Loader2 className="h-5 w-5 animate-spin" />
                ) : (
                    <Send className="h-5 w-5" />
                )}
            </Button>
        </div>
    );
}

export default ChatInput;
