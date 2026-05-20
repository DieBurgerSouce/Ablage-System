/**
 * Document Timeline - Dokumenten-Lebenszyklus
 *
 * Zeigt den Lebenszyklus eines Dokuments als vertikale Timeline an.
 */

import { CheckCircle2, Clock, SkipForward } from 'lucide-react';
import { cn } from '@/lib/utils';

export interface TimelineStage {
  name: string;
  timestamp?: string;
  status: 'completed' | 'pending' | 'skipped';
}

interface DocumentTimelineProps {
  stages: TimelineStage[];
}

export function DocumentTimeline({ stages }: DocumentTimelineProps) {
  return (
    <div className="space-y-4">
      {stages.map((stage, index) => {
        const isLast = index === stages.length - 1;

        return (
          <div key={index} className="flex gap-4">
            {/* Icon and Line */}
            <div className="flex flex-col items-center">
              {/* Icon */}
              <div
                className={cn(
                  'flex h-10 w-10 items-center justify-center rounded-full border-2',
                  stage.status === 'completed' &&
                    'border-green-600 bg-green-50 text-green-600',
                  stage.status === 'pending' &&
                    'border-yellow-600 bg-yellow-50 text-yellow-600',
                  stage.status === 'skipped' && 'border-gray-300 bg-gray-50 text-gray-400'
                )}
              >
                {stage.status === 'completed' && <CheckCircle2 className="h-5 w-5" />}
                {stage.status === 'pending' && <Clock className="h-5 w-5" />}
                {stage.status === 'skipped' && <SkipForward className="h-5 w-5" />}
              </div>

              {/* Connecting Line */}
              {!isLast && (
                <div
                  className={cn(
                    'w-0.5 flex-1 min-h-[2rem]',
                    stage.status === 'completed' ? 'bg-green-600' : 'bg-gray-300'
                  )}
                />
              )}
            </div>

            {/* Content */}
            <div className="flex-1 pb-8">
              <h4
                className={cn(
                  'font-semibold',
                  stage.status === 'completed' && 'text-foreground',
                  stage.status === 'pending' && 'text-yellow-600',
                  stage.status === 'skipped' && 'text-muted-foreground'
                )}
              >
                {stage.name}
              </h4>
              {stage.timestamp && (
                <p className="text-sm text-muted-foreground mt-1">
                  {new Date(stage.timestamp).toLocaleString('de-DE', {
                    dateStyle: 'medium',
                    timeStyle: 'short',
                  })}
                </p>
              )}
              {!stage.timestamp && stage.status === 'pending' && (
                <p className="text-sm text-muted-foreground mt-1">Ausstehend</p>
              )}
              {!stage.timestamp && stage.status === 'skipped' && (
                <p className="text-sm text-muted-foreground mt-1">Übersprungen</p>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
