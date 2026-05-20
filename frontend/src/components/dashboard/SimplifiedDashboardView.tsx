/**
 * Vereinfachte Dashboard-Ansicht für Azubis/Viewer
 *
 * Fokus auf einfache Bedienung:
 * - Große Quick-Action-Karten
 * - Zuletzt hinzugefügte Dokumente
 * - Keine komplexen Finanz-KPIs
 */

import { useNavigate } from '@tanstack/react-router'
import { useQuery } from '@tanstack/react-query'
import { documentsService } from '@/lib/api/services/documents'
import { DocumentCard } from '@/features/documents/components/DocumentCard'
import { UploadDropzone } from '@/features/upload/components/UploadDropzone'
import { EmptyState } from '@/components/ui/empty-state'
import { QuickActionCards } from './QuickActionCards'
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert'
import { Skeleton } from '@/components/ui/skeleton'
import { ErrorBoundary } from '@/components/ErrorBoundary'
import { AlertCircle, RefreshCw, HelpCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'

interface SimplifiedDashboardViewProps {
    userName?: string
}

export function SimplifiedDashboardView({ userName }: SimplifiedDashboardViewProps) {
    const navigate = useNavigate()

    const {
        data: documents = [],
        isLoading,
        isError,
        error,
        refetch
    } = useQuery({
        queryKey: ['recent-documents'],
        queryFn: () => documentsService.getAll({ limit: 4, sort: 'date_desc' })
    })

    // Document click handler
    const handleDocumentClick = (docId: string) => {
        navigate({ to: '/documents/$id', params: { id: docId } })
    }

    const greeting = getGreeting()

    return (
        <div className="min-h-full relative">
            <div className="noise-overlay absolute inset-0 pointer-events-none" />
            <div className="p-6 space-y-8 relative z-10">
                {/* Begrüßung */}
                <section className="space-y-2">
                    <h1 className="text-3xl font-bold tracking-tight">
                        {greeting}{userName ? `, ${userName}` : ''}
                    </h1>
                    <p className="text-muted-foreground">
                        Was möchten Sie heute erledigen?
                    </p>
                </section>

                {/* Quick Actions */}
                <section className="space-y-4">
                    <h2 className="text-xl font-semibold">Schnellzugriff</h2>
                    <QuickActionCards />
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
                            {documents.length > 0 && (
                                <Button
                                    variant="ghost"
                                    size="sm"
                                    onClick={() => navigate({ to: '/search' })}
                                    aria-label="Alle Dokumente anzeigen"
                                >
                                    Alle anzeigen
                                </Button>
                            )}
                        </div>

                        {isError ? (
                            <Alert variant="destructive">
                                <AlertCircle className="h-4 w-4" aria-hidden="true" />
                                <AlertTitle>Dokumente nicht verfügbar</AlertTitle>
                                <AlertDescription className="flex items-center justify-between">
                                    <span>{(error as Error)?.message || 'Verbindung fehlgeschlagen'}</span>
                                    <Button
                                        variant="ghost"
                                        size="sm"
                                        onClick={() => refetch()}
                                        aria-label="Dokumente erneut laden"
                                    >
                                        <RefreshCw className="w-3 h-3 mr-1" aria-hidden="true" />
                                        Wiederholen
                                    </Button>
                                </AlertDescription>
                            </Alert>
                        ) : isLoading ? (
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                                {[1, 2, 3, 4].map((i) => (
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
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                                {documents.slice(0, 4).map((doc) => (
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

                {/* Hilfe-Footer */}
                <section className="pt-4 border-t">
                    <div className="flex items-center gap-2 text-sm text-muted-foreground">
                        <HelpCircle className="w-4 h-4" />
                        <span>Bei Fragen wenden Sie sich an Ben oder nutzen Sie die Hilfe-Funktion.</span>
                    </div>
                </section>
            </div>
        </div>
    )
}

function getGreeting(): string {
    const hour = new Date().getHours()
    if (hour < 12) return 'Guten Morgen'
    if (hour < 18) return 'Guten Tag'
    return 'Guten Abend'
}
