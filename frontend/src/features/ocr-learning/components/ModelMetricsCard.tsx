/**
 * Model Metrics Card Component
 *
 * Zeigt Metriken für verschiedene Modell-Versionen.
 */

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { Badge } from '@/components/ui/badge';
import { BarChart3, FileCheck, AlertCircle, TrendingUp } from 'lucide-react';
import type { LearningStats } from '../api/ocr-learning-api';

interface ModelMetricsCardProps {
  stats: LearningStats;
}

export function ModelMetricsCard({ stats }: ModelMetricsCardProps) {
  const metrics = stats.model_metrics || {};

  // Sort models by quality score (highest first)
  const sortedModels = Object.entries(metrics).sort(
    ([, a], [, b]) => b.quality_score - a.quality_score
  );

  const getQualityColor = (score: number) => {
    if (score >= 0.9) return 'bg-green-500';
    if (score >= 0.7) return 'bg-yellow-500';
    return 'bg-red-500';
  };

  const getQualityLabel = (score: number) => {
    if (score >= 0.9) return 'Exzellent';
    if (score >= 0.8) return 'Gut';
    if (score >= 0.7) return 'Befriedigend';
    if (score >= 0.6) return 'Ausreichend';
    return 'Verbesserungsbedarf';
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg flex items-center gap-2">
          <BarChart3 className="w-5 h-5" />
          Modell-Metriken
        </CardTitle>
      </CardHeader>
      <CardContent>
        {sortedModels.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            Noch keine Modell-Metriken verfügbar.
          </div>
        ) : (
          <div className="space-y-6">
            {sortedModels.map(([model, data]) => (
              <div key={model} className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="font-medium capitalize">
                    {model === 'baseline' ? 'Baseline' : model}
                  </span>
                  <Badge className={getQualityColor(data.quality_score)}>
                    {getQualityLabel(data.quality_score)}
                  </Badge>
                </div>

                <div className="space-y-2">
                  <div className="flex justify-between text-sm">
                    <span className="flex items-center gap-1">
                      <TrendingUp className="w-3 h-3" />
                      Quality Score
                    </span>
                    <span>{(data.quality_score * 100).toFixed(1)}%</span>
                  </div>
                  <Progress
                    value={data.quality_score * 100}
                    className="h-2"
                  />
                </div>

                <div className="grid grid-cols-3 gap-2 text-sm">
                  <div className="flex items-center gap-1 text-muted-foreground">
                    <FileCheck className="w-3 h-3" />
                    <span>{data.total_documents} Docs</span>
                  </div>
                  <div className="flex items-center gap-1 text-muted-foreground">
                    <AlertCircle className="w-3 h-3" />
                    <span>{data.corrections_count} Korrekturen</span>
                  </div>
                  <div className="text-right">
                    <span className="text-muted-foreground">Genauigkeit:</span>
                    <span className="ml-1 font-medium">
                      {(data.accuracy_rate * 100).toFixed(1)}%
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
