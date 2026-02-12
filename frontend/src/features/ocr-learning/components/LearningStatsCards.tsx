/**
 * Learning Stats Cards Component
 *
 * Zeigt Übersichts-Karten für das Self-Learning System.
 */

import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Brain, FileText, RefreshCw, TrendingUp, FlaskConical, Zap } from 'lucide-react';
import type { LearningStats } from '../api/ocr-learning-api';

interface LearningStatsCardsProps {
  stats: LearningStats;
}

export function LearningStatsCards({ stats }: LearningStatsCardsProps) {
  const getModeIcon = () => {
    switch (stats.learning_mode) {
      case 'aggressive':
        return <Zap className="w-5 h-5 text-yellow-500" />;
      case 'cautious':
        return <Brain className="w-5 h-5 text-blue-500" />;
      case 'batch':
        return <RefreshCw className="w-5 h-5 text-purple-500" />;
      default:
        return <Brain className="w-5 h-5" />;
    }
  };

  const getModeBadge = () => {
    const variants: Record<string, { variant: 'default' | 'secondary' | 'outline'; label: string }> = {
      aggressive: { variant: 'default', label: 'Aggressiv' },
      cautious: { variant: 'secondary', label: 'Vorsichtig' },
      batch: { variant: 'outline', label: 'Batch' },
    };
    const { variant, label } = variants[stats.learning_mode] || variants.batch;
    return <Badge variant={variant}>{label}</Badge>;
  };

  // Calculate quality score from model metrics
  const baselineMetrics = stats.model_metrics?.baseline;
  const qualityScore = baselineMetrics?.quality_score || 0;

  // Count active adjustments
  const activeAdjustments = Object.keys(stats.backend_adjustments || {}).length;

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
      {/* Learning Mode */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              {getModeIcon()}
              <div>
                <p className="text-sm text-muted-foreground">Lernmodus</p>
                {getModeBadge()}
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Training Samples */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex items-center gap-2">
            <FileText className="w-5 h-5 text-green-500" />
            <div>
              <p className="text-sm text-muted-foreground">Training Samples</p>
              <p className="text-2xl font-bold">{stats.training_samples}</p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Quality Score */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex items-center gap-2">
            <TrendingUp className="w-5 h-5 text-blue-500" />
            <div>
              <p className="text-sm text-muted-foreground">Qualitäts-Score</p>
              <p className="text-2xl font-bold">{qualityScore.toFixed(1)}</p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Active Tests */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex items-center gap-2">
            <FlaskConical className="w-5 h-5 text-purple-500" />
            <div>
              <p className="text-sm text-muted-foreground">A/B Tests</p>
              <p className="text-2xl font-bold">{stats.active_ab_tests?.length || 0}</p>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
