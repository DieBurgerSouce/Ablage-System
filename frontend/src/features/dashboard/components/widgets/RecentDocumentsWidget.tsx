import { useQuery } from '@tanstack/react-query'
import { documentsService } from '@/lib/api/services/documents'
import { ErrorBoundary } from '@/components/ErrorBoundary'
import { DashboardSectionError, QueryErrorAlert } from '../shared'
import { Button } from '@/components/ui/button'
import { ArrowRight } from 'lucide-react'
import { useNavigate } from '@tanstack/react-router'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState } from '@/components/ui/empty-state'
import { DocumentCard } from '@/features/documents/components/DocumentCard'

export function RecentDocumentsWidget() {
    const navigate = useNavigate()
    const {
        data: documents = [],
        isLoading: isLoadingDocs,
        isError: isDocsError,
        error: docsError,
        refetch: refetchDocs
    } = useQuery({
        queryKey: ['recent-documents'],
        queryFn: () => documentsService.getAll({ limit: 5, sort: 'date_desc' })
    })

    // FIX Phase 7.6: Type-safe Navigation
    const handleDocumentClick = (docId: string) => {
        navigate({ to: '/documents/$id', params: { id: docId } })
    }

    return (
        <ErrorBoundary
            fallback={<DashboardSectionError section="Dokumente" />}
            errorTitle="Dokumente Fehler"
            errorDescription="Die Dokumentenliste konnte nicht geladen werden."
        >
            <section className="space-y-4 h-full" aria-labelledby="recent-docs-heading">
                <div className="flex items-center justify-between">
                    <h2 id="recent-docs-heading" className="text-xl font-semibold">Kürzlich hinzugefügt</h2>
                    <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => navigate({ to: '/search' })}
                        aria-label="Alle Dokumente anzeigen"
                    >
                        Alle anzeigen
                        <ArrowRight className="w-4 h-4 ml-1" aria-hidden="true" />
                    </Button>
                </div>

                {isDocsError ? (
                    <QueryErrorAlert
                        title="Dokumente nicht verfügbar"
                        error={docsError as Error}
                        onRetry={() => refetchDocs()}
                    />
                ) : isLoadingDocs ? (
                    <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-5 gap-4">
                        {[1, 2, 3, 4, 5].map((i) => (
                            <Skeleton key={i} className="h-48 rounded-xl" />
                        ))}
                    </div>
                ) : documents.length === 0 ? (
                    <EmptyState
                        variant="document"
                        title="Noch keine Dokumente"
                        description="Laden Sie Ihren ersten Beleg hoch."
                        action={{
                            label: 'Beleg hochladen',
                            onClick: () => navigate({ to: '/upload' })
                        }}
                        size="sm"
                    />
                ) : (
                    <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-5 gap-4">
                        {documents.slice(0, 5).map((doc) => (
                            <DocumentCard
                                key={doc.id}
                                document={doc}
                                isSelected={false}
                                onClick={() => handleDocumentClick(doc.id)}
                                onDoubleClick={() => handleDocumentClick(doc.id)}
                                onSelect={() => { }}
                            />
                        ))}
                    </div>
                )}
            </section>
        </ErrorBoundary>
    )
}
