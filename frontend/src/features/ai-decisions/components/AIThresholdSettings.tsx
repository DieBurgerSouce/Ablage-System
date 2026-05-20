/**
 * AI Threshold Settings - Konfidenz-Schwellenwerte
 *
 * Ermöglicht das Anpassen der Konfidenz-Schwellenwerte
 * für verschiedene Quality Decisions.
 */

import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Settings2, Save, RotateCcw, Info } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Slider } from '@/components/ui/slider';
import { Label } from '@/components/ui/label';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';
import {
  useConfidenceThresholds,
  useUpdateConfidenceThresholds,
} from '../hooks/useAIDecisions';
import type { ConfidenceThresholds } from '../types/ai-types';

interface ThresholdConfig {
  key: keyof ConfidenceThresholds;
  label: string;
  description: string;
  color: string;
  min: number;
  max: number;
  step: number;
}

const thresholdConfigs: ThresholdConfig[] = [
  {
    key: 'excellent',
    label: 'Exzellent',
    description: 'Konfidenz für höchste Qualität',
    color: 'bg-green-500',
    min: 0.9,
    max: 1.0,
    step: 0.01,
  },
  {
    key: 'high',
    label: 'Hoch',
    description: 'Hohe Konfidenz ohne Warnung',
    color: 'bg-emerald-500',
    min: 0.75,
    max: 0.95,
    step: 0.01,
  },
  {
    key: 'medium',
    label: 'Mittel',
    description: 'Akzeptable Konfidenz',
    color: 'bg-yellow-500',
    min: 0.5,
    max: 0.85,
    step: 0.01,
  },
  {
    key: 'low',
    label: 'Niedrig',
    description: 'Niedrige Konfidenz',
    color: 'bg-orange-500',
    min: 0.3,
    max: 0.7,
    step: 0.01,
  },
  {
    key: 'fallback_trigger',
    label: 'Fallback-Trigger',
    description: 'Unter diesem Wert wird ein anderes Backend versucht',
    color: 'bg-blue-500',
    min: 0.4,
    max: 0.8,
    step: 0.01,
  },
  {
    key: 'reject_trigger',
    label: 'Ablehnung',
    description: 'Unter diesem Wert wird das Ergebnis abgelehnt',
    color: 'bg-red-500',
    min: 0.1,
    max: 0.5,
    step: 0.01,
  },
];

export function AIThresholdSettings() {
  const { data: thresholds, isLoading } = useConfidenceThresholds();
  const updateMutation = useUpdateConfidenceThresholds();

  const [localThresholds, setLocalThresholds] = useState<ConfidenceThresholds | null>(null);
  const [hasChanges, setHasChanges] = useState(false);

  useEffect(() => {
    if (thresholds && !localThresholds) {
      setLocalThresholds(thresholds);
    }
  }, [thresholds, localThresholds]);

  const handleChange = (key: keyof ConfidenceThresholds, value: number) => {
    if (!localThresholds) return;

    setLocalThresholds({
      ...localThresholds,
      [key]: value,
    });
    setHasChanges(true);
  };

  const handleSave = async () => {
    if (!localThresholds) return;

    await updateMutation.mutateAsync(localThresholds);
    setHasChanges(false);
  };

  const handleReset = () => {
    if (thresholds) {
      setLocalThresholds(thresholds);
      setHasChanges(false);
    }
  };

  if (isLoading || !localThresholds) {
    return (
      <Card>
        <CardContent className="p-6">
          <div className="h-48 bg-muted animate-pulse rounded-lg" />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Settings2 className="w-5 h-5" />
            <CardTitle className="text-lg">Konfidenz-Schwellenwerte</CardTitle>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={handleReset}
              disabled={!hasChanges}
            >
              <RotateCcw className="w-4 h-4 mr-1" />
              Zurücksetzen
            </Button>
            <Button
              size="sm"
              onClick={handleSave}
              disabled={!hasChanges || updateMutation.isPending}
            >
              <Save className="w-4 h-4 mr-1" />
              {updateMutation.isPending ? 'Speichern...' : 'Speichern'}
            </Button>
          </div>
        </div>
        <CardDescription>
          Passen Sie die Schwellenwerte für Qualitätsentscheidungen an
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        <TooltipProvider>
          {thresholdConfigs.map((config) => (
            <ThresholdSlider
              key={config.key}
              config={config}
              value={localThresholds[config.key]}
              onChange={(value) => handleChange(config.key, value)}
            />
          ))}
        </TooltipProvider>

        {/* Visual Preview */}
        <div className="pt-4 border-t">
          <Label className="text-sm text-muted-foreground mb-3 block">
            Visualisierung
          </Label>
          <div className="h-8 rounded-lg overflow-hidden flex">
            <motion.div
              className="bg-red-500 flex items-center justify-center text-xs text-white"
              style={{ width: `${localThresholds.reject_trigger * 100}%` }}
              layout
            >
              Ablehnen
            </motion.div>
            <motion.div
              className="bg-orange-500 flex items-center justify-center text-xs text-white"
              style={{
                width: `${(localThresholds.low - localThresholds.reject_trigger) * 100}%`,
              }}
              layout
            >
              Niedrig
            </motion.div>
            <motion.div
              className="bg-yellow-500 flex items-center justify-center text-xs text-white"
              style={{
                width: `${(localThresholds.medium - localThresholds.low) * 100}%`,
              }}
              layout
            >
              Mittel
            </motion.div>
            <motion.div
              className="bg-emerald-500 flex items-center justify-center text-xs text-white"
              style={{
                width: `${(localThresholds.high - localThresholds.medium) * 100}%`,
              }}
              layout
            >
              Hoch
            </motion.div>
            <motion.div
              className="bg-green-500 flex items-center justify-center text-xs text-white"
              style={{
                width: `${(localThresholds.excellent - localThresholds.high) * 100}%`,
              }}
              layout
            >
              Exzellent
            </motion.div>
            <motion.div
              className="bg-green-600 flex items-center justify-center text-xs text-white"
              style={{
                width: `${(1 - localThresholds.excellent) * 100}%`,
              }}
              layout
            />
          </div>
          <div className="flex justify-between text-xs text-muted-foreground mt-1">
            <span>0%</span>
            <span>50%</span>
            <span>100%</span>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

interface ThresholdSliderProps {
  config: ThresholdConfig;
  value: number;
  onChange: (value: number) => void;
}

function ThresholdSlider({ config, value, onChange }: ThresholdSliderProps) {
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className={cn('w-3 h-3 rounded-full', config.color)} />
          <Label>{config.label}</Label>
          <Tooltip>
            <TooltipTrigger>
              <Info className="w-3.5 h-3.5 text-muted-foreground" />
            </TooltipTrigger>
            <TooltipContent>
              <p className="max-w-xs">{config.description}</p>
            </TooltipContent>
          </Tooltip>
        </div>
        <span className="font-mono text-sm">{(value * 100).toFixed(0)}%</span>
      </div>
      <Slider
        value={[value]}
        min={config.min}
        max={config.max}
        step={config.step}
        onValueChange={([v]) => onChange(v)}
        className="py-2"
      />
    </div>
  );
}
