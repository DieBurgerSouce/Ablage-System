import { createFileRoute } from '@tanstack/react-router'
import { lazy, Suspense } from 'react'
import { LazyLoadFallback } from '@/components/LazyLoadFallback'

const UploadWizard = lazy(() => import('@/features/upload/components/UploadWizard').then(m => ({ default: m.UploadWizard })))

export const Route = createFileRoute('/upload')({
    component: UploadPage,
})

function UploadPage() {
    return (
        <Suspense fallback={<LazyLoadFallback />}>
            <UploadWizard />
        </Suspense>
    )
}
