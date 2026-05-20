import { FileCheck } from 'lucide-react';

interface ApprovalStampProps {
  status: 'approved' | 'rejected';
  approverName: string;
  date: string;
  stepNumber?: number;
  totalSteps?: number;
  className?: string;
}

export function ApprovalStamp({
  status,
  approverName,
  date,
  stepNumber,
  totalSteps,
  className,
}: ApprovalStampProps) {
  const isApproved = status === 'approved';
  const borderColor = isApproved ? 'border-green-600' : 'border-red-600';
  const textColor = isApproved ? 'text-green-700' : 'text-red-700';
  const stampText = isApproved ? 'FREIGEGEBEN' : 'ABGELEHNT';

  const formatDate = (dateStr: string): string => {
    return new Date(dateStr).toLocaleDateString('de-DE', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  return (
    <div
      className={`inline-block rounded-lg border-2 ${borderColor} ${textColor} bg-white px-6 py-4 shadow-md ${className}`}
      style={{ transform: 'rotate(-2deg)' }}
    >
      <div className="flex items-start gap-3">
        <FileCheck className="h-8 w-8 flex-shrink-0" />
        <div className="flex-1">
          <div className="text-xl font-bold uppercase tracking-wide">{stampText}</div>
          <div className="mt-2 font-medium">{approverName}</div>
          <div className="mt-1 text-sm">{formatDate(date)}</div>
          {stepNumber !== undefined && totalSteps !== undefined && (
            <div className="mt-1 text-xs opacity-75">
              Schritt {stepNumber} von {totalSteps}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
