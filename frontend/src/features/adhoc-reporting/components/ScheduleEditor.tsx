/**
 * ScheduleEditor Component
 * German Enterprise Document Platform
 */

import { useState } from 'react';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Plus, Trash2, Clock } from 'lucide-react';
import type { Schedule } from '../types/adhoc-reporting-types';

interface ScheduleEditorProps {
  schedule?: Partial<Schedule>;
  onSave: (schedule: Partial<Schedule>) => void;
  onCancel: () => void;
}

export function ScheduleEditor({ schedule, onSave, onCancel }: ScheduleEditorProps) {
  const [frequency, setFrequency] = useState<Schedule['frequency']>(
    schedule?.frequency || 'daily'
  );
  const [time, setTime] = useState(schedule?.time || '09:00');
  const [recipients, setRecipients] = useState<string[]>(schedule?.recipients || []);
  const [active, setActive] = useState(schedule?.active ?? true);
  const [newRecipient, setNewRecipient] = useState('');

  const handleAddRecipient = () => {
    if (newRecipient && !recipients.includes(newRecipient)) {
      setRecipients([...recipients, newRecipient]);
      setNewRecipient('');
    }
  };

  const handleRemoveRecipient = (email: string) => {
    setRecipients(recipients.filter((r) => r !== email));
  };

  const handleSubmit = () => {
    onSave({
      frequency,
      time,
      recipients,
      active,
    });
  };

  return (
    <div className="space-y-6">
      <div className="space-y-4">
        <div className="space-y-2">
          <Label>Häufigkeit</Label>
          <Select value={frequency} onValueChange={(v) => setFrequency(v as Schedule['frequency'])}>
            <SelectTrigger>
              <SelectValue placeholder="Häufigkeit auswählen" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="daily">Täglich</SelectItem>
              <SelectItem value="weekly">Wöchentlich</SelectItem>
              <SelectItem value="monthly">Monatlich</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-2">
          <Label>Uhrzeit</Label>
          <Input
            type="time"
            value={time}
            onChange={(e) => setTime(e.target.value)}
          />
          <p className="text-xs text-muted-foreground">
            Der Report wird um diese Uhrzeit ausgeführt und versendet
          </p>
        </div>

        <div className="space-y-2">
          <Label>Empfänger</Label>
          <div className="flex space-x-2">
            <Input
              type="email"
              placeholder="email@beispiel.de"
              value={newRecipient}
              onChange={(e) => setNewRecipient(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault();
                  handleAddRecipient();
                }
              }}
            />
            <Button type="button" onClick={handleAddRecipient}>
              <Plus className="h-4 w-4" />
            </Button>
          </div>
          {recipients.length > 0 && (
            <div className="flex flex-wrap gap-2 mt-2">
              {recipients.map((email) => (
                <Badge key={email} variant="secondary">
                  {email}
                  <button
                    onClick={() => handleRemoveRecipient(email)}
                    className="ml-2 hover:text-destructive"
                  >
                    <Trash2 className="h-3 w-3" />
                  </button>
                </Badge>
              ))}
            </div>
          )}
        </div>

        <div className="flex items-center justify-between p-4 border rounded-lg">
          <div>
            <Label htmlFor="active-switch" className="cursor-pointer">
              Zeitplan aktiv
            </Label>
            <p className="text-xs text-muted-foreground">
              Aktivieren oder deaktivieren Sie die automatische Ausführung
            </p>
          </div>
          <Switch id="active-switch" checked={active} onCheckedChange={setActive} />
        </div>
      </div>

      {schedule?.next_execution && (
        <Card className="p-4 bg-muted/50">
          <div className="flex items-center space-x-2 text-sm">
            <Clock className="h-4 w-4 text-muted-foreground" />
            <span className="text-muted-foreground">Nächste Ausführung:</span>
            <span className="font-medium">
              {new Date(schedule.next_execution).toLocaleString('de-DE')}
            </span>
          </div>
        </Card>
      )}

      <div className="flex justify-end space-x-2 pt-4 border-t">
        <Button variant="outline" onClick={onCancel}>
          Abbrechen
        </Button>
        <Button onClick={handleSubmit} disabled={recipients.length === 0}>
          Zeitplan speichern
        </Button>
      </div>
    </div>
  );
}
