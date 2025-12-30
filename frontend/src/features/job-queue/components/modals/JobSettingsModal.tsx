/**
 * Job Settings Modal
 *
 * Notification Preferences für Job Queue Events.
 */

import { useState } from 'react';
import { Bell, BellOff, Check, Loader2, Volume2, VolumeX } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Separator } from '@/components/ui/separator';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { toast } from 'sonner';

// ==================== Types ====================

interface JobNotificationSettings {
  onComplete: boolean;
  onFailure: boolean;
  onStuck: boolean;
  soundEnabled: boolean;
  retentionDays: number;
}

interface JobSettingsModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

// ==================== Component ====================

export function JobSettingsModal({ open, onOpenChange }: JobSettingsModalProps) {
  // Default settings (in production would come from user preferences API)
  const [settings, setSettings] = useState<JobNotificationSettings>(() => {
    const stored = localStorage.getItem('jobQueueNotificationSettings');
    if (stored) {
      try {
        return JSON.parse(stored);
      } catch {
        // Ignore parse errors
      }
    }
    return {
      onComplete: false,
      onFailure: true,
      onStuck: true,
      soundEnabled: false,
      retentionDays: 7,
    };
  });

  const [isSaving, setIsSaving] = useState(false);

  const handleSave = async () => {
    setIsSaving(true);
    try {
      // Save to localStorage (in production would save to backend)
      localStorage.setItem('jobQueueNotificationSettings', JSON.stringify(settings));
      toast.success('Einstellungen gespeichert');
      onOpenChange(false);
    } catch (error) {
      toast.error('Fehler beim Speichern');
    } finally {
      setIsSaving(false);
    }
  };

  const updateSetting = <K extends keyof JobNotificationSettings>(
    key: K,
    value: JobNotificationSettings[K]
  ) => {
    setSettings((prev) => ({ ...prev, [key]: value }));
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Bell className="h-5 w-5" />
            Benachrichtigungseinstellungen
          </DialogTitle>
          <DialogDescription>
            Konfiguriere wann du über Job-Events benachrichtigt werden möchtest.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6 py-4">
          {/* Notification Events */}
          <div className="space-y-4">
            <h4 className="text-sm font-medium">Benachrichtigen bei</h4>

            <div className="flex items-center justify-between">
              <div className="space-y-0.5">
                <Label htmlFor="onComplete" className="flex items-center gap-2">
                  <Check className="h-4 w-4 text-green-600" />
                  Job abgeschlossen
                </Label>
                <p className="text-xs text-muted-foreground">
                  Benachrichtigung wenn ein Job erfolgreich abgeschlossen wurde
                </p>
              </div>
              <Switch
                id="onComplete"
                checked={settings.onComplete}
                onCheckedChange={(checked) => updateSetting('onComplete', checked)}
              />
            </div>

            <div className="flex items-center justify-between">
              <div className="space-y-0.5">
                <Label htmlFor="onFailure" className="flex items-center gap-2">
                  <BellOff className="h-4 w-4 text-red-600" />
                  Job fehlgeschlagen
                </Label>
                <p className="text-xs text-muted-foreground">
                  Benachrichtigung wenn ein Job fehlschlägt
                </p>
              </div>
              <Switch
                id="onFailure"
                checked={settings.onFailure}
                onCheckedChange={(checked) => updateSetting('onFailure', checked)}
              />
            </div>

            <div className="flex items-center justify-between">
              <div className="space-y-0.5">
                <Label htmlFor="onStuck" className="flex items-center gap-2">
                  <Bell className="h-4 w-4 text-yellow-600" />
                  Job hängt
                </Label>
                <p className="text-xs text-muted-foreground">
                  Benachrichtigung wenn ein Job ungewöhnlich lange läuft
                </p>
              </div>
              <Switch
                id="onStuck"
                checked={settings.onStuck}
                onCheckedChange={(checked) => updateSetting('onStuck', checked)}
              />
            </div>
          </div>

          <Separator />

          {/* Sound */}
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <Label htmlFor="soundEnabled" className="flex items-center gap-2">
                {settings.soundEnabled ? (
                  <Volume2 className="h-4 w-4" />
                ) : (
                  <VolumeX className="h-4 w-4 text-muted-foreground" />
                )}
                Ton aktivieren
              </Label>
              <p className="text-xs text-muted-foreground">
                Akustische Benachrichtigung abspielen
              </p>
            </div>
            <Switch
              id="soundEnabled"
              checked={settings.soundEnabled}
              onCheckedChange={(checked) => updateSetting('soundEnabled', checked)}
            />
          </div>

          <Separator />

          {/* Retention */}
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <Label>Historie Aufbewahrung</Label>
              <p className="text-xs text-muted-foreground">
                Wie lange sollen abgeschlossene Jobs angezeigt werden?
              </p>
            </div>
            <Select
              value={settings.retentionDays.toString()}
              onValueChange={(v) => updateSetting('retentionDays', Number(v))}
            >
              <SelectTrigger className="w-[120px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="3">3 Tage</SelectItem>
                <SelectItem value="7">7 Tage</SelectItem>
                <SelectItem value="14">14 Tage</SelectItem>
                <SelectItem value="30">30 Tage</SelectItem>
                <SelectItem value="90">90 Tage</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Abbrechen
          </Button>
          <Button onClick={handleSave} disabled={isSaving}>
            {isSaving ? (
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            ) : (
              <Check className="h-4 w-4 mr-2" />
            )}
            Speichern
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default JobSettingsModal;
