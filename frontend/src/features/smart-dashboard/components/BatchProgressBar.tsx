// Batch Progress Bar Component
// Shows: X von Y Dokumente, percentage bar, estimated time remaining

import { Progress } from '@/components/ui/progress';
import { Card, CardContent } from '@/components/ui/card';
import { Clock, FileText, AlertTriangle } from 'lucide-react';
import { cn } from '@/lib/utils';
import { type BatchProgress, formatEstimatedTime, UI_LABELS } from '../types/smart-dashboard-types';

interface BatchProgressBarProps {
  progress: BatchProgress;
  className?: string;
}

export function BatchProgressBar({ progress, className }: BatchProgressBarProps) {
  const percentage = Math.round(
    (progress.processedDocuments / progress.totalDocuments) * 100
  );
  const hasErrors = progress.failedDocuments > 0;

  return (
    <Card className={cn('', className)}>
      <CardContent className="pt-6">
        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <FileText className="h-5 w-5 text-muted-foreground" />
            <span className="font-medium">
              {UI_LABELS.BATCH_PROGRESS_LABEL}
            </span>
          </div>
          <span className="text-sm text-muted-foreground">
            {progress.processedDocuments} von {progress.totalDocuments} {UI_LABELS.BATCH_DOCUMENTS_LABEL}
          </span>
        </div>

        {/* Progress Bar */}
        <Progress
          value={percentage}
          className={cn('h-3', hasErrors && 'bg-red-100 dark:bg-red-950')}
        />

        {/* Stats Row */}
        <div className="flex items-center justify-between mt-4 text-sm">
          {/* Percentage */}
          <span className="font-medium">{percentage}%</span>

          {/* Estimated Time */}
          {progress.estimatedTimeRemainingSeconds !== undefined && (
            <div className="flex items-center gap-1 text-muted-foreground">
              <Clock className="h-4 w-4" />
              <span>
                {UI_LABELS.BATCH_ESTIMATED_TIME}: {formatEstimatedTime(progress.estimatedTimeRemainingSeconds)}
              </span>
            </div>
          )}

          {/* Failed Documents Warning */}
          {hasErrors && (
            <div className="flex items-center gap-1 text-red-600 dark:text-red-400">
              <AlertTriangle className="h-4 w-4" />
              <span>{progress.failedDocuments} fehlgeschlagen</span>
            </div>
          )}
        </div>

        {/* Detailed Stats */}
        <div className="mt-4 grid grid-cols-3 gap-4 text-center">
          <div>
            <p className="text-2xl font-bold text-green-600 dark:text-green-400">
              {progress.processedDocuments - progress.failedDocuments}
            </p>
            <p className="text-xs text-muted-foreground">Erfolgreich</p>
          </div>
          <div>
            <p className="text-2xl font-bold text-blue-600 dark:text-blue-400">
              {progress.totalDocuments - progress.processedDocuments}
            </p>
            <p className="text-xs text-muted-foreground">Verbleibend</p>
          </div>
          <div>
            <p className={cn(
              'text-2xl font-bold',
              hasErrors ? 'text-red-600 dark:text-red-400' : 'text-muted-foreground'
            )}>
              {progress.failedDocuments}
            </p>
            <p className="text-xs text-muted-foreground">Fehler</p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
