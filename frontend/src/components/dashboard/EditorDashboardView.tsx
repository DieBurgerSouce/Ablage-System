/**
 * Editor Dashboard-Ansicht
 *
 * Workflow-fokussierte Ansicht für Mitarbeiter mit Editor-Rechten:
 * - Validierungsaufgaben
 * - Upload und Verarbeitung
 * - Kürzliche Dokumente
 * - Grundlegende Statistiken (aus echten API-Daten)
 */

import { useNavigate, Link } from '@tanstack/react-router'
import { useQuery } from '@tanstack/react-query'
import { documentsService } from '@/lib/api/services/documents'
import { adminService } from '@/lib/api/services/admin'
import { Card, CardContent, CardHeader, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert'
import { Skeleton } from '@/components/ui/skeleton'
import { UploadDropzone } from '@/features/upload/components/UploadDropzone'
import { DocumentCard } from '@/features/documents/components/DocumentCard'
import { EmptyState } from '@/components/ui/empty-state'
import { ErrorBoundary } from '@/components/ErrorBoundary'
import {
    AlertCircle,
    ArrowRight,
    Calendar,
    CheckCircle,
    Clock,
    FileText,
    RefreshCw,
    Search,
    Upload,
    Wallet
} from 'lucide-react'

interface EditorDashboardViewProps {
    userName?: string
}

/**
 * Formatiert Sekunden zu lesbarer Zeitangabe
 */
function formatDuration(seconds: number | undefined): string {
    if (seconds === undefined || seconds === 0) return '0:00'
    const mins = Math.floor(seconds / 60)
    const secs = Math.round(seconds % 60)
    return `${mins}:${secs.toString().padStart(2, '0')}`
}

export function EditorDashboardView({ userName }: EditorDashboardViewProps) {
    const navigate = useNavigate()

    // Dokumente laden
    const {
        data: documents = [],
        isLoading: isLoadingDocs,
        isError: isDocsError,
        error: docsError,
        refetch: refetchDocs
    } = useQuery({
        queryKey: ['recent-documents'],
        queryFn: () => documentsService.getAll({ limit: 6, sort: 'date_desc' })
    })

    // Queue-Status laden (echte Daten statt Mock!)
    const {
        data: queueStatus,
        isLoading: isLoadingQueue,
        isError: isQueueError,
        error: queueError,
        refetch: refetchQueue
    } = useQuery({
        queryKey: ['queue-status'],
        queryFn: () => adminService.getQueueStatus(),
        staleTime: 30000, // 30 Sekunden Cache
        retry: 1,
    })

    // Echte Statistiken aus API-Daten
    const taskStats = {
        pendingValidation: queueStatus?.pending ?? 0,
        processedToday: queueStatus?.completed_today ?? 0,
        averageTime: formatDuration(queueStatus?.avg_processing_seconds),
    }

    // Document click handler
    const handleDocumentClick = (docId: string) => {
        navigate({ to: '/documents/$documentId', params: { documentId: docId } })
    }

    const greeting = getGreeting()
    const today = new Date().toLocaleDateString('de-DE', {
        weekday: 'long',
        day: 'numeric',
        month: 'long',
        year: 'numeric'
    })

    return (
        <div className="min-h-full relative">
            <div className="noise-overlay absolute inset-0 pointer-events-none" />
            <div className="p-6 space-y-8 relative z-10">
                {/* Header */}
                <header className="flex items-center justify-between">
                    <div>
                        <h1 className="text-3xl font-bold tracking-tight">
                            {greeting}{userName ? `, ${userName}` : ''}
                        </h1>
                        <p className="text-muted-foreground flex items-center gap-2">
                            <Calendar className="w-4 h-4" />
                            {today}
                        </p>
                    </div>
                    <Button onClick={() => navigate({ to: '/upload' })}>
                        <Upload className="w-4 h-4 mr-2" />
                        Neuer Beleg
                    </Button>
                </header>

                {/* Aufgaben-Übersicht */}
                <ErrorBoundary
                    errorTitle="Aufgaben-Fehler"
                    errorDescription="Die Aufgabenübersicht konnte nicht geladen werden."
                >
                    <section className="space-y-4" aria-labelledby="tasks-heading">
                        <h2 id="tasks-heading" className="text-xl font-semibold">Ihre Aufgaben</h2>
                        {isQueueError ? (
                            <Alert variant="destructive">
                                <AlertCircle className="h-4 w-4" aria-hidden="true" />
                                <AlertTitle>Statistiken nicht verfügbar</AlertTitle>
                                <AlertDescription className="flex items-center justify-between">
                                    <span>{(queueError as Error)?.message || 'Verbindung fehlgeschlagen'}</span>
                                    <Button
                                        variant="ghost"
                                        size="sm"
                                        onClick={() => refetchQueue()}
                                        aria-label="Statistiken erneut laden"
                                    >
                                        <RefreshCw className="w-3 h-3 mr-1" aria-hidden="true" />
                                        Wiederholen
                                    </Button>
                                </AlertDescription>
                            </Alert>
                        ) : isLoadingQueue ? (
                            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                                {[1, 2, 3].map((i) => (
                                    <Skeleton key={i} className="h-32 rounded-xl" />
                                ))}
                            </div>
                        ) : (
                            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                                <Link to="/validation-queue" aria-label={`${taskStats.pendingValidation} Belege zur Validierung`}>
                                    <Card className="hover:shadow-lg transition-all hover:border-primary/50 cursor-pointer">
                                        <CardHeader className="pb-2">
                                            <div className="flex items-center justify-between">
                                                <CardDescription>Zur Validierung</CardDescription>
                                                <CheckCircle className="w-5 h-5 text-amber-500" aria-hidden="true" />
                                            </div>
                                        </CardHeader>
                                        <CardContent>
                                            <p className="text-3xl font-bold">{taskStats.pendingValidation}</p>
                                            <p className="text-xs text-muted-foreground mt-1">
                                                Belege warten auf Prüfung
                                            </p>
                                        </CardContent>
                                    </Card>
                                </Link>

                                <Card aria-label={`${taskStats.processedToday} Belege heute verarbeitet`}>
                                    <CardHeader className="pb-2">
                                        <div className="flex items-center justify-between">
                                            <CardDescription>Heute verarbeitet</CardDescription>
                                            <FileText className="w-5 h-5 text-green-500" aria-hidden="true" />
                                        </div>
                                    </CardHeader>
                                    <CardContent>
                                        <p className="text-3xl font-bold">{taskStats.processedToday}</p>
                                        <p className="text-xs text-muted-foreground mt-1">
                                            Belege erfolgreich
                                        </p>
                                    </CardContent>
                                </Card>

                                <Card aria-label={`Durchschnittliche Bearbeitungszeit: ${taskStats.averageTime} Minuten`}>
                                    <CardHeader className="pb-2">
                                        <div className="flex items-center justify-between">
                                            <CardDescription>Durchschnitt/Beleg</CardDescription>
                                            <Clock className="w-5 h-5 text-blue-500" aria-hidden="true" />
                                        </div>
                                    </CardHeader>
                                    <CardContent>
                                        <p className="text-3xl font-bold">{taskStats.averageTime}</p>
                                        <p className="text-xs text-muted-foreground mt-1">
                                            Minuten Bearbeitungszeit
                                        </p>
                                    </CardContent>
                                </Card>
                            </div>
                        )}
                    </section>
                </ErrorBoundary>

                {/* Schnellzugriff */}
                <section className="space-y-4" aria-labelledby="quickaccess-heading">
                    <h2 id="quickaccess-heading" className="text-xl font-semibold">Schnellzugriff</h2>
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                        <QuickAction
                            icon={Upload}
                            label="Beleg hochladen"
                            href="/upload"
                            color="primary"
                        />
                        <QuickAction
                            icon={Search}
                            label="Dokument suchen"
                            href="/search"
                            color="secondary"
                        />
                        <QuickAction
                            icon={Wallet}
                            label="Kassenbuch"
                            href="/kassenbuch"
                            color="success"
                        />
                        <QuickAction
                            icon={CheckCircle}
                            label="Validierung"
                            href="/validierung"
                            badge={taskStats.pendingValidation}
                            color="warning"
                        />
                    </div>
                </section>

                {/* Upload-Bereich */}
                <section className="space-y-4">
                    <h2 className="text-xl font-semibold">Beleg hochladen</h2>
                    <UploadDropzone
                        onFilesAdd={(files) => {
                            // Navigate zur Upload-Seite mit den ausgewählten Dateien
                            if (files.length > 0) {
                                navigate({ to: '/upload' })
                            }
                        }}
                    />
                </section>

                {/* Kürzlich hinzugefügt */}
                <ErrorBoundary
                    errorTitle="Dokumente Fehler"
                    errorDescription="Die Dokumentenliste konnte nicht geladen werden."
                >
                    <section className="space-y-4" aria-labelledby="recent-docs-heading">
                        <div className="flex items-center justify-between">
                            <h2 id="recent-docs-heading" className="text-xl font-semibold">Kürzlich hinzugefügt</h2>
                            <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => navigate({ to: '/search' })}
                                aria-label="Alle Dokumente anzeigen"
                            >
                                Alle anzeigen
                                <ArrowRight className="w-4 h-4 ml-1" aria-hidden="true" />
                            </Button>
                        </div>

                        {isDocsError ? (
                            <Alert variant="destructive">
                                <AlertCircle className="h-4 w-4" aria-hidden="true" />
                                <AlertTitle>Dokumente nicht verfügbar</AlertTitle>
                                <AlertDescription className="flex items-center justify-between">
                                    <span>{(docsError as Error)?.message || 'Verbindung fehlgeschlagen'}</span>
                                    <Button
                                        variant="ghost"
                                        size="sm"
                                        onClick={() => refetchDocs()}
                                        aria-label="Dokumente erneut laden"
                                    >
                                        <RefreshCw className="w-3 h-3 mr-1" aria-hidden="true" />
                                        Wiederholen
                                    </Button>
                                </AlertDescription>
                            </Alert>
                        ) : isLoadingDocs ? (
                            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                                {[1, 2, 3, 4, 5, 6].map((i) => (
                                    <Skeleton key={i} className="h-48 rounded-xl" />
                                ))}
                            </div>
                        ) : documents.length === 0 ? (
                            <EmptyState
                                variant="document"
                                title="Noch keine Dokumente"
                                description="Laden Sie Ihren ersten Beleg hoch, um zu beginnen."
                                action={{
                                    label: 'Beleg hochladen',
                                    onClick: () => navigate({ to: '/upload' })
                                }}
                                size="sm"
                            />
                        ) : (
                            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                                {documents.slice(0, 6).map((doc) => (
                                    <DocumentCard
                                        key={doc.id}
                                        document={doc}
                                        isSelected={false}
                                        onClick={() => handleDocumentClick(doc.id)}
                                        onDoubleClick={() => handleDocumentClick(doc.id)}
                                        onSelect={() => {/* View-only - keine Selektion */}}
                                    />
                                ))}
                            </div>
                        )}
                    </section>
                </ErrorBoundary>
            </div>
        </div>
    )
}

interface QuickActionProps {
    icon: React.ComponentType<{ className?: string }>
    label: string
    href: string
    badge?: number
    color: 'primary' | 'secondary' | 'success' | 'warning'
}

function QuickAction({ icon: Icon, label, href, badge, color }: QuickActionProps) {
    const colorClasses = {
        primary: 'hover:border-primary/50 hover:bg-primary/5',
        secondary: 'hover:border-secondary hover:bg-secondary/10',
        success: 'hover:border-green-500/50 hover:bg-green-500/5',
        warning: 'hover:border-amber-500/50 hover:bg-amber-500/5',
    }

    const iconColors = {
        primary: 'text-primary',
        secondary: 'text-muted-foreground',
        success: 'text-green-600',
        warning: 'text-amber-600',
    }

    return (
        <Link to={href}>
            <Card className={`transition-all cursor-pointer ${colorClasses[color]}`}>
                <CardContent className="p-4 flex flex-col items-center justify-center gap-2 relative">
                    {badge !== undefined && badge > 0 && (
                        <Badge
                            variant="destructive"
                            className="absolute -top-2 -right-2 h-6 w-6 p-0 flex items-center justify-center"
                        >
                            {badge}
                        </Badge>
                    )}
                    <Icon className={`w-6 h-6 ${iconColors[color]}`} />
                    <span className="text-sm font-medium text-center">{label}</span>
                </CardContent>
            </Card>
        </Link>
    )
}

function getGreeting(): string {
    const hour = new Date().getHours()
    if (hour < 12) return 'Guten Morgen'
    if (hour < 18) return 'Guten Tag'
    return 'Guten Abend'
}
