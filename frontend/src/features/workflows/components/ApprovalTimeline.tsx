import { CheckCircle2, XCircle, Clock } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import type { ApprovalStep } from '../api/approval-api';

interface ApprovalTimelineProps {
  steps: ApprovalStep[];
  className?: string;
}

export function ApprovalTimeline({ steps, className }: ApprovalTimelineProps) {
  const formatDate = (date: string | null): string => {
    if (!date) return '';
    return new Date(date).toLocaleDateString('de-DE', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const getStepIcon = (decision: string | null) => {
    switch (decision) {
      case 'approved':
        return <CheckCircle2 className="h-5 w-5 text-green-600" />;
      case 'rejected':
        return <XCircle className="h-5 w-5 text-red-600" />;
      default:
        return <Clock className="h-5 w-5 text-gray-400" />;
    }
  };

  const getStepColor = (decision: string | null): string => {
    switch (decision) {
      case 'approved':
        return 'border-green-600 bg-green-50';
      case 'rejected':
        return 'border-red-600 bg-red-50';
      default:
        return 'border-gray-300 bg-gray-50';
    }
  };

  const getStatusText = (decision: string | null): string => {
    switch (decision) {
      case 'approved':
        return 'Genehmigt';
      case 'rejected':
        return 'Abgelehnt';
      default:
        return 'Ausstehend';
    }
  };

  return (
    <div className={className}>
      <div className="space-y-4">
        {steps.map((step, index) => (
          <div key={step.step_number} className="relative flex gap-4">
            {/* Left: Step indicator with connector line */}
            <div className="relative flex flex-col items-center">
              <div
                className={`flex h-10 w-10 items-center justify-center rounded-full border-2 ${getStepColor(
                  step.decision
                )}`}
              >
                {getStepIcon(step.decision)}
              </div>
              {/* Connector line to next step */}
              {index < steps.length - 1 && (
                <div className="absolute top-10 h-full w-0.5 bg-gray-300" />
              )}
            </div>

            {/* Right: Step content */}
            <div className="flex-1 pb-8">
              <div className="flex items-center gap-2">
                <h4 className="font-semibold">{step.role}</h4>
                {step.required && (
                  <Badge variant="outline" className="text-xs">
                    Pflicht
                  </Badge>
                )}
              </div>

              <div className="mt-1 text-sm text-muted-foreground">
                {step.approver_name ? (
                  <span>{step.approver_name}</span>
                ) : (
                  <span className="italic">Noch nicht zugewiesen</span>
                )}
              </div>

              <div className="mt-1">
                <Badge
                  variant={
                    step.decision === 'approved'
                      ? 'default'
                      : step.decision === 'rejected'
                        ? 'destructive'
                        : 'secondary'
                  }
                  className="text-xs"
                >
                  {getStatusText(step.decision)}
                </Badge>
              </div>

              {step.decided_at && (
                <div className="mt-1 text-xs text-muted-foreground">
                  {formatDate(step.decided_at)}
                </div>
              )}

              {step.comment && (
                <div className="mt-2 italic text-sm text-muted-foreground">
                  "{step.comment}"
                </div>
              )}

              {step.sla_hours && !step.decided_at && (
                <div className="mt-1 text-xs text-muted-foreground">
                  SLA: {step.sla_hours}h
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
