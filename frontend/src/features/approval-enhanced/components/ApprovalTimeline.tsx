/**
 * ApprovalTimeline Component
 * Visual horizontal timeline of approval stages
 */

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import {
  CheckCircle2,
  Circle,
  XCircle,
  AlertTriangle,
  ArrowRight,
} from 'lucide-react';
import { cn } from '@/lib/utils';

export type ApprovalStageStatus = 'pending' | 'approved' | 'rejected' | 'escalated';

export interface ApprovalStage {
  id: string;
  name: string;
  status: ApprovalStageStatus;
  timestamp?: string;
  approver?: string;
}

interface ApprovalTimelineProps {
  stages: ApprovalStage[];
  currentStageId?: string;
}

export function ApprovalTimeline({ stages, currentStageId }: ApprovalTimelineProps) {
  const getStatusIcon = (status: ApprovalStageStatus, isActive: boolean) => {
    const iconClass = cn('h-6 w-6', isActive && 'animate-pulse');

    switch (status) {
      case 'approved':
        return <CheckCircle2 className={cn(iconClass, 'text-green-600')} />;
      case 'rejected':
        return <XCircle className={cn(iconClass, 'text-destructive')} />;
      case 'escalated':
        return <AlertTriangle className={cn(iconClass, 'text-yellow-500')} />;
      case 'pending':
      default:
        return <Circle className={cn(iconClass, 'text-muted-foreground')} />;
    }
  };

  const getStatusColor = (status: ApprovalStageStatus) => {
    switch (status) {
      case 'approved':
        return 'bg-green-500';
      case 'rejected':
        return 'bg-destructive';
      case 'escalated':
        return 'bg-yellow-500';
      case 'pending':
      default:
        return 'bg-muted';
    }
  };

  const getStatusBadge = (status: ApprovalStageStatus) => {
    const labels = {
      pending: 'Ausstehend',
      approved: 'Genehmigt',
      rejected: 'Abgelehnt',
      escalated: 'Eskaliert',
    };

    const variants = {
      pending: 'secondary',
      approved: 'default',
      rejected: 'destructive',
      escalated: 'default',
    } as const;

    return <Badge variant={variants[status]}>{labels[status]}</Badge>;
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Genehmigungsverlauf</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="relative">
          {/* Timeline */}
          <div className="flex items-center justify-between">
            {stages.map((stage, index) => {
              const isActive = stage.id === currentStageId;
              const isLast = index === stages.length - 1;

              return (
                <div key={stage.id} className="flex items-center flex-1">
                  {/* Stage Node */}
                  <div className="flex flex-col items-center gap-2">
                    {/* Icon */}
                    <div
                      className={cn(
                        'relative z-10 flex items-center justify-center rounded-full bg-background',
                        'border-2',
                        isActive
                          ? 'border-primary'
                          : stage.status === 'approved'
                            ? 'border-green-500'
                            : stage.status === 'rejected'
                              ? 'border-destructive'
                              : stage.status === 'escalated'
                                ? 'border-yellow-500'
                                : 'border-muted'
                      )}
                    >
                      {getStatusIcon(stage.status, isActive)}
                    </div>

                    {/* Stage Info */}
                    <div className="flex flex-col items-center gap-1 min-w-[120px]">
                      <span className="text-sm font-medium text-center">
                        {stage.name}
                      </span>
                      {getStatusBadge(stage.status)}
                      {stage.approver && (
                        <span className="text-xs text-muted-foreground">
                          {stage.approver}
                        </span>
                      )}
                      {stage.timestamp && (
                        <span className="text-xs text-muted-foreground">
                          {new Date(stage.timestamp).toLocaleDateString('de-DE')}
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Connector Line */}
                  {!isLast && (
                    <div className="flex-1 flex items-center px-4">
                      <div
                        className={cn(
                          'h-1 flex-1 rounded-full',
                          getStatusColor(stage.status)
                        )}
                      />
                      <ArrowRight className="h-4 w-4 text-muted-foreground mx-2" />
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
