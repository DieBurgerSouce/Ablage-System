/**
 * Search Page Route - URL-synchronisierte Dokumentensuche
 *
 * Features:
 * - URL Search Params mit TanStack Router
 * - Deep-Linking (URL teilen)
 * - Browser-History (Zurueck/Vor)
 * - Gespeicherte Suchen
 */

import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { useQuery } from '@tanstack/react-query'
import { SearchPanel } from '@/features/search/components/SearchPanel'
import { SavedSearches } from '@/features/search/components/SavedSearches'
import { documentsService } from '@/lib/api/services/documents'
import { DocumentCard } from '@/features/documents/components/DocumentCard'
import { EmptyState } from '@/components/ui/empty-state'
import {
    searchParamsSchema,
    type SearchParams,
    defaultSearchParams,
    toLegacyFilters,
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

    // Convert to legacy format for API
    const { query, mode, filters } = toLegacyFilters(search)

    // Check if we have an active search
    const hasSearch = !!search.q?.trim()

    // Query for search results
    const { data: results = [], isLoading } = useQuery({
        queryKey: ['search', search.q, search.mode, search.type, search.ocrStatus, search.dateRange, search.page, search.limit, search.sort],
        queryFn: () =>
            documentsService.getAll({
                query: search.q,
                type: search.type?.join(','),
                ocrStatus: search.ocrStatus?.join(','),
                dateRange: search.dateRange,
                sort: search.sort as 'date_asc' | 'date_desc' | 'name_asc' | 'name_desc' | undefined,
                limit: search.limit,
            }),
        enabled: hasSearch,
    })

    return (
        <div className="p-8 space-y-8">
            {/* Header */}
            <div className="text-center space-y-4 mb-12">
                <h1 className="text-3xl font-bold tracking-tight">
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

            {/* Results / Empty States */}
            {!hasSearch && !isLoading && (
                <EmptyState
                    variant="search"
                    title="Dokumente durchsuchen"
                    description="Geben Sie einen Suchbegriff ein oder nutzen Sie die Filter, um Dokumente zu finden."
                    size="lg"
                />
            )}

            {isLoading && (
                <div className="text-center p-8 text-muted-foreground">
                    Suche läuft...
                </div>
            )}

            {results.length > 0 && (
                <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-4 gap-6 mt-8">
                    {results.map((doc) => (
                        <DocumentCard
                            key={doc.id}
                            document={doc}
                            isSelected={false}
                            onClick={() => {}}
                            onDoubleClick={() => {}}
                            onSelect={() => {}}
                        />
                    ))}
                </div>
            )}

            {hasSearch && !isLoading && results.length === 0 && (
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
    )
}
