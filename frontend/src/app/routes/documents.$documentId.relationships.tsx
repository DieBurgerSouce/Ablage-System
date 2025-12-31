import { createFileRoute } from '@tanstack/react-router'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { relationshipsService } from '@/lib/api/services/relationships'
import { documentsService } from '@/lib/api/services/documents'
import { RelationshipGraph } from '@/features/relationships/components/RelationshipGraph'
import { RelationshipTable } from '@/features/relationships/components/RelationshipTable'
import { RelationshipForm } from '@/features/relationships/components/RelationshipForm'
import { Loader2, ArrowLeft } from 'lucide-react'
import { useState } from 'react'
import { Link } from '@tanstack/react-router'
import { Button } from '@/components/ui/button'

export const Route = createFileRoute('/documents/$documentId/relationships')({
    component: DocumentRelationshipsPage,
})

function DocumentRelationshipsPage() {
    const { documentId } = Route.useParams()
    const queryClient = useQueryClient()
    const [viewMode, setViewMode] = useState<'graph' | 'table'>('graph')

    const { data: relationships, isLoading: isLoadingRelationships } = useQuery({
        queryKey: ['relationships', documentId],
        queryFn: () => relationshipsService.getByDocumentId(documentId),
    })

    const { data: document, isLoading: isLoadingDocument } = useQuery({
        queryKey: ['document', documentId],
        queryFn: () => documentsService.getById(documentId),
    })

    const { data: allDocuments } = useQuery({
        queryKey: ['documents'],
        queryFn: () => documentsService.getAll(),
    })

    const createMutation = useMutation({
        mutationFn: relationshipsService.create,
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['relationships', documentId] })
        },
    })

    const deleteMutation = useMutation({
        mutationFn: relationshipsService.delete,
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['relationships', documentId] })
        },
    })

    if (isLoadingRelationships || isLoadingDocument) {
        return (
            <div className="h-full flex items-center justify-center">
                <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
            </div>
        )
    }

    if (!document) {
        return <div>Document not found</div>
    }

    const relatedDocIds = new Set<string>()
    relatedDocIds.add(documentId)
    relationships?.forEach(rel => {
        relatedDocIds.add(rel.sourceDocumentId)
        relatedDocIds.add(rel.targetDocumentId)
    })

    const relevantDocuments = allDocuments?.filter(doc => relatedDocIds.has(doc.id)) || [document]

    return (
        <div className="container mx-auto py-8 space-y-8">
            <div className="flex items-center gap-4">
                <Link to="/documents/$documentId" params={{ documentId }}>
                    <Button variant="ghost" size="icon">
                        <ArrowLeft className="h-4 w-4" />
                    </Button>
                </Link>
                <div className="flex-1">
                    <h1 className="text-2xl font-bold tracking-tight">Relationships</h1>
                    <p className="text-muted-foreground">Managing relationships for {document.title || document.name}</p>
                </div>
                <div className="flex gap-2">
                    <Button
                        variant={viewMode === 'graph' ? 'default' : 'outline'}
                        onClick={() => setViewMode('graph')}
                    >
                        Graph
                    </Button>
                    <Button
                        variant={viewMode === 'table' ? 'default' : 'outline'}
                        onClick={() => setViewMode('table')}
                    >
                        Table
                    </Button>
                </div>
            </div>

            <RelationshipForm
                availableDocuments={allDocuments?.filter(d => d.id !== documentId) || []}
                onSubmit={(targetId, type) => {
                    createMutation.mutate({
                        sourceDocumentId: documentId,
                        targetDocumentId: targetId,
                        type,
                    })
                }}
                isSubmitting={createMutation.isPending}
            />

            {viewMode === 'graph' ? (
                <div className="h-[600px] border rounded-lg overflow-hidden">
                    <RelationshipGraph
                        relationships={relationships || []}
                        documents={relevantDocuments}
                    />
                </div>
            ) : (
                <RelationshipTable
                    relationships={relationships || []}
                    onDelete={(id) => deleteMutation.mutate(id)}
                />
            )}
        </div>
    )
}
