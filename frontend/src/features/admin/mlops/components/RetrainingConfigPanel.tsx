/**
 * Retraining Configuration Panel
 *
 * Konfiguration für automatisches Retraining.
 */

import { useState, useEffect } from 'react';
import { Settings, Save, RotateCcw, Loader2, Info } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { toast } from 'sonner';
import {
  useRetrainingConfig,
  useUpdateRetrainingConfig,
  type RetrainingConfig,
} from '../hooks/useMLOps';

const WEEKDAYS = [
  { value: '0', label: 'Montag' },
  { value: '1', label: 'Dienstag' },
  { value: '2', label: 'Mittwoch' },
  { value: '3', label: 'Donnerstag' },
  { value: '4', label: 'Freitag' },
  { value: '5', label: 'Samstag' },
  { value: '6', label: 'Sonntag' },
];

function InfoTooltip({ text }: { text: string }) {
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <Info className="h-4 w-4 text-muted-foreground cursor-help" />
        </TooltipTrigger>
        <TooltipContent>
          <p className="max-w-xs">{text}</p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

export function RetrainingConfigPanel() {
  const { data: config, isLoading } = useRetrainingConfig();
  const updateConfig = useUpdateRetrainingConfig();

  const [localConfig, setLocalConfig] = useState<RetrainingConfig | null>(null);
  const [hasChanges, setHasChanges] = useState(false);

  useEffect(() => {
    if (config && !localConfig) {
      setLocalConfig(config);
    }
  }, [config, localConfig]);

  useEffect(() => {
    if (config && localConfig) {
      setHasChanges(JSON.stringify(config) !== JSON.stringify(localConfig));
    }
  }, [config, localConfig]);

  const handleSave = async () => {
    if (!localConfig) return;

    try {
      await updateConfig.mutateAsync(localConfig);
      toast.success('Konfiguration gespeichert');
      setHasChanges(false);
    } catch {
      toast.error('Fehler beim Speichern');
    }
  };

  const handleReset = () => {
    if (config) {
      setLocalConfig(config);
      setHasChanges(false);
    }
  };

  const updateField = <K extends keyof RetrainingConfig>(
    field: K,
    value: RetrainingConfig[K]
  ) => {
    if (localConfig) {
      setLocalConfig({ ...localConfig, [field]: value });
    }
  };

  if (isLoading || !localConfig) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Settings className="h-5 w-5" />
            Retraining-Konfiguration
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-10 w-full" />
            ))}
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <div>
          <CardTitle className="flex items-center gap-2">
            <Settings className="h-5 w-5" />
            Retraining-Konfiguration
          </CardTitle>
          <CardDescription>
            Einstellungen für automatisches Modell-Retraining
          </CardDescription>
        </div>
        <div className="flex items-center gap-2">
          {hasChanges && (
            <>
              <Button variant="outline" size="sm" onClick={handleReset}>
                <RotateCcw className="h-4 w-4 mr-2" />
                Zurücksetzen
              </Button>
              <Button size="sm" onClick={handleSave} disabled={updateConfig.isPending}>
                {updateConfig.isPending ? (
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                ) : (
                  <Save className="h-4 w-4 mr-2" />
                )}
                Speichern
              </Button>
            </>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Feedback Threshold */}
        <div className="grid gap-4 md:grid-cols-2">
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <Label htmlFor="feedbackThreshold">Feedback-Schwellenwert</Label>
              <InfoTooltip text="Anzahl der Korrekturen, ab der ein automatisches Retraining gestartet wird" />
            </div>
            <Input
              id="feedbackThreshold"
              type="number"
              min={10}
              max={1000}
              value={localConfig.feedback_threshold}
              onChange={(e) =>
                updateField('feedback_threshold', parseInt(e.target.value) || 100)
              }
            />
          </div>

          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <Label htmlFor="feedbackWindow">Feedback-Zeitfenster (Stunden)</Label>
              <InfoTooltip text="Zeitraum, in dem Feedbacks für das Schwellenwert-Triggern gezaehlt werden" />
            </div>
            <Input
              id="feedbackWindow"
              type="number"
              min={24}
              max={720}
              value={localConfig.feedback_window_hours}
              onChange={(e) =>
                updateField('feedback_window_hours', parseInt(e.target.value) || 168)
              }
            />
          </div>
        </div>

        {/* Scheduled Retraining */}
        <div className="space-y-4 p-4 border rounded-lg">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Label>Wöchentliches Retraining</Label>
              <InfoTooltip text="Automatisches Retraining zu einem festen Zeitpunkt" />
            </div>
            <Switch
              checked={localConfig.weekly_enabled}
              onCheckedChange={(checked) => updateField('weekly_enabled', checked)}
            />
          </div>

          {localConfig.weekly_enabled && (
            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <Label>Wochentag</Label>
                <Select
                  value={String(localConfig.weekly_day)}
                  onValueChange={(v) => updateField('weekly_day', parseInt(v))}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {WEEKDAYS.map((day) => (
                      <SelectItem key={day.value} value={day.value}>
                        {day.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label htmlFor="weeklyHour">Uhrzeit (UTC)</Label>
                <Input
                  id="weeklyHour"
                  type="number"
                  min={0}
                  max={23}
                  value={localConfig.weekly_hour}
                  onChange={(e) =>
                    updateField('weekly_hour', parseInt(e.target.value) || 3)
                  }
                />
              </div>
            </div>
          )}
        </div>

        {/* Drift Detection */}
        <div className="grid gap-4 md:grid-cols-2">
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <Label htmlFor="driftThreshold">Drift-Schwellenwert (%)</Label>
              <InfoTooltip text="Prozentuale Accuracy-Verschlechterung, die ein Retraining auslöst" />
            </div>
            <Input
              id="driftThreshold"
              type="number"
              min={0.01}
              max={0.5}
              step={0.01}
              value={localConfig.drift_threshold}
              onChange={(e) =>
                updateField('drift_threshold', parseFloat(e.target.value) || 0.1)
              }
            />
          </div>

          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <Label htmlFor="driftInterval">Drift-Prüfintervall (Stunden)</Label>
              <InfoTooltip text="Wie oft die Modell-Performance auf Drift geprüft wird" />
            </div>
            <Input
              id="driftInterval"
              type="number"
              min={1}
              max={168}
              value={localConfig.drift_check_interval_hours}
              onChange={(e) =>
                updateField('drift_check_interval_hours', parseInt(e.target.value) || 24)
              }
            />
          </div>
        </div>

        {/* Quality Thresholds */}
        <div className="grid gap-4 md:grid-cols-2">
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <Label htmlFor="minSamples">Min. Trainingssamples</Label>
              <InfoTooltip text="Mindestanzahl Samples für ein Training" />
            </div>
            <Input
              id="minSamples"
              type="number"
              min={10}
              max={1000}
              value={localConfig.min_training_samples}
              onChange={(e) =>
                updateField('min_training_samples', parseInt(e.target.value) || 50)
              }
            />
          </div>

          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <Label htmlFor="minImprovement">Min. Accuracy-Verbesserung</Label>
              <InfoTooltip text="Mindestverbesserung, damit ein neues Modell aktiviert wird" />
            </div>
            <Input
              id="minImprovement"
              type="number"
              min={0.001}
              max={0.1}
              step={0.001}
              value={localConfig.min_accuracy_improvement}
              onChange={(e) =>
                updateField('min_accuracy_improvement', parseFloat(e.target.value) || 0.01)
              }
            />
          </div>
        </div>

        {/* Rate Limiting */}
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <Label htmlFor="minHours">Min. Stunden zwischen Retrainings</Label>
            <InfoTooltip text="Mindestabstand zwischen automatischen Retrainings zur Ressourcenschonung" />
          </div>
          <Input
            id="minHours"
            type="number"
            min={1}
            max={168}
            value={localConfig.min_hours_between_retrains}
            onChange={(e) =>
              updateField('min_hours_between_retrains', parseInt(e.target.value) || 24)
            }
            className="max-w-xs"
          />
        </div>
      </CardContent>
    </Card>
  );
}
