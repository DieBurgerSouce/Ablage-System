/**
 * SearchAutocomplete - Enhanced Search Input with Dropdown
 *
 * Features:
 * - Typeahead Suchvorschlaege
 * - Letzte Suchanfragen
 * - Did-you-mean Korrektur
 * - Kategorisierte Vorschlaege (Tags, Kunden, Dokumenttypen)
 * - Tastatur-Navigation (Arrow keys, Enter, Escape)
 *
 * WCAG 2.1 AA konform mit korrekter ARIA-Auszeichnung.
 */

import { useState, useRef, useCallback, useEffect, useMemo } from 'react';
import {
  Search,
  Clock,
  Tag,
  User,
  FileType,
  XCircle,
  Trash2,
  Lightbulb,
} from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import { useSearchSuggestions, type SearchSuggestion } from '../hooks/use-search-suggestions';
import { useRecentSearches } from '../hooks/use-recent-searches';

// ==================== Types ====================

interface SearchAutocompleteProps {
  /** Aktueller Suchwert */
  value: string;
  /** Callback bei Wertaenderung */
  onChange: (value: string) => void;
  /** Callback bei Suche ausfuehren */
  onSearch: (query: string) => void;
  /** Placeholder-Text */
  placeholder?: string;
  /** Ist das Input aktiv? */
  disabled?: boolean;
  /** Zusaetzliche Klassen */
  className?: string;
}

interface DropdownItem {
  id: string;
  type: 'suggestion' | 'recent' | 'did-you-mean';
  text: string;
  category?: SearchSuggestion['category'];
  count?: number;
}

// ==================== Helper Components ====================

function getCategoryIcon(category?: SearchSuggestion['category']) {
  switch (category) {
    case 'tag':
      return <Tag className="w-4 h-4" />;
    case 'customer':
      return <User className="w-4 h-4" />;
    case 'doctype':
      return <FileType className="w-4 h-4" />;
    default:
      return <Search className="w-4 h-4" />;
  }
}

function getCategoryLabel(category?: SearchSuggestion['category']): string {
  switch (category) {
    case 'tag':
      return 'Tag';
    case 'customer':
      return 'Kunde';
    case 'doctype':
      return 'Typ';
    default:
      return '';
  }
}

// ==================== Component ====================

export function SearchAutocomplete({
  value,
  onChange,
  onSearch,
  placeholder = 'Dokumente durchsuchen...',
  disabled = false,
  className,
}: SearchAutocompleteProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const [isOpen, setIsOpen] = useState(false);
  const [highlightedIndex, setHighlightedIndex] = useState(-1);

  // Hooks fuer Vorschlaege und letzte Suchen
  const { suggestions, didYouMean, isLoading } = useSearchSuggestions(value, {
    enabled: isOpen && value.length >= 2,
  });
  const { recentSearches, addRecentSearch, removeRecentSearch, clearRecentSearches } =
    useRecentSearches();

  // Kombiniere alle Items fuer das Dropdown
  const dropdownItems = useMemo<DropdownItem[]>(() => {
    const items: DropdownItem[] = [];

    // Did-you-mean zuerst
    if (didYouMean) {
      items.push({
        id: 'did-you-mean',
        type: 'did-you-mean',
        text: didYouMean,
      });
    }

    // Suchvorschlaege
    suggestions.forEach((s) => {
      items.push({
        id: s.id,
        type: 'suggestion',
        text: s.text,
        category: s.category,
        count: s.count,
      });
    });

    // Letzte Suchen wenn keine Eingabe
    if (value.length === 0 && recentSearches.length > 0) {
      recentSearches.slice(0, 5).forEach((r) => {
        items.push({
          id: r.id,
          type: 'recent',
          text: r.query,
        });
      });
    }

    return items;
  }, [suggestions, didYouMean, value, recentSearches]);

  // Reset highlight wenn Items sich aendern
  useEffect(() => {
    setHighlightedIndex(-1);
  }, [dropdownItems.length]);

  // Schliesse Dropdown bei Klick ausserhalb
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(event.target as Node) &&
        inputRef.current &&
        !inputRef.current.contains(event.target as Node)
      ) {
        setIsOpen(false);
      }
    }

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Item auswaehlen
  const selectItem = useCallback(
    (item: DropdownItem) => {
      onChange(item.text);
      addRecentSearch(item.text);
      onSearch(item.text);
      setIsOpen(false);
      inputRef.current?.blur();
    },
    [onChange, addRecentSearch, onSearch]
  );

  // Tastatur-Navigation
  const handleKeyDown = useCallback(
    (event: React.KeyboardEvent) => {
      if (!isOpen && event.key !== 'ArrowDown') {
        if (event.key === 'Enter' && value.trim()) {
          addRecentSearch(value);
          onSearch(value);
        }
        return;
      }

      switch (event.key) {
        case 'ArrowDown':
          event.preventDefault();
          if (!isOpen) {
            setIsOpen(true);
          } else {
            setHighlightedIndex((prev) =>
              prev < dropdownItems.length - 1 ? prev + 1 : prev
            );
          }
          break;

        case 'ArrowUp':
          event.preventDefault();
          setHighlightedIndex((prev) => (prev > 0 ? prev - 1 : 0));
          break;

        case 'Enter':
          event.preventDefault();
          if (highlightedIndex >= 0 && dropdownItems[highlightedIndex]) {
            selectItem(dropdownItems[highlightedIndex]);
          } else if (value.trim()) {
            addRecentSearch(value);
            onSearch(value);
            setIsOpen(false);
          }
          break;

        case 'Escape':
          event.preventDefault();
          setIsOpen(false);
          break;

        case 'Tab':
          setIsOpen(false);
          break;
      }
    },
    [
      isOpen,
      value,
      highlightedIndex,
      dropdownItems,
      selectItem,
      addRecentSearch,
      onSearch,
    ]
  );

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    onChange(e.target.value);
    if (!isOpen) setIsOpen(true);
  };

  const handleFocus = () => {
    setIsOpen(true);
  };

  const handleClear = () => {
    onChange('');
    inputRef.current?.focus();
  };

  const hasContent = dropdownItems.length > 0;
  const showDropdown = isOpen && (hasContent || isLoading);

  return (
    <div className={cn('relative', className)}>
      {/* Input */}
      <div className="relative">
        <Search
          className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-muted-foreground pointer-events-none"
          aria-hidden="true"
        />
        <Input
          ref={inputRef}
          type="search"
          value={value}
          onChange={handleInputChange}
          onFocus={handleFocus}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={disabled}
          className="pl-10 pr-10 h-14 text-lg"
          role="combobox"
          aria-expanded={showDropdown}
          aria-haspopup="listbox"
          aria-controls="search-autocomplete-dropdown"
          aria-autocomplete="list"
          autoComplete="off"
        />
        {value && (
          <Button
            variant="ghost"
            size="icon"
            className="absolute right-2 top-1/2 -translate-y-1/2 h-8 w-8"
            onClick={handleClear}
            type="button"
            aria-label="Suche loeschen"
          >
            <XCircle className="w-4 h-4" />
          </Button>
        )}
      </div>

      {/* Dropdown */}
      {showDropdown && (
        <div
          ref={dropdownRef}
          id="search-autocomplete-dropdown"
          role="listbox"
          className="absolute z-50 top-full mt-1 w-full bg-popover border rounded-lg shadow-lg overflow-hidden"
        >
          {isLoading && value.length >= 2 && (
            <div className="px-4 py-3 text-sm text-muted-foreground">
              Lade Vorschlaege...
            </div>
          )}

          {/* Letzte Suchen Header */}
          {value.length === 0 && recentSearches.length > 0 && (
            <div className="flex items-center justify-between px-4 py-2 border-b bg-muted/30">
              <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Letzte Suchen
              </span>
              <Button
                variant="ghost"
                size="sm"
                className="h-6 px-2 text-xs"
                onClick={(e) => {
                  e.stopPropagation();
                  clearRecentSearches();
                }}
              >
                <Trash2 className="w-3 h-3 mr-1" />
                Alle loeschen
              </Button>
            </div>
          )}

          {/* Items */}
          <div className="max-h-80 overflow-y-auto">
            {dropdownItems.map((item, index) => (
              <div
                key={item.id}
                role="option"
                aria-selected={highlightedIndex === index}
                className={cn(
                  'flex items-center gap-3 px-4 py-2.5 cursor-pointer transition-colors',
                  highlightedIndex === index && 'bg-accent',
                  item.type === 'did-you-mean' && 'bg-amber-500/10 border-b'
                )}
                onClick={() => selectItem(item)}
                onMouseEnter={() => setHighlightedIndex(index)}
              >
                {/* Icon */}
                <span
                  className={cn(
                    'flex-shrink-0 text-muted-foreground',
                    item.type === 'did-you-mean' && 'text-amber-600'
                  )}
                >
                  {item.type === 'recent' && <Clock className="w-4 h-4" />}
                  {item.type === 'did-you-mean' && <Lightbulb className="w-4 h-4" />}
                  {item.type === 'suggestion' && getCategoryIcon(item.category)}
                </span>

                {/* Text */}
                <span className="flex-1 truncate">
                  {item.type === 'did-you-mean' && (
                    <span className="text-muted-foreground mr-1">Meinten Sie:</span>
                  )}
                  <span className={cn(item.type === 'did-you-mean' && 'font-medium')}>
                    {item.text}
                  </span>
                </span>

                {/* Category Badge / Count */}
                {item.type === 'suggestion' && item.category && (
                  <Badge variant="secondary" className="text-xs">
                    {getCategoryLabel(item.category)}
                    {item.count && ` (${item.count})`}
                  </Badge>
                )}

                {/* Remove Button fuer Recent */}
                {item.type === 'recent' && (
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-6 w-6 opacity-0 group-hover:opacity-100 hover:opacity-100"
                    onClick={(e) => {
                      e.stopPropagation();
                      removeRecentSearch(item.id);
                    }}
                    aria-label="Aus letzten Suchen entfernen"
                  >
                    <XCircle className="w-3.5 h-3.5" />
                  </Button>
                )}
              </div>
            ))}
          </div>

          {/* Empty State */}
          {!isLoading && dropdownItems.length === 0 && value.length >= 2 && (
            <div className="px-4 py-6 text-center text-sm text-muted-foreground">
              Keine Vorschlaege gefunden
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default SearchAutocomplete;
