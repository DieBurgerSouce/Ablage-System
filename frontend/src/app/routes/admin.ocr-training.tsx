import { createFileRoute } from '@tanstack/react-router'
import { TrainingDashboard } from '@/features/ocr-training/components/TrainingDashboard'

export const Route = createFileRoute('/admin/ocr-training')({
    component: OCRTrainingPage,
})

function OCRTrainingPage() {
    return (
        <div className="space-y-8">
            <div>
                <h1 className="text-3xl font-bold tracking-tight font-display">OCR Training & Validation</h1>
                <p className="text-muted-foreground mt-2">
                    Verwalten Sie Ground-Truth-Daten, vergleichen Sie OCR-Backends und analysieren Sie Qualitätsmetriken.
                </p>
            </div>

            <TrainingDashboard />
        </div>
    )
}
