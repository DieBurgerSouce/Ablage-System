import { createFileRoute } from '@tanstack/react-router'
import { lazy, Suspense } from 'react'
import { LazyLoadFallback } from '@/components/LazyLoadFallback'

const CommandCenterView = lazy(() => import('@/features/command-center/CommandCenterView').then(m => ({ default: m.CommandCenterView })))

export const Route = createFileRoute('/command-center')({
    component: CommandCenterPage,
})

function CommandCenterPage() {
    return (
        <Suspense fallback={<LazyLoadFallback />}>
            <CommandCenterView />
        </Suspense>
    )
}
