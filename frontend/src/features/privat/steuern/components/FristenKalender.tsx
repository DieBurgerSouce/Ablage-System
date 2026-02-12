/**
 * FristenKalender Component
 *
 * Zeigt Steuerfristen in einer Kalender-Ansicht.
 * Warnt bei überfälligen und bevorstehenden Fristen.
 */

import * as React from 'react';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import {
  Calendar,
  CalendarDays,
  AlertTriangle,
  Clock,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Bell,
  RefreshCw,
} from 'lucide-react';
import type { TaxDeadline, TaxDeadlineType } from '@/lib/api/services/tax-optimization';

// ==================== Deadline-Typ Metadaten ====================

interface DeadlineTypeMetadata {
  label: string;
  color: string;
  bgColor: string;
}

const DEADLINE_TYPE_METADATA: Record<TaxDeadlineType, DeadlineTypeMetadata> = {
  einkommensteuer: {
    label: 'Einkommensteuer',
    color: 'text-blue-700',
    bgColor: 'bg-blue-100',
  },
  gewerbesteuer: {
    label: 'Gewerbesteuer',
    color: 'text-purple-700',
    bgColor: 'bg-purple-100',
  },
  umsatzsteuer_voranmeldung: {
    label: 'USt-Voranmeldung',
    color: 'text-green-700',
    bgColor: 'bg-green-100',
  },
  umsatzsteuer_erklärung: {
    label: 'USt-Erklärung',
    color: 'text-emerald-700',
    bgColor: 'bg-emerald-100',
  },
  grundsteuer: {
    label: 'Grundsteuer',
    color: 'text-amber-700',
    bgColor: 'bg-amber-100',
  },
  koerperschaftsteuer: {
    label: 'Körperschaftsteuer',
    color: 'text-indigo-700',
    bgColor: 'bg-indigo-100',
  },
  lohnsteuer: {
    label: 'Lohnsteuer',
    color: 'text-cyan-700',
    bgColor: 'bg-cyan-100',
  },
  fristverlaengerung: {
    label: 'Fristverlängerung',
    color: 'text-slate-700',
    bgColor: 'bg-slate-100',
  },
};

// ==================== Props ====================

interface FristenKalenderProps {
  upcomingDeadlines: TaxDeadline[];
  overdueDeadlines: TaxDeadline[];
  isLoading?: boolean;
  onRefresh?: () => void;
}

// ==================== Hilfsfunktionen ====================

const formatDate = (dateString: string): string => {
  return new Date(dateString).toLocaleDateString('de-DE', {
    weekday: 'short',
    day: '2-digit',
    month: 'long',
    year: 'numeric',
  });
};

const formatShortDate = (dateString: string): string => {
  return new Date(dateString).toLocaleDateString('de-DE', {
    day: '2-digit',
    month: '2-digit',
  });
};

const getDaysUntilColor = (days: number): string => {
  if (days < 0) return 'text-red-600 bg-red-50';
  if (days <= 7) return 'text-amber-600 bg-amber-50';
  if (days <= 30) return 'text-yellow-600 bg-yellow-50';
  return 'text-green-600 bg-green-50';
};

// ==================== Component ====================

export function FristenKalender({
  upcomingDeadlines,
  overdueDeadlines,
  isLoading,
  onRefresh,
}: FristenKalenderProps) {
  const [selectedMonth, setSelectedMonth] = React.useState(() => new Date());

  // Gruppiere Fristen nach Monat
  const deadlinesByMonth = React.useMemo(() => {
    const all = [...overdueDeadlines, ...upcomingDeadlines];
    const grouped: Record<string, TaxDeadline[]> = {};

    all.forEach((deadline) => {
      const date = new Date(deadline.dueDate);
      const monthKey = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`;

      if (!grouped[monthKey]) {
        grouped[monthKey] = [];
      }
      grouped[monthKey].push(deadline);
    });

    // Sortiere innerhalb jedes Monats nach Datum
    Object.values(grouped).forEach((deadlines) => {
      deadlines.sort((a, b) => new Date(a.dueDate).getTime() - new Date(b.dueDate).getTime());
    });

    return grouped;
  }, [upcomingDeadlines, overdueDeadlines]);

  // Aktueller Monat
  const currentMonthKey = `${selectedMonth.getFullYear()}-${String(selectedMonth.getMonth() + 1).padStart(2, '0')}`;
  const currentMonthDeadlines = deadlinesByMonth[currentMonthKey] || [];

  // Navigation
  const goToPreviousMonth = () => {
    setSelectedMonth((prev) => new Date(prev.getFullYear(), prev.getMonth() - 1, 1));
  };

  const goToNextMonth = () => {
    setSelectedMonth((prev) => new Date(prev.getFullYear(), prev.getMonth() + 1, 1));
  };

  const goToToday = () => {
    setSelectedMonth(new Date());
  };

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <CalendarDays className="h-5 w-5" />
            Steuerfristen-Kalender
          </CardTitle>
          <CardDescription>Lade Fristen...</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="animate-pulse space-y-4">
            <div className="h-10 bg-muted rounded" />
            <div className="h-48 bg-muted rounded" />
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="flex items-center gap-2">
              <CalendarDays className="h-5 w-5" />
              Steuerfristen-Kalender
            </CardTitle>
            <CardDescription>
              Alle wichtigen Termine im Überblick
            </CardDescription>
          </div>
          {onRefresh && (
            <Button variant="outline" size="sm" onClick={onRefresh}>
              <RefreshCw className="h-4 w-4 mr-2" />
              Aktualisieren
            </Button>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Überfällige Fristen Warnung */}
        {overdueDeadlines.length > 0 && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-4">
            <div className="flex items-center gap-2 text-red-700 font-medium mb-2">
              <AlertTriangle className="h-5 w-5" />
              {overdueDeadlines.length} überfällige Frist{overdueDeadlines.length !== 1 ? 'en' : ''}
            </div>
            <ul className="space-y-1 text-sm text-red-600">
              {overdueDeadlines.slice(0, 3).map((deadline, idx) => (
                <li key={idx} className="flex items-center gap-2">
                  <span className="font-medium">{deadline.title}</span>
                  <span>- fällig am {formatDate(deadline.dueDate)}</span>
                </li>
              ))}
              {overdueDeadlines.length > 3 && (
                <li className="text-red-500 italic">
                  +{overdueDeadlines.length - 3} weitere...
                </li>
              )}
            </ul>
          </div>
        )}

        {/* Monats-Navigation */}
        <div className="flex items-center justify-between">
          <Button variant="outline" size="sm" onClick={goToPreviousMonth}>
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <div className="flex items-center gap-2">
            <h3 className="text-lg font-semibold">
              {selectedMonth.toLocaleDateString('de-DE', { month: 'long', year: 'numeric' })}
            </h3>
            <Button variant="ghost" size="sm" onClick={goToToday}>
              Heute
            </Button>
          </div>
          <Button variant="outline" size="sm" onClick={goToNextMonth}>
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>

        {/* Fristen des Monats */}
        <ScrollArea className="h-[300px]">
          {currentMonthDeadlines.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              <Calendar className="h-12 w-12 mx-auto mb-2 opacity-50" />
              <p>Keine Fristen in diesem Monat</p>
            </div>
          ) : (
            <div className="space-y-3">
              {currentMonthDeadlines.map((deadline, idx) => {
                const metadata = DEADLINE_TYPE_METADATA[deadline.deadlineType];
                const daysColor = getDaysUntilColor(deadline.daysUntilDue);

                return (
                  <div
                    key={idx}
                    className={`p-4 border rounded-lg ${
                      deadline.isOverdue ? 'border-red-200 bg-red-50' : 'hover:bg-muted/50'
                    }`}
                  >
                    <div className="flex items-start justify-between">
                      <div className="flex items-start gap-3">
                        <div className="text-center min-w-[50px]">
                          <div className="text-2xl font-bold">
                            {new Date(deadline.dueDate).getDate()}
                          </div>
                          <div className="text-xs text-muted-foreground uppercase">
                            {new Date(deadline.dueDate).toLocaleDateString('de-DE', {
                              weekday: 'short',
                            })}
                          </div>
                        </div>
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="font-medium">{deadline.title}</span>
                            {deadline.isRecurring && (
                              <TooltipProvider>
                                <Tooltip>
                                  <TooltipTrigger>
                                    <RefreshCw className="h-3 w-3 text-muted-foreground" />
                                  </TooltipTrigger>
                                  <TooltipContent>
                                    <p>Wiederkehrende Frist ({deadline.recurrencePattern})</p>
                                  </TooltipContent>
                                </Tooltip>
                              </TooltipProvider>
                            )}
                          </div>
                          <p className="text-sm text-muted-foreground mt-1">
                            {deadline.description}
                          </p>
                          <div className="flex items-center gap-2 mt-2">
                            <Badge
                              variant="secondary"
                              className={`${metadata.bgColor} ${metadata.color}`}
                            >
                              {metadata.label}
                            </Badge>
                          </div>
                        </div>
                      </div>
                      <div className="text-right">
                        <Badge
                          variant="outline"
                          className={daysColor}
                        >
                          {deadline.isOverdue ? (
                            <span className="flex items-center gap-1">
                              <AlertTriangle className="h-3 w-3" />
                              {Math.abs(deadline.daysUntilDue)} Tage überfällig
                            </span>
                          ) : deadline.daysUntilDue === 0 ? (
                            <span className="flex items-center gap-1">
                              <Clock className="h-3 w-3" />
                              Heute fällig
                            </span>
                          ) : deadline.daysUntilDue === 1 ? (
                            <span className="flex items-center gap-1">
                              <Clock className="h-3 w-3" />
                              Morgen fällig
                            </span>
                          ) : (
                            <span className="flex items-center gap-1">
                              <Clock className="h-3 w-3" />
                              Noch {deadline.daysUntilDue} Tage
                            </span>
                          )}
                        </Badge>
                        {deadline.reminderSent && (
                          <div className="mt-1">
                            <TooltipProvider>
                              <Tooltip>
                                <TooltipTrigger>
                                  <Bell className="h-3 w-3 text-muted-foreground" />
                                </TooltipTrigger>
                                <TooltipContent>
                                  <p>Erinnerung wurde versendet</p>
                                </TooltipContent>
                              </Tooltip>
                            </TooltipProvider>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </ScrollArea>

        {/* Zusammenfassung */}
        <div className="grid grid-cols-3 gap-4 pt-4 border-t">
          <div className="text-center">
            <div className="text-2xl font-bold text-red-600">{overdueDeadlines.length}</div>
            <div className="text-xs text-muted-foreground">Überfällig</div>
          </div>
          <div className="text-center">
            <div className="text-2xl font-bold text-amber-600">
              {upcomingDeadlines.filter((d) => d.daysUntilDue <= 7).length}
            </div>
            <div className="text-xs text-muted-foreground">Diese Woche</div>
          </div>
          <div className="text-center">
            <div className="text-2xl font-bold text-green-600">
              {upcomingDeadlines.filter((d) => d.daysUntilDue > 7 && d.daysUntilDue <= 30).length}
            </div>
            <div className="text-xs text-muted-foreground">Diesen Monat</div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

export default FristenKalender;
