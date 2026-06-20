/**
 * ContractDeadlineCalendar Component
 *
 * Kalenderansicht für Vertragsfristen mit:
 * - Monats-/Wochen-/Tagesansicht
 * - Farbcodierung nach Dringlichkeit
 * - Klick auf Ereignisse öffnet Vertragsdetails
 */

import { useState, useMemo } from 'react';
import {
  format,
  startOfMonth,
  endOfMonth,
  startOfWeek,
  endOfWeek,
  eachDayOfInterval,
  isSameMonth,
  isToday,
  addMonths,
  subMonths,
  parseISO,
} from 'date-fns';
import { de } from 'date-fns/locale';
import {
  ChevronLeft,
  ChevronRight,
  Calendar as CalendarIcon,
  AlertTriangle,
  Clock,
  FileText,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import type { DeadlineAlert } from '../types/contract-types';

interface ContractDeadlineCalendarProps {
  deadlines: DeadlineAlert[];
  isLoading?: boolean;
  onSelectDeadline: (deadline: DeadlineAlert) => void;
}

type ViewMode = 'month' | 'week';

const urgencyConfig = {
  critical: {
    bg: 'bg-red-500',
    text: 'text-white',
    border: 'border-red-500',
    dot: 'bg-red-500',
  },
  warning: {
    bg: 'bg-orange-500',
    text: 'text-white',
    border: 'border-orange-500',
    dot: 'bg-orange-500',
  },
  upcoming: {
    bg: 'bg-yellow-500',
    text: 'text-black',
    border: 'border-yellow-500',
    dot: 'bg-yellow-500',
  },
};

const deadlineTypeLabels: Record<string, string> = {
  notice: 'Kündigungsfrist',
  end: 'Vertragsende',
  renewal: 'Verlängerung',
};

export function ContractDeadlineCalendar({
  deadlines,
  isLoading = false,
  onSelectDeadline,
}: ContractDeadlineCalendarProps) {
  const [currentDate, setCurrentDate] = useState(new Date());
  const [viewMode, setViewMode] = useState<ViewMode>('month');

  // Group deadlines by date
  const deadlinesByDate = useMemo(() => {
    const grouped = new Map<string, DeadlineAlert[]>();

    deadlines.forEach((deadline) => {
      const dateKey = format(parseISO(deadline.deadline_date), 'yyyy-MM-dd');
      const existing = grouped.get(dateKey) || [];
      grouped.set(dateKey, [...existing, deadline]);
    });

    return grouped;
  }, [deadlines]);

  // Generate calendar days
  const calendarDays = useMemo(() => {
    const monthStart = startOfMonth(currentDate);
    const monthEnd = endOfMonth(currentDate);
    const calendarStart = startOfWeek(monthStart, { weekStartsOn: 1 });
    const calendarEnd = endOfWeek(monthEnd, { weekStartsOn: 1 });

    return eachDayOfInterval({ start: calendarStart, end: calendarEnd });
  }, [currentDate]);

  // Navigation handlers
  const handlePrevMonth = () => setCurrentDate(subMonths(currentDate, 1));
  const handleNextMonth = () => setCurrentDate(addMonths(currentDate, 1));
  const handleToday = () => setCurrentDate(new Date());

  // Day names
  const dayNames = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'];


  const renderDayCell = (day: Date) => {
    const dateKey = format(day, 'yyyy-MM-dd');
    const dayDeadlines = deadlinesByDate.get(dateKey) || [];
    const isCurrentMonth = isSameMonth(day, currentDate);
    const isSelected = isToday(day);

    return (
      <TooltipProvider key={day.toString()}>
        <Tooltip>
          <TooltipTrigger asChild>
            <div
              className={cn(
                'min-h-[80px] p-1 border-b border-r cursor-pointer hover:bg-muted/50 transition-colors',
                !isCurrentMonth && 'opacity-40 bg-muted/20',
                isSelected && 'bg-primary/10'
              )}
              onClick={() => {
                if (dayDeadlines.length > 0) {
                  onSelectDeadline(dayDeadlines[0]);
                }
              }}
            >
              <div className="flex justify-between items-start">
                <span
                  className={cn(
                    'text-sm font-medium',
                    isToday(day) && 'bg-primary text-primary-foreground rounded-full w-6 h-6 flex items-center justify-center'
                  )}
                >
                  {format(day, 'd')}
                </span>
                {dayDeadlines.length > 1 && (
                  <Badge variant="secondary" className="text-xs px-1.5 py-0">
                    {dayDeadlines.length}
                  </Badge>
                )}
              </div>

              <div className="mt-1 space-y-0.5">
                {dayDeadlines.slice(0, 2).map((deadline, idx) => {
                  const config = urgencyConfig[deadline.urgency];
                  return (
                    <div
                      key={`${deadline.contract_id}-${idx}`}
                      className={cn(
                        'text-xs px-1 py-0.5 rounded truncate',
                        config.bg,
                        config.text
                      )}
                      onClick={(e) => {
                        e.stopPropagation();
                        onSelectDeadline(deadline);
                      }}
                    >
                      {deadline.contract_title}
                    </div>
                  );
                })}
                {dayDeadlines.length > 2 && (
                  <div className="text-xs text-muted-foreground px-1">
                    +{dayDeadlines.length - 2} weitere
                  </div>
                )}
              </div>
            </div>
          </TooltipTrigger>
          {dayDeadlines.length > 0 && (
            <TooltipContent side="right" className="max-w-xs">
              <div className="space-y-2">
                <p className="font-medium">{format(day, 'EEEE, d. MMMM yyyy', { locale: de })}</p>
                {dayDeadlines.map((deadline, idx) => (
                  <div key={idx} className="text-sm">
                    <p className="font-medium">{deadline.contract_title}</p>
                    <p className="text-muted-foreground">
                      {deadlineTypeLabels[deadline.deadline_type] || deadline.deadline_type}
                    </p>
                  </div>
                ))}
              </div>
            </TooltipContent>
          )}
        </Tooltip>
      </TooltipProvider>
    );
  };

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <CalendarIcon className="h-5 w-5" />
            Fristen-Kalender
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="h-[400px] flex items-center justify-center">
            <div className="text-muted-foreground">Lade Kalender...</div>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            <CalendarIcon className="h-5 w-5" />
            Fristen-Kalender
          </CardTitle>

          <div className="flex items-center gap-2">
            {/* Legend */}
            <div className="hidden md:flex items-center gap-3 text-xs text-muted-foreground mr-4">
              <div className="flex items-center gap-1">
                <div className={`w-2 h-2 rounded-full ${urgencyConfig.critical.dot}`} />
                <span>Kritisch</span>
              </div>
              <div className="flex items-center gap-1">
                <div className={`w-2 h-2 rounded-full ${urgencyConfig.warning.dot}`} />
                <span>Warnung</span>
              </div>
              <div className="flex items-center gap-1">
                <div className={`w-2 h-2 rounded-full ${urgencyConfig.upcoming.dot}`} />
                <span>Anstehend</span>
              </div>
            </div>

            <Select value={viewMode} onValueChange={(v: ViewMode) => setViewMode(v)}>
              <SelectTrigger className="w-[120px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="month">Monat</SelectItem>
                <SelectItem value="week">Woche</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>

        {/* Navigation */}
        <div className="flex items-center justify-between mt-2">
          <div className="flex items-center gap-2">
            <Button variant="outline" size="icon" onClick={handlePrevMonth}>
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <Button variant="outline" size="icon" onClick={handleNextMonth}>
              <ChevronRight className="h-4 w-4" />
            </Button>
            <Button variant="ghost" size="sm" onClick={handleToday}>
              Heute
            </Button>
          </div>
          <h3 className="text-lg font-semibold">
            {format(currentDate, 'MMMM yyyy', { locale: de })}
          </h3>
        </div>
      </CardHeader>

      <CardContent>
        {/* Day headers */}
        <div className="grid grid-cols-7 border-l border-t">
          {dayNames.map((day) => (
            <div
              key={day}
              className="p-2 text-center text-sm font-medium border-b border-r bg-muted/50"
            >
              {day}
            </div>
          ))}
        </div>

        {/* Calendar grid */}
        <div className="grid grid-cols-7 border-l">
          {calendarDays.map(renderDayCell)}
        </div>

        {/* Summary */}
        <div className="mt-4 pt-4 border-t">
          <div className="flex items-center gap-4 text-sm text-muted-foreground">
            <div className="flex items-center gap-1">
              <AlertTriangle className="h-4 w-4 text-red-500" />
              <span>
                {deadlines.filter((d) => d.urgency === 'critical').length} kritisch
              </span>
            </div>
            <div className="flex items-center gap-1">
              <Clock className="h-4 w-4 text-orange-500" />
              <span>
                {deadlines.filter((d) => d.urgency === 'warning').length} Warnungen
              </span>
            </div>
            <div className="flex items-center gap-1">
              <FileText className="h-4 w-4 text-yellow-500" />
              <span>
                {deadlines.filter((d) => d.urgency === 'upcoming').length} anstehend
              </span>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

export default ContractDeadlineCalendar;
