import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { TrendingUp, TrendingDown, Minus, Loader2 } from 'lucide-react';
import type { InsightsResponse, InsightTrend } from '../types/smart-inbox-types';

interface InboxInsightsPanelProps {
  insights: InsightsResponse | undefined;
  isLoading: boolean;
}

function getTrendIcon(trend: InsightTrend) {
  switch (trend) {
    case 'up':
      return <TrendingUp className="h-5 w-5 text-green-500" />;
    case 'down':
      return <TrendingDown className="h-5 w-5 text-red-500" />;
    case 'stable':
      return <Minus className="h-5 w-5 text-gray-500" />;
  }
}

function getTrendColor(trend: InsightTrend): string {
  switch (trend) {
    case 'up':
      return 'text-green-600';
    case 'down':
      return 'text-red-600';
    case 'stable':
      return 'text-gray-600';
  }
}

function formatValue(value: string | number): string {
  if (typeof value === 'number') {
    return value.toLocaleString('de-DE');
  }
  return value;
}

export function InboxInsightsPanel({ insights, isLoading }: InboxInsightsPanelProps) {
  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Erkenntnisse</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-center py-8">
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          </div>
        </CardContent>
      </Card>
    );
  }

  const items = insights?.insights ?? [];

  if (items.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Erkenntnisse</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            Keine Erkenntnisse verfügbar. Verarbeiten Sie mehr Dokumente, um KI-gestützte
            Empfehlungen zu erhalten.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Erkenntnisse</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {items.map((insight, index) => (
          <Card key={index} className="border-l-4 border-l-blue-500">
            <CardContent className="p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1 min-w-0">
                  <h4 className="font-semibold text-sm mb-1">{insight.title}</h4>
                  <p className="text-xs text-muted-foreground mb-2">
                    {insight.description}
                  </p>
                  <div className="flex items-baseline gap-2">
                    <span className={`text-2xl font-bold ${getTrendColor(insight.trend)}`}>
                      {formatValue(insight.value)}
                    </span>
                    <span className="text-sm text-muted-foreground">
                      {insight.metric}
                    </span>
                  </div>
                </div>
                <div className="flex-shrink-0">
                  {getTrendIcon(insight.trend)}
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </CardContent>
    </Card>
  );
}
