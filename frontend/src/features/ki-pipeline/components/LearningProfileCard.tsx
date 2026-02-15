/**
 * LearningProfileCard Component
 * Card showing per-supplier/type learning stats
 */

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { Separator } from '@/components/ui/separator';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { TrendingUp, FileText, Calendar } from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  ENTITY_TYPE_LABELS,
  FIELD_LABELS,
  type LearningProfile,
} from '../types/ki-pipeline-types';

interface LearningProfileCardProps {
  profile: LearningProfile;
  className?: string;
}

export function LearningProfileCard({
  profile,
  className,
}: LearningProfileCardProps) {
  const overallPercent = Math.round(profile.accuracy_overall * 100);
  const entityTypeLabel =
    ENTITY_TYPE_LABELS[profile.entity_type] || profile.entity_type;

  // Sort fields by accuracy (lowest first to highlight areas for improvement)
  const sortedFields = Object.entries(profile.accuracy_per_field)
    .map(([field, accuracy]) => ({
      field,
      accuracy,
      label: FIELD_LABELS[field] || field,
    }))
    .sort((a, b) => a.accuracy - b.accuracy);

  const getAccuracyColor = (accuracy: number) => {
    if (accuracy >= 0.9) return 'text-green-600 dark:text-green-400';
    if (accuracy >= 0.6) return 'text-yellow-600 dark:text-yellow-400';
    return 'text-red-600 dark:text-red-400';
  };

  const getProgressColor = (accuracy: number) => {
    if (accuracy >= 0.9) return 'bg-green-500';
    if (accuracy >= 0.6) return 'bg-yellow-500';
    return 'bg-red-500';
  };

  const formatDate = (dateString: string | null) => {
    if (!dateString) return 'Nie';
    const date = new Date(dateString);
    return new Intl.DateTimeFormat('de-DE', {
      dateStyle: 'short',
      timeStyle: 'short',
    }).format(date);
  };

  return (
    <Card className={cn('w-full hover:shadow-md transition-shadow', className)}>
      <CardHeader>
        <div className="flex items-start justify-between">
          <div className="space-y-1">
            <CardTitle className="text-lg">{profile.entity_name}</CardTitle>
            <Badge variant="secondary" className="text-xs">
              {entityTypeLabel}
            </Badge>
          </div>
          <Tooltip>
            <TooltipTrigger>
              <Badge
                variant={overallPercent >= 90 ? 'default' : 'secondary'}
                className={cn(
                  'text-lg px-3 py-1',
                  overallPercent >= 90 && 'bg-green-500',
                  overallPercent >= 60 &&
                    overallPercent < 90 &&
                    'bg-yellow-500 text-white',
                  overallPercent < 60 && 'bg-red-500 text-white'
                )}
              >
                <TrendingUp className="h-4 w-4 mr-1" />
                {overallPercent}%
              </Badge>
            </TooltipTrigger>
            <TooltipContent>Durchschnittliche Genauigkeit</TooltipContent>
          </Tooltip>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-2 gap-4 text-sm">
          <div className="flex items-center gap-2 text-muted-foreground">
            <FileText className="h-4 w-4" />
            <span>{profile.samples_count} Dokumente</span>
          </div>
          <div className="flex items-center gap-2 text-muted-foreground">
            <Calendar className="h-4 w-4" />
            <span>{formatDate(profile.last_trained)}</span>
          </div>
        </div>

        <Separator />

        <div className="space-y-3">
          <h4 className="text-sm font-semibold text-muted-foreground">
            Feldgenauigkeit
          </h4>
          {sortedFields.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              Keine Felddaten verfügbar
            </p>
          ) : (
            <div className="space-y-3">
              {sortedFields.map(({ field, accuracy, label }) => {
                const percent = Math.round(accuracy * 100);
                return (
                  <div key={field} className="space-y-1">
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-muted-foreground">{label}</span>
                      <span className={cn('font-medium', getAccuracyColor(accuracy))}>
                        {percent}%
                      </span>
                    </div>
                    <Progress
                      value={percent}
                      className="h-1.5"
                      indicatorClassName={getProgressColor(accuracy)}
                    />
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
