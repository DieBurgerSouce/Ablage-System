/**
 * SLABreachAlert Component
 * Warning banner for SLA breaches
 */

import { useState } from 'react';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { AlertTriangle, X } from 'lucide-react';
import { cn } from '@/lib/utils';

interface SLABreachAlertProps {
  breachCount: number;
  severity?: 'warning' | 'error';
  onDismiss?: () => void;
}

export function SLABreachAlert({
  breachCount,
  severity = 'warning',
  onDismiss,
}: SLABreachAlertProps) {
  const [isDismissed, setIsDismissed] = useState(false);

  if (isDismissed || breachCount === 0) {
    return null;
  }

  const handleDismiss = () => {
    setIsDismissed(true);
    onDismiss?.();
  };

  return (
    <Alert
      className={cn(
        'relative',
        severity === 'error' && 'border-destructive bg-destructive/10',
        severity === 'warning' && 'border-yellow-500 bg-yellow-50 dark:bg-yellow-950/20'
      )}
    >
      <AlertTriangle
        className={cn(
          'h-4 w-4',
          severity === 'error' && 'text-destructive',
          severity === 'warning' && 'text-yellow-600 dark:text-yellow-500'
        )}
      />
      <AlertTitle>SLA-Verstöße erkannt</AlertTitle>
      <AlertDescription>
        Es wurden{' '}
        <strong className={severity === 'error' ? 'text-destructive' : 'text-yellow-700'}>
          {breachCount} SLA-Verstöße
        </strong>{' '}
        festgestellt. Bitte überprüfen Sie die ausstehenden Genehmigungen.
      </AlertDescription>
      {onDismiss && (
        <Button
          variant="ghost"
          size="icon"
          className="absolute top-2 right-2 h-6 w-6"
          onClick={handleDismiss}
        >
          <X className="h-4 w-4" />
        </Button>
      )}
    </Alert>
  );
}
