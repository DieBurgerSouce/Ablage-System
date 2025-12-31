import { createFileRoute } from '@tanstack/react-router'
import { useQuery } from '@tanstack/react-query'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { FileText, Users, Cpu, HardDrive, Activity, CheckCircle, AlertCircle } from 'lucide-react'
import { apiClient } from '@/lib/api/client'

interface SystemDashboard {
    gpu: {
        available: boolean
        gpu_name: string | null
        total_gb: number
        free_gb: number
        allocated_gb: number
        utilization_percent: number
        temperature_celsius: number | null
        memory_usage_percent: number
    }
    queue: {
        pending_jobs: number
        processing_jobs: number
        completed_today: number
        failed_today: number
    }
    health: {
        postgresql: { status: string }
        redis: { status: string }
        minio: { status: string }
        celery: { status: string }
        overall: string
    }
    processing: {
        documents_processed_today: number
        documents_processed_hour: number
        success_rate: number
        total_documents: number
    }
    timestamp: string
}

// TanStack Router: admin.index.tsx = index route for /admin
// This component renders inside AdminLayout's <Outlet />
export const Route = createFileRoute('/admin/')({
    component: AdminDashboard,
})

function AdminDashboard() {
    // Fetch real stats from API
    const { data: dashboard, isLoading, error } = useQuery<SystemDashboard>({
        queryKey: ['admin', 'dashboard'],
        queryFn: async () => {
            const response = await apiClient.get('/admin/system/dashboard')
            return response.data
        },
        refetchInterval: 30000, // Refresh every 30 seconds
        staleTime: 10000,
    })

    // Derive stats from API response
    const stats = dashboard ? {
        totalDocuments: dashboard.processing.total_documents,
        ocrJobsToday: dashboard.processing.documents_processed_today,
        storageUsed: `${(dashboard.gpu.total_gb - dashboard.gpu.free_gb).toFixed(1)} GB`,
        systemHealth: dashboard.health.overall === 'healthy' ? 'Gesund' :
                      dashboard.health.overall === 'degraded' ? 'Eingeschraenkt' : 'Kritisch',
        pendingJobs: dashboard.queue.pending_jobs,
        processingJobs: dashboard.queue.processing_jobs,
        successRate: dashboard.processing.success_rate,
    } : null

    // Error state
    if (error) {
        return (
            <div className="space-y-8">
                <div>
                    <h1 className="text-3xl font-bold tracking-tight">Admin-Uebersicht</h1>
                    <p className="text-muted-foreground">
                        Systemstatus und wichtige Kennzahlen auf einen Blick
                    </p>
                </div>
                <Card className="border-destructive">
                    <CardHeader>
                        <CardTitle className="flex items-center gap-2 text-destructive">
                            <AlertCircle className="h-5 w-5" />
                            Fehler beim Laden
                        </CardTitle>
                    </CardHeader>
                    <CardContent>
                        <p>Dashboard-Daten konnten nicht geladen werden. Bitte pruefen Sie die Serververbindung.</p>
                    </CardContent>
                </Card>
            </div>
        )
    }

    return (
        <div className="space-y-8">
            <div>
                <h1 className="text-3xl font-bold tracking-tight">Admin-Uebersicht</h1>
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
                        {isLoading ? (
                            <Skeleton className="h-8 w-20" />
                        ) : (
                            <div className="text-2xl font-bold">{stats?.totalDocuments.toLocaleString('de-DE') ?? '-'}</div>
                        )}
                        <p className="text-xs text-muted-foreground">
                            Im System erfasst
                        </p>
                    </CardContent>
                </Card>

                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Warteschlange</CardTitle>
                        <Users className="h-4 w-4 text-muted-foreground" />
                    </CardHeader>
                    <CardContent>
                        {isLoading ? (
                            <Skeleton className="h-8 w-20" />
                        ) : (
                            <div className="text-2xl font-bold">{stats?.pendingJobs ?? 0}</div>
                        )}
                        <p className="text-xs text-muted-foreground">
                            {stats?.processingJobs ?? 0} in Bearbeitung
                        </p>
                    </CardContent>
                </Card>

                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">OCR-Jobs heute</CardTitle>
                        <Cpu className="h-4 w-4 text-muted-foreground" />
                    </CardHeader>
                    <CardContent>
                        {isLoading ? (
                            <Skeleton className="h-8 w-20" />
                        ) : (
                            <div className="text-2xl font-bold">{stats?.ocrJobsToday ?? 0}</div>
                        )}
                        <p className="text-xs text-muted-foreground">
                            Dokumente verarbeitet
                        </p>
                    </CardContent>
                </Card>

                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">GPU-Speicher</CardTitle>
                        <HardDrive className="h-4 w-4 text-muted-foreground" />
                    </CardHeader>
                    <CardContent>
                        {isLoading ? (
                            <Skeleton className="h-8 w-20" />
                        ) : (
                            <div className="text-2xl font-bold">{stats?.storageUsed ?? '-'}</div>
                        )}
                        <p className="text-xs text-muted-foreground">
                            von {dashboard?.gpu.total_gb.toFixed(0) ?? '16'} GB verfuegbar
                        </p>
                    </CardContent>
                </Card>

                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Systemstatus</CardTitle>
                        <Activity className="h-4 w-4 text-muted-foreground" />
                    </CardHeader>
                    <CardContent>
                        {isLoading ? (
                            <Skeleton className="h-8 w-20" />
                        ) : (
                            <div className={`text-2xl font-bold ${
                                stats?.systemHealth === 'Gesund' ? 'text-green-600' :
                                stats?.systemHealth === 'Eingeschraenkt' ? 'text-yellow-600' : 'text-red-600'
                            }`}>{stats?.systemHealth ?? '-'}</div>
                        )}
                        <p className="text-xs text-muted-foreground">
                            {dashboard?.health.overall === 'healthy' ? 'Alle Dienste verfuegbar' :
                             dashboard?.health.overall === 'degraded' ? 'Einige Dienste eingeschraenkt' : 'Systemprobleme erkannt'}
                        </p>
                    </CardContent>
                </Card>

                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Erfolgsrate</CardTitle>
                        <CheckCircle className="h-4 w-4 text-muted-foreground" />
                    </CardHeader>
                    <CardContent>
                        {isLoading ? (
                            <Skeleton className="h-8 w-20" />
                        ) : (
                            <div className="text-2xl font-bold">{stats?.successRate?.toFixed(1) ?? '0'}%</div>
                        )}
                        <p className="text-xs text-muted-foreground">
                            OCR-Verarbeitung erfolgreich
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
