/**
 * ContractTimeline - Zeitstrahl fuer Vertragslaufzeit und Fristen
 *
 * Zeigt:
 * - Vertragsbeginn und -ende
 * - Kuendigungsfrist
 * - Meilensteine
 * - Verlaengerungsoptionen
 * - Countdown bis zur naechsten kritischen Frist
 */

import { useMemo } from 'react';
import { format, differenceInDays, isAfter, isBefore } from 'date-fns';
import { de } from 'date-fns/locale';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import {
  Calendar,
  Clock,
  AlertTriangle,
  CheckCircle,
  Flag,
  RefreshCw,
  Bell,
} from 'lucide-react';
import type { Contract, ContractMilestone } from '../types/contract-types';
import { MilestoneType, MILESTONE_TYPE_LABELS } from '../types/contract-types';

interface ContractTimelineProps {
  contract: Contract;
  milestones?: ContractMilestone[];
  showMilestones?: boolean;
  compact?: boolean;
}

interface TimelineEvent {
  id: string;
  date: Date;
  type: 'start' | 'end' | 'notice' | 'milestone' | 'renewal' | 'today';
  label: string;
  description?: string;
  urgency?: 'critical' | 'warning' | 'normal' | 'completed';
  icon: React.ReactNode;
}

const urgencyColors = {
  critical: 'bg-red-500',
  warning: 'bg-orange-500',
  normal: 'bg-blue-500',
  completed: 'bg-green-500',
};

const urgencyTextColors = {
  critical: 'text-red-600',
  warning: 'text-orange-600',
  normal: 'text-blue-600',
  completed: 'text-green-600',
};

function formatDate(date: Date | string): string {
  const d = typeof date === 'string' ? new Date(date) : date;
  return format(d, 'dd.MM.yyyy', { locale: de });
}

function getUrgencyFromDays(days: number, isCompleted: boolean = false): TimelineEvent['urgency'] {
  if (isCompleted) return 'completed';
  if (days < 0) return 'critical';
  if (days <= 14) return 'critical';
  if (days <= 30) return 'warning';
  return 'normal';
}

export function ContractTimeline({
  contract,
  milestones = [],
  showMilestones = true,
  compact = false,
}: ContractTimelineProps) {
  const today = useMemo(() => new Date(), []);

  // Berechne Timeline-Events
  const events = useMemo(() => {
    const timelineEvents: TimelineEvent[] = [];

    // Vertragsbeginn
    if (contract.start_date) {
      const startDate = new Date(contract.start_date);
      timelineEvents.push({
        id: 'start',
        date: startDate,
        type: 'start',
        label: 'Vertragsbeginn',
        description: formatDate(startDate),
        urgency: isBefore(startDate, today) ? 'completed' : 'normal',
        icon: <Flag className="h-4 w-4" />,
      });
    }

    // Kuendigungsfrist
    if (contract.notice_deadline) {
      const noticeDate = new Date(contract.notice_deadline);
      const daysUntil = differenceInDays(noticeDate, today);
      timelineEvents.push({
        id: 'notice',
        date: noticeDate,
        type: 'notice',
        label: 'Kuendigungsfrist',
        description: `${formatDate(noticeDate)} (${daysUntil} Tage)`,
        urgency: getUrgencyFromDays(daysUntil),
        icon: <Bell className="h-4 w-4" />,
      });
    }

    // Vertragsende
    if (contract.end_date) {
      const endDate = new Date(contract.end_date);
      const daysUntil = differenceInDays(endDate, today);
      timelineEvents.push({
        id: 'end',
        date: endDate,
        type: 'end',
        label: 'Vertragsende',
        description: `${formatDate(endDate)} (${daysUntil} Tage)`,
        urgency: getUrgencyFromDays(daysUntil),
        icon: <Calendar className="h-4 w-4" />,
      });
    }

    // Meilensteine
    if (showMilestones && milestones.length > 0) {
      milestones.forEach((milestone) => {
        const milestoneDate = new Date(milestone.scheduled_date);
        const daysUntil = differenceInDays(milestoneDate, today);
        timelineEvents.push({
          id: `milestone-${milestone.id}`,
          date: milestoneDate,
          type: 'milestone',
          label: milestone.title,
          description: MILESTONE_TYPE_LABELS[milestone.milestone_type as MilestoneType],
          urgency: getUrgencyFromDays(daysUntil, milestone.is_completed),
          icon: milestone.is_completed ? (
            <CheckCircle className="h-4 w-4" />
          ) : (
            <Clock className="h-4 w-4" />
          ),
        });
      });
    }

    // Heute-Marker
    timelineEvents.push({
      id: 'today',
      date: today,
      type: 'today',
      label: 'Heute',
      urgency: 'normal',
      icon: <Clock className="h-4 w-4" />,
    });

    // Sortieren nach Datum
    return timelineEvents.sort((a, b) => a.date.getTime() - b.date.getTime());
  }, [contract, milestones, showMilestones, today]);

  // Berechne Fortschritt
  const progress = useMemo(() => {
    if (!contract.start_date || !contract.end_date) return null;

    const startDate = new Date(contract.start_date);
    const endDate = new Date(contract.end_date);
    const totalDays = differenceInDays(endDate, startDate);
    const elapsedDays = differenceInDays(today, startDate);

    if (totalDays <= 0) return null;

    const progressPercent = Math.min(100, Math.max(0, (elapsedDays / totalDays) * 100));
    const remainingDays = differenceInDays(endDate, today);

    return {
      percent: progressPercent,
      totalDays,
      elapsedDays: Math.max(0, elapsedDays),
      remainingDays: Math.max(0, remainingDays),
    };
  }, [contract.start_date, contract.end_date, today]);

  // Naechste kritische Frist
  const nextCriticalEvent = useMemo(() => {
    return events.find(
      (e) =>
        e.type !== 'today' &&
        e.type !== 'start' &&
        e.urgency !== 'completed' &&
        isAfter(e.date, today)
    );
  }, [events, today]);

  if (compact) {
    return (
      <div className="space-y-3">
        {/* Fortschrittsbalken */}
        {progress && (
          <div className="space-y-1">
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">Vertragslaufzeit</span>
              <span className="font-medium">{Math.round(progress.percent)}%</span>
            </div>
            <Progress value={progress.percent} className="h-2" />
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span>{progress.elapsedDays} Tage vergangen</span>
              <span>{progress.remainingDays} Tage verbleibend</span>
            </div>
          </div>
        )}

        {/* Naechste kritische Frist */}
        {nextCriticalEvent && (
          <div
            className={`p-3 rounded-lg border ${
              nextCriticalEvent.urgency === 'critical'
                ? 'bg-red-50 border-red-200'
                : nextCriticalEvent.urgency === 'warning'
                ? 'bg-orange-50 border-orange-200'
                : 'bg-blue-50 border-blue-200'
            }`}
          >
            <div className="flex items-center gap-2">
              {nextCriticalEvent.urgency === 'critical' ? (
                <AlertTriangle className="h-4 w-4 text-red-600" />
              ) : (
                <Clock className="h-4 w-4 text-blue-600" />
              )}
              <span className="text-sm font-medium">{nextCriticalEvent.label}</span>
            </div>
            <p
              className={`text-xs mt-1 ${urgencyTextColors[nextCriticalEvent.urgency || 'normal']}`}
            >
              {nextCriticalEvent.description}
            </p>
          </div>
        )}
      </div>
    );
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <Calendar className="h-4 w-4" />
          Vertragszeitraum
        </CardTitle>
        {contract.auto_renewal && (
          <CardDescription className="flex items-center gap-1">
            <RefreshCw className="h-3 w-3" />
            Automatische Verlaengerung aktiv
          </CardDescription>
        )}
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Fortschrittsbalken */}
        {progress && (
          <div className="space-y-2">
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">Laufzeit-Fortschritt</span>
              <span className="font-medium">{Math.round(progress.percent)}%</span>
            </div>
            <Progress value={progress.percent} className="h-3" />
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span>{progress.elapsedDays} Tage vergangen</span>
              <span>{progress.remainingDays} Tage verbleibend</span>
            </div>
          </div>
        )}

        {/* Timeline */}
        <div className="relative">
          <div className="absolute left-4 top-0 bottom-0 w-0.5 bg-border" />

          <TooltipProvider>
            <div className="space-y-4">
              {events.map((event, _index) => {
                const isEventToday = event.type === 'today';

                return (
                  <div key={event.id} className="relative flex items-start gap-4">
                    {/* Punkt auf der Linie */}
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <div
                          className={`relative z-10 flex items-center justify-center w-8 h-8 rounded-full border-2 border-background ${
                            isEventToday
                              ? 'bg-primary text-primary-foreground'
                              : urgencyColors[event.urgency || 'normal']
                          } text-white`}
                        >
                          {event.icon}
                        </div>
                      </TooltipTrigger>
                      <TooltipContent>
                        <p>{event.label}</p>
                        {event.description && (
                          <p className="text-xs text-muted-foreground">{event.description}</p>
                        )}
                      </TooltipContent>
                    </Tooltip>

                    {/* Event-Details */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between">
                        <p
                          className={`text-sm font-medium ${
                            isEventToday ? 'text-primary' : ''
                          }`}
                        >
                          {event.label}
                        </p>
                        {event.urgency && !isEventToday && (
                          <Badge
                            variant="outline"
                            className={urgencyTextColors[event.urgency]}
                          >
                            {event.urgency === 'critical'
                              ? 'Kritisch'
                              : event.urgency === 'warning'
                              ? 'Warnung'
                              : event.urgency === 'completed'
                              ? 'Erledigt'
                              : 'Geplant'}
                          </Badge>
                        )}
                      </div>
                      {event.description && !isEventToday && (
                        <p className="text-xs text-muted-foreground mt-0.5">
                          {event.description}
                        </p>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </TooltipProvider>
        </div>

        {/* Countdown-Karten */}
        <div className="grid grid-cols-2 gap-3 pt-4 border-t">
          {/* Kuendigungsfrist Countdown */}
          {contract.days_until_notice_deadline !== undefined && contract.days_until_notice_deadline >= 0 && (
            <div
              className={`p-3 rounded-lg ${
                contract.is_notice_deadline_critical
                  ? 'bg-red-50 border border-red-200'
                  : 'bg-muted'
              }`}
            >
              <div className="flex items-center gap-2 mb-1">
                <Bell
                  className={`h-4 w-4 ${
                    contract.is_notice_deadline_critical ? 'text-red-600' : 'text-muted-foreground'
                  }`}
                />
                <span className="text-xs text-muted-foreground">Kuendigungsfrist</span>
              </div>
              <p
                className={`text-2xl font-bold ${
                  contract.is_notice_deadline_critical ? 'text-red-600' : ''
                }`}
              >
                {contract.days_until_notice_deadline}
              </p>
              <p className="text-xs text-muted-foreground">Tage verbleibend</p>
            </div>
          )}

          {/* Vertragsende Countdown */}
          {contract.days_until_end !== undefined && contract.days_until_end >= 0 && (
            <div
              className={`p-3 rounded-lg ${
                contract.is_expiring_soon
                  ? 'bg-orange-50 border border-orange-200'
                  : 'bg-muted'
              }`}
            >
              <div className="flex items-center gap-2 mb-1">
                <Calendar
                  className={`h-4 w-4 ${
                    contract.is_expiring_soon ? 'text-orange-600' : 'text-muted-foreground'
                  }`}
                />
                <span className="text-xs text-muted-foreground">Vertragsende</span>
              </div>
              <p
                className={`text-2xl font-bold ${
                  contract.is_expiring_soon ? 'text-orange-600' : ''
                }`}
              >
                {contract.days_until_end}
              </p>
              <p className="text-xs text-muted-foreground">Tage verbleibend</p>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

export default ContractTimeline;
