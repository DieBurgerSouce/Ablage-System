/**
 * TypingIndicator - Zeigt "Max tippt..." mit animierten Punkten
 */

import { cn } from '@/lib/utils';

interface TypingIndicatorProps {
  typingUsers: Array<{ user_id: string }>;
  className?: string;
}

export function TypingIndicator({ typingUsers, className }: TypingIndicatorProps) {
  if (typingUsers.length === 0) return null;

  let text: string;

  if (typingUsers.length === 1) {
    text = 'Jemand tippt';
  } else if (typingUsers.length === 2) {
    text = '2 Personen tippen';
  } else {
    text = `${typingUsers.length} Personen tippen`;
  }

  return (
    <div className={cn('flex items-center gap-1.5 text-xs text-muted-foreground', className)}>
      <span>{text}</span>
      <span className="inline-flex gap-0.5">
        <span className="w-1 h-1 bg-muted-foreground rounded-full animate-bounce [animation-delay:0ms]" />
        <span className="w-1 h-1 bg-muted-foreground rounded-full animate-bounce [animation-delay:150ms]" />
        <span className="w-1 h-1 bg-muted-foreground rounded-full animate-bounce [animation-delay:300ms]" />
      </span>
    </div>
  );
}
