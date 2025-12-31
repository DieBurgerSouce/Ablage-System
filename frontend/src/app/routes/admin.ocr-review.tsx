import { createFileRoute } from '@tanstack/react-router'
import { ReviewDashboard } from '@/features/ocr-review/components/ReviewDashboard'

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
