/**
 * FinanceDocumentCard - Mobile-optimierte Dokument-Karte
 *
 * Wird auf mobilen Geräten anstelle der Tabelle verwendet.
 * Zeigt alle wichtigen Dokument-Informationen in kompakter Form.
 *
 * Optimiert mit React.memo für bessere Performance bei langen Listen.
 */

import { memo, useCallback } from 'react'
import { FileText, Calendar, AlertTriangle, Clock, Euro, ShieldAlert } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { formatDate, formatCurrency } from '../utils/format'
import type { FinanceCategoryDocument } from '@/lib/api/services/finance'

interface FinanceDocumentCardProps {
  document: FinanceCategoryDocument
  showAmounts?: boolean
  showDeadlines?: boolean
  onClick?: () => void
}

/**
 * Mobile Dokument-Karte mit Touch-optimiertem Layout
 */
const FinanceDocumentCardInner = memo(function FinanceDocumentCard({
  document,
  showAmounts = false,
  showDeadlines = false,
  onClick,
}: FinanceDocumentCardProps) {
  const isExpired =
    document.einspruchsfrist && new Date(document.einspruchsfrist) < new Date()

  return (
    <Card
      className="cursor-pointer hover:bg-muted/50 active:bg-muted/70 transition-colors touch-manipulation"
      onClick={onClick}
      role="button"
      tabIndex={0}
      aria-label={`Dokument: ${document.originalFilename || document.filename}`}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onClick?.()
        }
      }}
    >
      <CardContent className="p-4">
        {/* Header: Dateiname und Status */}
        <div className="flex items-start justify-between gap-3 mb-3">
          <div className="flex items-center gap-2 min-w-0 flex-1">
            <FileText className="w-5 h-5 text-emerald-500 flex-shrink-0" />
            <span className="font-medium text-sm truncate">
              {document.originalFilename || document.filename}
            </span>
            {document.hasAnomalies && (
              <Badge
                variant="outline"
                className="ml-1 gap-1 px-1.5 py-0 text-xs bg-amber-50 text-amber-700 border-amber-300 dark:bg-amber-950/50 dark:text-amber-400 dark:border-amber-700 flex-shrink-0"
                title={`${document.anomalyCount} Anomalie${document.anomalyCount !== 1 ? 'n' : ''} erkannt`}
              >
                <ShieldAlert className="w-3 h-3" />
                {document.anomalyCount}
              </Badge>
            )}
          </div>
          <Badge
            variant={document.processingStatus === 'completed' ? 'secondary' : 'outline'}
            className={
              document.processingStatus === 'completed'
                ? 'flex-shrink-0'
                : 'flex-shrink-0 bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950 dark:text-amber-400 dark:border-amber-800'
            }
          >
            {document.processingStatus === 'completed' ? 'Verarbeitet' : 'Ausstehend'}
          </Badge>
        </div>

        {/* Meta-Informationen Grid */}
        <div className="grid grid-cols-2 gap-3 text-sm">
          {/* Datum */}
          <div className="flex items-center gap-1.5 text-muted-foreground">
            <Calendar className="w-3.5 h-3.5" />
            <span>{formatDate(document.documentDate || document.createdAt)}</span>
          </div>

          {/* Aktenzeichen (wenn vorhanden) */}
          {showDeadlines && document.aktenzeichen && (
            <div className="flex items-center gap-1.5 text-muted-foreground">
              <FileText className="w-3.5 h-3.5" />
              <span className="font-mono text-xs truncate">{document.aktenzeichen}</span>
            </div>
          )}

          {/* Beträge */}
          {showAmounts && (document.totalAmount || document.nachzahlung || document.erstattung) && (
            <div className="col-span-2 flex flex-wrap gap-2 mt-1">
              {document.totalAmount && (
                <div className="flex items-center gap-1">
                  <Euro className="w-3.5 h-3.5 text-muted-foreground" />
                  <span className="font-mono text-sm">{formatCurrency(document.totalAmount)}</span>
                </div>
              )}
              {document.nachzahlung && (
                <Badge
                  variant="outline"
                  className="bg-red-50 text-red-700 border-red-200 dark:bg-red-950 dark:text-red-400 dark:border-red-800"
                >
                  -{formatCurrency(document.nachzahlung)}
                </Badge>
              )}
              {document.erstattung && (
                <Badge
                  variant="outline"
                  className="bg-green-50 text-green-700 border-green-200 dark:bg-green-950 dark:text-green-400 dark:border-green-800"
                >
                  +{formatCurrency(document.erstattung)}
                </Badge>
              )}
            </div>
          )}

          {/* Einspruchsfrist */}
          {showDeadlines && document.einspruchsfrist && (
            <div className="col-span-2 mt-1">
              {isExpired ? (
                <Badge variant="destructive" className="gap-1">
                  <AlertTriangle className="w-3 h-3" />
                  Frist abgelaufen
                </Badge>
              ) : (
                <div className="flex items-center gap-1.5 text-amber-600 dark:text-amber-400">
                  <Clock className="w-3.5 h-3.5" />
                  <span className="text-xs">
                    Frist bis {formatDate(document.einspruchsfrist)}
                  </span>
                </div>
              )}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  )
})

// Re-export for named import compatibility
export const FinanceDocumentCard = FinanceDocumentCardInner

/**
 * Mobile Dokument-Liste als Card-Grid
 * Optimiert mit useCallback für stabile Referenzen
 */
interface FinanceDocumentCardListProps {
  documents: FinanceCategoryDocument[]
  showAmounts?: boolean
  showDeadlines?: boolean
  onDocumentClick?: (doc: FinanceCategoryDocument) => void
}

export const FinanceDocumentCardList = memo(function FinanceDocumentCardList({
  documents,
  showAmounts = false,
  showDeadlines = false,
  onDocumentClick,
}: FinanceDocumentCardListProps) {
  // Memoized click handler factory
  const handleClick = useCallback(
    (doc: FinanceCategoryDocument) => () => onDocumentClick?.(doc),
    [onDocumentClick]
  )

  if (documents.length === 0) {
    return null
  }

  return (
    <div className="space-y-3" role="list" aria-label="Dokumentenliste">
      {documents.map((doc) => (
        <FinanceDocumentCardInner
          key={doc.id}
          document={doc}
          showAmounts={showAmounts}
          showDeadlines={showDeadlines}
          onClick={handleClick(doc)}
        />
      ))}
    </div>
  )
})

export default FinanceDocumentCard
