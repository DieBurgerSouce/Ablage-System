/**
 * Learning Mode Selector Component
 *
 * Erlaubt Admins den Learning-Modus zu aendern.
 * Enterprise-Grade mit Error Handling und Feedback.
 */

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Zap, Shield, RefreshCw, CheckCircle, Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { useSetLearningMode } from '../hooks/use-ocr-learning';
import type { LearningStats } from '../api/ocr-learning-api';

interface LearningModeSelectorProps {
  stats: LearningStats;
}

const modes = [
  {
    id: 'aggressive',
    name: 'Aggressiv',
    icon: Zap,
    description: 'Jede User-Korrektur fliesst sofort ins System ein.',
    color: 'text-yellow-500',
    bgColor: 'bg-yellow-500/10',
  },
  {
    id: 'cautious',
    name: 'Vorsichtig',
    icon: Shield,
    description: 'Nur verifizierte Korrekturen werden uebernommen.',
    color: 'text-blue-500',
    bgColor: 'bg-blue-500/10',
  },
  {
    id: 'batch',
    name: 'Batch',
    icon: RefreshCw,
    description: 'Korrekturen werden taeglich im Batch verarbeitet.',
    color: 'text-purple-500',
    bgColor: 'bg-purple-500/10',
  },
] as const;

export function LearningModeSelector({ stats }: LearningModeSelectorProps) {
  const setLearningMode = useSetLearningMode();
  const currentMode = stats.learning_mode;

  const handleModeChange = async (mode: 'aggressive' | 'cautious' | 'batch') => {
    if (mode !== currentMode) {
      try {
        await setLearningMode.mutateAsync(mode);
        const modeName = modes.find(m => m.id === mode)?.name || mode;
        toast.success('Lernmodus geaendert', {
          description: `Der Modus "${modeName}" ist jetzt aktiv.`,
        });
      } catch (error) {
        const message = error instanceof Error ? error.message : 'Unbekannter Fehler';
        toast.error('Fehler beim Aendern des Modus', {
          description: message,
        });
      }
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Lernmodus</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          {modes.map((mode) => {
            const Icon = mode.icon;
            const isActive = currentMode === mode.id;

            return (
              <Button
                key={mode.id}
                variant="outline"
                className={`w-full justify-start h-auto p-4 ${
                  isActive ? mode.bgColor + ' border-2' : ''
                }`}
                onClick={() =>
                  handleModeChange(mode.id as 'aggressive' | 'cautious' | 'batch')
                }
                disabled={setLearningMode.isPending}
              >
                <div className="flex items-start gap-3 w-full">
                  {setLearningMode.isPending && !isActive ? (
                    <Loader2 className={`w-5 h-5 mt-0.5 animate-spin ${mode.color}`} />
                  ) : (
                    <Icon className={`w-5 h-5 mt-0.5 ${mode.color}`} />
                  )}
                  <div className="flex-1 text-left">
                    <div className="flex items-center gap-2">
                      <span className="font-medium">{mode.name}</span>
                      {isActive && (
                        <Badge variant="outline" className="text-xs">
                          <CheckCircle className="w-3 h-3 mr-1" />
                          Aktiv
                        </Badge>
                      )}
                    </div>
                    <p className="text-sm text-muted-foreground mt-1">
                      {mode.description}
                    </p>
                  </div>
                </div>
              </Button>
            );
          })}
        </div>
        <p className="text-xs text-muted-foreground mt-4">
          Hinweis: Der Modus beeinflusst wie schnell das System aus Korrekturen lernt.
          Im aggressiven Modus koennen einzelne Fehlkorrekturen das System negativ
          beeinflussen.
        </p>
      </CardContent>
    </Card>
  );
}
