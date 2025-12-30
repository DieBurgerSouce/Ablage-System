import { createFileRoute } from '@tanstack/react-router'
import { SearchPanel } from '@/features/search/components/SearchPanel'
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { documentsService } from '@/lib/api/services/documents'
import { DocumentCard } from '@/features/documents/components/DocumentCard'
import { EmptyState } from '@/components/ui/empty-state'

export const Route = createFileRoute('/search')({
    component: SearchPage,
})

function SearchPage() {
    const [searchParams, setSearchParams] = useState<import('@/lib/api/services/documents').DocumentFilter | null>(null);

    const { data: results = [], isLoading } = useQuery({
        queryKey: ['search', searchParams],
        queryFn: () => documentsService.getAll({ query: searchParams?.query, ...searchParams }),
        enabled: !!searchParams
    });

    return (
        <div className="max-w-5xl mx-auto p-8 space-y-8">
            <div className="text-center space-y-4 mb-12">
                <h1 className="text-4xl font-bold tracking-tight font-display">Dokumentensuche</h1>
                <p className="text-muted-foreground text-lg max-w-2xl mx-auto">
                    Finden Sie Dokumente blitzschnell mit unserer hybriden Suche (Volltext & KI).
                </p>
            </div>

            <SearchPanel onSearch={setSearchParams} />

            {/* Before first search - search prompt */}
            {!searchParams && !isLoading && (
                <EmptyState
                    variant="search"
                    title="Dokumente durchsuchen"
                    description="Geben Sie einen Suchbegriff ein oder nutzen Sie die Filter, um Dokumente zu finden."
                    size="lg"
                />
            )}

            {/* Loading state */}
            {isLoading && (
                <div className="text-center p-8 text-muted-foreground">Suche laeuft...</div>
            )}

            {/* Search results */}
            {results.length > 0 && (
                <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-4 gap-6 mt-8">
                    {results.map((doc) => (
                        <DocumentCard
                            key={doc.id}
                            document={doc}
                            isSelected={false}
                            onClick={() => { }}
                            onDoubleClick={() => { }}
                            onSelect={() => { }}
                        />
                    ))}
                </div>
            )}

            {/* No results found */}
            {searchParams && !isLoading && results.length === 0 && (
                <EmptyState
                    variant="search"
                    title="Keine Ergebnisse gefunden"
                    description={`Keine Dokumente gefunden fuer Ihre Suche. Versuchen Sie andere Suchbegriffe oder passen Sie die Filter an.`}
                    action={{
                        label: 'Filter zuruecksetzen',
                        onClick: () => setSearchParams(null),
                        variant: 'outline'
                    }}
                />
            )}
        </div>
    )
}
