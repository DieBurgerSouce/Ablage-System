/**
 * SampleConfigDialog
 *
 * Dialog zur Konfiguration der automatischen Stichprobenauswahl.
 * Ermoeglicht Einstellung von Prozentsatz und Stratifizierung.
 */

import { useState, useEffect } from 'react';
import { Settings2, Percent, Layers, Gauge } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Slider } from '@/components/ui/slider';
import { Skeleton } from '@/components/ui/skeleton';
import { toast } from 'sonner';
import {
  useSampleConfig,
  useUpdateSampleConfig,
} from '../hooks/use-validation-queue';
import type { ValidationSampleConfigUpdate } from '../types/validation-queue.types';

interface SampleConfigDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function SampleConfigDialog({
  open,
  onOpenChange,
}: SampleConfigDialogProps) {
  // State
  const [samplePercentage, setSamplePercentage] = useState(10);
  const [minConfidenceThreshold, setMinConfidenceThreshold] = useState(70);
  const [stratifyByDocType, setStratifyByDocType] = useState(true);
  const [isActive, setIsActive] = useState(true);

  // Queries & Mutations
  const { data: config, isLoading } = useSampleConfig();
  const updateConfig = useUpdateSampleConfig();

  // Initialize from config
  useEffect(() => {
    if (config) {
      setSamplePercentage(config.sample_percentage);
      setMinConfidenceThreshold(config.min_confidence_threshold * 100);
      setStratifyByDocType(config.stratify_by_document_type);
      setIsActive(config.is_active);
    }
  }, [config]);

  const handleSave = async () => {
    const data: ValidationSampleConfigUpdate = {
      sample_percentage: samplePercentage,
      min_confidence_threshold: minConfidenceThreshold / 100,
      stratify_by_document_type: stratifyByDocType,
      is_active: isActive,
    };

    try {
      await updateConfig.mutateAsync(data);
      toast.success('Stichproben-Konfiguration gespeichert');
      onOpenChange(false);
    } catch {
      toast.error('Fehler beim Speichern der Konfiguration');
    }
  };

  const handleClose = () => {
    if (!updateConfig.isPending) {
      onOpenChange(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Settings2 className="w-5 h-5" />
            Stichproben-Konfiguration
          </DialogTitle>
          <DialogDescription>
            Einstellungen fuer die automatische Stichprobenauswahl bei der Validierung
          </DialogDescription>
        </DialogHeader>

        {isLoading ? (
          <div className="space-y-4 py-4">
            <Skeleton className="h-20 w-full" />
            <Skeleton className="h-20 w-full" />
            <Skeleton className="h-16 w-full" />
          </div>
        ) : (
          <div className="space-y-6 py-4">
            {/* Aktiviert */}
            <div className="flex items-center justify-between p-4 bg-muted/30 rounded-lg">
              <div className="flex items-center gap-3">
                <div className={`p-2 rounded-full ${isActive ? 'bg-green-100 text-green-600' : 'bg-muted text-muted-foreground'}`}>
                  <Settings2 className="w-5 h-5" />
                </div>
                <div>
                  <Label htmlFor="config-active" className="font-medium">
                    Automatische Stichproben
                  </Label>
                  <p className="text-xs text-muted-foreground">
                    Dokumente werden automatisch zur Validierung ausgewaehlt
                  </p>
                </div>
              </div>
              <Switch
                id="config-active"
                checked={isActive}
                onCheckedChange={setIsActive}
              />
            </div>

            {/* Stichproben-Prozentsatz */}
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <Percent className="w-4 h-4 text-muted-foreground" />
                <Label>Stichproben-Rate: {samplePercentage}%</Label>
              </div>
              <Slider
                value={[samplePercentage]}
                onValueChange={([value]) => setSamplePercentage(value)}
                min={0}
                max={100}
                step={5}
                disabled={!isActive}
                className="py-2"
              />
              <p className="text-xs text-muted-foreground">
                Prozentsatz der Dokumente, die zufaellig zur Validierung ausgewaehlt werden
              </p>
            </div>

            {/* Konfidenz-Schwellenwert */}
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <Gauge className="w-4 h-4 text-muted-foreground" />
                <Label>Min. Konfidenz-Schwelle: {minConfidenceThreshold}%</Label>
              </div>
              <Slider
                value={[minConfidenceThreshold]}
                onValueChange={([value]) => setMinConfidenceThreshold(value)}
                min={0}
                max={100}
                step={5}
                disabled={!isActive}
                className="py-2"
              />
              <p className="text-xs text-muted-foreground">
                Dokumente mit niedrigerer Konfidenz werden zusaetzlich markiert
              </p>
            </div>

            {/* Stratifizierung */}
            <div className="flex items-center justify-between p-4 border rounded-lg">
              <div className="flex items-center gap-3">
                <Layers className="w-5 h-5 text-muted-foreground" />
                <div>
                  <Label htmlFor="stratify" className="font-medium">
                    Nach Dokumenttyp stratifizieren
                  </Label>
                  <p className="text-xs text-muted-foreground">
                    Gleichmaessige Verteilung ueber alle Dokumenttypen
                  </p>
                </div>
              </div>
              <Switch
                id="stratify"
                checked={stratifyByDocType}
                onCheckedChange={setStratifyByDocType}
                disabled={!isActive}
              />
            </div>

            {/* Info-Box */}
            <div className="p-4 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg">
              <h4 className="font-medium text-blue-900 dark:text-blue-100 mb-1">
                Wie funktioniert die Stichprobenauswahl?
              </h4>
              <ul className="text-xs text-blue-800 dark:text-blue-200 space-y-1 list-disc list-inside">
                <li>
                  {samplePercentage}% aller verarbeiteten Dokumente werden zufaellig ausgewaehlt
                </li>
                <li>
                  Dokumente mit Konfidenz unter {minConfidenceThreshold}% werden immer markiert
                </li>
                {stratifyByDocType && (
                  <li>Die Auswahl erfolgt proportional fuer jeden Dokumenttyp</li>
                )}
                <li>Regelbasierte Auswahl hat Vorrang vor automatischer Auswahl</li>
              </ul>
            </div>
          </div>
        )}

        <DialogFooter>
          <Button
            variant="outline"
            onClick={handleClose}
            disabled={updateConfig.isPending}
          >
            Abbrechen
          </Button>
          <Button
            onClick={handleSave}
            disabled={updateConfig.isPending || isLoading}
          >
            {updateConfig.isPending ? 'Speichern...' : 'Speichern'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default SampleConfigDialog;
