/**
 * FinanceDocumentVersions - OCR Version Management Component
 *
 * Ermöglicht die Verwaltung von OCR-Versionen eines Finanz-Dokuments.
 *
 * Features:
 * - Versionsliste mit Details (Backend, Konfidenz, Wortanzahl)
 * - Versions-Vergleich mit Text-Diff (unified format)
 * - Rollback zu früheren Versionen
 * - Accessibility-konform (WCAG 2.1 AA)
 */

import { memo, useState, useMemo, useCallback } from 'react'
import { format, formatDistanceToNow } from 'date-fns'
import { de } from 'date-fns/locale'
import {
  Layers,
  RotateCcw,
  GitCompare,
  Check,
  AlertCircle,
  Clock,
  Cpu,
  FileText,
  ChevronDown,
  ChevronUp,
  Sparkles,
  Hash,
  ArrowUpDown,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import {
  useFinanceDocumentVersions,
  useFinanceVersionCompare,
  useRollbackToVersion,
} from '../hooks/use-finanzen-queries'
import type {
  FinanceDocumentVersionSummary,
  FinanceVersionCompareResult,
} from '@/lib/api/services/finance'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Alert, AlertDescription } from '@/components/ui/alert'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { ScrollArea } from '@/components/ui/scroll-area'
import { useToast } from '@/components/ui/use-toast'

// ==================== TYPES ====================

interface FinanceDocumentVersionsProps {
  documentId: string
  className?: string
}

// ==================== BACKEND LABELS ====================

const BACKEND_LABELS: Record<string, { label: string; color: string }> = {
  deepseek: { label: 'DeepSeek', color: 'text-purple-600 bg-purple-100 dark:bg-purple-900/30' },
  'deepseek-janus': { label: 'DeepSeek Janus', color: 'text-purple-600 bg-purple-100 dark:bg-purple-900/30' },
  'got-ocr': { label: 'GOT-OCR', color: 'text-blue-600 bg-blue-100 dark:bg-blue-900/30' },
  surya: { label: 'Surya', color: 'text-green-600 bg-green-100 dark:bg-green-900/30' },
  'surya-gpu': { label: 'Surya GPU', color: 'text-teal-600 bg-teal-100 dark:bg-teal-900/30' },
  docling: { label: 'Docling', color: 'text-orange-600 bg-orange-100 dark:bg-orange-900/30' },
}

// ==================== HELPER FUNCTIONS ====================

function getBackendInfo(backend: string) {
  const key = backend.toLowerCase()
  return BACKEND_LABELS[key] || { label: backend, color: 'text-gray-600 bg-gray-100 dark:bg-gray-900/30' }
}

function formatConfidence(score: number | undefined): string {
  if (score === undefined || score === null) return '-'
  return `${(score * 100).toFixed(1)}%`
}

function formatWordCount(count: number | undefined): string {
  if (count === undefined || count === null) return '-'
  return count.toLocaleString('de-DE')
}

function formatProcessingTime(ms: number | undefined): string {
  if (ms === undefined || ms === null) return '-'
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

// ==================== VERSION ITEM COMPONENT ====================

interface VersionItemProps {
  version: FinanceDocumentVersionSummary
  isSelected: boolean
  compareVersion: number | null
  onSelect: (versionNumber: number) => void
  onCompareSelect: (versionNumber: number) => void
  onRollback: (versionNumber: number) => void
}

const VersionItem = memo(function VersionItem({
  version,
  isSelected,
  compareVersion,
  onSelect: _onSelect,
  onCompareSelect,
  onRollback,
}: VersionItemProps) {
  void _onSelect // Reserved for row click selection
  const backendInfo = getBackendInfo(version.backend)
  const isCompareSelected = compareVersion === version.versionNumber

  const formattedDate = useMemo(() => {
    const date = new Date(version.createdAt)
    return {
      full: format(date, 'dd.MM.yyyy HH:mm:ss', { locale: de }),
      relative: formatDistanceToNow(date, { addSuffix: true, locale: de }),
    }
  }, [version.createdAt])

  return (
    <div
      className={cn(
        'p-4 border rounded-lg transition-colors',
        isSelected && 'border-primary bg-primary/5',
        !isSelected && 'hover:border-muted-foreground/50'
      )}
      role="listitem"
    >
      <div className="flex items-start justify-between gap-4">
        {/* Version header */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-medium flex items-center gap-1">
              <Hash className="h-4 w-4" aria-hidden="true" />
              Version {version.versionNumber}
            </span>
            {version.isCurrent && (
              <Badge variant="default" className="text-xs">
                <Check className="h-3 w-3 mr-1" aria-hidden="true" />
                Aktuell
              </Badge>
            )}
            {version.isRollback && (
              <Badge variant="secondary" className="text-xs">
                <RotateCcw className="h-3 w-3 mr-1" aria-hidden="true" />
                Rollback von V{version.rollbackFromVersion}
              </Badge>
            )}
          </div>

          {/* Metadata row */}
          <div className="flex items-center gap-4 mt-2 text-sm text-muted-foreground flex-wrap">
            <Badge
              variant="outline"
              className={cn('text-xs', backendInfo.color)}
            >
              <Cpu className="h-3 w-3 mr-1" aria-hidden="true" />
              {backendInfo.label}
            </Badge>

            {version.confidenceScore !== undefined && (
              <span className="flex items-center gap-1">
                <Sparkles className="h-3 w-3" aria-hidden="true" />
                {formatConfidence(version.confidenceScore)}
              </span>
            )}

            {version.wordCount !== undefined && (
              <span className="flex items-center gap-1">
                <FileText className="h-3 w-3" aria-hidden="true" />
                {formatWordCount(version.wordCount)} Wörter
              </span>
            )}

            {version.processingTimeMs !== undefined && (
              <span className="flex items-center gap-1">
                <Clock className="h-3 w-3" aria-hidden="true" />
                {formatProcessingTime(version.processingTimeMs)}
              </span>
            )}

            {version.hasUmlauts && (
              <Badge variant="outline" className="text-xs text-green-600">
                Umlaute
              </Badge>
            )}
          </div>

          {/* Version note */}
          {version.versionNote && (
            <p className="mt-2 text-sm text-muted-foreground italic">
              &quot;{version.versionNote}&quot;
            </p>
          )}

          {/* Timestamp */}
          <p className="mt-2 text-xs text-muted-foreground">
            <time dateTime={version.createdAt} title={formattedDate.full}>
              {formattedDate.relative}
            </time>
          </p>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2 shrink-0">
          <Button
            variant={isCompareSelected ? 'secondary' : 'outline'}
            size="sm"
            onClick={() => onCompareSelect(version.versionNumber)}
            aria-pressed={isCompareSelected}
            aria-label={`Version ${version.versionNumber} zum Vergleich ${isCompareSelected ? 'abwählen' : 'auswählen'}`}
          >
            <GitCompare className="h-4 w-4" aria-hidden="true" />
          </Button>

          {!version.isCurrent && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => onRollback(version.versionNumber)}
              aria-label={`Rollback zu Version ${version.versionNumber}`}
            >
              <RotateCcw className="h-4 w-4" aria-hidden="true" />
            </Button>
          )}
        </div>
      </div>
    </div>
  )
})

// ==================== DIFF VIEW COMPONENT ====================

interface DiffViewProps {
  compareResult: FinanceVersionCompareResult
}

const DiffView = memo(function DiffView({ compareResult }: DiffViewProps) {
  const [isExpanded, setIsExpanded] = useState(true)
  const { differences, textDiffUnified, wordCountDelta, confidenceDelta } = compareResult

  return (
    <div className="border rounded-lg overflow-hidden">
      {/* Diff header */}
      <button
        type="button"
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full p-4 bg-muted/50 flex items-center justify-between hover:bg-muted transition-colors"
        aria-expanded={isExpanded}
      >
        <div className="flex items-center gap-2">
          <GitCompare className="h-4 w-4" aria-hidden="true" />
          <span className="font-medium">
            Vergleich: V{compareResult.versionA.versionNumber} vs V{compareResult.versionB.versionNumber}
          </span>
        </div>
        {isExpanded ? (
          <ChevronUp className="h-4 w-4" aria-hidden="true" />
        ) : (
          <ChevronDown className="h-4 w-4" aria-hidden="true" />
        )}
      </button>

      {isExpanded && (
        <div className="p-4 space-y-4">
          {/* Summary stats */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="text-center p-2 bg-muted/30 rounded">
              <p className="text-xs text-muted-foreground">Wörter</p>
              <p className={cn(
                'font-medium',
                wordCountDelta && wordCountDelta > 0 && 'text-green-600',
                wordCountDelta && wordCountDelta < 0 && 'text-red-600'
              )}>
                {wordCountDelta !== undefined && wordCountDelta !== null
                  ? (wordCountDelta > 0 ? `+${wordCountDelta}` : wordCountDelta)
                  : '-'}
              </p>
            </div>

            <div className="text-center p-2 bg-muted/30 rounded">
              <p className="text-xs text-muted-foreground">Konfidenz</p>
              <p className={cn(
                'font-medium',
                confidenceDelta && confidenceDelta > 0 && 'text-green-600',
                confidenceDelta && confidenceDelta < 0 && 'text-red-600'
              )}>
                {confidenceDelta !== undefined && confidenceDelta !== null
                  ? (confidenceDelta > 0 ? `+${(confidenceDelta * 100).toFixed(1)}%` : `${(confidenceDelta * 100).toFixed(1)}%`)
                  : '-'}
              </p>
            </div>

            <div className="text-center p-2 bg-muted/30 rounded">
              <p className="text-xs text-muted-foreground">Backend geändert</p>
              <p className="font-medium">
                {differences.backendChanged ? 'Ja' : 'Nein'}
              </p>
            </div>

            <div className="text-center p-2 bg-muted/30 rounded">
              <p className="text-xs text-muted-foreground">Text-Länge</p>
              <p className={cn(
                'font-medium',
                differences.textLengthDelta > 0 && 'text-green-600',
                differences.textLengthDelta < 0 && 'text-red-600'
              )}>
                {differences.textLengthDelta > 0 ? `+${differences.textLengthDelta}` : differences.textLengthDelta}
              </p>
            </div>
          </div>

          {/* Unified diff view (safe text-based) */}
          {textDiffUnified && (
            <div className="space-y-2">
              <Label>Text-Unterschiede (Unified Diff)</Label>
              <ScrollArea className="h-64 border rounded">
                <pre
                  className="p-4 text-xs font-mono whitespace-pre-wrap overflow-x-auto"
                  aria-label="Text-Unterschiede zwischen den Versionen"
                >
                  {textDiffUnified.split('\n').map((line, index) => {
                    let lineClass = ''
                    if (line.startsWith('+') && !line.startsWith('+++')) {
                      lineClass = 'bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-200'
                    } else if (line.startsWith('-') && !line.startsWith('---')) {
                      lineClass = 'bg-red-100 dark:bg-red-900/30 text-red-800 dark:text-red-200'
                    } else if (line.startsWith('@@')) {
                      lineClass = 'bg-blue-100 dark:bg-blue-900/30 text-blue-800 dark:text-blue-200'
                    }
                    return (
                      <div key={index} className={cn('px-2', lineClass)}>
                        {line || '\u00A0'}
                      </div>
                    )
                  })}
                </pre>
              </ScrollArea>
            </div>
          )}
        </div>
      )}
    </div>
  )
})

// ==================== ROLLBACK DIALOG ====================

interface RollbackDialogProps {
  isOpen: boolean
  targetVersion: number | null
  documentId: string
  onClose: () => void
  onSuccess: () => void
}

const RollbackDialog = memo(function RollbackDialog({
  isOpen,
  targetVersion,
  documentId,
  onClose,
  onSuccess,
}: RollbackDialogProps) {
  const [note, setNote] = useState('')
  const { toast } = useToast()
  const rollbackMutation = useRollbackToVersion()

  const handleRollback = useCallback(async () => {
    if (!targetVersion) return

    try {
      const result = await rollbackMutation.mutateAsync({
        documentId,
        targetVersion,
        rollbackNote: note || undefined,
      })

      toast({
        title: 'Rollback erfolgreich',
        description: result.message,
      })

      setNote('')
      onSuccess()
      onClose()
    } catch (error) {
      toast({
        title: 'Rollback fehlgeschlagen',
        description: error instanceof Error ? error.message : 'Unbekannter Fehler',
        variant: 'destructive',
      })
    }
  }, [documentId, targetVersion, note, rollbackMutation, toast, onSuccess, onClose])

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Rollback zu Version {targetVersion}</DialogTitle>
          <DialogDescription>
            Erstellt eine neue Version mit dem Inhalt von Version {targetVersion}.
            Alle bisherigen Versionen bleiben erhalten.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          <div className="space-y-2">
            <Label htmlFor="rollback-note">
              Notiz (optional)
            </Label>
            <Textarea
              id="rollback-note"
              placeholder="Grund für den Rollback..."
              value={note}
              onChange={(e) => setNote(e.target.value)}
              maxLength={500}
            />
            <p className="text-xs text-muted-foreground">
              {note.length}/500 Zeichen
            </p>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Abbrechen
          </Button>
          <Button
            onClick={handleRollback}
            disabled={rollbackMutation.isPending}
          >
            {rollbackMutation.isPending ? 'Wird ausgeführt...' : 'Rollback durchführen'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
})

// ==================== LOADING SKELETON ====================

function VersionsSkeleton() {
  return (
    <div className="space-y-4">
      {[1, 2, 3].map((i) => (
        <div key={i} className="p-4 border rounded-lg">
          <div className="flex items-center gap-2">
            <Skeleton className="h-5 w-24" />
            <Skeleton className="h-5 w-16" />
          </div>
          <div className="flex items-center gap-4 mt-2">
            <Skeleton className="h-5 w-20" />
            <Skeleton className="h-4 w-12" />
            <Skeleton className="h-4 w-16" />
          </div>
          <Skeleton className="h-4 w-32 mt-2" />
        </div>
      ))}
    </div>
  )
}

// ==================== MAIN COMPONENT ====================

export const FinanceDocumentVersions = memo(function FinanceDocumentVersions({
  documentId,
  className,
}: FinanceDocumentVersionsProps) {
  const [selectedVersion, setSelectedVersion] = useState<number | null>(null)
  const [compareVersionA, setCompareVersionA] = useState<number | null>(null)
  const [compareVersionB, setCompareVersionB] = useState<number | null>(null)
  const [rollbackTarget, setRollbackTarget] = useState<number | null>(null)

  const { data: versionsData, isLoading, error, refetch } = useFinanceDocumentVersions(documentId)
  const { data: compareResult, isLoading: isComparing } = useFinanceVersionCompare(
    documentId,
    compareVersionA || undefined,
    compareVersionB || undefined
  )

  // Handle compare selection
  const handleCompareSelect = useCallback((versionNumber: number) => {
    if (!compareVersionA) {
      setCompareVersionA(versionNumber)
    } else if (compareVersionA === versionNumber) {
      setCompareVersionA(compareVersionB)
      setCompareVersionB(null)
    } else if (!compareVersionB) {
      setCompareVersionB(versionNumber)
    } else if (compareVersionB === versionNumber) {
      setCompareVersionB(null)
    } else {
      // Replace second selection
      setCompareVersionB(versionNumber)
    }
  }, [compareVersionA, compareVersionB])

  const handleRollbackSuccess = useCallback(() => {
    refetch()
    setCompareVersionA(null)
    setCompareVersionB(null)
  }, [refetch])

  if (isLoading) {
    return (
      <div className={cn('p-4', className)} aria-label="Versionen werden geladen...">
        <VersionsSkeleton />
      </div>
    )
  }

  if (error) {
    return (
      <Alert variant="destructive" className={className}>
        <AlertCircle className="h-4 w-4" />
        <AlertDescription>
          Versionen konnten nicht geladen werden.
          {error instanceof Error ? ` ${error.message}` : ''}
        </AlertDescription>
      </Alert>
    )
  }

  if (!versionsData || versionsData.versions.length === 0) {
    return (
      <div
        className={cn('p-4 text-center text-muted-foreground', className)}
        role="status"
      >
        <Layers className="h-8 w-8 mx-auto mb-2 opacity-50" aria-hidden="true" />
        <p>Keine Versionen vorhanden.</p>
      </div>
    )
  }

  return (
    <div className={cn('space-y-4', className)}>
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-medium">
            {versionsData.totalVersions} Version{versionsData.totalVersions !== 1 ? 'en' : ''}
          </h3>
          <p className="text-xs text-muted-foreground">
            Aktuelle Version: V{versionsData.currentVersion}
          </p>
        </div>

        {/* Compare selection info */}
        {(compareVersionA || compareVersionB) && (
          <div className="flex items-center gap-2 text-sm">
            <span className="text-muted-foreground">Vergleich:</span>
            {compareVersionA && (
              <Badge variant="secondary">V{compareVersionA}</Badge>
            )}
            {compareVersionA && compareVersionB && (
              <ArrowUpDown className="h-3 w-3 text-muted-foreground" aria-hidden="true" />
            )}
            {compareVersionB && (
              <Badge variant="secondary">V{compareVersionB}</Badge>
            )}
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setCompareVersionA(null)
                setCompareVersionB(null)
              }}
              className="text-xs"
            >
              Zurücksetzen
            </Button>
          </div>
        )}
      </div>

      {/* Compare result */}
      {isComparing && (
        <div className="p-4 border rounded-lg">
          <div className="flex items-center gap-2">
            <Skeleton className="h-5 w-5 rounded-full animate-spin" />
            <span className="text-sm text-muted-foreground">Versionen werden verglichen...</span>
          </div>
        </div>
      )}

      {compareResult && !isComparing && (
        <DiffView compareResult={compareResult} />
      )}

      {/* Version list */}
      <div role="list" aria-label="Versionsliste" className="space-y-3">
        {versionsData.versions.map((version) => (
          <VersionItem
            key={version.id}
            version={version}
            isSelected={selectedVersion === version.versionNumber}
            compareVersion={
              compareVersionA === version.versionNumber || compareVersionB === version.versionNumber
                ? version.versionNumber
                : null
            }
            onSelect={setSelectedVersion}
            onCompareSelect={handleCompareSelect}
            onRollback={setRollbackTarget}
          />
        ))}
      </div>

      {/* Rollback dialog */}
      <RollbackDialog
        isOpen={rollbackTarget !== null}
        targetVersion={rollbackTarget}
        documentId={documentId}
        onClose={() => setRollbackTarget(null)}
        onSuccess={handleRollbackSuccess}
      />
    </div>
  )
})

export default FinanceDocumentVersions
