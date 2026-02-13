import { Card, CardContent } from '@/components/ui/card';
import { Clock, Loader2, CheckCircle, Timer } from 'lucide-react';
import type { InboxStatsResponse } from '../types/smart-inbox-types';

interface InboxStatsBarProps {
  stats: InboxStatsResponse | undefined;
  isLoading: boolean;
}

export function InboxStatsBar({ stats, isLoading }: InboxStatsBarProps) {
  if (isLoading) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
        {[...Array(4)].map((_, i) => (
          <Card key={i}>
            <CardContent className="p-6">
              <div className="flex items-center justify-center">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    );
  }

  if (!stats) {
    return null;
  }

  const avgResponseTimeSec = Math.round(stats.avgResponseTimeMs / 1000);
  const avgResponseTimeMin = Math.round(avgResponseTimeSec / 60);

  return (
    <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
      <Card>
        <CardContent className="p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-muted-foreground">Ausstehend</p>
              <p className="text-2xl font-bold">{stats.pending.toLocaleString('de-DE')}</p>
            </div>
            <Clock className="h-8 w-8 text-orange-500" />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-muted-foreground">In Bearbeitung</p>
              <p className="text-2xl font-bold">{stats.inProgress.toLocaleString('de-DE')}</p>
            </div>
            <Loader2 className="h-8 w-8 text-blue-500" />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-muted-foreground">Heute erledigt</p>
              <p className="text-2xl font-bold">{stats.completedToday.toLocaleString('de-DE')}</p>
            </div>
            <CheckCircle className="h-8 w-8 text-green-500" />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-muted-foreground">
                Durchschn. Bearbeitungszeit
              </p>
              <p className="text-2xl font-bold">
                {avgResponseTimeMin > 0
                  ? `${avgResponseTimeMin} Min`
                  : `${avgResponseTimeSec} Sek`}
              </p>
            </div>
            <Timer className="h-8 w-8 text-purple-500" />
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
