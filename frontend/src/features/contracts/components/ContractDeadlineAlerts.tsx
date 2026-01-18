/**
 * ContractDeadlineAlerts - Anstehende Fristen-Warnungen
 *
 * Zeigt kritische und anstehende Fristen mit Farbcodierung:
 * - Kritisch (rot): < 14 Tage
 * - Warnung (orange): < 30 Tage
 * - Anstehend (gelb): < 90 Tage
 */

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { ScrollArea } from '@/components/ui/scroll-area';
import { AlertTriangle, Clock, FileText, ArrowRight } from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';
import { de } from 'date-fns/locale';
import type { DeadlineAlert } from '../types/contract-types';

interface ContractDeadlineAlertsProps {
  deadlines: DeadlineAlert[];
  isLoading: boolean;
  onViewContract: (contractId: string) => void;
  onViewAll: () => void;
}

const urgencyConfig = {
  critical: {
    color: 'bg-red-500',
    textColor: 'text-red-700',
    bgColor: 'bg-red-50',
    borderColor: 'border-red-200',
    icon: AlertTriangle,
    label: 'Kritisch',
  },
  warning: {
    color: 'bg-orange-500',
    textColor: 'text-orange-700',
    bgColor: 'bg-orange-50',
    borderColor: 'border-orange-200',
    icon: Clock,
    label: 'Warnung',
  },
  upcoming: {
    color: 'bg-yellow-500',
    textColor: 'text-yellow-700',
    bgColor: 'bg-yellow-50',
    borderColor: 'border-yellow-200',
    icon: FileText,
    label: 'Anstehend',
  },
};

const deadlineTypeLabels: Record<string, string> = {
  notice: 'Kuendigungsfrist',
  end: 'Vertragsende',
  renewal: 'Verlaengerung',
};

export function ContractDeadlineAlerts({
  deadlines,
  isLoading,
  onViewContract,
  onViewAll,
}: ContractDeadlineAlertsProps) {
  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-medium">Anstehende Fristen</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-16 w-full" />
            ))}
          </div>
        </CardContent>
      </Card>
    );
  }

  if (deadlines.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-medium">Anstehende Fristen</CardTitle>
          <CardDescription>Keine kritischen Fristen in den naechsten 90 Tagen</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-center py-8 text-muted-foreground">
            <Clock className="h-8 w-8 mr-2 opacity-50" />
            <span>Alles im gruenen Bereich</span>
          </div>
        </CardContent>
      </Card>
    );
  }

  const criticalCount = deadlines.filter((d) => d.urgency === 'critical').length;
  const warningCount = deadlines.filter((d) => d.urgency === 'warning').length;

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="text-sm font-medium">Anstehende Fristen</CardTitle>
            <CardDescription>
              {criticalCount > 0 && (
                <span className="text-red-600 font-medium">{criticalCount} kritisch</span>
              )}
              {criticalCount > 0 && warningCount > 0 && ' · '}
              {warningCount > 0 && (
                <span className="text-orange-600 font-medium">{warningCount} Warnung</span>
              )}
            </CardDescription>
          </div>
          <Button variant="ghost" size="sm" onClick={onViewAll}>
            Alle anzeigen
            <ArrowRight className="h-4 w-4 ml-1" />
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        <ScrollArea className="h-[300px] pr-4">
          <div className="space-y-3">
            {deadlines.map((deadline) => {
              const config = urgencyConfig[deadline.urgency];
              const Icon = config.icon;

              return (
                <div
                  key={`${deadline.contract_id}-${deadline.deadline_type}`}
                  className={`p-3 rounded-lg border ${config.bgColor} ${config.borderColor} cursor-pointer hover:shadow-sm transition-shadow`}
                  onClick={() => onViewContract(deadline.contract_id)}
                >
                  <div className="flex items-start justify-between">
                    <div className="flex items-start gap-3">
                      <div className={`p-1.5 rounded-full ${config.color} text-white`}>
                        <Icon className="h-3.5 w-3.5" />
                      </div>
                      <div className="space-y-1">
                        <p className="text-sm font-medium leading-none">
                          {deadline.contract_title}
                        </p>
                        <p className="text-xs text-muted-foreground">
                          {deadline.contract_number}
                          {deadline.party_name && ` · ${deadline.party_name}`}
                        </p>
                      </div>
                    </div>
                    <Badge variant="outline" className={config.textColor}>
                      {deadline.days_remaining} Tage
                    </Badge>
                  </div>
                  <div className="mt-2 flex items-center justify-between">
                    <span className={`text-xs font-medium ${config.textColor}`}>
                      {deadlineTypeLabels[deadline.deadline_type] || deadline.deadline_type}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {formatDistanceToNow(new Date(deadline.deadline_date), {
                        addSuffix: true,
                        locale: de,
                      })}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </ScrollArea>
      </CardContent>
    </Card>
  );
}
