/**
 * Review Dashboard Komponente
 * Hauptseite für den OCR Review mit Queue-Stats und Start-Button
 */

import { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Loader2, PlayCircle, AlertCircle, RefreshCw } from 'lucide-react'

import { useQueueStats, useLearnedWeights, useNextSample } from '../hooks/use-review-queries'
import { QueueStatsCards, CoverageByType, PriorityBreakdown } from './QueueStatsCards'
import { LearningProgressPanel } from './LearningProgressPanel'
import { ReviewWorkspace } from './ReviewWorkspace'

// Session Stats (localStorage)
function getSessionStats() {
    try {
        const today = new Date().toISOString().split('T')[0]
        const stored = localStorage.getItem(`ocr-review-session-${today}`)
        if (stored) {
            return JSON.parse(stored)
        }
    } catch {
        // Ignore
    }
    return { reviewed_today: 0, corrections_today: 0 }
}

function updateSessionStats(update: Partial<{ reviewed_today: number; corrections_today: number }>) {
    try {
        const today = new Date().toISOString().split('T')[0]
        const current = getSessionStats()
        const updated = { ...current, ...update }
        localStorage.setItem(`ocr-review-session-${today}`, JSON.stringify(updated))
        return updated
    } catch {
        return getSessionStats()
    }
}

export function ReviewDashboard() {
    const [isReviewing, setIsReviewing] = useState(false)
    const [sessionStats, setSessionStats] = useState(getSessionStats())

    // Queries
    const {
        data: queueStats,
        isLoading: statsLoading,
        error: statsError,
        refetch: refetchStats,
    } = useQueueStats()

    const {
        data: learnedWeights,
        isLoading: weightsLoading,
        refetch: refetchWeights,
    } = useLearnedWeights()

    // Prefetch nächstes Sample (disabled initially)
    useNextSample(undefined, false)

    // Session Stats aktualisieren bei Änderungen
    useEffect(() => {
        const handleStorageChange = () => {
            setSessionStats(getSessionStats())
        }
        window.addEventListener('storage', handleStorageChange)
        return () => window.removeEventListener('storage', handleStorageChange)
    }, [])

    const handleStartReview = () => {
        setIsReviewing(true)
    }

    const handleReviewComplete = (wasCorrection: boolean) => {
        const updated = updateSessionStats({
            reviewed_today: sessionStats.reviewed_today + 1,
            corrections_today: wasCorrection
                ? sessionStats.corrections_today + 1
                : sessionStats.corrections_today,
        })
        setSessionStats(updated)
        refetchStats()
    }

    const handleExitReview = () => {
        setIsReviewing(false)
        refetchStats()
        refetchWeights()
    }

    // Wenn im Review-Modus, zeige Workspace
    if (isReviewing) {
        return (
            <ReviewWorkspace
                onComplete={handleReviewComplete}
                onExit={handleExitReview}
                sessionStats={sessionStats}
            />
        )
    }

    // Dashboard-Ansicht
    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-3xl font-bold tracking-tight">OCR Review Queue</h1>
                    <p className="text-muted-foreground">
                        Überprüfe und korrigiere OCR-Ergebnisse für das Self-Learning
                    </p>
                </div>
                <div className="flex items-center gap-2">
                    <Button
                        variant="outline"
                        size="sm"
                        onClick={() => {
                            refetchStats()
                            refetchWeights()
                        }}
                    >
                        <RefreshCw className="h-4 w-4 mr-2" />
                        Aktualisieren
                    </Button>
                    <Button
                        size="lg"
                        onClick={handleStartReview}
                        disabled={statsLoading || !queueStats?.total_pending}
                    >
                        {statsLoading ? (
                            <Loader2 className="h-5 w-5 mr-2 animate-spin" />
                        ) : (
                            <PlayCircle className="h-5 w-5 mr-2" />
                        )}
                        Review Starten
                    </Button>
                </div>
            </div>

            {/* Error Alert */}
            {statsError && (
                <Alert variant="destructive">
                    <AlertCircle className="h-4 w-4" />
                    <AlertTitle>Fehler beim Laden</AlertTitle>
                    <AlertDescription>
                        Die Queue-Statistiken konnten nicht geladen werden.
                        <Button variant="link" onClick={() => refetchStats()} className="p-0 h-auto ml-2">
                            Erneut versuchen
                        </Button>
                    </AlertDescription>
                </Alert>
            )}

            {/* Stats Cards */}
            <QueueStatsCards
                stats={queueStats || {
                    total_pending: 0,
                    pending_by_priority: {},
                    pending_by_type: {},
                    spot_checks_pending: 0,
                    coverage_gaps: [],
                    oldest_item_days: 0,
                }}
                sessionStats={sessionStats}
                isLoading={statsLoading}
            />

            {/* Details Grid */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Coverage by Type */}
                {queueStats && <CoverageByType stats={queueStats} />}

                {/* Priority Breakdown */}
                {queueStats && <PriorityBreakdown stats={queueStats} />}

                {/* Learning Progress */}
                <LearningProgressPanel
                    weights={learnedWeights}
                    isLoading={weightsLoading}
                    onRefresh={() => refetchWeights()}
                />
            </div>

            {/* Info wenn Queue leer */}
            {queueStats?.total_pending === 0 && !statsLoading && (
                <Alert>
                    <AlertCircle className="h-4 w-4" />
                    <AlertTitle>Keine Samples ausstehend</AlertTitle>
                    <AlertDescription>
                        Alle Training-Samples wurden bereits überprüft. Neue Samples werden automatisch
                        hinzugefügt, wenn Dokumente mit hoher OCR-Konfidenz verarbeitet werden.
                    </AlertDescription>
                </Alert>
            )}
        </div>
    )
}
