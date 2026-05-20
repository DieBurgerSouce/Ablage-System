/**
 * DeadlineCreateDialog - Dialog zum Erstellen einer neuen Frist
 */

import * as React from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Switch } from '@/components/ui/switch';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Loader2 } from 'lucide-react';
import type { PrivatDeadlineCreate, PrivatDeadlineType } from '@/types/privat';

interface DeadlineCreateDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSubmit: (data: PrivatDeadlineCreate) => Promise<void>;
  isLoading?: boolean;
}

const DEADLINE_TYPES: { value: PrivatDeadlineType; label: string }[] = [
  { value: 'insurance_payment', label: 'Versicherungszahlung' },
  { value: 'loan_payment', label: 'Kreditzahlung' },
  { value: 'tax_deadline', label: 'Steuerfrist' },
  { value: 'contract_renewal', label: 'Vertragsverlängerung' },
  { value: 'vehicle_inspection', label: 'Fahrzeugprüfung (TÜV/HU)' },
  { value: 'registration_renewal', label: 'Registrierungsverlängerung' },
  { value: 'custom', label: 'Benutzerdefiniert' },
];

const RECURRENCE_OPTIONS = [
  { value: 'monthly', label: 'Monatlich' },
  { value: 'quarterly', label: 'Vierteljährlich' },
  { value: 'semi-annually', label: 'Halbjährlich' },
  { value: 'annually', label: 'Jährlich' },
];

const PRIORITY_OPTIONS = [
  { value: 1, label: 'Niedrig' },
  { value: 2, label: 'Mittel' },
  { value: 3, label: 'Hoch' },
];

export function DeadlineCreateDialog({
  open,
  onOpenChange,
  onSubmit,
  isLoading = false,
}: DeadlineCreateDialogProps) {
  const [formData, setFormData] = React.useState<PrivatDeadlineCreate>({
    title: '',
    deadlineType: 'custom',
    dueDate: '',
    isRecurring: false,
  });
  const [error, setError] = React.useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!formData.title.trim()) {
      setError('Titel ist erforderlich');
      return;
    }

    if (!formData.dueDate) {
      setError('Fälligkeitsdatum ist erforderlich');
      return;
    }

    try {
      await onSubmit({
        ...formData,
        title: formData.title.trim(),
        description: formData.description?.trim() || undefined,
        recurrenceInterval: formData.isRecurring ? formData.recurrenceInterval : undefined,
      });
      resetForm();
      onOpenChange(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Fehler beim Erstellen');
    }
  };

  const resetForm = () => {
    setFormData({
      title: '',
      deadlineType: 'custom',
      dueDate: '',
      isRecurring: false,
    });
    setError(null);
  };

  const handleOpenChange = (newOpen: boolean) => {
    if (!newOpen) {
      resetForm();
    }
    onOpenChange(newOpen);
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-[500px] max-h-[90vh] overflow-y-auto">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>Neue Frist</DialogTitle>
            <DialogDescription>
              Erstellen Sie eine neue Frist oder Erinnerung.
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-4 py-4">
            {/* Title */}
            <div className="grid gap-2">
              <Label htmlFor="title">
                Titel <span className="text-destructive">*</span>
              </Label>
              <Input
                id="title"
                value={formData.title}
                onChange={(e) => setFormData({ ...formData, title: e.target.value })}
                placeholder="z.B. KFZ-Versicherung bezahlen"
                maxLength={200}
                disabled={isLoading}
              />
            </div>

            {/* Deadline Type */}
            <div className="grid gap-2">
              <Label htmlFor="deadlineType">Fristtyp</Label>
              <Select
                value={formData.deadlineType}
                onValueChange={(value) => setFormData({ ...formData, deadlineType: value as PrivatDeadlineType })}
                disabled={isLoading}
              >
                <SelectTrigger id="deadlineType">
                  <SelectValue placeholder="Typ auswählen" />
                </SelectTrigger>
                <SelectContent>
                  {DEADLINE_TYPES.map((type) => (
                    <SelectItem key={type.value} value={type.value}>
                      {type.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Due Date & Priority */}
            <div className="grid grid-cols-2 gap-4">
              <div className="grid gap-2">
                <Label htmlFor="dueDate">
                  Fälligkeitsdatum <span className="text-destructive">*</span>
                </Label>
                <Input
                  id="dueDate"
                  type="date"
                  value={formData.dueDate}
                  onChange={(e) => setFormData({ ...formData, dueDate: e.target.value })}
                  disabled={isLoading}
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="priority">Priorität</Label>
                <Select
                  value={formData.priority?.toString() || ''}
                  onValueChange={(value) => setFormData({ ...formData, priority: value ? Number(value) : undefined })}
                  disabled={isLoading}
                >
                  <SelectTrigger id="priority">
                    <SelectValue placeholder="Optional" />
                  </SelectTrigger>
                  <SelectContent>
                    {PRIORITY_OPTIONS.map((opt) => (
                      <SelectItem key={opt.value} value={opt.value.toString()}>
                        {opt.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            {/* Recurring Toggle */}
            <div className="flex items-center justify-between">
              <div className="space-y-0.5">
                <Label htmlFor="isRecurring">Wiederkehrend</Label>
                <p className="text-sm text-muted-foreground">
                  Frist wiederholt sich automatisch
                </p>
              </div>
              <Switch
                id="isRecurring"
                checked={formData.isRecurring || false}
                onCheckedChange={(checked) => setFormData({
                  ...formData,
                  isRecurring: checked,
                  recurrenceInterval: checked ? 'annually' : undefined
                })}
                disabled={isLoading}
              />
            </div>

            {/* Recurrence Interval */}
            {formData.isRecurring && (
              <div className="grid gap-2">
                <Label htmlFor="recurrenceInterval">Wiederholungsintervall</Label>
                <Select
                  value={formData.recurrenceInterval || 'annually'}
                  onValueChange={(value) => setFormData({ ...formData, recurrenceInterval: value })}
                  disabled={isLoading}
                >
                  <SelectTrigger id="recurrenceInterval">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {RECURRENCE_OPTIONS.map((opt) => (
                      <SelectItem key={opt.value} value={opt.value}>
                        {opt.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}

            {/* Description */}
            <div className="grid gap-2">
              <Label htmlFor="description">Beschreibung</Label>
              <Textarea
                id="description"
                value={formData.description || ''}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                placeholder="Optionale Beschreibung..."
                rows={2}
                maxLength={1000}
                disabled={isLoading}
              />
            </div>

            {/* Error */}
            {error && (
              <p className="text-sm text-destructive" role="alert">
                {error}
              </p>
            )}
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => handleOpenChange(false)}
              disabled={isLoading}
            >
              Abbrechen
            </Button>
            <Button type="submit" disabled={isLoading}>
              {isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Erstellen
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export default DeadlineCreateDialog;
