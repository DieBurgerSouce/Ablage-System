import { createFileRoute } from '@tanstack/react-router'
import { Construction } from 'lucide-react'

export const Route = createFileRoute('/admin/settings')({
    component: AdminSettingsPage,
})

function AdminSettingsPage() {
    return (
        <div className="space-y-8">
            <div>
                <h1 className="text-3xl font-bold tracking-tight">Einstellungen</h1>
                <p className="text-muted-foreground">Systemkonfiguration und Einstellungen</p>
            </div>

            <div className="flex flex-col items-center justify-center py-16 px-8 border-2 border-dashed rounded-xl bg-muted/30">
                <Construction className="w-16 h-16 text-muted-foreground mb-4" />
                <h2 className="text-xl font-medium mb-2">In Entwicklung</h2>
                <p className="text-muted-foreground text-center max-w-md">
                    Die Einstellungsseite befindet sich derzeit in Entwicklung.
                    Hier werden zukünftig System- und Benutzereinstellungen konfiguriert.
                </p>
            </div>
        </div>
    )
}
