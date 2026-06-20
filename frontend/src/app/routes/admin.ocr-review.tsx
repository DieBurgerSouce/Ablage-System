import { createFileRoute } from '@tanstack/react-router'
import { lazyRoute } from '@/lib/lazyRoute'

const ReviewDashboard = lazyRoute(() => import('@/features/ocr-review/components/ReviewDashboard').then(m => ({ default: m.ReviewDashboard })))

export const Route = createFileRoute('/admin/ocr-review')({
    component: OCRReviewPage,
})

function OCRReviewPage() {
    return (
        <div>
            <ReviewDashboard />
        </div>
    )
}
