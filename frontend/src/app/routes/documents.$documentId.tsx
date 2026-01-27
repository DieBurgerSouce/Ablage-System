import { createFileRoute } from '@tanstack/react-router'
import { SplitDocumentViewer } from '@/features/viewer/components/SplitDocumentViewer'
import { useQuery } from '@tanstack/react-query'
import { documentsService } from '@/lib/api/services/documents'
import { Loader2 } from 'lucide-react'

export const Route = createFileRoute('/documents/$documentId')({
    component: DocumentViewerPage,
})

function DocumentViewerPage() {
    const { documentId } = Route.useParams()

    const { data: document, isLoading, isError } = useQuery({
        queryKey: ['document', documentId],
        queryFn: () => documentsService.getById(documentId)
    });

    if (isLoading) {
        return (
            <div className="h-full flex items-center justify-center">
                <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
            </div>
        )
    }

    if (isError) {
        return (
            <div className="flex items-center justify-center h-full">
                <div className="text-center">
                    <p className="text-destructive text-lg font-medium">
                        Fehler beim Laden des Dokuments
                    </p>
                    <p className="text-muted-foreground mt-2">
                        Das Dokument konnte nicht geladen werden. Bitte versuchen Sie es erneut.
                    </p>
                </div>
            </div>
        )
    }

    if (!document) {
        return (
            <div className="h-full flex items-center justify-center text-muted-foreground">
                Dokument nicht gefunden.
            </div>
        )
    }

    // In a real backend, OCR results would be part of the document object or a separate endpoint
    // For now, we'll use the document's metadata if available, or fallback to empty
    const ocrResults = document.ocrResults || { pages: [] };

    return (
        <div className="h-full flex flex-col relative bg-background">
            <div className="noise-overlay absolute inset-0 pointer-events-none" />

            <div className="h-16 border-b flex items-center px-6 justify-between relative z-10 bg-background/80 backdrop-blur-md supports-[backdrop-filter]:bg-background/60">
                <div className="flex items-center gap-4">
                    <div className="p-2 rounded-lg bg-primary/10 text-primary">
                        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                        </svg>
                    </div>
                    <div>
                        <h1 className="text-2xl font-bold tracking-tight truncate max-w-md">{document.title}</h1>
                        <p className="text-xs text-muted-foreground font-mono">{document.id}</p>
                    </div>
                </div>
                <div className="flex items-center gap-2">
                    <span className="px-2 py-1 rounded-full bg-accent/10 text-accent-foreground text-xs font-medium border border-accent/20">
                        {document.mimeType}
                    </span>
                </div>
            </div>
            <div className="flex-1 overflow-hidden">
                <SplitDocumentViewer
                    documentId={documentId}
                    ocrResults={ocrResults}
                    mimeType={document.mimeType}
                    extractedText={document.extractedText}
                />
            </div>
        </div>
    )
}
