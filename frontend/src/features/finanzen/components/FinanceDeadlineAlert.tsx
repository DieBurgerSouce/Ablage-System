/**
 * FinanceDeadlineAlert - Deadline Warning Banner
 *
 * Zeigt Warnungen für:
 * - Überfällige Fristen (rot)
 * - Bald ablaufende Fristen (gelb/orange)
 * - Kommende Fristen (blau)
 */

import { useMemo } from 'react'
import { Link } from '@tanstack/react-router'
import { AlertTriangle, Clock, Calendar, ChevronRight, X, Bell } from 'lucide-react'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

export interface DeadlineItem {
  id: string
  documentId: string
  documentName: string
  category: string
  categoryLabel: string
  year: string
  deadline: string // ISO date string
  type: 'einspruchsfrist' | 'zahlungsfrist' | 'abgabefrist' | 'sonstige'
  aktenzeichen?: string
}

interface FinanceDeadlineAlertProps {
  deadlines: DeadlineItem[]
  onDismiss?: () => void
  className?: string
}

// Calculate days until deadline
function getDaysUntil(dateString: string): number {
  const deadline = new Date(dateString)
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  deadline.setHours(0, 0, 0, 0)
  const diffTime = deadline.getTime() - today.getTime()
  return Math.ceil(diffTime / (1000 * 60 * 60 * 24))
}

// Categorize deadlines by urgency
function categorizeDeadlines(deadlines: DeadlineItem[]) {
  const overdue: DeadlineItem[] = []
  const urgent: DeadlineItem[] = [] // <= 7 days
  const upcoming: DeadlineItem[] = [] // 8-30 days
  const later: DeadlineItem[] = [] // > 30 days

  deadlines.forEach((deadline) => {
    const days = getDaysUntil(deadline.deadline)
    if (days < 0) {
      overdue.push(deadline)
    } else if (days <= 7) {
      urgent.push(deadline)
    } else if (days <= 30) {
      upcoming.push(deadline)
    } else {
      later.push(deadline)
    }
  })

  return { overdue, urgent, upcoming, later }
}

// Format deadline type to German
function formatDeadlineType(type: DeadlineItem['type']): string {
  switch (type) {
    case 'einspruchsfrist':
      return 'Einspruchsfrist'
    case 'zahlungsfrist':
      return 'Zahlungsfrist'
    case 'abgabefrist':
      return 'Abgabefrist'
    case 'sonstige':
    default:
      return 'Frist'
  }
}

// Format date to German locale
function formatDate(dateString: string): string {
  return new Date(dateString).toLocaleDateString('de-DE', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  })
}

// Format relative time
function formatRelativeTime(days: number): string {
  if (days === 0) return 'Heute'
  if (days === 1) return 'Morgen'
  if (days < 0) return `${Math.abs(days)} Tage überfällig`
  if (days <= 7) return `in ${days} Tagen`
  if (days <= 30) return `in ${Math.ceil(days / 7)} Wochen`
  return `in ${Math.ceil(days / 30)} Monaten`
}

export function FinanceDeadlineAlert({
  deadlines,
  onDismiss,
  className,
}: FinanceDeadlineAlertProps) {
  const { overdue, urgent, upcoming } = useMemo(() => categorizeDeadlines(deadlines), [deadlines])

  // Don't render if no critical deadlines
  if (overdue.length === 0 && urgent.length === 0 && upcoming.length === 0) {
    return null
  }

  // Determine alert severity
  const hasOverdue = overdue.length > 0
  const hasUrgent = urgent.length > 0
  const _totalCritical = overdue.length + urgent.length
  void _totalCritical // Reserved for future badge

  return (
    <Alert
      variant={hasOverdue ? 'destructive' : 'default'}
      className={cn(
        'relative',
        hasOverdue
          ? 'border-red-500 bg-red-50 dark:bg-red-950/20'
          : hasUrgent
            ? 'border-amber-500 bg-amber-50 dark:bg-amber-950/20'
            : 'border-blue-500 bg-blue-50 dark:bg-blue-950/20',
        className
      )}
      role="alert"
      aria-live="polite"
      aria-label={
        hasOverdue
          ? `Warnung: ${overdue.length} überfällige Fristen`
          : hasUrgent
            ? `Achtung: ${urgent.length} dringende Fristen`
            : `Hinweis: ${upcoming.length} anstehende Fristen`
      }
    >
      {/* Dismiss Button */}
      {onDismiss && (
        <Button
          variant="ghost"
          size="icon"
          className="absolute right-2 top-2 h-6 w-6"
          onClick={onDismiss}
          aria-label="Warnung schließen"
        >
          <X className="h-4 w-4" />
        </Button>
      )}

      {/* Header */}
      <div className="flex items-center gap-2">
        {hasOverdue ? (
          <AlertTriangle className="h-5 w-5 text-red-600" aria-hidden="true" />
        ) : hasUrgent ? (
          <Bell className="h-5 w-5 text-amber-600" aria-hidden="true" />
        ) : (
          <Clock className="h-5 w-5 text-blue-600" aria-hidden="true" />
        )}
        <AlertTitle
          className={cn(
            'text-base font-semibold',
            hasOverdue
              ? 'text-red-800 dark:text-red-300'
              : hasUrgent
                ? 'text-amber-800 dark:text-amber-300'
                : 'text-blue-800 dark:text-blue-300'
          )}
        >
          {hasOverdue
            ? `${overdue.length} überfällige Frist${overdue.length > 1 ? 'en' : ''}`
            : hasUrgent
              ? `${urgent.length} dringende Frist${urgent.length > 1 ? 'en' : ''}`
              : `${upcoming.length} anstehende Frist${upcoming.length > 1 ? 'en' : ''}`}
        </AlertTitle>
      </div>

      <AlertDescription className="mt-3 space-y-3">
        {/* Overdue Items */}
        {overdue.length > 0 && (
          <div className="space-y-2">
            {overdue.slice(0, 3).map((item) => (
              <DeadlineItemRow key={item.id} item={item} variant="overdue" />
            ))}
            {overdue.length > 3 && (
              <p className="text-sm text-red-600 dark:text-red-400">
                + {overdue.length - 3} weitere überfällige Fristen
              </p>
            )}
          </div>
        )}

        {/* Urgent Items */}
        {urgent.length > 0 && (
          <div className="space-y-2">
            {!hasOverdue && <div className="text-xs font-medium text-amber-700 dark:text-amber-400 uppercase tracking-wide">Dringend (7 Tage)</div>}
            {urgent.slice(0, hasOverdue ? 2 : 3).map((item) => (
              <DeadlineItemRow key={item.id} item={item} variant="urgent" />
            ))}
            {urgent.length > (hasOverdue ? 2 : 3) && (
              <p className="text-sm text-amber-600 dark:text-amber-400">
                + {urgent.length - (hasOverdue ? 2 : 3)} weitere dringende Fristen
              </p>
            )}
          </div>
        )}

        {/* Upcoming Items (only show if no overdue/urgent) */}
        {!hasOverdue && !hasUrgent && upcoming.length > 0 && (
          <div className="space-y-2">
            {upcoming.slice(0, 3).map((item) => (
              <DeadlineItemRow key={item.id} item={item} variant="upcoming" />
            ))}
            {upcoming.length > 3 && (
              <p className="text-sm text-blue-600 dark:text-blue-400">
                + {upcoming.length - 3} weitere anstehende Fristen
              </p>
            )}
          </div>
        )}

        {/* Summary Badge */}
        {(hasOverdue || hasUrgent) && upcoming.length > 0 && (
          <div className="flex items-center gap-2 pt-2 border-t border-current/10">
            <Badge variant="outline" className="text-xs">
              <Calendar className="w-3 h-3 mr-1" aria-hidden="true" />
              {upcoming.length} weitere in 30 Tagen
            </Badge>
          </div>
        )}
      </AlertDescription>
    </Alert>
  )
}

// Individual deadline row
function DeadlineItemRow({
  item,
  variant,
}: {
  item: DeadlineItem
  variant: 'overdue' | 'urgent' | 'upcoming'
}) {
  const days = getDaysUntil(item.deadline)

  return (
    <Link
      to="/finanzen/$year/$category"
      params={{ year: item.year, category: item.category }}
      className={cn(
        'flex items-center justify-between p-2 rounded-md transition-colors group',
        'focus:outline-none focus:ring-2 focus:ring-offset-2',
        variant === 'overdue'
          ? 'bg-red-100/50 hover:bg-red-100 dark:bg-red-900/20 dark:hover:bg-red-900/30 focus:ring-red-500'
          : variant === 'urgent'
            ? 'bg-amber-100/50 hover:bg-amber-100 dark:bg-amber-900/20 dark:hover:bg-amber-900/30 focus:ring-amber-500'
            : 'bg-blue-100/50 hover:bg-blue-100 dark:bg-blue-900/20 dark:hover:bg-blue-900/30 focus:ring-blue-500'
      )}
      aria-label={`${item.documentName} - ${formatDeadlineType(item.type)} ${formatRelativeTime(days)}, ${item.categoryLabel}`}
    >
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="font-medium truncate">{item.documentName}</span>
          <Badge
            variant="outline"
            className={cn(
              'text-xs shrink-0',
              variant === 'overdue'
                ? 'border-red-300 text-red-700 dark:border-red-700 dark:text-red-400'
                : variant === 'urgent'
                  ? 'border-amber-300 text-amber-700 dark:border-amber-700 dark:text-amber-400'
                  : 'border-blue-300 text-blue-700 dark:border-blue-700 dark:text-blue-400'
            )}
          >
            {formatDeadlineType(item.type)}
          </Badge>
        </div>
        <div className="flex items-center gap-2 text-xs text-muted-foreground mt-0.5">
          <span>{item.categoryLabel}</span>
          {item.aktenzeichen && (
            <>
              <span>·</span>
              <span>{item.aktenzeichen}</span>
            </>
          )}
        </div>
      </div>

      <div className="flex items-center gap-2 shrink-0 ml-2">
        <div className="text-right">
          <div
            className={cn(
              'text-sm font-medium',
              variant === 'overdue'
                ? 'text-red-700 dark:text-red-400'
                : variant === 'urgent'
                  ? 'text-amber-700 dark:text-amber-400'
                  : 'text-blue-700 dark:text-blue-400'
            )}
          >
            {formatRelativeTime(days)}
          </div>
          <div className="text-xs text-muted-foreground">{formatDate(item.deadline)}</div>
        </div>
        <ChevronRight className="w-4 h-4 text-muted-foreground group-hover:translate-x-0.5 transition-transform" aria-hidden="true" />
      </div>
    </Link>
  )
}

export default FinanceDeadlineAlert
