/**
 * MentionInput - Eingabefeld mit @mention Unterstützung
 *
 * Features:
 * - @user Autocomplete
 * - Inline-Vorschläge beim Tippen
 * - Keyboard-Navigation
 * - Formatierten Text mit Mentions
 */

import { useState, useRef, useCallback, useEffect, type KeyboardEvent } from 'react';
import { AtSign, Send, Loader2 } from 'lucide-react';
import { Textarea } from '@/components/ui/textarea';
import { Button } from '@/components/ui/button';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { cn } from '@/lib/utils';
import type { UserSuggestion } from '../types/collaboration.types';
import { useUserSearch } from '../hooks/use-user-search';

interface MentionInputProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  placeholder?: string;
  disabled?: boolean;
  isSubmitting?: boolean;
  mentions: { userId: string; userName: string }[];
  onMentionsChange: (mentions: { userId: string; userName: string }[]) => void;
}

function getInitials(name: string): string {
  return name
    .split(' ')
    .map((n) => n[0])
    .join('')
    .toUpperCase()
    .slice(0, 2);
}

export function MentionInput({
  value,
  onChange,
  onSubmit,
  placeholder = 'Kommentar schreiben... (@erwähnen)',
  disabled = false,
  isSubmitting = false,
  mentions,
  onMentionsChange,
}: MentionInputProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [suggestionQuery, setSuggestionQuery] = useState('');
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [cursorPosition, setCursorPosition] = useState(0);

  // API-basierte Benutzersuche mit Debounce
  const { users: filteredSuggestions, isLoading: isSearching } = useUserSearch(suggestionQuery);

  // Detect @ mentions
  const detectMentionTrigger = useCallback((text: string, cursorPos: number) => {
    // Find the last @ before cursor
    const textBeforeCursor = text.slice(0, cursorPos);
    const lastAtIndex = textBeforeCursor.lastIndexOf('@');

    if (lastAtIndex === -1) {
      setShowSuggestions(false);
      return;
    }

    // Check if there's a space between @ and cursor
    const textAfterAt = textBeforeCursor.slice(lastAtIndex + 1);
    if (textAfterAt.includes(' ') || textAfterAt.includes('\n')) {
      setShowSuggestions(false);
      return;
    }

    setSuggestionQuery(textAfterAt);
    setShowSuggestions(true);
    setSelectedIndex(0);
  }, []);

  // Handle input change
  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      const newValue = e.target.value;
      const cursorPos = e.target.selectionStart || 0;
      onChange(newValue);
      setCursorPosition(cursorPos);
      detectMentionTrigger(newValue, cursorPos);
    },
    [onChange, detectMentionTrigger]
  );

  // Insert mention into text
  const insertMention = useCallback(
    (user: UserSuggestion) => {
      const textBeforeCursor = value.slice(0, cursorPosition);
      const textAfterCursor = value.slice(cursorPosition);
      const lastAtIndex = textBeforeCursor.lastIndexOf('@');

      const newText =
        textBeforeCursor.slice(0, lastAtIndex) +
        `@${user.name} ` +
        textAfterCursor;

      onChange(newText);
      onMentionsChange([...mentions, { userId: user.id, userName: user.name }]);
      setShowSuggestions(false);

      // Focus textarea
      setTimeout(() => {
        textareaRef.current?.focus();
      }, 0);
    },
    [value, cursorPosition, mentions, onChange, onMentionsChange]
  );

  // Handle keyboard navigation
  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      if (!showSuggestions) {
        // Submit on Ctrl/Cmd + Enter
        if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
          e.preventDefault();
          onSubmit();
        }
        return;
      }

      switch (e.key) {
        case 'ArrowDown':
          e.preventDefault();
          setSelectedIndex((prev) =>
            prev < filteredSuggestions.length - 1 ? prev + 1 : prev
          );
          break;
        case 'ArrowUp':
          e.preventDefault();
          setSelectedIndex((prev) => (prev > 0 ? prev - 1 : 0));
          break;
        case 'Enter':
        case 'Tab':
          e.preventDefault();
          if (filteredSuggestions[selectedIndex]) {
            insertMention(filteredSuggestions[selectedIndex]);
          }
          break;
        case 'Escape':
          e.preventDefault();
          setShowSuggestions(false);
          break;
      }
    },
    [showSuggestions, filteredSuggestions, selectedIndex, onSubmit, insertMention]
  );

  // Click outside to close
  useEffect(() => {
    const handleClickOutside = () => setShowSuggestions(false);
    if (showSuggestions) {
      document.addEventListener('click', handleClickOutside);
      return () => document.removeEventListener('click', handleClickOutside);
    }
  }, [showSuggestions]);

  return (
    <div className="relative">
      {/* Textarea */}
      <div className="relative">
        <Textarea
          ref={textareaRef}
          value={value}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={disabled || isSubmitting}
          className="min-h-[80px] pr-12 resize-none"
          rows={3}
        />

        {/* Submit Button */}
        <Button
          type="button"
          size="icon"
          className="absolute bottom-2 right-2"
          onClick={onSubmit}
          disabled={disabled || isSubmitting || !value.trim()}
        >
          {isSubmitting ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Send className="h-4 w-4" />
          )}
        </Button>
      </div>

      {/* Mention Suggestions */}
      {showSuggestions && suggestionQuery.length >= 2 && (
        <div
          className="absolute left-0 right-0 mt-1 bg-popover border rounded-md shadow-lg z-50 max-h-48 overflow-auto"
          onClick={(e) => e.stopPropagation()}
        >
          <div className="p-1">
            <div className="px-2 py-1.5 text-xs font-medium text-muted-foreground flex items-center gap-1">
              <AtSign className="h-3 w-3" />
              Benutzer erwähnen
            </div>
            {isSearching && (
              <div className="flex items-center gap-2 px-2 py-3 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                Suche...
              </div>
            )}
            {!isSearching && filteredSuggestions.length === 0 && (
              <div className="px-2 py-3 text-sm text-muted-foreground text-center">
                Keine Benutzer gefunden
              </div>
            )}
            {!isSearching && filteredSuggestions.map((user, index) => (
              <button
                key={user.id}
                type="button"
                className={cn(
                  'w-full flex items-center gap-3 px-2 py-2 rounded-md text-left text-sm transition-colors',
                  index === selectedIndex
                    ? 'bg-accent text-accent-foreground'
                    : 'hover:bg-muted'
                )}
                onClick={() => insertMention(user)}
              >
                <Avatar className="h-7 w-7">
                  <AvatarImage src={user.avatar} alt={user.name} />
                  <AvatarFallback className="text-xs">
                    {getInitials(user.name)}
                  </AvatarFallback>
                </Avatar>
                <div className="flex-1 min-w-0">
                  <div className="font-medium truncate">{user.name}</div>
                  <div className="text-xs text-muted-foreground truncate">
                    {user.department || user.email}
                  </div>
                </div>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Hint */}
      <div className="flex items-center justify-between mt-1.5 text-xs text-muted-foreground">
        <span>@ zum Erwähnen, Ctrl+Enter zum Senden</span>
        {mentions.length > 0 && (
          <span>{mentions.length} Erwähnung{mentions.length > 1 ? 'en' : ''}</span>
        )}
      </div>
    </div>
  );
}

export default MentionInput;
