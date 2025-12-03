import { createFileRoute } from '@tanstack/react-router'
import { ValidationEditor } from '@/features/validation/components/ValidationEditor'

export const Route = createFileRoute('/validation-queue/$id')({
    component: ValidationItemPage,
})

function ValidationItemPage() {
    const { id } = Route.useParams()

    return (
        <div className="h-screen flex flex-col">
            <ValidationEditor documentId={id} />
        </div>
    )
}
