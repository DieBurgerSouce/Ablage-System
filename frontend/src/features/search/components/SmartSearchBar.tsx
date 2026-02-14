/**
 * SmartSearchBar - NLQ-powered Search with Entity Linking
 *
 * Features:
 * - Natural Language Query (NLQ) mit automatischer Erkennung
 * - Keyword-Suche mit Fallback
 * - As-you-type Autocomplete
 * - Entity-Linking (Kunden, Lieferanten)
 * - Query-Interpretation Display
 * - Facet-basierte Filter (Sidebar)
 * - Relevanz-Scores
 * - Query-Suggestions (Ähnliche Suchen, Verfeinern)
 *
 * @example
 * ```tsx
 * <SmartSearchBar onResultClick={(docId) => navigate(`/documents/${docId}`)} />
 * ```
 */

import { useState, useCallback, useEffect } from 'react';
import DOMPurify from 'dompurify';
import {
    Search,
    Sparkles,
    FileText,
    Filter,
    X,
    ChevronDown,
    ChevronUp,
    Calendar,
    Building2,
    DollarSign,
    FileType,
    CheckCircle2,
    TrendingUp,
    Lightbulb,
    Target,
} from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Separator } from '@/components/ui/separator';
import { cn } from '@/lib/utils';
import { motion, AnimatePresence } from 'framer-motion';
import { motionTokens } from '@/lib/motion-tokens';
import { useSmartSearch } from '../hooks/useSmartSearch';
import { useSmartAutocomplete } from '../hooks/useSmartAutocomplete';
import type { SmartSearchFilters, EntityMatch, QuerySuggestion } from '../api/smart-search-api';

// ==================== Types ====================

interface SmartSearchBarProps {
    /** Callback bei Klick auf ein Suchergebnis */
    onResultClick?: (documentId: string) => void;
    /** Initiale Filter */
    initialFilters?: SmartSearchFilters;
    /** Zusätzliche CSS-Klassen */
    className?: string;
}

// ==================== Helper Components ====================

const MotionDiv = motion.div;

function SearchModeIndicator({ mode }: { mode: 'nlq' | 'keyword' }) {
    return (
        <Badge
            variant={mode === 'nlq' ? 'default' : 'secondary'}
            className={cn(
                'text-xs',
                mode === 'nlq' ? 'bg-gradient-to-r from-blue-500 to-purple-500' : 'bg-muted'
            )}
        >
            {mode === 'nlq' ? (
                <>
                    <Sparkles className="w-3 h-3 mr-1" />
                    NLQ
                </>
            ) : (
                <>
                    <FileText className="w-3 h-3 mr-1" />
                    Keyword
                </>
            )}
        </Badge>
    );
}

function EntityMatchCard({ entity }: { entity: EntityMatch }) {
    return (
        <div className="flex items-center gap-2 p-2 rounded-md bg-muted/50 border">
            <Building2 className="w-4 h-4 text-muted-foreground" />
            <div className="flex-1 min-w-0">
                <div className="text-sm font-medium truncate">{entity.entity_name}</div>
                <div className="text-xs text-muted-foreground">
                    {entity.entity_type === 'customer' ? 'Kunde' : 'Lieferant'}
                    {entity.customer_number && ` • ${entity.customer_number}`}
                    {entity.supplier_number && ` • ${entity.supplier_number}`}
                </div>
            </div>
            <Badge variant="outline" className="text-xs">
                {Math.round(entity.match_confidence * 100)}%
            </Badge>
        </div>
    );
}

function SuggestionCard({ suggestion, onClick }: { suggestion: QuerySuggestion; onClick: () => void }) {
    const icons = {
        refine: Target,
        similar: TrendingUp,
        related: Lightbulb,
    };
    const Icon = icons[suggestion.suggestion_type] || Lightbulb;

    return (
        <Button
            variant="outline"
            className="justify-start text-left h-auto py-2 px-3"
            onClick={onClick}
        >
            <Icon className="w-4 h-4 mr-2 flex-shrink-0 text-muted-foreground" />
            <div className="flex-1 min-w-0">
                <div className="text-sm font-medium truncate">{suggestion.text}</div>
                {suggestion.description && (
                    <div className="text-xs text-muted-foreground truncate">{suggestion.description}</div>
                )}
            </div>
        </Button>
    );
}

// ==================== Main Component ====================

export function SmartSearchBar({ onResultClick, initialFilters, className }: SmartSearchBarProps) {
    // State
    const [query, setQuery] = useState('');
    const [filters, setFilters] = useState<SmartSearchFilters>(initialFilters || {});
    const [showFilters, setShowFilters] = useState(false);
    const [showAutocomplete, setShowAutocomplete] = useState(false);
    const [highlightedIndex, setHighlightedIndex] = useState(-1);

    // Hooks
    const { data, isLoading, error } = useSmartSearch({
        query,
        filters,
        enabled: query.length >= 2,
    });

    const { suggestions: autocompleteSuggestions, isLoading: isAutocompleteLoading } =
        useSmartAutocomplete(query, {
            enabled: showAutocomplete && query.length >= 2,
        });

    // Reset highlighted index when autocomplete results change
    useEffect(() => {
        setHighlightedIndex(-1);
    }, [autocompleteSuggestions.length]);

    // Handlers
    const handleSearch = useCallback((searchQuery: string) => {
        setQuery(searchQuery);
        setShowAutocomplete(false);
    }, []);

    const handleAutocompleteSelect = useCallback(
        (text: string) => {
            setQuery(text);
            setShowAutocomplete(false);
        },
        []
    );

    const handleKeyDown = useCallback(
        (e: React.KeyboardEvent) => {
            if (!showAutocomplete || autocompleteSuggestions.length === 0) {
                if (e.key === 'Enter') {
                    handleSearch(query);
                }
                return;
            }

            switch (e.key) {
                case 'ArrowDown':
                    e.preventDefault();
                    setHighlightedIndex((prev) =>
                        prev < autocompleteSuggestions.length - 1 ? prev + 1 : prev
                    );
                    break;
                case 'ArrowUp':
                    e.preventDefault();
                    setHighlightedIndex((prev) => (prev > 0 ? prev - 1 : 0));
                    break;
                case 'Enter':
                    e.preventDefault();
                    if (highlightedIndex >= 0 && autocompleteSuggestions[highlightedIndex]) {
                        handleAutocompleteSelect(autocompleteSuggestions[highlightedIndex].text);
                    } else {
                        handleSearch(query);
                    }
                    break;
                case 'Escape':
                    e.preventDefault();
                    setShowAutocomplete(false);
                    break;
            }
        },
        [showAutocomplete, autocompleteSuggestions, highlightedIndex, query, handleSearch, handleAutocompleteSelect]
    );

    const handleClearFilters = () => {
        setFilters({});
    };

    const activeFilterCount =
        (filters.document_types?.length || 0) +
        (filters.status?.length || 0) +
        (filters.entity_id ? 1 : 0) +
        (filters.date_from ? 1 : 0) +
        (filters.date_to ? 1 : 0) +
        (filters.amount_min ? 1 : 0) +
        (filters.amount_max ? 1 : 0);

    return (
        <div className={cn('space-y-6 w-full max-w-7xl mx-auto', className)}>
            {/* Hero Search Bar */}
            <MotionDiv
                initial={{ opacity: 0, y: -20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={motionTokens.spring.gentle}
                className="space-y-4"
            >
                <div className="relative group">
                    {/* Glow effect */}
                    <div
                        className="absolute inset-0 bg-gradient-to-r from-primary/20 to-accent/20 rounded-2xl blur-2xl opacity-0 group-hover:opacity-100 transition-opacity duration-500"
                        aria-hidden="true"
                    />

                    {/* Search Input */}
                    <div className="relative flex items-center bg-background/80 backdrop-blur-xl border-2 rounded-2xl shadow-lg focus-within:shadow-xl focus-within:border-primary/50 transition-all overflow-hidden">
                        <Search className="absolute left-5 w-6 h-6 text-muted-foreground pointer-events-none" />
                        <Input
                            type="search"
                            value={query}
                            onChange={(e) => {
                                setQuery(e.target.value);
                                setShowAutocomplete(true);
                            }}
                            onFocus={() => setShowAutocomplete(true)}
                            onKeyDown={handleKeyDown}
                            placeholder="Suche nach Dokumenten, Kunden, Rechnungen..."
                            className="border-none shadow-none focus-visible:ring-0 bg-transparent pl-14 pr-4 h-16 text-lg"
                            autoComplete="off"
                        />
                        {query && (
                            <Button
                                variant="ghost"
                                size="icon"
                                className="mr-2"
                                onClick={() => {
                                    setQuery('');
                                    setShowAutocomplete(false);
                                }}
                            >
                                <X className="w-4 h-4" />
                            </Button>
                        )}
                    </div>

                    {/* Autocomplete Dropdown */}
                    <AnimatePresence>
                        {showAutocomplete && query.length >= 2 && (
                            <MotionDiv
                                initial={{ opacity: 0, y: -10 }}
                                animate={{ opacity: 1, y: 0 }}
                                exit={{ opacity: 0, y: -10 }}
                                transition={motionTokens.spring.gentle}
                                className="absolute z-50 top-full mt-2 w-full bg-popover border rounded-xl shadow-lg overflow-hidden"
                            >
                                {isAutocompleteLoading ? (
                                    <div className="p-4 space-y-2">
                                        <Skeleton className="h-10 w-full" />
                                        <Skeleton className="h-10 w-full" />
                                        <Skeleton className="h-10 w-full" />
                                    </div>
                                ) : autocompleteSuggestions.length > 0 ? (
                                    <div className="max-h-96 overflow-y-auto">
                                        {autocompleteSuggestions.map((suggestion, index) => (
                                            <div
                                                key={`${suggestion.type}-${index}`}
                                                className={cn(
                                                    'flex items-center gap-3 px-4 py-3 cursor-pointer transition-colors',
                                                    highlightedIndex === index && 'bg-accent'
                                                )}
                                                onClick={() => handleAutocompleteSelect(suggestion.text)}
                                                onMouseEnter={() => setHighlightedIndex(index)}
                                            >
                                                {suggestion.type === 'entity' && <Building2 className="w-4 h-4 text-muted-foreground" />}
                                                {suggestion.type === 'document_type' && <FileType className="w-4 h-4 text-muted-foreground" />}
                                                {suggestion.type === 'recent' && <Search className="w-4 h-4 text-muted-foreground" />}
                                                {suggestion.type === 'suggestion' && <Lightbulb className="w-4 h-4 text-muted-foreground" />}
                                                <span className="flex-1 truncate">{suggestion.text}</span>
                                                {suggestion.confidence && (
                                                    <Badge variant="outline" className="text-xs">
                                                        {Math.round(suggestion.confidence * 100)}%
                                                    </Badge>
                                                )}
                                            </div>
                                        ))}
                                    </div>
                                ) : (
                                    <div className="p-4 text-sm text-muted-foreground text-center">
                                        Keine Vorschläge gefunden
                                    </div>
                                )}
                            </MotionDiv>
                        )}
                    </AnimatePresence>
                </div>

                {/* Filter Toggle */}
                <div className="flex items-center justify-between">
                    <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setShowFilters(!showFilters)}
                        className="gap-2"
                    >
                        <Filter className="w-4 h-4" />
                        Filter
                        {activeFilterCount > 0 && (
                            <Badge variant="secondary" className="ml-1">
                                {activeFilterCount}
                            </Badge>
                        )}
                        {showFilters ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                    </Button>
                    {activeFilterCount > 0 && (
                        <Button variant="ghost" size="sm" onClick={handleClearFilters}>
                            Filter zurücksetzen
                        </Button>
                    )}
                </div>

                {/* Filter Panel */}
                <AnimatePresence>
                    {showFilters && (
                        <MotionDiv
                            initial={{ opacity: 0, height: 0 }}
                            animate={{ opacity: 1, height: 'auto' }}
                            exit={{ opacity: 0, height: 0 }}
                            transition={motionTokens.spring.gentle}
                            className="overflow-hidden"
                        >
                            <Card>
                                <CardContent className="pt-6">
                                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                                        {/* Document Types */}
                                        <div className="space-y-2">
                                            <label className="text-sm font-medium flex items-center gap-2">
                                                <FileType className="w-4 h-4" />
                                                Dokumenttyp
                                            </label>
                                            {/* Simplified - in production use Select component */}
                                            <div className="text-xs text-muted-foreground">
                                                Rechnung, Bestellung, Lieferschein, etc.
                                            </div>
                                        </div>

                                        {/* Status */}
                                        <div className="space-y-2">
                                            <label className="text-sm font-medium flex items-center gap-2">
                                                <CheckCircle2 className="w-4 h-4" />
                                                Status
                                            </label>
                                            <div className="text-xs text-muted-foreground">
                                                Offen, Bezahlt, Überfällig, etc.
                                            </div>
                                        </div>

                                        {/* Date Range */}
                                        <div className="space-y-2">
                                            <label className="text-sm font-medium flex items-center gap-2">
                                                <Calendar className="w-4 h-4" />
                                                Zeitraum
                                            </label>
                                            <div className="text-xs text-muted-foreground">
                                                Von - Bis Datum
                                            </div>
                                        </div>
                                    </div>
                                </CardContent>
                            </Card>
                        </MotionDiv>
                    )}
                </AnimatePresence>
            </MotionDiv>

            {/* Results Section */}
            {query.length >= 2 && (
                <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
                    {/* Main Results (3/4 width) */}
                    <div className="lg:col-span-3 space-y-4">
                        {/* Query Interpretation */}
                        {data?.interpretation && (
                            <Card className="bg-gradient-to-r from-blue-500/10 to-purple-500/10 border-blue-500/20">
                                <CardContent className="pt-6">
                                    <div className="flex items-start gap-3">
                                        <Sparkles className="w-5 h-5 text-blue-500 mt-0.5" />
                                        <div className="flex-1 space-y-2">
                                            <div className="flex items-center gap-2">
                                                <span className="text-sm font-medium">Ich suche nach:</span>
                                                <SearchModeIndicator mode={data.interpretation.search_mode} />
                                            </div>
                                            <p className="text-lg font-semibold">{data.interpretation.interpreted_as}</p>
                                            {data.interpretation.confidence && (
                                                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                                                    <span>Konfidenz:</span>
                                                    <Badge variant="outline" className="text-xs">
                                                        {Math.round(data.interpretation.confidence * 100)}%
                                                    </Badge>
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                </CardContent>
                            </Card>
                        )}

                        {/* Entity Matches */}
                        {data?.entities && data.entities.length > 0 && (
                            <Card>
                                <CardHeader>
                                    <CardTitle className="text-base flex items-center gap-2">
                                        <Building2 className="w-4 h-4" />
                                        Gefundene Entitäten
                                    </CardTitle>
                                </CardHeader>
                                <CardContent>
                                    <div className="space-y-2">
                                        {data.entities.map((entity) => (
                                            <EntityMatchCard key={entity.entity_id} entity={entity} />
                                        ))}
                                    </div>
                                </CardContent>
                            </Card>
                        )}

                        {/* Loading State */}
                        {isLoading && (
                            <div className="space-y-4">
                                <Skeleton className="h-32 w-full" />
                                <Skeleton className="h-32 w-full" />
                                <Skeleton className="h-32 w-full" />
                            </div>
                        )}

                        {/* Error State */}
                        {error && (
                            <Card className="border-destructive">
                                <CardContent className="pt-6">
                                    <p className="text-sm text-destructive">
                                        Fehler bei der Suche: {error.message}
                                    </p>
                                </CardContent>
                            </Card>
                        )}

                        {/* Results */}
                        {data?.results && data.results.length > 0 && (
                            <div className="space-y-3">
                                <div className="flex items-center justify-between">
                                    <p className="text-sm text-muted-foreground">
                                        {data.total} Ergebnisse gefunden in {data.search_time_ms}ms
                                    </p>
                                </div>
                                {data.results.map((result) => (
                                    <Card
                                        key={result.document_id}
                                        className="hover:shadow-md transition-shadow cursor-pointer"
                                        onClick={() => onResultClick?.(result.document_id)}
                                    >
                                        <CardContent className="pt-6">
                                            <div className="flex items-start justify-between gap-4">
                                                <div className="flex-1 space-y-2">
                                                    <div className="flex items-center gap-2">
                                                        <FileText className="w-4 h-4 text-muted-foreground" />
                                                        <h3 className="font-semibold">{result.filename}</h3>
                                                        <Badge variant="outline">{result.document_type}</Badge>
                                                    </div>
                                                    {result.highlight && (
                                                        <div
                                                            className="text-sm text-muted-foreground"
                                                            dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(result.highlight, { ALLOWED_TAGS: ['mark'], ALLOWED_ATTR: [] }) }}
                                                        />
                                                    )}
                                                    {result.matched_text && (
                                                        <div className="text-sm text-muted-foreground line-clamp-2">
                                                            {result.matched_text}
                                                        </div>
                                                    )}
                                                    {result.entity_match && (
                                                        <EntityMatchCard entity={result.entity_match} />
                                                    )}
                                                </div>
                                                <div className="flex flex-col items-end gap-2">
                                                    <Badge
                                                        variant="secondary"
                                                        className="bg-primary/10 text-primary"
                                                    >
                                                        {Math.round(result.relevance_score * 100)}%
                                                    </Badge>
                                                    <span className="text-xs text-muted-foreground">
                                                        {new Date(result.created_at).toLocaleDateString('de-DE')}
                                                    </span>
                                                </div>
                                            </div>
                                        </CardContent>
                                    </Card>
                                ))}
                            </div>
                        )}

                        {/* No Results */}
                        {data && data.results.length === 0 && !isLoading && (
                            <Card>
                                <CardContent className="pt-6 text-center">
                                    <p className="text-sm text-muted-foreground">
                                        Keine Ergebnisse gefunden
                                    </p>
                                </CardContent>
                            </Card>
                        )}
                    </div>

                    {/* Sidebar (1/4 width) */}
                    <div className="space-y-4">
                        {/* Facets */}
                        {data?.facets && (
                            <Card>
                                <CardHeader>
                                    <CardTitle className="text-sm">Verfeinern</CardTitle>
                                </CardHeader>
                                <CardContent className="space-y-4">
                                    {/* Document Types Facet */}
                                    {data.facets.document_types.length > 0 && (
                                        <div className="space-y-2">
                                            <h4 className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                                                Dokumenttyp
                                            </h4>
                                            {data.facets.document_types.slice(0, 5).map((facet) => (
                                                <Button
                                                    key={facet.value}
                                                    variant="ghost"
                                                    size="sm"
                                                    className="w-full justify-between"
                                                    onClick={() => {
                                                        setFilters({
                                                            ...filters,
                                                            document_types: [facet.value],
                                                        });
                                                    }}
                                                >
                                                    <span className="text-xs truncate">{facet.label}</span>
                                                    <Badge variant="secondary" className="text-xs">
                                                        {facet.count}
                                                    </Badge>
                                                </Button>
                                            ))}
                                        </div>
                                    )}

                                    <Separator />

                                    {/* Status Facet */}
                                    {data.facets.statuses.length > 0 && (
                                        <div className="space-y-2">
                                            <h4 className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                                                Status
                                            </h4>
                                            {data.facets.statuses.slice(0, 5).map((facet) => (
                                                <Button
                                                    key={facet.value}
                                                    variant="ghost"
                                                    size="sm"
                                                    className="w-full justify-between"
                                                    onClick={() => {
                                                        setFilters({
                                                            ...filters,
                                                            status: [facet.value],
                                                        });
                                                    }}
                                                >
                                                    <span className="text-xs truncate">{facet.label}</span>
                                                    <Badge variant="secondary" className="text-xs">
                                                        {facet.count}
                                                    </Badge>
                                                </Button>
                                            ))}
                                        </div>
                                    )}
                                </CardContent>
                            </Card>
                        )}

                        {/* Suggestions */}
                        {data?.suggestions && data.suggestions.length > 0 && (
                            <Card>
                                <CardHeader>
                                    <CardTitle className="text-sm">Vorschläge</CardTitle>
                                </CardHeader>
                                <CardContent className="space-y-2">
                                    {data.suggestions.map((suggestion, index) => (
                                        <SuggestionCard
                                            key={index}
                                            suggestion={suggestion}
                                            onClick={() => {
                                                setQuery(suggestion.text);
                                                if (suggestion.filters) {
                                                    setFilters(suggestion.filters);
                                                }
                                            }}
                                        />
                                    ))}
                                </CardContent>
                            </Card>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
}

export default SmartSearchBar;
