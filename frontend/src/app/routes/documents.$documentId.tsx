import { createFileRoute } from '@tanstack/react-router'
import { SplitDocumentViewer } from '@/features/viewer/components/SplitDocumentViewer'
import { useMemo } from 'react'

export const Route = createFileRoute('/documents/$documentId')({
    component: DocumentViewerPage,
})

function DocumentViewerPage() {
    const { documentId } = Route.useParams()

    // Mock OCR results
    const ocrResults = useMemo(() => ({
        pages: [
            {
                boxes: [
                    { id: 'b1', x: 100, y: 100, width: 200, height: 50, confidence: 0.98, text: 'Rechnung Nr. 123' },
                    { id: 'b2', x: 100, y: 160, width: 100, height: 30, confidence: 0.88, text: 'Datum: 01.01.2024' },
                    { id: 'b3', x: 400, y: 100, width: 100, height: 50, confidence: 0.65, text: 'Unclear Text' },
                ]
            },
            {
                boxes: []
            }
        ]
    }), [documentId])

    return (
        <div className="h-full flex flex-col">
            <div className="h-14 border-b flex items-center px-4 bg-background">
                <h1 className="font-medium">Dokument: {documentId}</h1>
            </div>
            <div className="flex-1 overflow-hidden">
                <SplitDocumentViewer
                    documentId={documentId}
                    ocrResults={ocrResults}
                />
            </div>
        </div>
    )
}
