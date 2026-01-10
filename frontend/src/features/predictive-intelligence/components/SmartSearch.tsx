/**
 * SmartSearch Component.
 *
 * Semantische Suche mit KI-Unterstützung:
 * - Natürliche Sprachverarbeitung
 * - Kontext-basierte Ergebnisse
 * - Such-Vorschläge
 * - Filter nach Entitätstyp
 */

import React, { useState, useCallback, useEffect, useRef } from 'react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from '@/components/ui/command';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Search,
  FileText,
  Home,
  Car,
  Shield,
  CreditCard,
  Calendar,
  Clock,
  Sparkles,
  Filter,
  X,
  ArrowRight,
} from 'lucide-react';
import { useDebounce } from '@/hooks/useDebounce';

export type EntityType =
  | 'document'
  | 'property'
  | 'vehicle'
  | 'insurance'
  | 'finance'
  | 'deadline';

export interface SearchResult {
  id: string;
  type: EntityType;
  title: string;
  subtitle: string;
  snippet?: string;
  score: number;
  highlightedTerms?: string[];
  metadata?: Record<string, unknown>;
  url?: string;
}

export interface SearchSuggestion {
  query: string;
  type: 'recent' | 'suggested' | 'popular';
}

interface SmartSearchProps {
  onSearch: (query: string, filters?: EntityType[]) => Promise<SearchResult[]>;
  onSuggestions?: (query: string) => Promise<SearchSuggestion[]>;
  onResultClick?: (result: SearchResult) => void;
  placeholder?: string;
  showFilters?: boolean;
  maxResults?: number;
  isSemanticEnabled?: boolean;
}

const getEntityIcon = (type: EntityType) => {
  switch (type) {
    case 'document':
      return <FileText className="h-4 w-4" />;
    case 'property':
      return <Home className="h-4 w-4" />;
    case 'vehicle':
      return <Car className="h-4 w-4" />;
    case 'insurance':
      return <Shield className="h-4 w-4" />;
    case 'finance':
      return <CreditCard className="h-4 w-4" />;
    case 'deadline':
      return <Calendar className="h-4 w-4" />;
    default:
      return <FileText className="h-4 w-4" />;
  }
};

const getEntityLabel = (type: EntityType): string => {
  switch (type) {
    case 'document':
      return 'Dokument';
    case 'property':
      return 'Immobilie';
    case 'vehicle':
      return 'Fahrzeug';
    case 'insurance':
      return 'Versicherung';
    case 'finance':
      return 'Finanzen';
    case 'deadline':
      return 'Frist';
    default:
      return 'Unbekannt';
  }
};

const getEntityColor = (type: EntityType): string => {
  switch (type) {
    case 'document':
      return 'bg-blue-500';
    case 'property':
      return 'bg-green-500';
    case 'vehicle':
      return 'bg-purple-500';
    case 'insurance':
      return 'bg-yellow-500';
    case 'finance':
      return 'bg-emerald-500';
    case 'deadline':
      return 'bg-red-500';
    default:
      return 'bg-gray-500';
  }
};

export const SmartSearch: React.FC<SmartSearchProps> = ({
  onSearch,
  onSuggestions,
  onResultClick,
  placeholder = 'Suchen Sie nach Dokumenten, Verträgen, Fristen...',
  showFilters = true,
  maxResults = 10,
  isSemanticEnabled = true,
}) => {
  const [query, setQuery] = useState('');
  const [isOpen, setIsOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [results, setResults] = useState<SearchResult[]>([]);
  const [suggestions, setSuggestions] = useState<SearchSuggestion[]>([]);
  const [activeFilters, setActiveFilters] = useState<EntityType[]>([]);
  const [searchTime, setSearchTime] = useState<number | null>(null);

  const inputRef = useRef<HTMLInputElement>(null);
  const debouncedQuery = useDebounce(query, 300);

  // Suche ausführen
  const executeSearch = useCallback(async () => {
    if (!debouncedQuery.trim()) {
      setResults([]);
      setSearchTime(null);
      return;
    }

    setIsLoading(true);
    const startTime = performance.now();

    try {
      const searchResults = await onSearch(
        debouncedQuery,
        activeFilters.length > 0 ? activeFilters : undefined
      );
      setResults(searchResults.slice(0, maxResults));
      setSearchTime(performance.now() - startTime);
    } catch (error) {
      console.error('Suchfehler:', error);
      setResults([]);
    } finally {
      setIsLoading(false);
    }
  }, [debouncedQuery, activeFilters, onSearch, maxResults]);

  // Vorschläge laden
  const loadSuggestions = useCallback(async () => {
    if (!onSuggestions || !query.trim() || query.length < 2) {
      setSuggestions([]);
      return;
    }

    try {
      const suggestionsData = await onSuggestions(query);
      setSuggestions(suggestionsData);
    } catch (error) {
      console.error('Fehler beim Laden der Vorschläge:', error);
      setSuggestions([]);
    }
  }, [query, onSuggestions]);

  // Effekte
  useEffect(() => {
    executeSearch();
  }, [executeSearch]);

  useEffect(() => {
    loadSuggestions();
  }, [loadSuggestions]);

  // Filter toggle
  const toggleFilter = (type: EntityType) => {
    setActiveFilters((prev) =>
      prev.includes(type)
        ? prev.filter((t) => t !== type)
        : [...prev, type]
    );
  };

  // Clear all
  const clearSearch = () => {
    setQuery('');
    setResults([]);
    setSuggestions([]);
    setActiveFilters([]);
    setSearchTime(null);
    inputRef.current?.focus();
  };

  // Handle result click
  const handleResultClick = (result: SearchResult) => {
    setIsOpen(false);
    onResultClick?.(result);
  };

  // Handle suggestion click
  const handleSuggestionClick = (suggestion: SearchSuggestion) => {
    setQuery(suggestion.query);
  };

  const allEntityTypes: EntityType[] = [
    'document',
    'property',
    'vehicle',
    'insurance',
    'finance',
    'deadline',
  ];

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="flex items-center gap-2">
              <Search className="h-5 w-5" />
              Intelligente Suche
              {isSemanticEnabled && (
                <Badge variant="secondary" className="ml-2">
                  <Sparkles className="h-3 w-3 mr-1" />
                  KI
                </Badge>
              )}
            </CardTitle>
            <CardDescription>
              Durchsuchen Sie alle Ihre Dokumente und Daten mit natürlicher Sprache
            </CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          {/* Suchfeld */}
          <div className="relative">
            <Popover open={isOpen && (results.length > 0 || suggestions.length > 0)} onOpenChange={setIsOpen}>
              <PopoverTrigger asChild>
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <Input
                    ref={inputRef}
                    value={query}
                    onChange={(e) => {
                      setQuery(e.target.value);
                      setIsOpen(true);
                    }}
                    onFocus={() => setIsOpen(true)}
                    placeholder={placeholder}
                    className="pl-10 pr-10"
                  />
                  {query && (
                    <Button
                      variant="ghost"
                      size="sm"
                      className="absolute right-1 top-1/2 -translate-y-1/2 h-7 w-7 p-0"
                      onClick={clearSearch}
                    >
                      <X className="h-4 w-4" />
                    </Button>
                  )}
                </div>
              </PopoverTrigger>
              <PopoverContent
                className="w-[var(--radix-popover-trigger-width)] p-0"
                align="start"
                onOpenAutoFocus={(e) => e.preventDefault()}
              >
                <Command>
                  <CommandList>
                    {/* Vorschläge */}
                    {suggestions.length > 0 && !results.length && (
                      <CommandGroup heading="Vorschläge">
                        {suggestions.map((suggestion, index) => (
                          <CommandItem
                            key={index}
                            onSelect={() => handleSuggestionClick(suggestion)}
                          >
                            {suggestion.type === 'recent' && (
                              <Clock className="h-4 w-4 mr-2 text-muted-foreground" />
                            )}
                            {suggestion.type === 'suggested' && (
                              <Sparkles className="h-4 w-4 mr-2 text-yellow-500" />
                            )}
                            {suggestion.query}
                          </CommandItem>
                        ))}
                      </CommandGroup>
                    )}

                    {/* Ergebnisse */}
                    {results.length > 0 && (
                      <CommandGroup heading={`${results.length} Ergebnisse`}>
                        {results.map((result) => (
                          <CommandItem
                            key={result.id}
                            onSelect={() => handleResultClick(result)}
                            className="flex items-start gap-3 p-3"
                          >
                            <div className={`p-2 rounded-md ${getEntityColor(result.type)} text-white flex-shrink-0`}>
                              {getEntityIcon(result.type)}
                            </div>
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2">
                                <span className="font-medium truncate">
                                  {result.title}
                                </span>
                                <Badge variant="outline" className="text-xs">
                                  {getEntityLabel(result.type)}
                                </Badge>
                              </div>
                              <p className="text-sm text-muted-foreground truncate">
                                {result.subtitle}
                              </p>
                              {result.snippet && (
                                <p className="text-xs text-muted-foreground mt-1 line-clamp-2">
                                  {result.snippet}
                                </p>
                              )}
                            </div>
                            <ArrowRight className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                          </CommandItem>
                        ))}
                      </CommandGroup>
                    )}

                    {/* Keine Ergebnisse */}
                    {query && !isLoading && results.length === 0 && suggestions.length === 0 && (
                      <CommandEmpty>
                        <div className="py-6 text-center">
                          <Search className="h-10 w-10 text-muted-foreground mx-auto mb-3" />
                          <p className="text-sm text-muted-foreground">
                            Keine Ergebnisse für "{query}"
                          </p>
                          <p className="text-xs text-muted-foreground mt-1">
                            Versuchen Sie andere Suchbegriffe
                          </p>
                        </div>
                      </CommandEmpty>
                    )}

                    {/* Loading */}
                    {isLoading && (
                      <div className="p-4 space-y-3">
                        {[...Array(3)].map((_, i) => (
                          <div key={i} className="flex items-center gap-3">
                            <Skeleton className="h-10 w-10 rounded-md" />
                            <div className="flex-1 space-y-2">
                              <Skeleton className="h-4 w-3/4" />
                              <Skeleton className="h-3 w-1/2" />
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </CommandList>
                </Command>
              </PopoverContent>
            </Popover>
          </div>

          {/* Filter */}
          {showFilters && (
            <div className="flex flex-wrap gap-2">
              <span className="text-sm text-muted-foreground flex items-center gap-1">
                <Filter className="h-4 w-4" />
                Filter:
              </span>
              {allEntityTypes.map((type) => (
                <Badge
                  key={type}
                  variant={activeFilters.includes(type) ? 'default' : 'outline'}
                  className="cursor-pointer"
                  onClick={() => toggleFilter(type)}
                >
                  {getEntityIcon(type)}
                  <span className="ml-1">{getEntityLabel(type)}</span>
                </Badge>
              ))}
              {activeFilters.length > 0 && (
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-6 px-2 text-xs"
                  onClick={() => setActiveFilters([])}
                >
                  Alle entfernen
                </Button>
              )}
            </div>
          )}

          {/* Suchstatistik */}
          {searchTime !== null && results.length > 0 && (
            <p className="text-xs text-muted-foreground">
              {results.length} Ergebnisse in {searchTime.toFixed(0)} ms
              {isSemanticEnabled && ' (semantische Suche)'}
            </p>
          )}
        </div>
      </CardContent>
    </Card>
  );
};

export default SmartSearch;
