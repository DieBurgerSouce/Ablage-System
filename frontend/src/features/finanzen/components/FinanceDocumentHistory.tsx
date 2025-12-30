/**
 * FinanceDocumentHistory - Audit Trail Komponente
 *
 * Zeigt die vollständige Änderungs-History eines Finanz-Dokuments.
 *
 * Features:
 * - Chronologische Timeline
 * - Aktionstyp-Icons
 * - Benutzer-Info
 * - Änderungsdetails (diff-View)
 * - Accessibility-konform
 */

import { memo, useMemo } from 'react'
import { format, formatDistanceToNow } from 'date-fns'
import { de } from 'date-fns/locale'
import {
  FileText,
  Edit,
  Trash2,
  RefreshCw,
  FolderSync,
  Calendar,
  CalendarX,
  ScanLine,
  Layers,
  Clock,
  User,
  ChevronDown,
  ChevronUp,
  AlertCircle,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { useFinanceDocumentHistory } from '../hooks/use-finanzen-queries'
import type { FinanceHistoryItem } from '@/lib/api/services/finance'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { useState } from 'react'

// ==================== TYPES ====================

interface FinanceDocumentHistoryProps {
  documentId: string
  className?: string
}

type ActionType = FinanceHistoryItem['action']

// ==================== ACTION CONFIGURATION ====================

const ACTION_CONFIG: Record<ActionType, {
  label: string
  icon: typeof FileText
  color: string
  bgColor: string
}> = {
  created: {
    label: 'Erstellt',
    icon: FileText,
    color: 'text-green-600',
    bgColor: 'bg-green-100 dark:bg-green-900/30',
  },
  updated: {
    label: 'Bearbeitet',
    icon: Edit,
    color: 'text-blue-600',
    bgColor: 'bg-blue-100 dark:bg-blue-900/30',
  },
  deleted: {
    label: 'Gelöscht',
    icon: Trash2,
    color: 'text-red-600',
    bgColor: 'bg-red-100 dark:bg-red-900/30',
  },
  restored: {
    label: 'Wiederhergestellt',
    icon: RefreshCw,
    color: 'text-purple-600',
    bgColor: 'bg-purple-100 dark:bg-purple-900/30',
  },
  category_changed: {
    label: 'Kategorie geändert',
    icon: FolderSync,
    color: 'text-amber-600',
    bgColor: 'bg-amber-100 dark:bg-amber-900/30',
  },
  year_changed: {
    label: 'Jahr geändert',
    icon: Calendar,
    color: 'text-amber-600',
    bgColor: 'bg-amber-100 dark:bg-amber-900/30',
  },
  ocr_completed: {
    label: 'OCR abgeschlossen',
    icon: ScanLine,
    color: 'text-teal-600',
    bgColor: 'bg-teal-100 dark:bg-teal-900/30',
  },
  deadline_set: {
    label: 'Frist gesetzt',
    icon: Calendar,
    color: 'text-orange-600',
    bgColor: 'bg-orange-100 dark:bg-orange-900/30',
  },
  deadline_removed: {
    label: 'Frist entfernt',
    icon: CalendarX,
    color: 'text-gray-600',
    bgColor: 'bg-gray-100 dark:bg-gray-900/30',
  },
  bulk_update: {
    label: 'Massenaktualisierung',
    icon: Layers,
    color: 'text-indigo-600',
    bgColor: 'bg-indigo-100 dark:bg-indigo-900/30',
  },
}

// ==================== FIELD LABELS ====================

const FIELD_LABELS: Record<string, string> = {
  category: 'Kategorie',
  year: 'Jahr',
  einspruchsfrist: 'Einspruchsfrist',
  zahlungsfrist: 'Zahlungsfrist',
  nachzahlung: 'Nachzahlung',
  erstattung: 'Erstattung',
  aktenzeichen: 'Aktenzeichen',
  steuernummer: 'Steuernummer',
  finanzamt: 'Finanzamt',
  steuerart: 'Steuerart',
  document_date: 'Dokumentdatum',
  document_number: 'Dokumentnummer',
  total_amount: 'Betrag',
}

// ==================== HELPER FUNCTIONS ====================

function formatFieldValue(value: unknown): string {
  if (value === null || value === undefined) return '-'
  if (typeof value === 'boolean') return value ? 'Ja' : 'Nein'
  if (typeof value === 'number') return value.toLocaleString('de-DE')
  if (typeof value === 'string') {
    // Try to detect date strings
    if (/^\d{4}-\d{2}-\d{2}/.test(value)) {
      try {
        const date = new Date(value)
        return format(date, 'dd.MM.yyyy', { locale: de })
      } catch {
        return value
      }
    }
    return value
  }
  return String(value)
}

// ==================== HISTORY ITEM COMPONENT ====================

interface HistoryItemProps {
  item: FinanceHistoryItem
  isLast: boolean
}

const HistoryItem = memo(function HistoryItem({ item, isLast }: HistoryItemProps) {
  const [isExpanded, setIsExpanded] = useState(false)
  const config = ACTION_CONFIG[item.action] || ACTION_CONFIG.updated
  const Icon = config.icon

  const hasDetails = item.changedFields.length > 0 ||
    Object.keys(item.oldValues).length > 0 ||
    Object.keys(item.newValues).length > 0

  const formattedDate = useMemo(() => {
    const date = new Date(item.createdAt)
    return {
      full: format(date, 'dd.MM.yyyy HH:mm:ss', { locale: de }),
      relative: formatDistanceToNow(date, { addSuffix: true, locale: de }),
    }
  }, [item.createdAt])

  return (
    <div className="relative pl-8 pb-6">
      {/* Timeline line */}
      {!isLast && (
        <div
          className="absolute left-3 top-6 bottom-0 w-0.5 bg-border"
          aria-hidden="true"
        />
      )}

      {/* Timeline dot */}
      <div
        className={cn(
          'absolute left-0 top-0.5 w-6 h-6 rounded-full flex items-center justify-center',
          config.bgColor
        )}
        aria-hidden="true"
      >
        <Icon className={cn('h-3.5 w-3.5', config.color)} />
      </div>

      {/* Content */}
      <Collapsible open={isExpanded} onOpenChange={setIsExpanded}>
        <div className="min-w-0">
          {/* Header */}
          <div className="flex items-start justify-between gap-2">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <Badge variant="secondary" className={cn('text-xs', config.color)}>
                  {config.label}
                </Badge>
                {item.userName || item.userEmail ? (
                  <span className="text-sm text-muted-foreground flex items-center gap-1">
                    <User className="h-3 w-3" aria-hidden="true" />
                    {item.userName || item.userEmail}
                  </span>
                ) : null}
              </div>

              {/* Description */}
              {item.description && (
                <p className="text-sm text-foreground mt-1">
                  {item.description}
                </p>
              )}
            </div>

            {/* Timestamp */}
            <div className="flex items-center gap-2 text-xs text-muted-foreground shrink-0">
              <Clock className="h-3 w-3" aria-hidden="true" />
              <time
                dateTime={item.createdAt}
                title={formattedDate.full}
              >
                {formattedDate.relative}
              </time>
            </div>
          </div>

          {/* Expandable details */}
          {hasDetails && (
            <CollapsibleTrigger
              className="mt-2 text-xs text-muted-foreground hover:text-foreground flex items-center gap-1 transition-colors"
              aria-label={isExpanded ? 'Details ausblenden' : 'Details anzeigen'}
            >
              {isExpanded ? (
                <ChevronUp className="h-3 w-3" aria-hidden="true" />
              ) : (
                <ChevronDown className="h-3 w-3" aria-hidden="true" />
              )}
              {item.changedFields.length} Feld(er) geändert
            </CollapsibleTrigger>
          )}

          <CollapsibleContent className="mt-2">
            {item.changedFields.length > 0 && (
              <div
                className="text-sm border rounded-md overflow-hidden"
                role="table"
                aria-label="Geänderte Felder"
              >
                <div className="bg-muted/50 px-3 py-1.5 border-b">
                  <div className="grid grid-cols-3 gap-2 text-xs font-medium text-muted-foreground">
                    <span>Feld</span>
                    <span>Vorher</span>
                    <span>Nachher</span>
                  </div>
                </div>
                <div className="divide-y">
                  {item.changedFields.map((field) => (
                    <div
                      key={field}
                      className="grid grid-cols-3 gap-2 px-3 py-2 text-xs"
                    >
                      <span className="font-medium">
                        {FIELD_LABELS[field] || field}
                      </span>
                      <span className="text-red-600 dark:text-red-400 line-through">
                        {formatFieldValue(item.oldValues[field])}
                      </span>
                      <span className="text-green-600 dark:text-green-400">
                        {formatFieldValue(item.newValues[field])}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </CollapsibleContent>
        </div>
      </Collapsible>
    </div>
  )
})

// ==================== LOADING SKELETON ====================

function HistorySkeleton() {
  return (
    <div className="space-y-4">
      {[1, 2, 3].map((i) => (
        <div key={i} className="pl-8 relative">
          <Skeleton className="absolute left-0 top-0 w-6 h-6 rounded-full" />
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <Skeleton className="h-5 w-24" />
              <Skeleton className="h-4 w-32" />
            </div>
            <Skeleton className="h-4 w-full max-w-xs" />
          </div>
        </div>
      ))}
    </div>
  )
}

// ==================== MAIN COMPONENT ====================

export const FinanceDocumentHistory = memo(function FinanceDocumentHistory({
  documentId,
  className,
}: FinanceDocumentHistoryProps) {
  const { data, isLoading, error } = useFinanceDocumentHistory(documentId)

  if (isLoading) {
    return (
      <div className={cn('p-4', className)} aria-label="History wird geladen...">
        <HistorySkeleton />
      </div>
    )
  }

  if (error) {
    return (
      <Alert variant="destructive" className={className}>
        <AlertCircle className="h-4 w-4" />
        <AlertDescription>
          History konnte nicht geladen werden.
          {error instanceof Error ? ` ${error.message}` : ''}
        </AlertDescription>
      </Alert>
    )
  }

  if (!data || data.items.length === 0) {
    return (
      <div
        className={cn('p-4 text-center text-muted-foreground', className)}
        role="status"
      >
        <FileText className="h-8 w-8 mx-auto mb-2 opacity-50" aria-hidden="true" />
        <p>Keine History-Einträge vorhanden.</p>
      </div>
    )
  }

  return (
    <div
      className={cn('p-4', className)}
      role="log"
      aria-label={`Dokument-History: ${data.total} Einträge`}
    >
      <div className="mb-4">
        <h3 className="text-sm font-medium text-muted-foreground">
          {data.total} Änderung{data.total !== 1 ? 'en' : ''}
        </h3>
      </div>

      <div role="list" aria-label="History-Timeline">
        {data.items.map((item, index) => (
          <HistoryItem
            key={item.id}
            item={item}
            isLast={index === data.items.length - 1}
          />
        ))}
      </div>
    </div>
  )
})

export default FinanceDocumentHistory
