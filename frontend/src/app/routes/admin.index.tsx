import { createFileRoute } from '@tanstack/react-router'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { FileText, Users, Cpu, HardDrive, Activity, CheckCircle } from 'lucide-react'

export const Route = createFileRoute('/admin/')({
    component: AdminDashboard,
})

function AdminDashboard() {
    // TODO: Fetch real stats from API
    const stats = {
        totalDocuments: 1247,
        activeUsers: 12,
        ocrJobsToday: 89,
        storageUsed: '45.2 GB',
        systemHealth: 'Gesund',
        lastBackup: 'Vor 2 Stunden',
    }

    return (
        <div className="space-y-8">
            <div>
                <h2 className="text-3xl font-bold tracking-tight">Admin-Übersicht</h2>
                <p className="text-muted-foreground">
                    Systemstatus und wichtige Kennzahlen auf einen Blick
                </p>
            </div>

            {/* Stats Grid */}
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Dokumente gesamt</CardTitle>
                        <FileText className="h-4 w-4 text-muted-foreground" />
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold">{stats.totalDocuments.toLocaleString('de-DE')}</div>
                        <p className="text-xs text-muted-foreground">
                            +12% gegenüber letztem Monat
                        </p>
                    </CardContent>
                </Card>

                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Aktive Benutzer</CardTitle>
                        <Users className="h-4 w-4 text-muted-foreground" />
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold">{stats.activeUsers}</div>
                        <p className="text-xs text-muted-foreground">
                            Derzeit angemeldet
                        </p>
                    </CardContent>
                </Card>

                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">OCR-Jobs heute</CardTitle>
                        <Cpu className="h-4 w-4 text-muted-foreground" />
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold">{stats.ocrJobsToday}</div>
                        <p className="text-xs text-muted-foreground">
                            Dokumente verarbeitet
                        </p>
                    </CardContent>
                </Card>

                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Speichernutzung</CardTitle>
                        <HardDrive className="h-4 w-4 text-muted-foreground" />
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold">{stats.storageUsed}</div>
                        <p className="text-xs text-muted-foreground">
                            von 500 GB verfügbar
                        </p>
                    </CardContent>
                </Card>

                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Systemstatus</CardTitle>
                        <Activity className="h-4 w-4 text-muted-foreground" />
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold text-green-600">{stats.systemHealth}</div>
                        <p className="text-xs text-muted-foreground">
                            Alle Dienste verfügbar
                        </p>
                    </CardContent>
                </Card>

                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Letztes Backup</CardTitle>
                        <CheckCircle className="h-4 w-4 text-muted-foreground" />
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold">{stats.lastBackup}</div>
                        <p className="text-xs text-muted-foreground">
                            Automatisches tägliches Backup
                        </p>
                    </CardContent>
                </Card>
            </div>

            {/* Quick Actions */}
            <Card>
                <CardHeader>
                    <CardTitle>Schnellzugriff</CardTitle>
                    <CardDescription>
                        Häufig verwendete Administrationsaufgaben
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
                        <QuickAction
                            href="/admin/users"
                            title="Benutzer verwalten"
                            description="Benutzerkonten anlegen, bearbeiten und Rechte vergeben"
                        />
                        <QuickAction
                            href="/admin/tunes"
                            title="Tunes konfigurieren"
                            description="Dokumenttypen und OCR-Profile anpassen"
                        />
                        <QuickAction
                            href="/admin/ocr-backends"
                            title="OCR-Backends"
                            description="OCR-Engines verwalten und konfigurieren"
                        />
                        <QuickAction
                            href="/admin/settings"
                            title="Einstellungen"
                            description="Systemweite Konfigurationen anpassen"
                        />
                    </div>
                </CardContent>
            </Card>
        </div>
    )
}

function QuickAction({ href, title, description }: { href: string; title: string; description: string }) {
    return (
        <a
            href={href}
            className="block p-4 rounded-lg border bg-card hover:bg-muted/50 transition-colors"
        >
            <h3 className="font-medium">{title}</h3>
            <p className="text-sm text-muted-foreground mt-1">{description}</p>
        </a>
    )
}
