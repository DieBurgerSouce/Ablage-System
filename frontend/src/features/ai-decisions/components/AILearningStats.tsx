/**
 * AI Learning Stats - Lernfortschritt
 *
 * Zeigt den Lernfortschritt des ML-Systems,
 * angewendete Korrekturen und Modell-Verbesserungen.
 */

import { motion } from 'framer-motion';
import {
  TrendingUp,
  GraduationCap,
  Calendar,
  CheckCircle2,
  Clock,
  Sparkles,
} from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { cn } from '@/lib/utils';
import { useLearningStats } from '../hooks/useAIDecisions';

export function AILearningStats() {
  const { data: stats, isLoading } = useLearningStats();

  if (isLoading) {
    return (
      <Card>
        <CardContent className="p-6">
          <div className="h-48 bg-muted animate-pulse rounded-lg" />
        </CardContent>
      </Card>
    );
  }

  if (!stats) {
    return (
      <Card>
        <CardContent className="p-6 text-center text-muted-foreground">
          Keine Lernstatistiken verfuegbar
        </CardContent>
      </Card>
    );
  }

  const correctionsAppliedPercent =
    stats.total_corrections > 0
      ? (stats.corrections_applied / stats.total_corrections) * 100
      : 0;

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <GraduationCap className="w-5 h-5" />
          <CardTitle className="text-lg">Lernfortschritt</CardTitle>
        </div>
        <CardDescription>
          Modell-Optimierung durch User-Korrekturen
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Accuracy Improvement */}
        <div className="space-y-3">
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">Modell-Genauigkeit</span>
            <div className="flex items-center gap-2">
              <TrendingUp className="w-4 h-4 text-green-500" />
              <span className="font-medium text-green-600">
                +{stats.improvement_percent.toFixed(1)}%
              </span>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="p-3 bg-muted/50 rounded-lg">
              <p className="text-xs text-muted-foreground">Vor Training</p>
              <p className="text-xl font-bold">
                {(stats.model_accuracy_before * 100).toFixed(1)}%
              </p>
            </div>
            <div className="p-3 bg-green-500/10 rounded-lg">
              <p className="text-xs text-muted-foreground">Nach Training</p>
              <p className="text-xl font-bold text-green-600">
                {(stats.model_accuracy_after * 100).toFixed(1)}%
              </p>
            </div>
          </div>
        </div>

        {/* Corrections Applied */}
        <div className="space-y-2">
          <div className="flex justify-between text-sm">
            <span className="text-muted-foreground">Angewendete Korrekturen</span>
            <span className="font-medium">
              {stats.corrections_applied} / {stats.total_corrections}
            </span>
          </div>
          <Progress value={correctionsAppliedPercent} className="h-2" />
          <p className="text-xs text-muted-foreground">
            {correctionsAppliedPercent.toFixed(0)}% der Korrekturen wurden ins Modell integriert
          </p>
        </div>

        {/* Training Schedule */}
        <div className="space-y-3 pt-3 border-t">
          <div className="flex items-center gap-2 text-sm">
            <Calendar className="w-4 h-4 text-muted-foreground" />
            <span className="text-muted-foreground">Training-Zeitplan</span>
          </div>

          <div className="space-y-2 text-sm">
            {stats.last_training_date && (
              <div className="flex items-center justify-between">
                <span className="flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 text-green-500" />
                  Letztes Training
                </span>
                <span className="font-mono text-xs">
                  {new Date(stats.last_training_date).toLocaleDateString('de-DE')}
                </span>
              </div>
            )}

            {stats.next_training_scheduled && (
              <div className="flex items-center justify-between">
                <span className="flex items-center gap-2">
                  <Clock className="w-4 h-4 text-blue-500" />
                  Naechstes Training
                </span>
                <span className="font-mono text-xs">
                  {new Date(stats.next_training_scheduled).toLocaleDateString('de-DE')}
                </span>
              </div>
            )}
          </div>
        </div>

        {/* Improved Backends */}
        {stats.backends_improved.length > 0 && (
          <div className="space-y-2 pt-3 border-t">
            <div className="flex items-center gap-2 text-sm">
              <Sparkles className="w-4 h-4 text-yellow-500" />
              <span className="text-muted-foreground">Verbesserte Backends</span>
            </div>
            <div className="flex flex-wrap gap-2">
              {stats.backends_improved.map((backend) => (
                <Badge key={backend} variant="secondary" className="font-mono text-xs">
                  {backend}
                </Badge>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
