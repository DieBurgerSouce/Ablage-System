/**
 * ConfidenceFieldDisplay Component
 * Displays a single field with confidence indicator
 */

import { cn } from '@/lib/utils';
import { Progress } from '@/components/ui/progress';
import { Badge } from '@/components/ui/badge';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { Check, AlertTriangle, X } from 'lucide-react';
import {
  getConfidenceLevel,
  FIELD_LABELS,
  SOURCE_LABELS,
  type FieldConfidence,
} from '../types/ki-pipeline-types';

interface ConfidenceFieldDisplayProps {
  field: FieldConfidence;
  className?: string;
}

export function ConfidenceFieldDisplay({
  field,
  className,
}: ConfidenceFieldDisplayProps) {
  const level = getConfidenceLevel(field.confidence);
  const confidencePercent = Math.round(field.confidence * 100);
  const fieldLabel = FIELD_LABELS[field.field] || field.field;
  const sourceLabel = SOURCE_LABELS[field.source] || field.source;

  const getIcon = () => {
    if (level.color === 'green') return <Check className="h-4 w-4" />;
    if (level.color === 'yellow')
      return <AlertTriangle className="h-4 w-4" />;
    return <X className="h-4 w-4" />;
  };

  const getColorClass = () => {
    if (level.color === 'green') return 'text-green-600 dark:text-green-400';
    if (level.color === 'yellow')
      return 'text-yellow-600 dark:text-yellow-400';
    return 'text-red-600 dark:text-red-400';
  };

  const getProgressColor = () => {
    if (level.color === 'green') return 'bg-green-500';
    if (level.color === 'yellow') return 'bg-yellow-500';
    return 'bg-red-500';
  };

  return (
    <div className={cn('flex flex-col gap-2', className)}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Tooltip>
            <TooltipTrigger>
              <div className={cn('flex items-center gap-1', getColorClass())}>
                {getIcon()}
                <span className="text-sm font-medium">{fieldLabel}</span>
              </div>
            </TooltipTrigger>
            <TooltipContent>
              <div className="space-y-1">
                <p className="font-medium">Konfidenz: {confidencePercent}%</p>
                <p className="text-xs text-muted-foreground">
                  Quelle: {sourceLabel}
                </p>
              </div>
            </TooltipContent>
          </Tooltip>
        </div>
        <Badge
          variant={level.color === 'green' ? 'default' : 'secondary'}
          className={cn(
            level.color === 'yellow' && 'bg-yellow-500 text-white',
            level.color === 'red' && 'bg-red-500 text-white'
          )}
        >
          {confidencePercent}%
        </Badge>
      </div>

      <div className="flex items-center gap-3">
        <div className="flex-1">
          <Progress
            value={confidencePercent}
            className="h-2"
            indicatorClassName={getProgressColor()}
          />
        </div>
        <span className="text-sm text-muted-foreground min-w-[100px] text-right">
          {field.extracted_value !== null && field.extracted_value !== undefined
            ? String(field.extracted_value)
            : '-'}
        </span>
      </div>
    </div>
  );
}
