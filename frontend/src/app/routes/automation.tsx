import { createFileRoute } from '@tanstack/react-router'
import { RuleBuilder } from '@/features/automation/components/RuleBuilder'

export const Route = createFileRoute('/automation')({
    component: AutomationPage,
})

function AutomationPage() {
    return (
        <div className="max-w-7xl mx-auto p-8 space-y-8">
            <div>
                <h1 className="text-3xl font-bold tracking-tight font-display">Automatisierung</h1>
                <p className="text-muted-foreground mt-2">
                    Erstellen und verwalten Sie Regeln für die automatische Dokumentenverarbeitung.
                </p>
            </div>

            <RuleBuilder />
        </div>
    )
}
