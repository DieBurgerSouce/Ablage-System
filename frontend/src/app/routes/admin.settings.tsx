import { createFileRoute } from '@tanstack/react-router'
import { Settings, Construction } from 'lucide-react'

export const Route = createFileRoute('/admin/settings')({
    component: AdminSettingsPage,
})

function AdminSettingsPage() {
    return (
        <div className="max-w-7xl mx-auto p-8 space-y-8">
            <div className="flex items-center gap-3 mb-8">
                <div className="p-3 rounded-lg bg-primary/10">
                    <Settings className="w-6 h-6 text-primary" />
                </div>
                <div>
                    <h1 className="text-2xl font-semibold tracking-tight">Einstellungen</h1>
                    <p className="text-muted-foreground">Systemkonfiguration und Einstellungen</p>
                </div>
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
