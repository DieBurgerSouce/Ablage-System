import { createFileRoute } from '@tanstack/react-router'
import { lazy, Suspense } from 'react'
import { LazyLoadFallback } from '@/components/LazyLoadFallback'

const RuleBuilder = lazy(() => import('@/features/automation/components/RuleBuilder').then(m => ({ default: m.RuleBuilder })))

export const Route = createFileRoute('/automation')({
    component: AutomationPage,
})

function AutomationPage() {
    return (
        <Suspense fallback={<LazyLoadFallback />}>
            <div className="p-8 space-y-8">
                <div>
                    <h1 className="text-3xl font-bold tracking-tight font-display">Automatisierung</h1>
                    <p className="text-muted-foreground mt-2">
                        Erstellen und verwalten Sie Regeln für die automatische Dokumentenverarbeitung.
                    </p>
                </div>

                <RuleBuilder />
            </div>
        </Suspense>
    )
}
