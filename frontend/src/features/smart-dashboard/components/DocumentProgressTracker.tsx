// Document Progress Tracker Component
// DHL-style horizontal stepper: Hochgeladen → OCR → Validierung → Freigabe → Archiviert

import { Check, Clock, AlertCircle } from 'lucide-react';
import { cn } from '@/lib/utils';
import { type DocumentProgress, PROGRESS_STEP_CONFIG } from '../types/smart-dashboard-types';

interface DocumentProgressTrackerProps {
  progress: DocumentProgress;
  className?: string;
}

export function DocumentProgressTracker({ progress, className }: DocumentProgressTrackerProps) {
  const steps = progress.steps;

  return (
    <div className={cn('w-full', className)}>
      <div className="flex items-center justify-between">
        {steps.map((step, index) => {
          const config = PROGRESS_STEP_CONFIG[step.stepName.toLowerCase()];
          const Icon = config?.icon || Clock;
          const isCompleted = step.status === 'completed';
          const isActive = step.status === 'active';
          const isFailed = step.status === 'failed';
          const isPending = step.status === 'pending';

          return (
            <div key={step.stepName} className="flex-1 flex flex-col items-center relative">
              {/* Connector Line */}
              {index < steps.length - 1 && (
                <div
                  className={cn(
                    'absolute left-1/2 top-5 h-0.5 w-full',
                    isCompleted ? 'bg-green-500' : 'bg-muted'
                  )}
                  style={{ transform: 'translateX(50%)' }}
                />
              )}

              {/* Step Circle */}
              <div
                className={cn(
                  'relative z-10 flex h-10 w-10 items-center justify-center rounded-full border-2 bg-background transition-colors',
                  isCompleted && 'border-green-500 bg-green-500 text-white',
                  isActive && 'border-blue-500 bg-blue-500 text-white animate-pulse',
                  isFailed && 'border-red-500 bg-red-500 text-white',
                  isPending && 'border-muted bg-muted text-muted-foreground'
                )}
              >
                {isCompleted && <Check className="h-5 w-5" />}
                {isFailed && <AlertCircle className="h-5 w-5" />}
                {(isActive || isPending) && <Icon className="h-5 w-5" />}
              </div>

              {/* Step Label */}
              <div className="mt-2 text-center">
                <p
                  className={cn(
                    'text-sm font-medium',
                    isActive && 'text-blue-600 dark:text-blue-400',
                    isCompleted && 'text-green-600 dark:text-green-400',
                    isFailed && 'text-red-600 dark:text-red-400',
                    isPending && 'text-muted-foreground'
                  )}
                >
                  {config?.label || step.stepName}
                </p>
                {step.timestamp && (
                  <p className="text-xs text-muted-foreground mt-1">
                    {new Date(step.timestamp).toLocaleString('de-DE', {
                      dateStyle: 'short',
                      timeStyle: 'short',
                    })}
                  </p>
                )}
                {step.message && (
                  <p className="text-xs text-muted-foreground mt-1">{step.message}</p>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Overall Status Banner */}
      <div className="mt-6 text-center">
        {progress.overallStatus === 'completed' && (
          <p className="text-sm font-medium text-green-600 dark:text-green-400">
            ✓ Verarbeitung abgeschlossen
          </p>
        )}
        {progress.overallStatus === 'failed' && (
          <p className="text-sm font-medium text-red-600 dark:text-red-400">
            ✗ Verarbeitung fehlgeschlagen
          </p>
        )}
        {progress.overallStatus === 'in_progress' && (
          <p className="text-sm font-medium text-blue-600 dark:text-blue-400">
            ⟳ Aktueller Schritt: {PROGRESS_STEP_CONFIG[progress.currentStep.toLowerCase()]?.label || progress.currentStep}
          </p>
        )}
      </div>
    </div>
  );
}
