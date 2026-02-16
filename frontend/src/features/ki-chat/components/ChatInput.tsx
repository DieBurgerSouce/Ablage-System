/**
 * ChatInput - Eingabefeld fuer Chat-Nachrichten
 *
 * Unterstuetzt:
 * - Enter zum Senden (Shift+Enter fuer Zeilenumbruch)
 * - Optionaler Kontext-Badge
 * - Lade-/Deaktivierungs-Status
 */

import { useState, useCallback, type KeyboardEvent } from 'react';
import { Send, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';

interface ChatInputProps {
  onSend: (message: string) => void;
  isLoading?: boolean;
  contextLabel?: string;
  disabled?: boolean;
}

export function ChatInput({
  onSend,
  isLoading,
  contextLabel,
  disabled,
}: ChatInputProps) {
  const [value, setValue] = useState('');

  const handleSend = useCallback(() => {
    if (!value.trim() || isLoading || disabled) return;
    onSend(value.trim());
    setValue('');
  }, [value, isLoading, disabled, onSend]);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    },
    [handleSend]
  );

  return (
    <div className="border-t p-3 space-y-2">
      {contextLabel && (
        <Badge variant="outline" className="text-xs">
          Kontext: {contextLabel}
        </Badge>
      )}
      <div className="flex gap-2 items-end">
        <Textarea
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Frage stellen..."
          className="min-h-[44px] max-h-32 resize-none text-sm"
          disabled={isLoading || disabled}
          rows={1}
        />
        <Button
          size="icon"
          onClick={handleSend}
          disabled={!value.trim() || isLoading || disabled}
          className="shrink-0 h-11 w-11"
        >
          {isLoading ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Send className="h-4 w-4" />
          )}
        </Button>
      </div>
      <p className="text-[10px] text-muted-foreground text-center">
        Shift+Enter fuer Zeilenumbruch
      </p>
    </div>
  );
}
