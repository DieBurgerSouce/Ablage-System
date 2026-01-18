/**
 * SkontoAlertBadge - Skonto-Status Badge Komponente
 *
 * Zeigt den Skonto-Status einer Rechnung als farbkodiertes Badge an.
 * - Gruen: Skonto verfuegbar und Zeit vorhanden
 * - Gelb: Skonto laeuft bald ab (< 3 Tage)
 * - Rot: Skonto abgelaufen
 * - Grau: Kein Skonto konfiguriert oder bereits genutzt
 */

import { Badge } from '@/components/ui/badge';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { Clock, CheckCircle, AlertTriangle, XCircle, Percent } from 'lucide-react';
import { cn } from '@/lib/utils';
import { UI_LABELS } from '../types/invoice-types';
import { formatCurrency, formatDate, formatDaysUntil } from '@/features/banking/utils/format';

type SkontoStatus = 'available' | 'expiring' | 'expired' | 'used' | 'none';

interface SkontoAlertBadgeProps {
  percentage: number | null;
  deadline: string | null;
  amount: number | null;
  used: boolean;
  totalAmount?: number;
  className?: string;
  showDetails?: boolean;
}

/**
 * Berechnet den Skonto-Status basierend auf Deadline und Used-Flag
 */
function getSkontoStatus(
  deadline: string | null,
  used: boolean,
  percentage: number | null
): SkontoStatus {
  if (used) return 'used';
  if (!deadline || !percentage) return 'none';

  const deadlineDate = new Date(deadline);
  const now = new Date();
  const daysUntil = Math.ceil(
    (deadlineDate.getTime() - now.getTime()) / (1000 * 60 * 60 * 24)
  );

  if (daysUntil < 0) return 'expired';
  if (daysUntil <= 3) return 'expiring';
  return 'available';
}

const STATUS_CONFIG: Record<
  SkontoStatus,
  {
    label: string;
    icon: typeof Clock;
    className: string;
    tooltipClassName: string;
  }
> = {
  available: {
    label: UI_LABELS.skontoAvailable,
    icon: Percent,
    className: 'bg-green-50 text-green-700 border-green-200',
    tooltipClassName: 'text-green-700',
  },
  expiring: {
    label: UI_LABELS.skontoExpiring,
    icon: AlertTriangle,
    className: 'bg-yellow-50 text-yellow-700 border-yellow-200 animate-pulse',
    tooltipClassName: 'text-yellow-700',
  },
  expired: {
    label: UI_LABELS.skontoExpired,
    icon: XCircle,
    className: 'bg-red-50 text-red-700 border-red-200',
    tooltipClassName: 'text-red-700',
  },
  used: {
    label: UI_LABELS.skontoUsed,
    icon: CheckCircle,
    className: 'bg-blue-50 text-blue-700 border-blue-200',
    tooltipClassName: 'text-blue-700',
  },
  none: {
    label: UI_LABELS.skontoNotConfigured,
    icon: Percent,
    className: 'bg-gray-100 text-gray-500 border-gray-200',
    tooltipClassName: 'text-gray-500',
  },
};

export function SkontoAlertBadge({
  percentage,
  deadline,
  amount,
  used,
  totalAmount,
  className,
  showDetails = false,
}: SkontoAlertBadgeProps) {
  const status = getSkontoStatus(deadline, used, percentage);
  const config = STATUS_CONFIG[status];
  const Icon = config.icon;

  // Berechne Tage bis Deadline
  const daysUntil = deadline
    ? Math.ceil(
        (new Date(deadline).getTime() - new Date().getTime()) /
          (1000 * 60 * 60 * 24)
      )
    : null;

  // Tooltip-Inhalt
  const tooltipContent = (
    <div className="space-y-1 text-sm">
      <div className={cn('font-medium', config.tooltipClassName)}>
        {config.label}
      </div>
      {percentage && (
        <div className="flex justify-between gap-4">
          <span className="text-muted-foreground">Skonto:</span>
          <span className="font-medium">{percentage}%</span>
        </div>
      )}
      {amount !== null && amount !== undefined && (
        <div className="flex justify-between gap-4">
          <span className="text-muted-foreground">Ersparnis:</span>
          <span className="font-medium text-green-600">
            {formatCurrency(amount)}
          </span>
        </div>
      )}
      {deadline && status !== 'expired' && status !== 'used' && (
        <div className="flex justify-between gap-4">
          <span className="text-muted-foreground">Frist:</span>
          <span className="font-medium">{formatDate(deadline)}</span>
        </div>
      )}
      {daysUntil !== null && status === 'available' && (
        <div className="flex justify-between gap-4">
          <span className="text-muted-foreground">Verbleibend:</span>
          <span className="font-medium">{formatDaysUntil(daysUntil)}</span>
        </div>
      )}
      {daysUntil !== null && status === 'expiring' && (
        <div className="text-yellow-600 font-medium mt-1">
          Nur noch {daysUntil} {daysUntil === 1 ? 'Tag' : 'Tage'}!
        </div>
      )}
      {totalAmount && amount && status !== 'used' && status !== 'none' && (
        <div className="border-t pt-1 mt-1 flex justify-between gap-4">
          <span className="text-muted-foreground">Netto-Betrag:</span>
          <span className="font-medium">{formatCurrency(totalAmount - amount)}</span>
        </div>
      )}
    </div>
  );

  if (status === 'none' && !showDetails) {
    return null;
  }

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Badge
          variant="outline"
          className={cn(
            'font-medium border cursor-help',
            config.className,
            className
          )}
        >
          <Icon className="w-3 h-3 mr-1" />
          {showDetails && percentage ? `${percentage}%` : config.label}
        </Badge>
      </TooltipTrigger>
      <TooltipContent side="top" align="center" className="max-w-xs">
        {tooltipContent}
      </TooltipContent>
    </Tooltip>
  );
}

/**
 * Kompakte Version fuer Tabellen - zeigt nur Icon wenn Skonto verfuegbar
 */
export function SkontoAlertBadgeCompact({
  percentage,
  deadline,
  amount,
  used,
  className,
}: Omit<SkontoAlertBadgeProps, 'showDetails' | 'totalAmount'>) {
  const status = getSkontoStatus(deadline, used, percentage);

  if (status === 'none') {
    return <span className={cn('text-muted-foreground', className)}>-</span>;
  }

  const config = STATUS_CONFIG[status];
  const Icon = config.icon;

  const daysUntil = deadline
    ? Math.ceil(
        (new Date(deadline).getTime() - new Date().getTime()) /
          (1000 * 60 * 60 * 24)
      )
    : null;

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Badge
          variant="outline"
          className={cn(
            'font-medium border text-xs px-1.5 py-0.5 cursor-help',
            config.className,
            className
          )}
        >
          <Icon className="w-3 h-3 mr-0.5" />
          {percentage}%
        </Badge>
      </TooltipTrigger>
      <TooltipContent side="top" align="center">
        <div className="text-sm">
          <div className={cn('font-medium', config.tooltipClassName)}>
            {config.label}
          </div>
          {amount !== null && (
            <div>Ersparnis: {formatCurrency(amount)}</div>
          )}
          {deadline && status !== 'expired' && status !== 'used' && (
            <div>
              Frist: {formatDate(deadline)}
              {daysUntil !== null && daysUntil >= 0 && (
                <span className="ml-1">({daysUntil}d)</span>
              )}
            </div>
          )}
        </div>
      </TooltipContent>
    </Tooltip>
  );
}

/**
 * Alert Banner fuer bevorstehende Skonto-Fristen
 */
export function SkontoExpiringAlert({
  invoiceNumber,
  deadline,
  amount,
  percentage,
  onApplySkonto,
  className,
}: {
  invoiceNumber: string | null;
  deadline: string;
  amount: number;
  percentage: number;
  onApplySkonto?: () => void;
  className?: string;
}) {
  const daysUntil = Math.ceil(
    (new Date(deadline).getTime() - new Date().getTime()) /
      (1000 * 60 * 60 * 24)
  );

  const isUrgent = daysUntil <= 1;

  return (
    <div
      className={cn(
        'flex items-center justify-between gap-4 p-3 rounded-lg border',
        isUrgent
          ? 'bg-red-50 border-red-200'
          : 'bg-yellow-50 border-yellow-200',
        className
      )}
    >
      <div className="flex items-center gap-3">
        <AlertTriangle
          className={cn(
            'w-5 h-5',
            isUrgent ? 'text-red-500' : 'text-yellow-500'
          )}
        />
        <div>
          <div className="font-medium">
            {invoiceNumber || 'Rechnung'}: {UI_LABELS.skontoExpiring}
          </div>
          <div className="text-sm text-muted-foreground">
            {percentage}% Skonto ({formatCurrency(amount)}) bis{' '}
            {formatDate(deadline)}
            {isUrgent && (
              <span className="text-red-600 font-medium ml-1">
                – {daysUntil === 0 ? 'Heute!' : 'Morgen!'}
              </span>
            )}
          </div>
        </div>
      </div>
      {onApplySkonto && (
        <button
          onClick={onApplySkonto}
          className={cn(
            'px-3 py-1.5 rounded-md font-medium text-sm transition-colors',
            isUrgent
              ? 'bg-red-600 text-white hover:bg-red-700'
              : 'bg-yellow-600 text-white hover:bg-yellow-700'
          )}
        >
          {UI_LABELS.actionApplySkonto}
        </button>
      )}
    </div>
  );
}
