/**
 * ABTestCard Component
 *
 * Zeigt A/B Test Status und Ergebnisse an.
 */

import { format } from 'date-fns';
import { de } from 'date-fns/locale';
import { Play, Pause, Trophy, Clock, CheckCircle2, XCircle, FlaskConical } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { Separator } from '@/components/ui/separator';
import type { WorkflowABTest } from '../types/version-types';
import { useStartABTest, useStopABTest } from '../hooks/useWorkflowVersions';
import { formatABTestStatus } from '@/lib/api/services/workflow-versions';
import { cn } from '@/lib/utils';

interface ABTestCardProps {
  test: WorkflowABTest;
  workflowId: string;
  controlVersion?: string;
  treatmentVersion?: string;
}

export function ABTestCard({
  test,
  workflowId,
  controlVersion,
  treatmentVersion,
}: ABTestCardProps) {
  const startMutation = useStartABTest();
  const stopMutation = useStopABTest();

  const handleStart = () => {
    startMutation.mutate({ workflowId, testId: test.id });
  };

  const handleStop = (winner?: 'control' | 'treatment' | 'inconclusive') => {
    stopMutation.mutate({ workflowId, testId: test.id, winner });
  };

  const getStatusBadgeVariant = () => {
    switch (test.status) {
      case 'running':
        return 'default';
      case 'completed':
        return 'secondary';
      case 'draft':
        return 'outline';
      case 'cancelled':
        return 'destructive';
      default:
        return 'outline';
    }
  };

  const getWinnerLabel = () => {
    switch (test.winner) {
      case 'control':
        return 'Control gewinnt';
      case 'treatment':
        return 'Treatment gewinnt';
      case 'inconclusive':
        return 'Unentschieden';
      default:
        return null;
    }
  };

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <FlaskConical className="h-5 w-5 text-primary" />
            <CardTitle className="text-lg">{test.name}</CardTitle>
          </div>
          <Badge variant={getStatusBadgeVariant()}>
            {formatABTestStatus(test.status)}
          </Badge>
        </div>
        {test.description && (
          <p className="text-sm text-muted-foreground mt-1">{test.description}</p>
        )}
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Traffic Split */}
        <div>
          <div className="flex justify-between text-sm mb-1">
            <span>Traffic-Aufteilung</span>
            <span className="text-muted-foreground">
              {100 - test.treatment_percentage}% / {test.treatment_percentage}%
            </span>
          </div>
          <div className="h-3 rounded-full overflow-hidden bg-muted flex">
            <div
              className="bg-blue-500 h-full"
              style={{ width: `${100 - test.treatment_percentage}%` }}
            />
            <div
              className="bg-purple-500 h-full"
              style={{ width: `${test.treatment_percentage}%` }}
            />
          </div>
          <div className="flex justify-between text-xs text-muted-foreground mt-1">
            <span>Control {controlVersion && `(v${controlVersion})`}</span>
            <span>Treatment {treatmentVersion && `(v${treatmentVersion})`}</span>
          </div>
        </div>

        <Separator />

        {/* Results Grid */}
        <div className="grid grid-cols-2 gap-4">
          {/* Control Results */}
          <div className="space-y-2">
            <h4 className="text-sm font-medium flex items-center gap-1">
              <div className="h-2 w-2 rounded-full bg-blue-500" />
              Control
            </h4>
            <div className="space-y-1 text-sm">
              <div className="flex justify-between">
                <span className="text-muted-foreground">Ausführungen</span>
                <span className="font-medium">{test.control_executions}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Erfolgsrate</span>
                <span
                  className={cn(
                    'font-medium',
                    test.control_success_rate >= 90 && 'text-green-600',
                    test.control_success_rate < 70 && 'text-red-600'
                  )}
                >
                  {test.control_success_rate.toFixed(1)}%
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Avg. Zeit</span>
                <span className="font-medium">
                  {test.control_avg_time_ms
                    ? `${test.control_avg_time_ms.toLocaleString('de-DE')}ms`
                    : '-'}
                </span>
              </div>
            </div>
          </div>

          {/* Treatment Results */}
          <div className="space-y-2">
            <h4 className="text-sm font-medium flex items-center gap-1">
              <div className="h-2 w-2 rounded-full bg-purple-500" />
              Treatment
            </h4>
            <div className="space-y-1 text-sm">
              <div className="flex justify-between">
                <span className="text-muted-foreground">Ausführungen</span>
                <span className="font-medium">{test.treatment_executions}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Erfolgsrate</span>
                <span
                  className={cn(
                    'font-medium',
                    test.treatment_success_rate >= 90 && 'text-green-600',
                    test.treatment_success_rate < 70 && 'text-red-600'
                  )}
                >
                  {test.treatment_success_rate.toFixed(1)}%
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Avg. Zeit</span>
                <span className="font-medium">
                  {test.treatment_avg_time_ms
                    ? `${test.treatment_avg_time_ms.toLocaleString('de-DE')}ms`
                    : '-'}
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Winner Badge */}
        {test.winner && (
          <div className="flex items-center justify-center gap-2 p-3 bg-muted rounded-lg">
            <Trophy className="h-5 w-5 text-yellow-500" />
            <span className="font-medium">{getWinnerLabel()}</span>
          </div>
        )}

        {/* Time Info */}
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <div className="flex items-center gap-1">
            <Clock className="h-3 w-3" />
            {test.start_at ? (
              <span>
                Gestartet:{' '}
                {format(new Date(test.start_at), 'dd.MM.yyyy HH:mm', { locale: de })}
              </span>
            ) : (
              <span>Noch nicht gestartet</span>
            )}
          </div>
          {test.end_at && (
            <span>
              Endet: {format(new Date(test.end_at), 'dd.MM.yyyy', { locale: de })}
            </span>
          )}
        </div>

        {/* Actions */}
        <div className="flex gap-2">
          {test.status === 'draft' && (
            <Button
              className="flex-1"
              onClick={handleStart}
              disabled={startMutation.isPending}
            >
              <Play className="h-4 w-4 mr-2" />
              Test starten
            </Button>
          )}
          {test.status === 'running' && (
            <>
              <Button
                variant="outline"
                className="flex-1"
                onClick={() => handleStop()}
                disabled={stopMutation.isPending}
              >
                <Pause className="h-4 w-4 mr-2" />
                Beenden
              </Button>
              <Button
                variant="secondary"
                onClick={() => handleStop('control')}
                disabled={stopMutation.isPending}
              >
                <CheckCircle2 className="h-4 w-4" />
              </Button>
              <Button
                variant="secondary"
                onClick={() => handleStop('treatment')}
                disabled={stopMutation.isPending}
              >
                <XCircle className="h-4 w-4" />
              </Button>
            </>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

export function ABTestCardSkeleton() {
  return (
    <Card>
      <CardHeader className="pb-2">
        <Skeleton className="h-6 w-48" />
        <Skeleton className="h-4 w-full mt-2" />
      </CardHeader>
      <CardContent className="space-y-4">
        <Skeleton className="h-3 w-full" />
        <div className="grid grid-cols-2 gap-4">
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-24 w-full" />
        </div>
        <Skeleton className="h-10 w-full" />
      </CardContent>
    </Card>
  );
}
