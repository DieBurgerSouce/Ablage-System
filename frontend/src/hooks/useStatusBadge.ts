/**
 * useStatusBadge - Hook for Status Badge Configuration
 *
 * Provides a convenient way to get status badge configurations
 * based on status values or risk scores.
 */

import { useMemo } from 'react';
import type { StatusBadgeVariant } from '@/components/ui/status-badge';
import {
  DOCUMENT_STATUS,
  INVOICE_STATUS,
  DUNNING_STATUS,
  APPROVAL_STATUS,
  ALERT_STATUS,
  ALERT_SEVERITY,
  WORKFLOW_STATUS,
  RISK_LEVEL,
  type StatusConfig,
} from '@/components/ui/status-badge';
import {
  CheckCircle,
  XCircle,
  Clock,
  AlertTriangle,
  AlertCircle,
  type LucideIcon,
} from 'lucide-react';

// ==================== TYPES ====================

export type StatusType =
  | 'document'
  | 'invoice'
  | 'dunning'
  | 'approval'
  | 'alert'
  | 'severity'
  | 'workflow'
  | 'risk';

export interface StatusBadgeConfig extends StatusConfig {
  pulse?: boolean;
  spinning?: boolean;
}

export interface UseStatusBadgeOptions {
  /** Status type */
  type: StatusType;
  /** Status value */
  status: string | number;
  /** Custom configurations to override defaults */
  customConfigs?: Record<string | number, Partial<StatusConfig>>;
}

export interface UseStatusBadgeReturn {
  config: StatusBadgeConfig;
  label: string;
  variant: StatusBadgeVariant;
  icon: LucideIcon;
  isError: boolean;
  isWarning: boolean;
  isSuccess: boolean;
  isPending: boolean;
}

// ==================== STATUS MAPS ====================

const STATUS_MAPS: Record<StatusType, Record<string | number, StatusConfig>> = {
  document: DOCUMENT_STATUS,
  invoice: INVOICE_STATUS,
  dunning: DUNNING_STATUS,
  approval: APPROVAL_STATUS,
  alert: ALERT_STATUS,
  severity: ALERT_SEVERITY,
  workflow: WORKFLOW_STATUS,
  risk: RISK_LEVEL,
};

const DEFAULT_CONFIG: StatusConfig = {
  label: 'Unbekannt',
  variant: 'neutral',
  icon: AlertCircle,
};

// ==================== HOOK ====================

/**
 * Hook to get status badge configuration
 *
 * @example
 * ```tsx
 * function InvoiceRow({ invoice }) {
 *   const { config, isError } = useStatusBadge({
 *     type: 'invoice',
 *     status: invoice.status,
 *   });
 *
 *   return (
 *     <StatusBadge
 *       label={config.label}
 *       variant={config.variant}
 *       icon={config.icon}
 *     />
 *   );
 * }
 * ```
 */
export function useStatusBadge({
  type,
  status,
  customConfigs,
}: UseStatusBadgeOptions): UseStatusBadgeReturn {
  const config = useMemo<StatusBadgeConfig>(() => {
    // Check custom configs first
    if (customConfigs && status in customConfigs) {
      return { ...DEFAULT_CONFIG, ...customConfigs[status] };
    }

    // Get from status map
    const statusMap = STATUS_MAPS[type];
    if (statusMap && status in statusMap) {
      const baseConfig = statusMap[status];

      // Add dynamic properties
      const isProcessing =
        (type === 'document' && status === 'processing') ||
        (type === 'alert' && status === 'in_progress');

      const isCritical =
        (type === 'severity' && (status === 'critical' || status === 'high')) ||
        (type === 'risk' && (status === 'critical' || status === 'high'));

      return {
        ...baseConfig,
        spinning: isProcessing,
        pulse: isCritical,
      };
    }

    return DEFAULT_CONFIG;
  }, [type, status, customConfigs]);

  const isError = config.variant === 'error';
  const isWarning = config.variant === 'warning';
  const isSuccess = config.variant === 'success';
  const isPending = config.variant === 'pending' || config.variant === 'info';

  return {
    config,
    label: config.label,
    variant: config.variant,
    icon: config.icon,
    isError,
    isWarning,
    isSuccess,
    isPending,
  };
}

// ==================== UTILITY FUNCTIONS ====================

/**
 * Get risk level config from a risk score (0-100)
 *
 * @example
 * ```tsx
 * const config = getRiskLevelFromScore(85);
 * // { label: 'Hohes Risiko', variant: 'error', ... }
 * ```
 */
export function getRiskLevelFromScore(score: number): StatusConfig {
  if (score >= 90) {
    return RISK_LEVEL.critical;
  }
  if (score >= 75) {
    return RISK_LEVEL.high;
  }
  if (score >= 50) {
    return RISK_LEVEL.medium;
  }
  return RISK_LEVEL.low;
}

/**
 * Get dunning config from dunning level number
 */
export function getDunningConfig(level: number): StatusConfig {
  return DUNNING_STATUS[level] ?? DUNNING_STATUS[0];
}

/**
 * Get variant from boolean conditions
 *
 * @example
 * ```tsx
 * const variant = getVariantFromConditions({
 *   error: isOverdue,
 *   warning: isApproachingDeadline,
 *   success: isPaid,
 * });
 * ```
 */
export function getVariantFromConditions(conditions: {
  error?: boolean;
  warning?: boolean;
  success?: boolean;
  info?: boolean;
  pending?: boolean;
}): StatusBadgeVariant {
  if (conditions.error) return 'error';
  if (conditions.warning) return 'warning';
  if (conditions.success) return 'success';
  if (conditions.info) return 'info';
  if (conditions.pending) return 'pending';
  return 'neutral';
}

/**
 * Get variant from numeric value with thresholds
 *
 * @example
 * ```tsx
 * const variant = getVariantFromThresholds(ocrConfidence, {
 *   error: 0.5,
 *   warning: 0.7,
 *   success: 0.9,
 * });
 * ```
 */
export function getVariantFromThresholds(
  value: number,
  thresholds: {
    error?: number;
    warning?: number;
    success?: number;
  },
  ascending: boolean = true
): StatusBadgeVariant {
  if (ascending) {
    // Higher is better (e.g., confidence)
    if (thresholds.success !== undefined && value >= thresholds.success) {
      return 'success';
    }
    if (thresholds.warning !== undefined && value >= thresholds.warning) {
      return 'warning';
    }
    if (thresholds.error !== undefined && value < thresholds.error) {
      return 'error';
    }
  } else {
    // Lower is better (e.g., error count)
    if (thresholds.success !== undefined && value <= thresholds.success) {
      return 'success';
    }
    if (thresholds.warning !== undefined && value <= thresholds.warning) {
      return 'warning';
    }
    if (thresholds.error !== undefined && value > thresholds.error) {
      return 'error';
    }
  }
  return 'neutral';
}

/**
 * Hook for OCR confidence badge
 */
export function useOCRConfidenceBadge(confidence: number): StatusBadgeConfig {
  return useMemo(() => {
    const variant = getVariantFromThresholds(confidence, {
      success: 0.9,
      warning: 0.7,
      error: 0.5,
    });

    const labels: Record<StatusBadgeVariant, string> = {
      success: 'Hohe Konfidenz',
      warning: 'Mittlere Konfidenz',
      error: 'Niedrige Konfidenz',
      neutral: 'Unbekannt',
      info: 'Unbekannt',
      pending: 'Unbekannt',
      special: 'Unbekannt',
      'outline-success': 'Hohe Konfidenz',
      'outline-warning': 'Mittlere Konfidenz',
      'outline-error': 'Niedrige Konfidenz',
      'outline-info': 'Unbekannt',
      'outline-neutral': 'Unbekannt',
    };

    const icons: Record<StatusBadgeVariant, LucideIcon> = {
      success: CheckCircle,
      warning: AlertCircle,
      error: AlertTriangle,
      neutral: AlertCircle,
      info: AlertCircle,
      pending: Clock,
      special: AlertCircle,
      'outline-success': CheckCircle,
      'outline-warning': AlertCircle,
      'outline-error': AlertTriangle,
      'outline-info': AlertCircle,
      'outline-neutral': AlertCircle,
    };

    return {
      label: labels[variant],
      variant,
      icon: icons[variant],
    };
  }, [confidence]);
}

/**
 * Hook for days overdue badge
 */
export function useDaysOverdueBadge(daysOverdue: number): StatusBadgeConfig {
  return useMemo(() => {
    if (daysOverdue <= 0) {
      return {
        label: 'Fristgerecht',
        variant: 'success' as StatusBadgeVariant,
        icon: CheckCircle,
      };
    }
    if (daysOverdue <= 7) {
      return {
        label: `${daysOverdue} Tage ueberfaellig`,
        variant: 'warning' as StatusBadgeVariant,
        icon: Clock,
      };
    }
    if (daysOverdue <= 30) {
      return {
        label: `${daysOverdue} Tage ueberfaellig`,
        variant: 'pending' as StatusBadgeVariant,
        icon: AlertTriangle,
      };
    }
    return {
      label: `${daysOverdue} Tage ueberfaellig`,
      variant: 'error' as StatusBadgeVariant,
      icon: XCircle,
      pulse: true,
    };
  }, [daysOverdue]);
}

export default useStatusBadge;
