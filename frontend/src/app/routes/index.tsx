import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { UploadDropzone } from '@/features/upload/components/UploadDropzone'
import { DocumentCard } from '@/features/documents/components/DocumentCard'
import { useQuery } from '@tanstack/react-query'
import { documentsService } from '@/lib/api/services/documents'
import { Loader2 } from 'lucide-react'
import { EmptyState } from '@/components/ui/empty-state'

export const Route = createFileRoute('/')({
    component: Index,
})

function Index() {
    const navigate = useNavigate()
    const { data: documents = [], isLoading } = useQuery({
        queryKey: ['recent-documents'],
        queryFn: () => documentsService.getAll({ limit: 5, sort: 'date_desc' })
    });

    return (
        <div className="min-h-full relative">
            <div className="noise-overlay absolute inset-0 pointer-events-none" />
            <div className="max-w-5xl mx-auto p-8 space-y-12 relative z-10">
                <section className="space-y-6">
                    <div className="text-center space-y-4">
                        <h1 className="text-5xl font-bold tracking-tight font-display bg-gradient-to-br from-foreground to-muted-foreground bg-clip-text text-transparent">
                            Ablage System
                        </h1>
                        <p className="text-muted-foreground text-lg max-w-2xl mx-auto">
                            Intelligentes Dokumentenmanagement mit deutscher Präzision.
                            Ziehen Sie Dateien hierher, um zu beginnen.
                        </p>
                    </div>

                    <UploadDropzone onFilesAdd={() => { }} />
                </section>

                <section className="space-y-6">
                    <div className="flex items-center justify-between">
                        <h2 className="text-2xl font-semibold font-display">Kürzlich hinzugefügt</h2>
                        <span className="text-sm text-muted-foreground bg-muted/50 px-3 py-1 rounded-full border">
                            {isLoading ? <Loader2 className="w-3 h-3 animate-spin inline mr-1" /> : documents.length} Dateien
                        </span>
                    </div>

                    {isLoading ? (
                        <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-4 gap-6">
                            {[1, 2, 3, 4].map((i) => (
                                <div key={i} className="h-[280px] rounded-xl bg-muted/20 animate-pulse" />
                            ))}
                        </div>
                    ) : documents.length === 0 ? (
                        <EmptyState
                            variant="document"
                            title="Noch keine Dokumente"
                            description="Laden Sie Ihr erstes Dokument hoch, um mit der intelligenten Dokumentenverwaltung zu beginnen."
                            action={{
                                label: 'Dokument hochladen',
                                onClick: () => navigate({ to: '/upload' })
                            }}
                        />
                    ) : (
                        <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-4 gap-6">
                            {documents.map((doc) => (
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
                </section>
            </div>
        </div>
    )
}
