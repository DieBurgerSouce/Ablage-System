/**
 * Search Page Route - URL-synchronisierte Dokumentensuche
 *
 * Features:
 * - URL Search Params mit TanStack Router
 * - Deep-Linking (URL teilen)
 * - Browser-History (Zurück/Vor)
 * - Gespeicherte Suchen
 * - Relevanz-Score Visualisierung
 */

import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { useState } from 'react'
import { AnimatedPage } from '@/components/animations'
import { SearchPanel } from '@/features/search/components/SearchPanel'
import { SavedSearches } from '@/features/search/components/SavedSearches'
import { SearchResultCard } from '@/features/search/components/SearchResultCard'
import { FacetSidebar } from '@/features/search/components/FacetSidebar'
import { EmptyState } from '@/components/ui/empty-state'
import { useSearch, type SearchType } from '@/features/search/hooks/useSearch'
import { Loader2, Clock, FileSearch } from 'lucide-react'
import {
    searchParamsSchema,
    type SearchParams,
    defaultSearchParams,
} from '@/features/search/types/search-params'

// ==================== Route Definition ====================

export const Route = createFileRoute('/search')({
    validateSearch: searchParamsSchema,
    component: SearchPage,
})

// ==================== Page Component ====================

function SearchPage() {
    const search = Route.useSearch()
    const navigate = useNavigate({ from: Route.fullPath })

    // Update URL when search params change
    const updateSearch = (updates: Partial<SearchParams>) => {
        navigate({
            search: (prev) => ({
                ...prev,
                ...updates,
                // Reset page when filters change
                page: updates.page ?? (updates.q !== undefined || updates.type !== undefined ? 1 : prev.page),
            }),
            replace: true, // Don't add history entry for every keystroke
        })
    }

    // Reset all filters
    const resetFilters = () => {
        navigate({
            search: defaultSearchParams,
        })
    }

    // Facet filter state (Phase C)
    const [selectedTypes, setSelectedTypes] = useState<string[]>([])
    const [selectedStatuses, setSelectedStatuses] = useState<string[]>([])
    const [selectedTags, setSelectedTags] = useState<string[]>([])
    const [selectedBackends, setSelectedBackends] = useState<string[]>([])

    // Check if we have an active search
    const hasSearch = !!search.q?.trim() && search.q.trim().length >= 2

    // Use the search API with relevance scores
    const { data: searchResponse, isLoading, isFetching } = useSearch({
        query: search.q ?? '',
        searchType: (search.mode as SearchType) ?? 'hybrid',
        page: search.page ?? 1,
        perPage: search.limit ?? 20,
        filters: {
            documentType: search.type?.[0],
            status: search.ocrStatus?.[0],
        },
        sortBy: search.sort?.includes('date') ? 'created_at' : search.sort?.includes('name') ? 'filename' : 'relevance',
        sortOrder: search.sort?.includes('asc') ? 'asc' : 'desc',
        highlight: true,
    }, {
        enabled: hasSearch,
    })

    const results = searchResponse?.results ?? []

    return (
        <AnimatedPage><div className="p-8 space-y-8">
            {/* Header */}
            <div className="text-center space-y-4 mb-12">
                <h1 className="text-3xl font-bold tracking-tight flex items-center justify-center gap-3">
                    <FileSearch className="h-8 w-8 text-primary" />
                    Dokumentensuche
                </h1>
                <p className="text-muted-foreground text-lg max-w-2xl mx-auto">
                    Finden Sie Dokumente blitzschnell mit unserer hybriden Suche (Volltext & KI).
                </p>
            </div>

            {/* Search Panel - Controlled by URL */}
            <SearchPanel
                value={{
                    query: search.q ?? '',
                    mode: search.mode ?? 'hybrid',
                    filters: {
                        type: search.type ?? [],
                        ocrStatus: search.ocrStatus ?? [],
                        dateRange: search.dateRange ?? 'all',
                    },
                }}
                onChange={(updates) => {
                    updateSearch({
                        q: updates.query,
                        mode: updates.mode as SearchParams['mode'],
                        type: updates.filters?.type as SearchParams['type'],
                        ocrStatus: updates.filters?.ocrStatus as SearchParams['ocrStatus'],
                        dateRange: updates.filters?.dateRange as SearchParams['dateRange'],
                    })
                }}
                onReset={resetFilters}
            />

            {/* Saved Searches */}
            <SavedSearches
                currentParams={search}
                onSelectSearch={(params) => {
                    navigate({ search: params })
                }}
            />

            {/* Search Stats */}
            {searchResponse && results.length > 0 && (
                <div className="flex items-center justify-between text-sm text-muted-foreground border-b pb-4">
                    <span>
                        {searchResponse.total} Ergebnis{searchResponse.total !== 1 ? 'se' : ''} gefunden
                        {searchResponse.totalPages > 1 && ` (Seite ${searchResponse.page} von ${searchResponse.totalPages})`}
                    </span>
                    <span className="flex items-center gap-1">
                        <Clock className="h-4 w-4" />
                        {searchResponse.executionTimeMs}ms
                        {searchResponse.searchType === 'hybrid' && ' (Hybrid)'}
                        {searchResponse.searchType === 'semantic' && ' (Semantisch)'}
                        {searchResponse.searchType === 'fts' && ' (Volltext)'}
                    </span>
                </div>
            )}

            {/* Results with Facet Sidebar (Phase C) */}
            <div className="flex gap-6">
                {/* Facet Sidebar - links */}
                {hasSearch && (
                    <aside className="hidden lg:block w-64 flex-shrink-0">
                        <div className="sticky top-4 border rounded-lg bg-card">
                            <FacetSidebar
                                selectedTypes={selectedTypes}
                                onTypesChange={setSelectedTypes}
                                selectedStatuses={selectedStatuses}
                                onStatusesChange={setSelectedStatuses}
                                selectedTags={selectedTags}
                                onTagsChange={setSelectedTags}
                                selectedBackends={selectedBackends}
                                onBackendsChange={setSelectedBackends}
                            />
                        </div>
                    </aside>
                )}

                {/* Results / Empty States */}
                <div className="flex-1 min-w-0">
                    {!hasSearch && !isLoading && (
                        <EmptyState
                            variant="search"
                            title="Dokumente durchsuchen"
                            description="Geben Sie einen Suchbegriff ein (mindestens 2 Zeichen) oder nutzen Sie die Filter, um Dokumente zu finden."
                            size="lg"
                        />
                    )}

                    {(isLoading || isFetching) && (
                        <div className="flex items-center justify-center gap-3 p-8 text-muted-foreground">
                            <Loader2 className="h-5 w-5 animate-spin" />
                            <span>Suche läuft...</span>
                        </div>
                    )}

                    {results.length > 0 && !isLoading && (
                        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                            {results.map((result) => (
                                <SearchResultCard
                                    key={result.documentId}
                                    result={result}
                                />
                            ))}
                        </div>
                    )}

                    {hasSearch && !isLoading && !isFetching && results.length === 0 && (
                        <EmptyState
                            variant="search"
                            title="Keine Ergebnisse gefunden"
                            description="Keine Dokumente gefunden für Ihre Suche. Versuchen Sie andere Suchbegriffe oder passen Sie die Filter an."
                            action={{
                                label: 'Filter zurücksetzen',
                                onClick: resetFilters,
                                variant: 'outline',
                            }}
                        />
                    )}
                </div>
            </div>
        </div></AnimatedPage>
    )
}
