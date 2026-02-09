/**
 * ScheduleConfig Component
 *
 * Konfiguration fuer automatische Report-Ausfuehrung mit Cron-Presets und E-Mail-Versand.
 */

import { useState } from 'react';
import {
  Calendar,
  Clock,
  Mail,
  Plus,
  Trash2,
  X,
} from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog';
import { formatDistanceToNow } from 'date-fns';
import { de } from 'date-fns/locale';
import {
  useSchedulePresets,
  useEnableSchedule,
  useDisableSchedule,
} from '../hooks/useReports';
import type { ReportTemplate, ExportFormat, SchedulePreset } from '../types';

interface ScheduleConfigProps {
  template: ReportTemplate;
}

const formatOptions: { value: ExportFormat; label: string }[] = [
  { value: 'excel', label: 'Excel (.xlsx)' },
  { value: 'pdf', label: 'PDF' },
  { value: 'csv', label: 'CSV' },
  { value: 'json', label: 'JSON' },
];

const timezoneOptions = [
  { value: 'Europe/Berlin', label: 'Europa/Berlin (CET/CEST)' },
  { value: 'Europe/Vienna', label: 'Europa/Wien (CET/CEST)' },
  { value: 'Europe/Zurich', label: 'Europa/Zuerich (CET/CEST)' },
  { value: 'UTC', label: 'UTC' },
];

export function ScheduleConfig({ template }: ScheduleConfigProps) {
  const [scheduleEnabled, setScheduleEnabled] = useState(template.is_scheduled);
  const [selectedPreset, setSelectedPreset] = useState<string>('daily_morning');
  const [customCron, setCustomCron] = useState('');
  const [useCustomCron, setUseCustomCron] = useState(false);
  const [timezone, setTimezone] = useState('Europe/Berlin');
  const [format, setFormat] = useState<ExportFormat>(template.default_format || 'excel');
  const [recipients, setRecipients] = useState<string[]>([]);
  const [newRecipient, setNewRecipient] = useState('');

  const { data: presets } = useSchedulePresets();
  const enableMutation = useEnableSchedule();
  const disableMutation = useDisableSchedule();

  // Sync state from template.schedule_config (without useEffect)
  const [prevConfigJson, setPrevConfigJson] = useState<string | null>(null);
  const configJson = template.schedule_config ? JSON.stringify(template.schedule_config) : null;
  const presetsJson = presets ? JSON.stringify(presets.map((p) => ({ id: p.id, cron: p.cron }))) : null;
  const syncKey = `${configJson}|${presetsJson}`;
  if (syncKey !== prevConfigJson) {
    setPrevConfigJson(syncKey);
    if (template.schedule_config) {
      const config = template.schedule_config;
      setTimezone(config.timezone || 'Europe/Berlin');
      setFormat(config.format || template.default_format || 'excel');
      setRecipients(config.recipients || []);

      const matchingPreset = presets?.find((p) => p.cron === config.cron_expression);
      if (matchingPreset) {
        setSelectedPreset(matchingPreset.id);
        setUseCustomCron(false);
      } else {
        setCustomCron(config.cron_expression);
        setUseCustomCron(true);
      }
    }
  }

  const handleToggleSchedule = (enabled: boolean) => {
    setScheduleEnabled(enabled);

    if (!enabled) {
      // Deaktiviere Zeitplan
      disableMutation.mutate(template.id);
    }
  };

  const handleSaveSchedule = () => {
    const cronExpression = useCustomCron
      ? customCron
      : presets?.find((p) => p.id === selectedPreset)?.cron || '0 8 * * *';

    enableMutation.mutate({
      templateId: template.id,
      data: {
        cron_expression: cronExpression,
        timezone,
        recipients,
        format,
      },
    });
  };

  const handleAddRecipient = () => {
    if (newRecipient && newRecipient.includes('@') && !recipients.includes(newRecipient)) {
      setRecipients((prev) => [...prev, newRecipient]);
      setNewRecipient('');
    }
  };

  const handleRemoveRecipient = (email: string) => {
    setRecipients((prev) => prev.filter((r) => r !== email));
  };

  const isLoading = enableMutation.isPending || disableMutation.isPending;

  return (
    <div className="space-y-4">
      {/* Schedule Toggle */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Clock className="h-5 w-5 text-muted-foreground" />
              <CardTitle className="text-base">Automatische Ausfuehrung</CardTitle>
            </div>
            <Switch
              checked={scheduleEnabled}
              onCheckedChange={handleToggleSchedule}
              disabled={isLoading}
            />
          </div>
          <CardDescription>
            Fuehren Sie diesen Report automatisch nach Zeitplan aus.
          </CardDescription>
        </CardHeader>

        {scheduleEnabled && (
          <CardContent className="space-y-4">
            {/* Aktueller Status */}
            {template.schedule_config && (
              <div className="rounded-md bg-muted/50 p-3 text-sm">
                <div className="flex items-center gap-2 mb-2">
                  <Calendar className="h-4 w-4 text-primary" />
                  <span className="font-medium">Aktiver Zeitplan</span>
                </div>
                <div className="space-y-1 text-muted-foreground">
                  {template.schedule_config.last_run && (
                    <p>
                      Letzte Ausfuehrung:{' '}
                      {formatDistanceToNow(new Date(template.schedule_config.last_run), {
                        addSuffix: true,
                        locale: de,
                      })}
                    </p>
                  )}
                  {template.schedule_config.next_run && (
                    <p>
                      Naechste Ausfuehrung:{' '}
                      {format(new Date(template.schedule_config.next_run), "d. MMMM yyyy 'um' HH:mm", {
                        locale: de,
                      })}
                    </p>
                  )}
                </div>
              </div>
            )}

            {/* Zeitplan-Auswahl */}
            <div className="space-y-2">
              <Label>Zeitplan</Label>
              <div className="flex items-center gap-2 mb-2">
                <Switch
                  id="custom-cron"
                  checked={useCustomCron}
                  onCheckedChange={setUseCustomCron}
                />
                <Label htmlFor="custom-cron" className="text-sm font-normal cursor-pointer">
                  Benutzerdefinierter Cron-Ausdruck
                </Label>
              </div>

              {useCustomCron ? (
                <div className="space-y-2">
                  <Input
                    value={customCron}
                    onChange={(e) => setCustomCron(e.target.value)}
                    placeholder="z.B. 0 8 * * 1-5 (Werktags 08:00)"
                  />
                  <p className="text-xs text-muted-foreground">
                    Format: Minute Stunde Tag Monat Wochentag
                  </p>
                </div>
              ) : (
                <Select value={selectedPreset} onValueChange={setSelectedPreset}>
                  <SelectTrigger>
                    <SelectValue placeholder="Zeitplan waehlen" />
                  </SelectTrigger>
                  <SelectContent>
                    {presets?.map((preset: SchedulePreset) => (
                      <SelectItem key={preset.id} value={preset.id}>
                        {preset.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            </div>

            {/* Zeitzone */}
            <div className="space-y-2">
              <Label>Zeitzone</Label>
              <Select value={timezone} onValueChange={setTimezone}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {timezoneOptions.map((tz) => (
                    <SelectItem key={tz.value} value={tz.value}>
                      {tz.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Export-Format */}
            <div className="space-y-2">
              <Label>Export-Format</Label>
              <Select value={format} onValueChange={(v: ExportFormat) => setFormat(v)}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {formatOptions.map((f) => (
                    <SelectItem key={f.value} value={f.value}>
                      {f.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* E-Mail-Empfaenger */}
            <div className="space-y-2">
              <Label className="flex items-center gap-2">
                <Mail className="h-4 w-4" />
                E-Mail-Empfaenger
              </Label>
              <p className="text-xs text-muted-foreground mb-2">
                Der Report wird automatisch an diese Adressen gesendet.
              </p>

              {recipients.length > 0 && (
                <div className="flex flex-wrap gap-2 mb-2">
                  {recipients.map((email) => (
                    <Badge key={email} variant="secondary" className="gap-1">
                      {email}
                      <button
                        onClick={() => handleRemoveRecipient(email)}
                        className="hover:text-destructive"
                      >
                        <X className="h-3 w-3" />
                      </button>
                    </Badge>
                  ))}
                </div>
              )}

              <div className="flex gap-2">
                <Input
                  type="email"
                  value={newRecipient}
                  onChange={(e) => setNewRecipient(e.target.value)}
                  placeholder="email@example.com"
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault();
                      handleAddRecipient();
                    }
                  }}
                />
                <Button
                  type="button"
                  variant="outline"
                  size="icon"
                  onClick={handleAddRecipient}
                  disabled={!newRecipient || !newRecipient.includes('@')}
                >
                  <Plus className="h-4 w-4" />
                </Button>
              </div>
            </div>

            {/* Speichern-Button */}
            <div className="flex justify-end gap-2 pt-4 border-t">
              <AlertDialog>
                <AlertDialogTrigger asChild>
                  <Button variant="outline" size="sm">
                    <Trash2 className="h-4 w-4 mr-2" />
                    Zeitplan deaktivieren
                  </Button>
                </AlertDialogTrigger>
                <AlertDialogContent>
                  <AlertDialogHeader>
                    <AlertDialogTitle>Zeitplan deaktivieren?</AlertDialogTitle>
                    <AlertDialogDescription>
                      Der automatische Report wird nicht mehr ausgefuehrt.
                      Die Konfiguration wird geloescht.
                    </AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel>Abbrechen</AlertDialogCancel>
                    <AlertDialogAction
                      onClick={() => handleToggleSchedule(false)}
                      className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                    >
                      Deaktivieren
                    </AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>

              <Button onClick={handleSaveSchedule} disabled={isLoading}>
                Zeitplan speichern
              </Button>
            </div>
          </CardContent>
        )}
      </Card>

      {/* Info-Karte */}
      {!scheduleEnabled && (
        <Card className="border-dashed">
          <CardContent className="flex flex-col items-center justify-center py-8">
            <Clock className="h-10 w-10 text-muted-foreground mb-3" />
            <h3 className="font-medium mb-1">Automatische Reports</h3>
            <p className="text-sm text-muted-foreground text-center max-w-sm">
              Aktivieren Sie den Zeitplan, um diesen Report automatisch ausfuehren
              und per E-Mail versenden zu lassen.
            </p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
