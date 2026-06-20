import { createFileRoute } from '@tanstack/react-router'
import { lazyRoute } from '@/lib/lazyRoute'

// B7-Fix: lazyRoute statt React.lazy + Suspense (siehe src/lib/lazyRoute.tsx)
const UploadWizard = lazyRoute(() => import('@/features/upload/components/UploadWizard').then(m => ({ default: m.UploadWizard })))

export const Route = createFileRoute('/upload')({
    component: UploadPage,
})

function UploadPage() {
    return <UploadWizard />
}
