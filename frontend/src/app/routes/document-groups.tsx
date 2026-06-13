import { createFileRoute } from '@tanstack/react-router'
import { lazyRoute } from '@/lib/lazyRoute'

const DocumentGroupsPageContent = lazyRoute(() => import('@/features/document-groups/components/DocumentGroupsPageContent').then(m => ({ default: m.DocumentGroupsPageContent })))

export const Route = createFileRoute('/document-groups')({
    component: DocumentGroupsPage,
})

function DocumentGroupsPage() {
    return <DocumentGroupsPageContent />
}
