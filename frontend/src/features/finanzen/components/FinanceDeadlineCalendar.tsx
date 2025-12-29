/**
 * FinanceDeadlineCalendar - Kalender-Ansicht für Fristen
 *
 * Features:
 * - Monatsansicht mit Frist-Markierungen
 * - Farbcodierung nach Dringlichkeit
 * - Klick auf Tag zeigt Details
 * - Navigation zwischen Monaten
 */

import { useState, useMemo } from 'react'
import { Link } from '@tanstack/react-router'
import {
  ChevronLeft,
  ChevronRight,
  Calendar as CalendarIcon,
  AlertTriangle,
  Clock,
  FileText,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { ScrollArea } from '@/components/ui/scroll-area'
import { cn } from '@/lib/utils'
import type { DeadlineItem } from './FinanceDeadlineAlert'

interface FinanceDeadlineCalendarProps {
  deadlines: DeadlineItem[]
  className?: string
}

// German month names
const MONTH_NAMES = [
  'Januar',
  'Februar',
  'Maerz',
  'April',
  'Mai',
  'Juni',
  'Juli',
  'August',
  'September',
  'Oktober',
  'November',
  'Dezember',
]

// German day names (short)
const DAY_NAMES = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So']

// Get days in month
function getDaysInMonth(year: number, month: number): number {
  return new Date(year, month + 1, 0).getDate()
}

// Get first day of month (0 = Sunday, 1 = Monday, etc.)
function getFirstDayOfMonth(year: number, month: number): number {
  const day = new Date(year, month, 1).getDay()
  // Convert to Monday-based (0 = Monday, 6 = Sunday)
  return day === 0 ? 6 : day - 1
}

// Check if date is today
function isToday(year: number, month: number, day: number): boolean {
  const today = new Date()
  return today.getFullYear() === year && today.getMonth() === month && today.getDate() === day
}

// Format date to ISO string (YYYY-MM-DD)
function toISODateString(year: number, month: number, day: number): string {
  return `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`
}

// Get deadline urgency
function getUrgency(dateString: string): 'overdue' | 'urgent' | 'upcoming' | 'later' {
  const deadline = new Date(dateString)
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  deadline.setHours(0, 0, 0, 0)
  const diffDays = Math.ceil((deadline.getTime() - today.getTime()) / (1000 * 60 * 60 * 24))

  if (diffDays < 0) return 'overdue'
  if (diffDays <= 7) return 'urgent'
  if (diffDays <= 30) return 'upcoming'
  return 'later'
}

// Format deadline type
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

export function FinanceDeadlineCalendar({ deadlines, className }: FinanceDeadlineCalendarProps) {
  const today = new Date()
  const [currentYear, setCurrentYear] = useState(today.getFullYear())
  const [currentMonth, setCurrentMonth] = useState(today.getMonth())
  const [selectedDay, setSelectedDay] = useState<{
    year: number
    month: number
    day: number
  } | null>(null)

  // Group deadlines by date
  const deadlinesByDate = useMemo(() => {
    const map = new Map<string, DeadlineItem[]>()
    deadlines.forEach((deadline) => {
      const dateKey = deadline.deadline.split('T')[0] // Get YYYY-MM-DD part
      if (!map.has(dateKey)) {
        map.set(dateKey, [])
      }
      map.get(dateKey)!.push(deadline)
    })
    return map
  }, [deadlines])

  // Navigation
  const goToPreviousMonth = () => {
    if (currentMonth === 0) {
      setCurrentMonth(11)
      setCurrentYear(currentYear - 1)
    } else {
      setCurrentMonth(currentMonth - 1)
    }
  }

  const goToNextMonth = () => {
    if (currentMonth === 11) {
      setCurrentMonth(0)
      setCurrentYear(currentYear + 1)
    } else {
      setCurrentMonth(currentMonth + 1)
    }
  }

  const goToToday = () => {
    setCurrentYear(today.getFullYear())
    setCurrentMonth(today.getMonth())
  }

  // Generate calendar days
  const calendarDays = useMemo(() => {
    const daysInMonth = getDaysInMonth(currentYear, currentMonth)
    const firstDay = getFirstDayOfMonth(currentYear, currentMonth)
    const days: (number | null)[] = []

    // Add empty cells for days before the first day of the month
    for (let i = 0; i < firstDay; i++) {
      days.push(null)
    }

    // Add days of the month
    for (let i = 1; i <= daysInMonth; i++) {
      days.push(i)
    }

    return days
  }, [currentYear, currentMonth])

  // Get deadlines for selected day
  const selectedDayDeadlines = useMemo(() => {
    if (!selectedDay) return []
    const dateKey = toISODateString(selectedDay.year, selectedDay.month, selectedDay.day)
    return deadlinesByDate.get(dateKey) || []
  }, [selectedDay, deadlinesByDate])

  // Get most urgent status for a day
  const getDayStatus = (day: number): 'overdue' | 'urgent' | 'upcoming' | 'later' | null => {
    const dateKey = toISODateString(currentYear, currentMonth, day)
    const dayDeadlines = deadlinesByDate.get(dateKey)
    if (!dayDeadlines || dayDeadlines.length === 0) return null

    // Return most urgent status
    if (dayDeadlines.some((d) => getUrgency(d.deadline) === 'overdue')) return 'overdue'
    if (dayDeadlines.some((d) => getUrgency(d.deadline) === 'urgent')) return 'urgent'
    if (dayDeadlines.some((d) => getUrgency(d.deadline) === 'upcoming')) return 'upcoming'
    return 'later'
  }

  return (
    <>
      <Card className={cn('', className)}>
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <CardTitle className="text-lg flex items-center gap-2">
              <CalendarIcon className="w-5 h-5 text-emerald-500" />
              Fristen-Kalender
            </CardTitle>
            <div className="flex items-center gap-1">
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8"
                onClick={goToPreviousMonth}
                aria-label="Vorheriger Monat"
              >
                <ChevronLeft className="w-4 h-4" />
              </Button>
              <Button
                variant="ghost"
                size="sm"
                className="h-8 text-xs"
                onClick={goToToday}
              >
                Heute
              </Button>
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8"
                onClick={goToNextMonth}
                aria-label="Nächster Monat"
              >
                <ChevronRight className="w-4 h-4" />
              </Button>
            </div>
          </div>
          <div className="text-center font-medium text-lg">
            {MONTH_NAMES[currentMonth]} {currentYear}
          </div>
        </CardHeader>

        <CardContent className="pt-2">
          {/* Day names header */}
          <div className="grid grid-cols-7 gap-1 mb-2">
            {DAY_NAMES.map((day) => (
              <div
                key={day}
                className="text-center text-xs font-medium text-muted-foreground py-1"
              >
                {day}
              </div>
            ))}
          </div>

          {/* Calendar grid */}
          <div className="grid grid-cols-7 gap-1">
            {calendarDays.map((day, index) => {
              if (day === null) {
                return <div key={`empty-${index}`} className="aspect-square" />
              }

              const dayStatus = getDayStatus(day)
              const isCurrentDay = isToday(currentYear, currentMonth, day)
              const dateKey = toISODateString(currentYear, currentMonth, day)
              const dayDeadlineCount = deadlinesByDate.get(dateKey)?.length || 0

              return (
                <button
                  key={day}
                  onClick={() => {
                    if (dayDeadlineCount > 0) {
                      setSelectedDay({ year: currentYear, month: currentMonth, day })
                    }
                  }}
                  disabled={dayDeadlineCount === 0}
                  className={cn(
                    'aspect-square flex flex-col items-center justify-center rounded-md text-sm relative',
                    'transition-colors',
                    isCurrentDay && 'ring-2 ring-emerald-500 ring-offset-1',
                    dayDeadlineCount > 0 && 'cursor-pointer hover:bg-muted/50',
                    dayDeadlineCount === 0 && 'text-muted-foreground',
                    dayStatus === 'overdue' && 'bg-red-100 dark:bg-red-950/30 text-red-700 dark:text-red-400',
                    dayStatus === 'urgent' && 'bg-amber-100 dark:bg-amber-950/30 text-amber-700 dark:text-amber-400',
                    dayStatus === 'upcoming' && 'bg-blue-100 dark:bg-blue-950/30 text-blue-700 dark:text-blue-400',
                    dayStatus === 'later' && 'bg-gray-100 dark:bg-gray-800/30'
                  )}
                  aria-label={
                    dayDeadlineCount > 0
                      ? `${day}. ${MONTH_NAMES[currentMonth]}: ${dayDeadlineCount} Frist${dayDeadlineCount > 1 ? 'en' : ''}`
                      : `${day}. ${MONTH_NAMES[currentMonth]}`
                  }
                >
                  <span className="font-medium">{day}</span>
                  {dayDeadlineCount > 0 && (
                    <span className="text-[10px] leading-none">
                      {dayDeadlineCount} {dayDeadlineCount === 1 ? 'Frist' : 'Fristen'}
                    </span>
                  )}
                </button>
              )
            })}
          </div>

          {/* Legend */}
          <div className="flex flex-wrap items-center justify-center gap-3 mt-4 pt-4 border-t">
            <div className="flex items-center gap-1.5 text-xs">
              <div className="w-3 h-3 rounded bg-red-100 dark:bg-red-950/30 border border-red-300" />
              <span>Überfällig</span>
            </div>
            <div className="flex items-center gap-1.5 text-xs">
              <div className="w-3 h-3 rounded bg-amber-100 dark:bg-amber-950/30 border border-amber-300" />
              <span>Dringend</span>
            </div>
            <div className="flex items-center gap-1.5 text-xs">
              <div className="w-3 h-3 rounded bg-blue-100 dark:bg-blue-950/30 border border-blue-300" />
              <span>Anstehend</span>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Day Detail Dialog */}
      <Dialog open={!!selectedDay} onOpenChange={() => setSelectedDay(null)}>
        <DialogContent className="sm:max-w-[500px]">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <CalendarIcon className="w-5 h-5" />
              {selectedDay &&
                `${selectedDay.day}. ${MONTH_NAMES[selectedDay.month]} ${selectedDay.year}`}
            </DialogTitle>
            <DialogDescription>
              {selectedDayDeadlines.length} Frist{selectedDayDeadlines.length !== 1 && 'en'} an
              diesem Tag
            </DialogDescription>
          </DialogHeader>

          <ScrollArea className="max-h-[400px]">
            <div className="space-y-3">
              {selectedDayDeadlines.map((deadline) => {
                const urgency = getUrgency(deadline.deadline)
                return (
                  <Link
                    key={deadline.id}
                    to="/finanzen/$year/$category"
                    params={{ year: deadline.year, category: deadline.category }}
                    className={cn(
                      'block p-3 rounded-lg border transition-colors hover:bg-muted/50',
                      urgency === 'overdue' && 'border-red-200 bg-red-50/50 dark:bg-red-950/10',
                      urgency === 'urgent' && 'border-amber-200 bg-amber-50/50 dark:bg-amber-950/10',
                      urgency === 'upcoming' && 'border-blue-200 bg-blue-50/50 dark:bg-blue-950/10'
                    )}
                    onClick={() => setSelectedDay(null)}
                  >
                    <div className="flex items-start gap-3">
                      {urgency === 'overdue' ? (
                        <AlertTriangle className="w-5 h-5 text-red-500 shrink-0 mt-0.5" />
                      ) : urgency === 'urgent' ? (
                        <Clock className="w-5 h-5 text-amber-500 shrink-0 mt-0.5" />
                      ) : (
                        <FileText className="w-5 h-5 text-blue-500 shrink-0 mt-0.5" />
                      )}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="font-medium truncate">{deadline.documentName}</span>
                          <Badge
                            variant="outline"
                            className={cn(
                              'text-xs shrink-0',
                              urgency === 'overdue' && 'border-red-300 text-red-700',
                              urgency === 'urgent' && 'border-amber-300 text-amber-700',
                              urgency === 'upcoming' && 'border-blue-300 text-blue-700'
                            )}
                          >
                            {formatDeadlineType(deadline.type)}
                          </Badge>
                        </div>
                        <div className="text-sm text-muted-foreground mt-1">
                          {deadline.categoryLabel} · {deadline.year}
                        </div>
                        {deadline.aktenzeichen && (
                          <div className="text-xs text-muted-foreground mt-0.5">
                            Az.: {deadline.aktenzeichen}
                          </div>
                        )}
                      </div>
                    </div>
                  </Link>
                )
              })}
            </div>
          </ScrollArea>
        </DialogContent>
      </Dialog>
    </>
  )
}

export default FinanceDeadlineCalendar
