import { createFileRoute } from '@tanstack/react-router'
import { UploadWizard } from '@/features/upload/components/UploadWizard'

export const Route = createFileRoute('/upload')({
    component: UploadPage,
})

function UploadPage() {
    return <UploadWizard />
}
