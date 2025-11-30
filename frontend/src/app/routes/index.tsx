import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { useState } from 'react'
import { DocumentGrid } from '@/features/documents/components/DocumentGrid'
import { mockDocuments } from '@/lib/mock-data'

export const Route = createFileRoute('/')({
    component: Index,
})

function Index() {
    const navigate = useNavigate()
    const [selectedIds, setSelectedIds] = useState<string[]>([])

    const handleSelect = (id: string, selected: boolean) => {
        if (selected) {
            setSelectedIds(prev => [...prev, id])
        } else {
            setSelectedIds(prev => prev.filter(i => i !== id))
        }
    }

    return (
        <div className="h-full flex flex-col">
            <div className="p-6 border-b flex justify-between items-center bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60 z-10">
                <div>
                    <h1 className="text-2xl font-bold tracking-tight">Dokumente</h1>
                    <p className="text-muted-foreground">Verwalten Sie Ihre digitalen Assets.</p>
                </div>
                <div className="text-sm text-muted-foreground">
                    {mockDocuments.length} Dateien
                </div>
            </div>

            <div className="flex-1 overflow-hidden">
                <DocumentGrid
                    documents={mockDocuments}
                    viewMode="grid"
                    selectedIds={selectedIds}
                    onSelect={handleSelect}
                    onDocumentClick={(id) => navigate({ to: '/documents/$documentId', params: { documentId: id } })}
                />
            </div>
        </div>
    )
}
