import { createFileRoute } from '@tanstack/react-router'
import { lazy, Suspense } from 'react'
import { LazyLoadFallback } from '@/components/LazyLoadFallback'

const DocumentGroupsPageContent = lazy(() => import('@/features/document-groups/components/DocumentGroupsPageContent').then(m => ({ default: m.DocumentGroupsPageContent })))

export const Route = createFileRoute('/document-groups')({
    component: DocumentGroupsPage,
})

function DocumentGroupsPage() {
    return (
        <Suspense fallback={<LazyLoadFallback />}>
            <DocumentGroupsPageContent />
        </Suspense>
    )
}
