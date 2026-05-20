/**
 * Experiments Panel - A/B Testing Übersicht
 *
 * Zeigt alle A/B Experimente mit Status,
 * Varianten und Ergebnissen.
 */

import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  FlaskConical,
  Play,
  Square,
  Trophy,
  Users,
  Clock,
  ChevronDown,
  Plus,
} from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import { cn } from '@/lib/utils';
import {
  useExperiments,
  useStartExperiment,
  useConcludeExperiment,
} from '../hooks/useAIDecisions';
import type { Experiment, ExperimentStatus } from '../types/ai-types';

const listVariants = {
  visible: {
    transition: { staggerChildren: 0.05 },
  },
};

const itemVariants = {
  hidden: { opacity: 0, y: 10 },
  visible: { opacity: 1, y: 0 },
};

export function ExperimentsPanel() {
  const { data: experiments, isLoading } = useExperiments();
  const startMutation = useStartExperiment();
  const concludeMutation = useConcludeExperiment();

  const runningExperiments = experiments?.filter((e) => e.status === 'running') ?? [];
  const otherExperiments = experiments?.filter((e) => e.status !== 'running') ?? [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">A/B Experimente</h2>
          <p className="text-sm text-muted-foreground">
            Vergleiche OCR-Backends und Konfigurationen
          </p>
        </div>
        <Button>
          <Plus className="w-4 h-4 mr-2" />
          Neues Experiment
        </Button>
      </div>

      {/* Running Experiments */}
      {runningExperiments.length > 0 && (
        <div className="space-y-4">
          <h3 className="text-sm font-medium text-muted-foreground flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
            Laufende Experimente
          </h3>
          <motion.div
            variants={listVariants}
            initial="hidden"
            animate="visible"
            className="space-y-4"
          >
            {runningExperiments.map((experiment) => (
              <ExperimentCard
                key={experiment.experiment_id}
                experiment={experiment}
                onStart={() => {}}
                onConclude={() => concludeMutation.mutate(experiment.experiment_id)}
                isStarting={false}
                isConcluding={concludeMutation.isPending}
              />
            ))}
          </motion.div>
        </div>
      )}

      {/* Other Experiments */}
      {otherExperiments.length > 0 && (
        <div className="space-y-4">
          <h3 className="text-sm font-medium text-muted-foreground">
            Andere Experimente
          </h3>
          <motion.div
            variants={listVariants}
            initial="hidden"
            animate="visible"
            className="space-y-4"
          >
            {otherExperiments.map((experiment) => (
              <ExperimentCard
                key={experiment.experiment_id}
                experiment={experiment}
                onStart={() => startMutation.mutate(experiment.experiment_id)}
                onConclude={() => concludeMutation.mutate(experiment.experiment_id)}
                isStarting={startMutation.isPending}
                isConcluding={concludeMutation.isPending}
              />
            ))}
          </motion.div>
        </div>
      )}

      {/* Empty State */}
      {isLoading ? (
        <div className="space-y-4">
          {[1, 2].map((i) => (
            <div key={i} className="h-32 bg-muted animate-pulse rounded-lg" />
          ))}
        </div>
      ) : experiments?.length === 0 ? (
        <Card>
          <CardContent className="p-12 text-center">
            <FlaskConical className="w-12 h-12 mx-auto text-muted-foreground mb-4" />
            <h3 className="font-medium mb-2">Keine Experimente</h3>
            <p className="text-sm text-muted-foreground mb-4">
              Erstellen Sie ein neues A/B Experiment um OCR-Backends zu vergleichen
            </p>
            <Button>
              <Plus className="w-4 h-4 mr-2" />
              Erstes Experiment erstellen
            </Button>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}

interface ExperimentCardProps {
  experiment: Experiment;
  onStart: () => void;
  onConclude: () => void;
  isStarting: boolean;
  isConcluding: boolean;
}

function ExperimentCard({
  experiment,
  onStart,
  onConclude,
  isStarting,
  isConcluding,
}: ExperimentCardProps) {
  const [expanded, setExpanded] = useState(experiment.status === 'running');

  const statusConfig: Record<
    ExperimentStatus,
    { color: string; label: string; icon: React.ElementType }
  > = {
    draft: { color: 'text-slate-500', label: 'Entwurf', icon: Clock },
    running: { color: 'text-green-500', label: 'Laufend', icon: Play },
    completed: { color: 'text-blue-500', label: 'Abgeschlossen', icon: Trophy },
    stopped: { color: 'text-orange-500', label: 'Gestoppt', icon: Square },
  };

  const config = statusConfig[experiment.status];
  const StatusIcon = config.icon;

  return (
    <motion.div variants={itemVariants}>
      <Collapsible open={expanded} onOpenChange={setExpanded}>
        <Card
          className={cn(
            experiment.status === 'running' && 'border-green-500/50 bg-green-500/5'
          )}
        >
          <CardHeader className="p-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div
                  className={cn(
                    'p-2 rounded-lg',
                    experiment.status === 'running'
                      ? 'bg-green-500/10'
                      : 'bg-muted'
                  )}
                >
                  <FlaskConical className="w-4 h-4" />
                </div>
                <div>
                  <CardTitle className="text-base">{experiment.name}</CardTitle>
                  <div className="flex items-center gap-2 mt-1">
                    <Badge variant="outline" className="gap-1">
                      <StatusIcon className={cn('w-3 h-3', config.color)} />
                      {config.label}
                    </Badge>
                    <span className="text-xs text-muted-foreground">
                      {experiment.total_samples} Samples
                    </span>
                    {experiment.significance_reached && (
                      <Badge variant="secondary" className="gap-1">
                        <Trophy className="w-3 h-3" />
                        Signifikant
                      </Badge>
                    )}
                  </div>
                </div>
              </div>

              <div className="flex items-center gap-2">
                {experiment.status === 'draft' && (
                  <Button
                    size="sm"
                    onClick={onStart}
                    disabled={isStarting}
                  >
                    <Play className="w-4 h-4 mr-1" />
                    Starten
                  </Button>
                )}
                {experiment.status === 'running' && (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={onConclude}
                    disabled={isConcluding}
                  >
                    <Square className="w-4 h-4 mr-1" />
                    Abschließen
                  </Button>
                )}
                <CollapsibleTrigger asChild>
                  <Button variant="ghost" size="icon">
                    <ChevronDown
                      className={cn(
                        'w-4 h-4 transition-transform',
                        expanded && 'rotate-180'
                      )}
                    />
                  </Button>
                </CollapsibleTrigger>
              </div>
            </div>
          </CardHeader>

          <CollapsibleContent>
            <CardContent className="pt-0 pb-4 px-4">
              <div className="border-t pt-4 space-y-4">
                {/* Variants */}
                <div className="space-y-3">
                  {experiment.variants.map((variant, index) => {
                    const isWinner = experiment.winner === variant.name;
                    const maxSamples = Math.max(
                      ...experiment.variants.map((v) => v.samples)
                    );

                    return (
                      <div
                        key={variant.name}
                        className={cn(
                          'p-3 rounded-lg border',
                          isWinner && 'border-yellow-500/50 bg-yellow-500/5'
                        )}
                      >
                        <div className="flex items-center justify-between mb-2">
                          <div className="flex items-center gap-2">
                            {isWinner && (
                              <Trophy className="w-4 h-4 text-yellow-500" />
                            )}
                            <span className="font-medium">{variant.name}</span>
                            <Badge variant="outline" className="font-mono text-xs">
                              {experiment.variants[index] &&
                                `Backend: ${variant.name}`}
                            </Badge>
                          </div>
                          <div className="flex items-center gap-4 text-sm">
                            <span>
                              <Users className="w-3 h-3 inline mr-1" />
                              {variant.samples}
                            </span>
                            <span
                              className={cn(
                                'font-medium',
                                variant.success_rate >= 0.8
                                  ? 'text-green-600'
                                  : variant.success_rate >= 0.6
                                  ? 'text-yellow-600'
                                  : 'text-red-600'
                              )}
                            >
                              {(variant.success_rate * 100).toFixed(1)}% Erfolg
                            </span>
                          </div>
                        </div>

                        <Progress
                          value={(variant.samples / maxSamples) * 100}
                          className="h-1.5"
                        />

                        <div className="flex justify-between text-xs text-muted-foreground mt-2">
                          <span>Latenz: {variant.avg_latency_ms.toFixed(0)}ms</span>
                          {variant.avg_accuracy !== null && (
                            <span>
                              Genauigkeit: {(variant.avg_accuracy * 100).toFixed(1)}%
                            </span>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </CardContent>
          </CollapsibleContent>
        </Card>
      </Collapsible>
    </motion.div>
  );
}
