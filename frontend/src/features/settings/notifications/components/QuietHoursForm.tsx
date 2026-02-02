/**
 * QuietHoursForm Component
 *
 * Konfiguration fuer Ruhezeiten (Benachrichtigungen pausieren).
 */

import { useState, useEffect } from 'react';
import { Moon, Clock, AlertTriangle, Info } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Switch } from '@/components/ui/switch';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription } from '@/components/ui/alert';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import type { QuietHoursConfig, Weekday } from '../types';
import { WEEKDAY_LABELS, ALL_WEEKDAYS, DEFAULT_QUIET_HOURS } from '../types';

interface QuietHoursFormProps {
  config: QuietHoursConfig;
  onUpdate: (config: Partial<QuietHoursConfig>) => void;
  isLoading?: boolean;
  disabled?: boolean;
}

// Stunden-Optionen fuer Select
const HOUR_OPTIONS = Array.from({ length: 24 }, (_, i) => ({
  value: i.toString(),
  label: `${i.toString().padStart(2, '0')}:00`,
}));

// Verfuegbare Zeitzonen (Deutschland-relevante)
const TIMEZONE_OPTIONS = [
  { value: 'Europe/Berlin', label: 'Berlin (MEZ/MESZ)' },
  { value: 'Europe/Vienna', label: 'Wien (MEZ/MESZ)' },
  { value: 'Europe/Zurich', label: 'Zuerich (MEZ/MESZ)' },
  { value: 'UTC', label: 'UTC' },
];

export function QuietHoursForm({
  config,
  onUpdate,
  isLoading = false,
  disabled = false,
}: QuietHoursFormProps) {
  const [localConfig, setLocalConfig] = useState<QuietHoursConfig>(config || DEFAULT_QUIET_HOURS);
  const [hasChanges, setHasChanges] = useState(false);

  useEffect(() => {
    if (config) {
      setLocalConfig(config);
      setHasChanges(false);
    }
  }, [config]);

  const handleChange = <K extends keyof QuietHoursConfig>(
    key: K,
    value: QuietHoursConfig[K]
  ) => {
    setLocalConfig((prev) => ({ ...prev, [key]: value }));
    setHasChanges(true);
  };

  const toggleWeekday = (day: Weekday) => {
    const current = localConfig.weekdays || [];
    const newWeekdays = current.includes(day)
      ? current.filter((d) => d !== day)
      : [...current, day];
    handleChange('weekdays', newWeekdays);
  };

  const handleSave = () => {
    onUpdate(localConfig);
    setHasChanges(false);
  };

  const handleReset = () => {
    setLocalConfig(config || DEFAULT_QUIET_HOURS);
    setHasChanges(false);
  };

  // Berechne Ruhezeit-Dauer
  const calculateDuration = (): string => {
    let hours = localConfig.endHour - localConfig.startHour;
    if (hours <= 0) hours += 24;
    return `${hours} Stunden`;
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <Moon className="h-5 w-5 text-primary" />
          <CardTitle className="text-lg">Ruhezeiten</CardTitle>
        </div>
        <CardDescription>
          Legen Sie Zeiten fest, in denen Sie keine Benachrichtigungen erhalten moechten.
          Kritische Alerts koennen optional durchgelassen werden.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Aktivierung */}
        <div className="flex items-center justify-between">
          <div className="space-y-0.5">
            <Label htmlFor="quiet-hours-enabled">Ruhezeiten aktivieren</Label>
            <p className="text-sm text-muted-foreground">
              Benachrichtigungen waehrend der Ruhezeit pausieren
            </p>
          </div>
          <Switch
            id="quiet-hours-enabled"
            checked={localConfig.enabled}
            onCheckedChange={(checked) => handleChange('enabled', checked)}
            disabled={disabled || isLoading}
          />
        </div>

        {localConfig.enabled && (
          <>
            {/* Zeitraum */}
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label>Beginn</Label>
                <Select
                  value={localConfig.startHour.toString()}
                  onValueChange={(value) => handleChange('startHour', parseInt(value))}
                  disabled={disabled || isLoading}
                >
                  <SelectTrigger>
                    <Clock className="h-4 w-4 mr-2" />
                    <SelectValue placeholder="Startzeit" />
                  </SelectTrigger>
                  <SelectContent>
                    {HOUR_OPTIONS.map((option) => (
                      <SelectItem key={option.value} value={option.value}>
                        {option.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label>Ende</Label>
                <Select
                  value={localConfig.endHour.toString()}
                  onValueChange={(value) => handleChange('endHour', parseInt(value))}
                  disabled={disabled || isLoading}
                >
                  <SelectTrigger>
                    <Clock className="h-4 w-4 mr-2" />
                    <SelectValue placeholder="Endzeit" />
                  </SelectTrigger>
                  <SelectContent>
                    {HOUR_OPTIONS.map((option) => (
                      <SelectItem key={option.value} value={option.value}>
                        {option.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            {/* Dauer-Info */}
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Info className="h-4 w-4" />
              <span>
                Ruhezeit: {HOUR_OPTIONS[localConfig.startHour]?.label} bis{' '}
                {HOUR_OPTIONS[localConfig.endHour]?.label} ({calculateDuration()})
              </span>
            </div>

            {/* Zeitzone */}
            <div className="space-y-2">
              <Label>Zeitzone</Label>
              <Select
                value={localConfig.timezone}
                onValueChange={(value) => handleChange('timezone', value)}
                disabled={disabled || isLoading}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Zeitzone waehlen" />
                </SelectTrigger>
                <SelectContent>
                  {TIMEZONE_OPTIONS.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Wochentage */}
            <div className="space-y-2">
              <Label>Aktive Wochentage</Label>
              <div className="flex flex-wrap gap-2">
                {ALL_WEEKDAYS.map((day) => (
                  <Button
                    key={day}
                    type="button"
                    variant={localConfig.weekdays?.includes(day) ? 'default' : 'outline'}
                    size="sm"
                    onClick={() => toggleWeekday(day)}
                    disabled={disabled || isLoading}
                    className="min-w-[40px]"
                  >
                    {WEEKDAY_LABELS[day]}
                  </Button>
                ))}
              </div>
              <p className="text-sm text-muted-foreground">
                Ruhezeiten gelten nur an den ausgewaehlten Tagen.
              </p>
            </div>

            {/* Kritische Alerts */}
            <div className="flex items-center justify-between pt-4 border-t">
              <div className="space-y-0.5">
                <Label htmlFor="skip-critical" className="flex items-center gap-2">
                  <AlertTriangle className="h-4 w-4 text-red-500" />
                  Kritische Alerts durchlassen
                </Label>
                <p className="text-sm text-muted-foreground">
                  Kritische Benachrichtigungen werden auch waehrend der Ruhezeit gesendet.
                </p>
              </div>
              <Switch
                id="skip-critical"
                checked={localConfig.skipCritical}
                onCheckedChange={(checked) => handleChange('skipCritical', checked)}
                disabled={disabled || isLoading}
              />
            </div>

            {!localConfig.skipCritical && (
              <Alert variant="default" className="border-yellow-500/50 bg-yellow-500/10">
                <AlertTriangle className="h-4 w-4 text-yellow-500" />
                <AlertDescription>
                  <strong>Achtung:</strong> Kritische Sicherheits- und System-Alerts werden
                  ebenfalls pausiert. Dies kann zu verzoegerten Reaktionen auf wichtige
                  Ereignisse fuehren.
                </AlertDescription>
              </Alert>
            )}
          </>
        )}

        {/* Speichern/Abbrechen */}
        {hasChanges && (
          <div className="flex gap-2 pt-4 border-t">
            <Button onClick={handleSave} disabled={isLoading}>
              Speichern
            </Button>
            <Button variant="outline" onClick={handleReset} disabled={isLoading}>
              Zuruecksetzen
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default QuietHoursForm;
