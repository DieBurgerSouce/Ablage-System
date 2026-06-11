/**
 * ActionProposalCard - Displays a proposed action from the Finance Assistant
 *
 * Vision 2.0 - Phase 1 (Januar 2026)
 */

import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Play,
  X,
  AlertTriangle,
  CheckCircle,
  Loader2,
  ChevronDown,
  ChevronUp,
  Undo2,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { cn } from '@/lib/utils';
import { type ActionData, type ExecuteActionResponse, getActionTypeLabel } from '@/lib/api/services/finance-assistant';

interface ActionProposalCardProps {
  action: ActionData;
  onExecute: (action: ActionData) => Promise<ExecuteActionResponse>;
  onDismiss: () => void;
  onRollback?: (actionId: string) => Promise<void>;
  executionResult?: ExecuteActionResponse;
  className?: string;
}

export function ActionProposalCard({
  action,
  onExecute,
  onDismiss,
  onRollback,
  executionResult,
  className,
}: ActionProposalCardProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [isConfirmOpen, setIsConfirmOpen] = useState(false);
  const [isExecuting, setIsExecuting] = useState(false);
  const [isRollingBack, setIsRollingBack] = useState(false);
  const [localResult, setLocalResult] = useState<ExecuteActionResponse | null>(null);

  const result = executionResult || localResult;
  const isCompleted = result?.success === true;
  const isFailed = result?.success === false;
  const canRollback = result?.rollback_possible && onRollback;

  const handleExecute = async () => {
    if (action.requires_confirmation) {
      setIsConfirmOpen(true);
    } else {
      await executeAction();
    }
  };

  const executeAction = async () => {
    setIsExecuting(true);
    try {
      const response = await onExecute(action);
      setLocalResult(response);
    } catch (error) {
      setLocalResult({
        action_id: '',
        status: 'failed' as const,
        success: false,
        message: error instanceof Error ? error.message : 'Unbekannter Fehler',
        affected_count: 0,
        rollback_possible: false,
        execution_time_ms: 0,
        metadata: {},
      });
    } finally {
      setIsExecuting(false);
      setIsConfirmOpen(false);
    }
  };

  const handleRollback = async () => {
    if (!result?.action_id || !onRollback) return;
    setIsRollingBack(true);
    try {
      await onRollback(result.action_id);
      setLocalResult(null);
    } finally {
      setIsRollingBack(false);
    }
  };

  const confidenceColor =
    action.confidence >= 0.9
      ? 'text-green-500'
      : action.confidence >= 0.7
        ? 'text-yellow-500'
        : 'text-orange-500';

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      className={cn(
        'rounded-lg border bg-card p-4 shadow-sm',
        isCompleted && 'border-green-500/30 bg-green-500/5',
        isFailed && 'border-red-500/30 bg-red-500/5',
        className
      )}
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1">
          <div className="flex items-center gap-2">
            <h4 className="font-medium">{getActionTypeLabel(action.action_type)}</h4>
            {action.requires_confirmation && (
              <Badge variant="outline\" className="text-xs">
                <AlertTriangle className="mr-1 h-3 w-3" />
                Bestätigung
              </Badge>
            )}
          </div>
          <p className="mt-1 text-sm text-muted-foreground">{action.description}</p>
        </div>

        {!result && (
          <Button variant="ghost" size="icon" onClick={onDismiss} className="h-8 w-8">
            <X className="h-4 w-4" />
          </Button>
        )}
      </div>

      {/* Stats */}
      <div className="mt-3 flex flex-wrap items-center gap-4 text-sm">
        <div className="flex items-center gap-1.5">
          <span className="text-muted-foreground">Betroffene:</span>
          <span className="font-medium">{action.affected_count}</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="text-muted-foreground">Konfidenz:</span>
          <span className={cn('font-medium', confidenceColor)}>
            {Math.round(action.confidence * 100)}%
          </span>
        </div>
      </div>

      {/* Confidence Bar */}
      <Progress value={action.confidence * 100} className="mt-2 h-1" />

      {/* Expandable Parameters */}
      {Object.keys(action.parameters).length > 0 && (
        <div className="mt-3">
          <button
            onClick={() => setIsExpanded(!isExpanded)}
            className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
          >
            {isExpanded ? (
              <ChevronUp className="h-4 w-4" />
            ) : (
              <ChevronDown className="h-4 w-4" />
            )}
            Parameter anzeigen
          </button>
          <AnimatePresence>
            {isExpanded && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: 'auto', opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                className="overflow-hidden"
              >
                <div className="mt-2 rounded-md bg-muted/50 p-3 text-xs font-mono">
                  {Object.entries(action.parameters).map(([key, value]) => (
                    <div key={key} className="flex gap-2">
                      <span className="text-muted-foreground">{key}:</span>
                      <span>{JSON.stringify(value)}</span>
                    </div>
                  ))}
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      )}

      {/* Result Display */}
      {result && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="mt-3 rounded-md border p-3"
        >
          <div className="flex items-center gap-2">
            {result.success ? (
              <CheckCircle className="h-4 w-4 text-green-500" />
            ) : (
              <AlertTriangle className="h-4 w-4 text-red-500" />
            )}
            <span className={cn('text-sm font-medium', result.success ? 'text-green-600' : 'text-red-600')}>
              {result.message}
            </span>
          </div>
          {result.affected_count > 0 && (
            <p className="mt-1 text-xs text-muted-foreground">
              {result.affected_count} Elemente betroffen in {result.execution_time_ms}ms
            </p>
          )}
          {result.error_details && (
            <p className="mt-1 text-xs text-red-500">{result.error_details}</p>
          )}
        </motion.div>
      )}

      {/* Actions */}
      <div className="mt-4 flex items-center gap-2">
        {!result ? (
          <>
            <Button
              onClick={handleExecute}
              disabled={isExecuting}
              size="sm"
              className="flex-1"
            >
              {isExecuting ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Play className="mr-2 h-4 w-4" />
              )}
              Ausführen
            </Button>
            <Button variant="outline" size="sm" onClick={onDismiss}>
              Verwerfen
            </Button>
          </>
        ) : canRollback ? (
          <Button
            variant="outline"
            size="sm"
            onClick={handleRollback}
            disabled={isRollingBack}
          >
            {isRollingBack ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Undo2 className="mr-2 h-4 w-4" />
            )}
            Rückgängig
          </Button>
        ) : null}
      </div>

      {/* Confirmation Dialog */}
      <AlertDialog open={isConfirmOpen} onOpenChange={setIsConfirmOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Aktion bestätigen</AlertDialogTitle>
            <AlertDialogDescription>
              Möchten Sie die Aktion "{getActionTypeLabel(action.action_type)}" wirklich
              ausführen? Dies betrifft {action.affected_count} Elemente.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Abbrechen</AlertDialogCancel>
            <AlertDialogAction onClick={executeAction}>
              {isExecuting ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : null}
              Bestätigen
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </motion.div>
  );
}
