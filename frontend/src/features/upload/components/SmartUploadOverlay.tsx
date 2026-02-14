/**
 * SmartUploadOverlay - Globale Drop & Forget Upload-Zone
 *
 * Wickelt den App-Inhalt und lauscht auf Drag-Events.
 * Bei Datei-Drop: Upload -> Smart Tagging -> Auto-Kategorisierung.
 * Ergebnisse werden inline angezeigt, Undo ist global verfuegbar.
 */

import { useState, useCallback, useRef, useEffect, type ReactNode, type DragEvent } from 'react'
import { Upload, Loader2, X, FileCheck, AlertCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { apiClient } from '@/lib/api/client'
import { useGlobalUndo } from '@/hooks/useUndoableAction'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'
import { SmartUploadResults } from './SmartUploadResults'

// ============================================================================
// Types
// ============================================================================

interface ProcessingFile {
    file: File
    status: 'uploading' | 'analyzing' | 'tagging' | 'done' | 'error'
    documentId?: string
    category?: string
    categoryConfidence?: number
    tags: Array<{ name: string; displayName: string; confidence: number; color: string }>
    error?: string
}

type OverlayPhase = 'idle' | 'drag-over' | 'processing' | 'results'

// Accepted MIME types matching UploadDropzone config
const ACCEPTED_TYPES = new Set([
    'application/pdf',
    'image/png',
    'image/jpeg',
    'image/tiff',
    'image/bmp',
    'image/gif',
    'image/webp',
    'image/heic',
])

const ACCEPTED_EXTENSIONS = new Set([
    '.pdf',
    '.png',
    '.jpg',
    '.jpeg',
    '.tif',
    '.tiff',
    '.bmp',
    '.gif',
    '.webp',
    '.heic',
    '.heif',
])

const MAX_FILE_SIZE = 50 * 1024 * 1024 // 50 MB

// ============================================================================
// Helpers
// ============================================================================

function isFileAccepted(file: File): boolean {
    if (ACCEPTED_TYPES.has(file.type)) return true
    const ext = '.' + file.name.split('.').pop()?.toLowerCase()
    return ACCEPTED_EXTENSIONS.has(ext)
}

function formatFileSize(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function getStatusLabel(status: ProcessingFile['status']): string {
    switch (status) {
        case 'uploading':
            return 'Wird hochgeladen...'
        case 'analyzing':
            return 'Wird kategorisiert...'
        case 'tagging':
            return 'Tags werden analysiert...'
        case 'done':
            return 'Fertig'
        case 'error':
            return 'Fehler'
    }
}

// ============================================================================
// Component
// ============================================================================

interface SmartUploadOverlayProps {
    children: ReactNode
}

export function SmartUploadOverlay({ children }: SmartUploadOverlayProps) {
    const [phase, setPhase] = useState<OverlayPhase>('idle')
    const [processingFiles, setProcessingFiles] = useState<Array<ProcessingFile>>([])
    const dragCounterRef = useRef(0)
    const { executeAction } = useGlobalUndo()

    // Reset drag counter when overlay is not in drag-over state
    useEffect(() => {
        if (phase !== 'drag-over') {
            dragCounterRef.current = 0
        }
    }, [phase])

    // ---- Drag event handlers ----

    const handleDragEnter = useCallback(
        (e: DragEvent) => {
            e.preventDefault()
            e.stopPropagation()

            // Only react to file drags
            if (!e.dataTransfer.types.includes('Files')) return

            dragCounterRef.current += 1

            if (phase === 'idle') {
                setPhase('drag-over')
            }
        },
        [phase]
    )

    const handleDragOver = useCallback((e: DragEvent) => {
        e.preventDefault()
        e.stopPropagation()
        // Required for drop to work
        e.dataTransfer.dropEffect = 'copy'
    }, [])

    const handleDragLeave = useCallback(
        (e: DragEvent) => {
            e.preventDefault()
            e.stopPropagation()

            dragCounterRef.current -= 1

            if (dragCounterRef.current <= 0) {
                dragCounterRef.current = 0
                if (phase === 'drag-over') {
                    setPhase('idle')
                }
            }
        },
        [phase]
    )

    // ---- File processing pipeline ----

    const processFile = useCallback(async (file: File, index: number): Promise<void> => {
        const updateFile = (patch: Partial<ProcessingFile>) => {
            setProcessingFiles((prev) => {
                const next = [...prev]
                next[index] = { ...next[index], ...patch }
                return next
            })
        }

        try {
            // Step 1: Upload
            updateFile({ status: 'uploading' })

            const formData = new FormData()
            formData.append('file', file)

            const uploadResponse = await apiClient.post('/documents/upload', formData, {
                headers: { 'Content-Type': 'multipart/form-data' },
                timeout: 120000, // 2 min for large files
            })

            const documentId: string = uploadResponse.data.id
            const filename: string = uploadResponse.data.filename || file.name
            updateFile({ documentId, status: 'analyzing' })

            // Step 2: Auto-categorize
            let category: string | undefined
            let categoryConfidence: number | undefined

            try {
                const catResponse = await apiClient.post(
                    `/ai/documents/${documentId}/categorize`,
                    null,
                    { params: { auto_apply: true } }
                )
                category = catResponse.data.display_name || catResponse.data.category
                categoryConfidence = catResponse.data.confidence
            } catch {
                // Categorization is best-effort, continue with tagging
            }

            updateFile({ category, categoryConfidence, status: 'tagging' })

            // Step 3: Smart tagging
            let tags: ProcessingFile['tags'] = []

            try {
                const tagResponse = await apiClient.post(
                    `/smart-tagging/analyze/${documentId}`,
                    null,
                    { params: { auto_apply: true } }
                )

                const rawTags = tagResponse.data.suggested_tags || tagResponse.data.tags || []
                if (Array.isArray(rawTags)) {
                    tags = rawTags.map(
                        (t: { name?: string; display_name?: string; confidence?: number; color?: string }) => ({
                            name: t.name || '',
                            displayName: t.display_name || t.name || '',
                            confidence: t.confidence || 0,
                            color: t.color || '',
                        })
                    )
                }
            } catch {
                // Tagging is best-effort, continue
            }

            updateFile({ tags, status: 'done' })

            // Quiet toast per file for background feedback
            toast.success(`${filename} verarbeitet`, {
                description: category ? `Kategorie: ${category}` : undefined,
                duration: 3000,
            })
        } catch (err) {
            const errorMessage =
                err instanceof Error ? err.message : 'Upload fehlgeschlagen'
            updateFile({ status: 'error', error: errorMessage })
        }
    }, [])

    const handleDrop = useCallback(
        async (e: DragEvent) => {
            e.preventDefault()
            e.stopPropagation()
            dragCounterRef.current = 0

            if (phase === 'processing' || phase === 'results') return

            const droppedFiles = Array.from(e.dataTransfer.files)

            // Validate files
            const validFiles: File[] = []
            const rejectedNames: string[] = []

            for (const file of droppedFiles) {
                if (!isFileAccepted(file)) {
                    rejectedNames.push(`${file.name} (Typ nicht unterstuetzt)`)
                } else if (file.size > MAX_FILE_SIZE) {
                    rejectedNames.push(`${file.name} (zu gross, max. 50 MB)`)
                } else {
                    validFiles.push(file)
                }
            }

            if (rejectedNames.length > 0) {
                toast.error('Einige Dateien wurden abgelehnt', {
                    description: rejectedNames.join(', '),
                    duration: 5000,
                })
            }

            if (validFiles.length === 0) {
                setPhase('idle')
                return
            }

            // Initialize processing state
            const initialProcessing: Array<ProcessingFile> = validFiles.map((file) => ({
                file,
                status: 'uploading',
                tags: [],
            }))

            setProcessingFiles(initialProcessing)
            setPhase('processing')

            // Process all files concurrently
            await Promise.allSettled(
                validFiles.map((file, index) => processFile(file, index))
            )

            // All done - switch to results
            setPhase('results')

            // Register undo action for the batch.
            // Read from the latest state via the setState callback to avoid stale closures.
            setProcessingFiles((currentFiles) => {
                const successfulIds = currentFiles
                    .filter((f) => f.status === 'done' && f.documentId)
                    .map((f) => f.documentId as string)

                if (successfulIds.length > 0) {
                    // Fire and forget - executeAction is async but we handle errors inside
                    executeAction({
                        description: `${successfulIds.length} Dokument${successfulIds.length > 1 ? 'e' : ''} hochgeladen`,
                        execute: async () => {
                            // Already executed - this is a no-op for the forward action
                            return successfulIds
                        },
                        undo: async () => {
                            // Delete all uploaded documents
                            const deleteResults = await Promise.allSettled(
                                successfulIds.map((id) =>
                                    apiClient.delete(`/documents/${id}`)
                                )
                            )
                            const failedCount = deleteResults.filter(
                                (r) => r.status === 'rejected'
                            ).length
                            if (failedCount > 0) {
                                toast.error(
                                    `${failedCount} von ${successfulIds.length} Dokumenten konnten nicht geloescht werden`
                                )
                            } else {
                                toast.success(
                                    `${successfulIds.length} Dokument${successfulIds.length > 1 ? 'e' : ''} geloescht`
                                )
                            }
                        },
                    }).catch(() => {
                        // executeAction already shows toast on error
                    })
                }

                return currentFiles // No state mutation
            })
        },
        [phase, processFile, executeAction]
    )

    // ---- Close overlay ----

    const handleClose = useCallback(() => {
        setPhase('idle')
        setProcessingFiles([])
    }, [])

    const handleConfirmAll = useCallback(() => {
        toast.success('Upload bestaetigt', {
            description: 'Alle Dokumente wurden korrekt verarbeitet.',
            duration: 3000,
        })
        handleClose()
    }, [handleClose])

    // ---- Escape key to close ----

    useEffect(() => {
        if (phase === 'idle') return

        const handleKeyDown = (e: KeyboardEvent) => {
            if (e.key === 'Escape') {
                if (phase === 'drag-over') {
                    setPhase('idle')
                } else if (phase === 'results') {
                    handleClose()
                }
                // Don't close during processing
            }
        }

        window.addEventListener('keydown', handleKeyDown)
        return () => window.removeEventListener('keydown', handleKeyDown)
    }, [phase, handleClose])

    // ---- Build results for SmartUploadResults ----

    const buildResults = () =>
        processingFiles.map((pf) => ({
            filename: pf.file.name,
            documentId: pf.documentId || '',
            category: pf.category,
            categoryConfidence: pf.categoryConfidence,
            tags: pf.tags,
            error: pf.error,
        }))

    // ---- Render ----

    const isOverlayVisible = phase !== 'idle'

    return (
        <div
            onDragEnter={handleDragEnter}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            className="relative"
        >
            {children}

            {/* Overlay */}
            {isOverlayVisible && (
                <div
                    className={cn(
                        'fixed inset-0 z-[60] flex items-center justify-center transition-all duration-200',
                        phase === 'drag-over'
                            ? 'bg-background/80 backdrop-blur-sm'
                            : 'bg-background/95 backdrop-blur-md'
                    )}
                    role="dialog"
                    aria-modal="true"
                    aria-label="Smart Upload"
                >
                    {/* Close button - always visible except during processing */}
                    {phase !== 'processing' && (
                        <Button
                            variant="ghost"
                            size="icon"
                            className="absolute top-4 right-4 z-10 rounded-full"
                            onClick={handleClose}
                            aria-label="Schliessen"
                        >
                            <X className="h-5 w-5" />
                        </Button>
                    )}

                    {/* Phase: Drag Over */}
                    {phase === 'drag-over' && (
                        <div className="flex flex-col items-center gap-6 animate-in fade-in zoom-in-95 duration-200">
                            <div className="w-32 h-32 rounded-3xl bg-primary/10 flex items-center justify-center ring-2 ring-primary/20 ring-offset-2 ring-offset-background">
                                <Upload className="w-16 h-16 text-primary animate-bounce" />
                            </div>
                            <div className="text-center space-y-2">
                                <h2 className="text-2xl font-semibold">
                                    Dateien hier ablegen
                                </h2>
                                <p className="text-muted-foreground max-w-sm">
                                    Dokumente werden automatisch hochgeladen, kategorisiert und getaggt.
                                </p>
                            </div>
                            <div className="flex items-center gap-3 text-xs text-muted-foreground font-mono bg-muted/50 px-4 py-2 rounded-full border">
                                <span>PDF, PNG, JPG, TIF, BMP, GIF, WEBP, HEIC</span>
                                <span className="w-px h-3 bg-border" />
                                <span>Max. 50 MB</span>
                            </div>
                        </div>
                    )}

                    {/* Phase: Processing */}
                    {phase === 'processing' && (
                        <div className="w-full max-w-lg mx-auto px-6 animate-in fade-in duration-300">
                            <div className="flex flex-col items-center gap-6">
                                <div className="flex items-center gap-3">
                                    <Loader2 className="h-6 w-6 text-primary animate-spin" />
                                    <h2 className="text-xl font-semibold">
                                        Verarbeite {processingFiles.length}{' '}
                                        {processingFiles.length === 1 ? 'Datei' : 'Dateien'}...
                                    </h2>
                                </div>

                                <div className="w-full space-y-2 max-h-96 overflow-y-auto pr-1">
                                    {processingFiles.map((pf, idx) => (
                                        <div
                                            key={`${pf.file.name}-${idx}`}
                                            className={cn(
                                                'flex items-center gap-3 p-3 rounded-lg border transition-colors',
                                                pf.status === 'done'
                                                    ? 'border-green-500/30 bg-green-500/5'
                                                    : pf.status === 'error'
                                                      ? 'border-destructive/30 bg-destructive/5'
                                                      : 'border-border/50 bg-muted/20'
                                            )}
                                        >
                                            {/* Status icon */}
                                            <div className="flex-shrink-0">
                                                {pf.status === 'done' ? (
                                                    <FileCheck className="h-4 w-4 text-green-500" />
                                                ) : pf.status === 'error' ? (
                                                    <AlertCircle className="h-4 w-4 text-destructive" />
                                                ) : (
                                                    <Loader2 className="h-4 w-4 text-primary animate-spin" />
                                                )}
                                            </div>

                                            {/* File info */}
                                            <div className="flex-1 min-w-0">
                                                <p className="text-sm font-medium truncate">
                                                    {pf.file.name}
                                                </p>
                                                <p className="text-xs text-muted-foreground">
                                                    {formatFileSize(pf.file.size)} &middot;{' '}
                                                    {getStatusLabel(pf.status)}
                                                </p>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        </div>
                    )}

                    {/* Phase: Results */}
                    {phase === 'results' && (
                        <div className="w-full px-6 animate-in fade-in slide-in-from-bottom-4 duration-300">
                            <SmartUploadResults
                                results={buildResults()}
                                onClose={handleClose}
                                onConfirmAll={handleConfirmAll}
                            />
                        </div>
                    )}
                </div>
            )}
        </div>
    )
}
