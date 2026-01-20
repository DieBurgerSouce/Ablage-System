/**
 * Onboarding Progress - Progress-Anzeige für Onboarding-Tour
 */

import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { CheckCircle2, Circle } from 'lucide-react';
import { useOnboardingStatus } from '../hooks/useHelp';

interface OnboardingProgressProps {
  onContinue?: () => void;
  compact?: boolean;
}

export function OnboardingProgress({
  onContinue,
  compact = false,
}: OnboardingProgressProps) {
  const { data: status, isLoading } = useOnboardingStatus();

  if (isLoading || !status || status.completed) {
    return null;
  }

  const progress = (status.steps_completed / status.total_steps) * 100;

  if (compact) {
    return (
      <div className="flex items-center gap-3 p-3 bg-muted rounded-md">
        <div className="flex-1">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-medium">Onboarding-Tour</span>
            <span className="text-xs text-muted-foreground">
              {status.steps_completed}/{status.total_steps}
            </span>
          </div>
          <Progress value={progress} className="h-2" />
        </div>
        {onContinue && status.steps_completed > 0 && (
          <Button size="sm" onClick={onContinue}>
            Fortsetzen
          </Button>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-4 p-4 border rounded-lg">
      <div>
        <h3 className="font-semibold mb-1">Willkommens-Tour</h3>
        <p className="text-sm text-muted-foreground">
          {status.steps_completed === 0
            ? 'Lernen Sie die wichtigsten Funktionen kennen'
            : `${status.steps_completed} von ${status.total_steps} Schritten abgeschlossen`}
        </p>
      </div>

      <Progress value={progress} />

      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1">
          {Array.from({ length: status.total_steps }).map((_, index) => (
            <div key={index} className="relative">
              {index < status.steps_completed ? (
                <CheckCircle2 className="h-4 w-4 text-primary" />
              ) : (
                <Circle
                  className={`h-4 w-4 ${
                    index === status.current_step
                      ? 'text-primary'
                      : 'text-muted-foreground'
                  }`}
                />
              )}
            </div>
          ))}
        </div>

        {onContinue && (
          <Button onClick={onContinue}>
            {status.steps_completed === 0 ? 'Tour starten' : 'Tour fortsetzen'}
          </Button>
        )}
      </div>
    </div>
  );
}

/**
 * Minimal Progress - Noch kompaktere Variante
 */
export function MinimalOnboardingProgress({ onContinue }: OnboardingProgressProps) {
  const { data: status, isLoading } = useOnboardingStatus();

  if (isLoading || !status || status.completed) {
    return null;
  }

  const progress = (status.steps_completed / status.total_steps) * 100;

  return (
    <button
      onClick={onContinue}
      className="w-full text-left p-2 rounded-md hover:bg-muted transition-colors"
    >
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs font-medium">Willkommens-Tour</span>
        <span className="text-xs text-muted-foreground">
          {status.steps_completed}/{status.total_steps}
        </span>
      </div>
      <Progress value={progress} className="h-1" />
    </button>
  );
}
