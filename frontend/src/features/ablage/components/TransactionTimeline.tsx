/**
 * TransactionTimeline - Horizontale Vorgangs-Timeline
 *
 * Zeigt den Ablauf eines Vorgangs als horizontale Timeline:
 * Anfrage → Angebot → Auftrag → Lieferschein → Rechnung → Zahlung
 *
 * Jeder Schritt kann einen Status haben:
 * - pending (grau, gestrichelt)
 * - active (blau, pulsierend)
 * - completed (gruen, Haekchen)
 * - skipped (grau, durchgestrichen)
 */

import { useMemo } from 'react';
import { Link } from '@tanstack/react-router';
import {
  HelpCircle,
  FileText,
  FileCheck,
  Truck,
  Receipt,
  Banknote,
  Check,
  Clock,
  SkipForward,
  ChevronRight,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';
import type {
  Transaction,
  TransactionStep,
  TransactionStepStatus,
  TransactionStepType,
} from '../types';
import { TRANSACTION_STEPS } from '../types';

// ==================== Types ====================

interface TransactionTimelineProps {
  transaction: Transaction;
  compact?: boolean;
  showHeader?: boolean;
  onStepClick?: (step: TransactionStep) => void;
}

// ==================== Helper Functions ====================

const STEP_ICONS: Record<TransactionStepType, React.ElementType> = {
  anfrage: HelpCircle,
  angebot: FileText,
  auftrag: FileCheck,
  lieferschein: Truck,
  rechnung: Receipt,
  zahlung: Banknote,
};

const STATUS_STYLES: Record<TransactionStepStatus, {
  bg: string;
  border: string;
  text: string;
  icon: React.ElementType | null;
}> = {
  pending: {
    bg: 'bg-gray-100 dark:bg-gray-800',
    border: 'border-gray-300 dark:border-gray-600 border-dashed',
    text: 'text-gray-400 dark:text-gray-500',
    icon: Clock,
  },
  active: {
    bg: 'bg-blue-100 dark:bg-blue-900/30',
    border: 'border-blue-500 border-2',
    text: 'text-blue-600 dark:text-blue-400',
    icon: null,
  },
  completed: {
    bg: 'bg-green-100 dark:bg-green-900/30',
    border: 'border-green-500',
    text: 'text-green-600 dark:text-green-400',
    icon: Check,
  },
  skipped: {
    bg: 'bg-gray-100 dark:bg-gray-800',
    border: 'border-gray-300 dark:border-gray-600',
    text: 'text-gray-400 dark:text-gray-500 line-through',
    icon: SkipForward,
  },
};

/**
 * Formatiert ein Datum für die Timeline-Anzeige (DD.MM.YY)
 */
function formatShortDate(dateString: string | null): string {
  if (!dateString) return '—';
  const date = new Date(dateString);
  return date.toLocaleDateString('de-DE', {
    day: '2-digit',
    month: '2-digit',
    year: '2-digit',
  });
}

/**
 * Formatiert einen Betrag als Währung
 */
function formatCurrency(amount: number | null, currency = 'EUR'): string {
  if (amount === null) return '—';
  return new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency,
    minimumFractionDigits: 2,
  }).format(amount);
}

/**
 * Berechnet den Fortschritt des Vorgangs (0-100%)
 */
function calculateProgress(steps: TransactionStep[]): number {
  const completed = steps.filter(
    (s) => s.status === 'completed' || s.status === 'skipped'
  ).length;
  return Math.round((completed / steps.length) * 100);
}

/**
 * Ermittelt den aktuellen Status-Text für den Vorgang
 */
function getStatusText(transaction: Transaction): string {
  const { status, steps } = transaction;

  if (status === 'completed') return 'Abgeschlossen';
  if (status === 'cancelled') return 'Abgebrochen';
  if (status === 'draft') return 'Entwurf';

  // Finde den aktiven oder nächsten pending Schritt
  const activeStep = steps.find((s) => s.status === 'active');
  if (activeStep) {
    const config = TRANSACTION_STEPS.find((c) => c.type === activeStep.type);
    return `Warte auf ${config?.label || activeStep.type}`;
  }

  const nextPending = steps.find((s) => s.status === 'pending');
  if (nextPending) {
    const config = TRANSACTION_STEPS.find((c) => c.type === nextPending.type);
    return `Nächster Schritt: ${config?.label || nextPending.type}`;
  }

  return 'In Bearbeitung';
}

// ==================== Sub-Components ====================

function TimelineStep({
  step,
  config,
  isLast,
  compact,
  onClick,
}: {
  step: TransactionStep;
  config: typeof TRANSACTION_STEPS[0];
  isLast: boolean;
  compact?: boolean;
  onClick?: () => void;
}) {
  const Icon = STEP_ICONS[step.type];
  const styles = STATUS_STYLES[step.status];
  const StatusIcon = styles.icon;

  const hasDocument = !!step.documentId;
  const isClickable = hasDocument && onClick;

  return (
    <div className="flex items-center">
      {/* Step Circle */}
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              type="button"
              onClick={isClickable ? onClick : undefined}
              disabled={!isClickable}
              className={cn(
                'relative flex flex-col items-center',
                isClickable && 'cursor-pointer hover:scale-105 transition-transform',
                !isClickable && 'cursor-default'
              )}
            >
              {/* Circle with Icon */}
              <div
                className={cn(
                  'w-12 h-12 rounded-full flex items-center justify-center border-2 transition-all',
                  styles.bg,
                  styles.border,
                  step.status === 'active' && 'animate-pulse'
                )}
              >
                <Icon className={cn('w-5 h-5', styles.text)} />

                {/* Status Badge */}
                {StatusIcon && (
                  <div
                    className={cn(
                      'absolute -bottom-1 -right-1 w-5 h-5 rounded-full flex items-center justify-center',
                      step.status === 'completed' && 'bg-green-500 text-white',
                      step.status === 'skipped' && 'bg-gray-400 text-white',
                      step.status === 'pending' && 'bg-gray-300 text-gray-600'
                    )}
                  >
                    <StatusIcon className="w-3 h-3" />
                  </div>
                )}
              </div>

              {/* Labels */}
              {!compact && (
                <div className="mt-2 text-center min-w-[80px]">
                  <p className={cn('text-xs font-medium', styles.text)}>
                    {step.documentNumber || config.shortCode}
                  </p>
                  <p className="text-[10px] text-muted-foreground">
                    {config.label}
                  </p>
                  {step.completedAt && (
                    <p className="text-[10px] text-muted-foreground">
                      {formatShortDate(step.completedAt)}
                    </p>
                  )}
                </div>
              )}
            </button>
          </TooltipTrigger>
          <TooltipContent side="bottom">
            <div className="text-sm">
              <p className="font-medium">{config.label}</p>
              {step.documentNumber && (
                <p className="text-muted-foreground">{step.documentNumber}</p>
              )}
              {step.amount !== null && (
                <p>{formatCurrency(step.amount, step.currency)}</p>
              )}
              {step.completedAt && (
                <p className="text-muted-foreground">
                  Abgeschlossen: {formatShortDate(step.completedAt)}
                </p>
              )}
              {!hasDocument && step.status === 'pending' && (
                <p className="text-muted-foreground italic">Noch kein Dokument</p>
              )}
            </div>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>

      {/* Connector Line */}
      {!isLast && (
        <div
          className={cn(
            'h-0.5 w-8 mx-1',
            step.status === 'completed' || step.status === 'skipped'
              ? 'bg-green-500'
              : 'bg-gray-300 dark:bg-gray-600'
          )}
        />
      )}
    </div>
  );
}

function TimelineHeader({
  transaction,
}: {
  transaction: Transaction;
}) {
  const progress = calculateProgress(transaction.steps);
  const statusText = getStatusText(transaction);

  return (
    <div className="flex items-center justify-between mb-4">
      <div>
        <h3 className="text-lg font-semibold">
          {transaction.transactionNumber}
        </h3>
        <p className="text-sm text-muted-foreground">
          {transaction.name}
        </p>
      </div>

      <div className="flex items-center gap-4">
        <div className="text-right">
          <p className="text-sm font-medium">{statusText}</p>
          <p className="text-xs text-muted-foreground">
            {progress}% abgeschlossen
          </p>
        </div>

        {transaction.totalAmount !== null && (
          <Badge variant="outline" className="text-base font-semibold">
            {formatCurrency(transaction.totalAmount, transaction.currency)}
          </Badge>
        )}
      </div>
    </div>
  );
}

// ==================== Main Component ====================

export function TransactionTimeline({
  transaction,
  compact = false,
  showHeader = true,
  onStepClick,
}: TransactionTimelineProps) {
  // Map transaction steps to configs
  const stepsWithConfig = useMemo(() => {
    return transaction.steps.map((step) => {
      const config = TRANSACTION_STEPS.find((c) => c.type === step.type);
      return { step, config: config! };
    });
  }, [transaction.steps]);

  return (
    <Card data-testid="transaction-timeline" className={cn(compact && 'border-0 shadow-none')}>
      {showHeader && !compact && (
        <CardHeader className="pb-2">
          <TimelineHeader transaction={transaction} />
        </CardHeader>
      )}

      <CardContent className={cn(compact && 'p-0')}>
        {/* Timeline */}
        <div className="flex items-start justify-center overflow-x-auto py-2">
          {stepsWithConfig.map(({ step, config }, index) => (
            <TimelineStep
              key={step.id}
              step={step}
              config={config}
              isLast={index === stepsWithConfig.length - 1}
              compact={compact}
              onClick={
                onStepClick && step.documentId
                  ? () => onStepClick(step)
                  : undefined
              }
            />
          ))}
        </div>

        {/* Footer with dates */}
        {!compact && (
          <div className="flex items-center justify-between mt-4 pt-4 border-t text-xs text-muted-foreground">
            <span>
              Erstellt: {formatShortDate(transaction.createdAt)}
            </span>
            <span>
              Letzte Aktivität: {formatShortDate(transaction.lastActivityAt)}
            </span>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ==================== Compact Variant ====================

export function TransactionTimelineCompact({
  transaction,
  onStepClick,
}: {
  transaction: Transaction;
  onStepClick?: (step: TransactionStep) => void;
}) {
  return (
    <TransactionTimeline
      transaction={transaction}
      compact
      showHeader={false}
      onStepClick={onStepClick}
    />
  );
}

// ==================== List Item Variant ====================

export function TransactionListItem({
  transaction,
  onStepClick,
  onClick,
}: {
  transaction: Transaction;
  onStepClick?: (step: TransactionStep) => void;
  onClick?: () => void;
}) {
  const progress = calculateProgress(transaction.steps);
  const statusText = getStatusText(transaction);

  return (
    <Card
      data-testid="transaction-list-item"
      className={cn(
        'transition-all hover:shadow-md',
        onClick && 'cursor-pointer hover:border-blue-300'
      )}
      onClick={onClick}
    >
      <CardContent className="p-4">
        {/* Header Row */}
        <div className="flex items-start justify-between mb-3">
          <div className="flex-1">
            <div className="flex items-center gap-2">
              <h4 className="font-semibold">{transaction.transactionNumber}</h4>
              <Badge
                variant={
                  transaction.status === 'completed'
                    ? 'default'
                    : transaction.status === 'cancelled'
                    ? 'destructive'
                    : 'secondary'
                }
              >
                {statusText}
              </Badge>
            </div>
            <p className="text-sm text-muted-foreground mt-0.5">
              {transaction.name}
            </p>
            <p className="text-xs text-muted-foreground">
              {transaction.entityName}
            </p>
          </div>

          <div className="text-right">
            {transaction.totalAmount !== null && (
              <p className="font-semibold">
                {formatCurrency(transaction.totalAmount, transaction.currency)}
              </p>
            )}
            <p className="text-xs text-muted-foreground">
              {progress}% abgeschlossen
            </p>
          </div>
        </div>

        {/* Compact Timeline */}
        <TransactionTimelineCompact
          transaction={transaction}
          onStepClick={onStepClick}
        />

        {/* Footer */}
        <div className="flex items-center justify-between mt-3 pt-3 border-t text-xs text-muted-foreground">
          <span>Erstellt: {formatShortDate(transaction.createdAt)}</span>
          {onClick && (
            <span className="flex items-center text-blue-600 dark:text-blue-400">
              Details anzeigen
              <ChevronRight className="w-3 h-3 ml-1" />
            </span>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

export default TransactionTimeline;
