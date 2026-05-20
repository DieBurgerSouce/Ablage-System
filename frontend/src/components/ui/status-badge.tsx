/**
 * StatusBadge - Unified Status Badge Component
 *
 * Provides consistent status badges across the application.
 * Supports predefined status configurations and custom variants.
 */

import * as React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '@/lib/utils';
import {
  CheckCircle,
  XCircle,
  Clock,
  AlertTriangle,
  AlertCircle,
  Loader2,
  Pause,
  Play,
  Ban,
  FileQuestion,
  type LucideIcon,
} from 'lucide-react';

// ==================== BADGE VARIANTS ====================

const statusBadgeVariants = cva(
  'inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium transition-colors',
  {
    variants: {
      variant: {
        // Success variants
        success: 'bg-green-100 text-green-800 dark:bg-green-950 dark:text-green-300',
        // Warning variants
        warning: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-950 dark:text-yellow-300',
        // Error variants
        error: 'bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300',
        // Info variants
        info: 'bg-blue-100 text-blue-800 dark:bg-blue-950 dark:text-blue-300',
        // Neutral variants
        neutral: 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-300',
        // Processing/pending
        pending: 'bg-orange-100 text-orange-800 dark:bg-orange-950 dark:text-orange-300',
        // Purple/special
        special: 'bg-purple-100 text-purple-800 dark:bg-purple-950 dark:text-purple-300',
        // Outline variants
        'outline-success': 'border border-green-500 text-green-700 dark:text-green-400',
        'outline-warning': 'border border-yellow-500 text-yellow-700 dark:text-yellow-400',
        'outline-error': 'border border-red-500 text-red-700 dark:text-red-400',
        'outline-info': 'border border-blue-500 text-blue-700 dark:text-blue-400',
        'outline-neutral': 'border border-gray-400 text-gray-700 dark:text-gray-400',
      },
      size: {
        sm: 'text-[10px] px-2 py-0.5',
        default: 'text-xs px-2.5 py-0.5',
        lg: 'text-sm px-3 py-1',
      },
    },
    defaultVariants: {
      variant: 'neutral',
      size: 'default',
    },
  }
);

// ==================== TYPES ====================

export type StatusBadgeVariant = NonNullable<VariantProps<typeof statusBadgeVariants>['variant']>;
export type StatusBadgeSize = NonNullable<VariantProps<typeof statusBadgeVariants>['size']>;

export interface StatusBadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof statusBadgeVariants> {
  /** Status label (German) */
  label: string;
  /** Optional icon */
  icon?: LucideIcon;
  /** Show icon */
  showIcon?: boolean;
  /** Pulsing animation for active states */
  pulse?: boolean;
  /** Spinning icon for loading states */
  spinning?: boolean;
}

// ==================== PREDEFINED STATUSES ====================

export interface StatusConfig {
  label: string;
  variant: StatusBadgeVariant;
  icon: LucideIcon;
}

/**
 * Document processing statuses
 */
export const DOCUMENT_STATUS: Record<string, StatusConfig> = {
  pending: { label: 'Ausstehend', variant: 'pending', icon: Clock },
  processing: { label: 'Wird verarbeitet', variant: 'info', icon: Loader2 },
  completed: { label: 'Abgeschlossen', variant: 'success', icon: CheckCircle },
  failed: { label: 'Fehlgeschlagen', variant: 'error', icon: XCircle },
  review_required: { label: 'Prüfung erforderlich', variant: 'warning', icon: AlertTriangle },
};

/**
 * Invoice statuses
 */
export const INVOICE_STATUS: Record<string, StatusConfig> = {
  draft: { label: 'Entwurf', variant: 'neutral', icon: FileQuestion },
  open: { label: 'Offen', variant: 'info', icon: Clock },
  partially_paid: { label: 'Teilweise bezahlt', variant: 'pending', icon: AlertCircle },
  paid: { label: 'Bezahlt', variant: 'success', icon: CheckCircle },
  overdue: { label: 'Überfällig', variant: 'error', icon: AlertTriangle },
  cancelled: { label: 'Storniert', variant: 'neutral', icon: Ban },
};

/**
 * Dunning levels
 */
export const DUNNING_STATUS: Record<number, StatusConfig> = {
  0: { label: 'Keine Mahnung', variant: 'neutral', icon: CheckCircle },
  1: { label: '1. Mahnung', variant: 'warning', icon: AlertCircle },
  2: { label: '2. Mahnung', variant: 'pending', icon: AlertTriangle },
  3: { label: '3. Mahnung', variant: 'error', icon: AlertTriangle },
  4: { label: 'Inkasso', variant: 'error', icon: Ban },
};

/**
 * Approval statuses
 */
export const APPROVAL_STATUS: Record<string, StatusConfig> = {
  pending: { label: 'Ausstehend', variant: 'pending', icon: Clock },
  approved: { label: 'Genehmigt', variant: 'success', icon: CheckCircle },
  rejected: { label: 'Abgelehnt', variant: 'error', icon: XCircle },
  escalated: { label: 'Eskaliert', variant: 'warning', icon: AlertTriangle },
};

/**
 * Alert statuses
 */
export const ALERT_STATUS: Record<string, StatusConfig> = {
  new: { label: 'Neu', variant: 'error', icon: AlertCircle },
  acknowledged: { label: 'Bestätigt', variant: 'info', icon: CheckCircle },
  in_progress: { label: 'In Bearbeitung', variant: 'pending', icon: Loader2 },
  resolved: { label: 'Gelöst', variant: 'success', icon: CheckCircle },
  dismissed: { label: 'Verworfen', variant: 'neutral', icon: Ban },
  escalated: { label: 'Eskaliert', variant: 'warning', icon: AlertTriangle },
};

/**
 * Alert severities
 */
export const ALERT_SEVERITY: Record<string, StatusConfig> = {
  info: { label: 'Info', variant: 'info', icon: AlertCircle },
  low: { label: 'Niedrig', variant: 'neutral', icon: AlertCircle },
  medium: { label: 'Mittel', variant: 'warning', icon: AlertTriangle },
  high: { label: 'Hoch', variant: 'pending', icon: AlertTriangle },
  critical: { label: 'Kritisch', variant: 'error', icon: XCircle },
};

/**
 * Workflow statuses
 */
export const WORKFLOW_STATUS: Record<string, StatusConfig> = {
  draft: { label: 'Entwurf', variant: 'neutral', icon: FileQuestion },
  active: { label: 'Aktiv', variant: 'success', icon: Play },
  paused: { label: 'Pausiert', variant: 'warning', icon: Pause },
  completed: { label: 'Abgeschlossen', variant: 'success', icon: CheckCircle },
  failed: { label: 'Fehlgeschlagen', variant: 'error', icon: XCircle },
  cancelled: { label: 'Abgebrochen', variant: 'neutral', icon: Ban },
};

/**
 * Risk levels
 */
export const RISK_LEVEL: Record<string, StatusConfig> = {
  low: { label: 'Niedriges Risiko', variant: 'success', icon: CheckCircle },
  medium: { label: 'Mittleres Risiko', variant: 'warning', icon: AlertCircle },
  high: { label: 'Hohes Risiko', variant: 'error', icon: AlertTriangle },
  critical: { label: 'Kritisches Risiko', variant: 'error', icon: XCircle },
};

// ==================== COMPONENT ====================

export const StatusBadge = React.forwardRef<HTMLSpanElement, StatusBadgeProps>(
  ({ className, variant, size, label, icon: Icon, showIcon = true, pulse, spinning, ...props }, ref) => {
    return (
      <span
        ref={ref}
        className={cn(
          statusBadgeVariants({ variant, size }),
          pulse && 'animate-pulse',
          className
        )}
        role="status"
        {...props}
      >
        {showIcon && Icon && (
          <Icon className={cn('h-3 w-3', spinning && 'animate-spin')} aria-hidden="true" />
        )}
        {label}
      </span>
    );
  }
);
StatusBadge.displayName = 'StatusBadge';

// ==================== SPECIALIZED BADGES ====================

/**
 * Document Status Badge
 */
export function DocumentStatusBadge({
  status,
  size,
  className,
}: {
  status: keyof typeof DOCUMENT_STATUS;
  size?: StatusBadgeSize;
  className?: string;
}) {
  const config = DOCUMENT_STATUS[status] ?? DOCUMENT_STATUS.pending;
  const isProcessing = status === 'processing';

  return (
    <StatusBadge
      label={config.label}
      variant={config.variant}
      icon={config.icon}
      size={size}
      spinning={isProcessing}
      className={className}
    />
  );
}

/**
 * Invoice Status Badge
 */
export function InvoiceStatusBadge({
  status,
  size,
  className,
}: {
  status: keyof typeof INVOICE_STATUS;
  size?: StatusBadgeSize;
  className?: string;
}) {
  const config = INVOICE_STATUS[status] ?? INVOICE_STATUS.draft;

  return (
    <StatusBadge
      label={config.label}
      variant={config.variant}
      icon={config.icon}
      size={size}
      className={className}
    />
  );
}

/**
 * Dunning Level Badge
 */
export function DunningLevelBadge({
  level,
  size,
  className,
}: {
  level: number;
  size?: StatusBadgeSize;
  className?: string;
}) {
  const config = DUNNING_STATUS[level] ?? DUNNING_STATUS[0];

  return (
    <StatusBadge
      label={config.label}
      variant={config.variant}
      icon={config.icon}
      size={size}
      className={className}
    />
  );
}

/**
 * Approval Status Badge
 */
export function ApprovalStatusBadge({
  status,
  size,
  className,
}: {
  status: keyof typeof APPROVAL_STATUS;
  size?: StatusBadgeSize;
  className?: string;
}) {
  const config = APPROVAL_STATUS[status] ?? APPROVAL_STATUS.pending;

  return (
    <StatusBadge
      label={config.label}
      variant={config.variant}
      icon={config.icon}
      size={size}
      className={className}
    />
  );
}

/**
 * Alert Status Badge
 */
export function AlertStatusBadge({
  status,
  size,
  className,
}: {
  status: keyof typeof ALERT_STATUS;
  size?: StatusBadgeSize;
  className?: string;
}) {
  const config = ALERT_STATUS[status] ?? ALERT_STATUS.new;
  const isInProgress = status === 'in_progress';

  return (
    <StatusBadge
      label={config.label}
      variant={config.variant}
      icon={config.icon}
      size={size}
      spinning={isInProgress}
      className={className}
    />
  );
}

/**
 * Alert Severity Badge
 */
export function AlertSeverityBadge({
  severity,
  size,
  className,
}: {
  severity: keyof typeof ALERT_SEVERITY;
  size?: StatusBadgeSize;
  className?: string;
}) {
  const config = ALERT_SEVERITY[severity] ?? ALERT_SEVERITY.info;
  const isCritical = severity === 'critical' || severity === 'high';

  return (
    <StatusBadge
      label={config.label}
      variant={config.variant}
      icon={config.icon}
      size={size}
      pulse={isCritical}
      className={className}
    />
  );
}

/**
 * Risk Level Badge
 */
export function RiskLevelBadge({
  level,
  size,
  className,
}: {
  level: keyof typeof RISK_LEVEL;
  size?: StatusBadgeSize;
  className?: string;
}) {
  const config = RISK_LEVEL[level] ?? RISK_LEVEL.low;

  return (
    <StatusBadge
      label={config.label}
      variant={config.variant}
      icon={config.icon}
      size={size}
      className={className}
    />
  );
}

export { statusBadgeVariants };
