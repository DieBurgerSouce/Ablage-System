/**
 * Automation Config Panel
 *
 * Konfigurationsformular fuer Zahlungsautomatisierung.
 */

import { useState } from 'react';
import {
  Settings,
  Save,
  Loader2,
  Info,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { toast } from 'sonner';
import {
  useAutomationConfig,
  useUpdateAutomationConfig,
  type AutomationConfig,
} from '../hooks/usePaymentAutomation';

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

export function AutomationConfigPanel() {
  const { data: config, isLoading } = useAutomationConfig();
  const updateMutation = useUpdateAutomationConfig();

  const [formData, setFormData] = useState<Partial<AutomationConfig>>({});
  const [hasChanges, setHasChanges] = useState(false);

  // Sync form data with loaded config
  const currentConfig = { ...config, ...formData };

  const handleChange = <K extends keyof AutomationConfig>(
    key: K,
    value: AutomationConfig[K]
  ) => {
    setFormData((prev) => ({ ...prev, [key]: value }));
    setHasChanges(true);
  };

  const handleSave = async () => {
    if (!hasChanges) return;

    try {
      await updateMutation.mutateAsync(formData);
      toast.success('Konfiguration gespeichert');
      setFormData({});
      setHasChanges(false);
    } catch {
      toast.error('Fehler beim Speichern');
    }
  };

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <Skeleton className="h-6 w-48" />
          <Skeleton className="h-4 w-64 mt-2" />
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

  if (!config) return null;

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <div>
          <CardTitle className="flex items-center gap-2">
            <Settings className="h-5 w-5" />
            Automatisierungs-Konfiguration
          </CardTitle>
          <CardDescription>
            Einstellungen fuer automatische Zahlungsvorschlaege
          </CardDescription>
        </div>
        {hasChanges && (
          <Button onClick={handleSave} disabled={updateMutation.isPending}>
            {updateMutation.isPending ? (
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            ) : (
              <Save className="h-4 w-4 mr-2" />
            )}
            Speichern
          </Button>
        )}
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Automatisierung */}
        <div className="space-y-4">
          <h4 className="font-medium">Automatisierung</h4>

          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Label htmlFor="auto_generate">Batch bei Genehmigung erstellen</Label>
              <InfoTooltip text="Erstellt automatisch einen Zahlungs-Batch wenn Rechnungen genehmigt werden" />
            </div>
            <Switch
              id="auto_generate"
              checked={currentConfig.auto_generate_on_approval ?? false}
              onCheckedChange={(v) => handleChange('auto_generate_on_approval', v)}
            />
          </div>

          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Label htmlFor="auto_execute">Automatisch ausfuehren</Label>
              <InfoTooltip text="Fuehrt genehmigte Batches automatisch aus (nur mit Bank-Integration)" />
            </div>
            <Switch
              id="auto_execute"
              checked={currentConfig.auto_execute ?? false}
              onCheckedChange={(v) => handleChange('auto_execute', v)}
            />
          </div>

          <div className="grid gap-2">
            <div className="flex items-center gap-2">
              <Label htmlFor="auto_approve_threshold">Auto-Approve Schwelle (EUR)</Label>
              <InfoTooltip text="Zahlungen unter diesem Betrag werden automatisch freigegeben" />
            </div>
            <Input
              id="auto_approve_threshold"
              type="number"
              value={currentConfig.auto_approve_threshold ?? 1000}
              onChange={(e) => handleChange('auto_approve_threshold', Number(e.target.value))}
            />
          </div>
        </div>

        {/* Skonto-Optimierung */}
        <div className="space-y-4 pt-4 border-t">
          <h4 className="font-medium">Skonto-Optimierung</h4>

          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Label htmlFor="prioritize_skonto">Skonto priorisieren</Label>
              <InfoTooltip text="Rechnungen mit Skonto werden hoeher priorisiert" />
            </div>
            <Switch
              id="prioritize_skonto"
              checked={currentConfig.prioritize_skonto ?? true}
              onCheckedChange={(v) => handleChange('prioritize_skonto', v)}
            />
          </div>

          <div className="grid gap-2">
            <div className="flex items-center gap-2">
              <Label htmlFor="skonto_alert_days">Skonto-Alert Tage</Label>
              <InfoTooltip text="Tage vor Ablauf fuer kritische Warnung" />
            </div>
            <Input
              id="skonto_alert_days"
              type="number"
              min={1}
              max={14}
              value={currentConfig.skonto_alert_days ?? 3}
              onChange={(e) => handleChange('skonto_alert_days', Number(e.target.value))}
            />
          </div>

          <div className="grid gap-2">
            <div className="flex items-center gap-2">
              <Label htmlFor="skonto_min_savings">Mindest-Skonto-Ersparnis (EUR)</Label>
              <InfoTooltip text="Minimum Ersparnis damit Skonto angewendet wird" />
            </div>
            <Input
              id="skonto_min_savings"
              type="number"
              min={0}
              step={5}
              value={currentConfig.skonto_min_savings ?? 10}
              onChange={(e) => handleChange('skonto_min_savings', Number(e.target.value))}
            />
          </div>
        </div>

        {/* Timing */}
        <div className="space-y-4 pt-4 border-t">
          <h4 className="font-medium">Timing</h4>

          <div className="grid gap-2">
            <div className="flex items-center gap-2">
              <Label htmlFor="advance_days">Vorlauf-Tage</Label>
              <InfoTooltip text="Tage vor Faelligkeit fuer Zahlungsvorschlag" />
            </div>
            <Input
              id="advance_days"
              type="number"
              min={0}
              max={14}
              value={currentConfig.advance_days ?? 2}
              onChange={(e) => handleChange('advance_days', Number(e.target.value))}
            />
          </div>

          <div className="grid gap-2">
            <div className="flex items-center gap-2">
              <Label htmlFor="batch_window_days">Batch-Fenster (Tage)</Label>
              <InfoTooltip text="Rechnungen der naechsten X Tage in Batch einbeziehen" />
            </div>
            <Input
              id="batch_window_days"
              type="number"
              min={1}
              max={30}
              value={currentConfig.batch_window_days ?? 7}
              onChange={(e) => handleChange('batch_window_days', Number(e.target.value))}
            />
          </div>
        </div>

        {/* Limits */}
        <div className="space-y-4 pt-4 border-t">
          <h4 className="font-medium">Limits</h4>

          <div className="grid gap-2">
            <div className="flex items-center gap-2">
              <Label htmlFor="max_batch_size">Max. Zahlungen pro Batch</Label>
              <InfoTooltip text="Maximale Anzahl Zahlungen in einem Batch" />
            </div>
            <Input
              id="max_batch_size"
              type="number"
              min={1}
              max={200}
              value={currentConfig.max_batch_size ?? 50}
              onChange={(e) => handleChange('max_batch_size', Number(e.target.value))}
            />
          </div>

          <div className="grid gap-2">
            <div className="flex items-center gap-2">
              <Label htmlFor="max_single_payment">Max. Einzelzahlung (EUR)</Label>
              <InfoTooltip text="Einzelne Zahlungen ueber diesem Betrag werden ausgeschlossen" />
            </div>
            <Input
              id="max_single_payment"
              type="number"
              min={1000}
              step={1000}
              value={currentConfig.max_single_payment ?? 100000}
              onChange={(e) => handleChange('max_single_payment', Number(e.target.value))}
            />
          </div>

          <div className="grid gap-2">
            <div className="flex items-center gap-2">
              <Label htmlFor="daily_limit">Tageslimit (EUR)</Label>
              <InfoTooltip text="Maximaler Zahlungsausgang pro Tag" />
            </div>
            <Input
              id="daily_limit"
              type="number"
              min={10000}
              step={10000}
              value={currentConfig.daily_limit ?? 500000}
              onChange={(e) => handleChange('daily_limit', Number(e.target.value))}
            />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
