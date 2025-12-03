import { createFileRoute } from '@tanstack/react-router'
import { DocumentGroupViewer } from '@/features/document-groups/components/DocumentGroupViewer'

export const Route = createFileRoute('/document-groups/$id')({
    component: DocumentGroupDetailPage,
})

function DocumentGroupDetailPage() {
    const { id } = Route.useParams()

    return (
        <div className="p-8">
            <DocumentGroupViewer groupId={id} />
        </div>
    )
}
