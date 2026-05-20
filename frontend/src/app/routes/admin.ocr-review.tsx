import { createFileRoute } from '@tanstack/react-router'
import { lazy, Suspense } from 'react'
import { LazyLoadFallback } from '@/components/LazyLoadFallback'

const ReviewDashboard = lazy(() => import('@/features/ocr-review/components/ReviewDashboard').then(m => ({ default: m.ReviewDashboard })))

export const Route = createFileRoute('/admin/ocr-review')({
    component: OCRReviewPage,
})

function OCRReviewPage() {
    return (
        <Suspense fallback={<LazyLoadFallback />}>
            <div>
                <ReviewDashboard />
            </div>
        </Suspense>
    )
}
