/**
 * RuleFormDialog
 *
 * Dialog zum Erstellen und Bearbeiten von Validierungsregeln.
 * Unterstützt verschiedene Regeltypen mit spezifischen Bedingungen.
 */

import { useState, useEffect } from 'react';
import { Settings2 } from 'lucide-react';
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
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { Slider } from '@/components/ui/slider';
import {
  ValidationRuleType,
  RULE_TYPE_LABELS,
} from '../types/validation-queue.types';
import type { ValidationRule, ValidationRuleCreate, ValidationRuleUpdate } from '../types/validation-queue.types';

interface RuleFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSubmit: (data: ValidationRuleCreate | ValidationRuleUpdate) => void;
  isLoading?: boolean;
  initialData?: ValidationRule;
}

const DOCUMENT_TYPE_OPTIONS = [
  { value: 'invoice', label: 'Rechnungen' },
  { value: 'delivery_note', label: 'Lieferscheine' },
  { value: 'contract', label: 'Verträge' },
  { value: 'letter', label: 'Briefe' },
  { value: 'order', label: 'Bestellungen' },
  { value: 'receipt', label: 'Kassenbelege' },
];

export function RuleFormDialog({
  open,
  onOpenChange,
  onSubmit,
  isLoading = false,
  initialData,
}: RuleFormDialogProps) {
  const isEdit = !!initialData;

  // Form State
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [ruleType, setRuleType] = useState<ValidationRuleType>(ValidationRuleType.CONFIDENCE_THRESHOLD);
  const [priority, setPriority] = useState(50);
  const [isActive, setIsActive] = useState(true);

  // Condition-spezifische States
  const [confidenceThreshold, setConfidenceThreshold] = useState(70);
  const [documentType, setDocumentType] = useState('');
  const [fieldPattern, setFieldPattern] = useState('');
  const [errorPattern, setErrorPattern] = useState('');

  // Initialize form with initial data
  useEffect(() => {
    if (initialData) {
      setName(initialData.name);
      setDescription(initialData.description || '');
      setRuleType(initialData.rule_type);
      setPriority(initialData.priority);
      setIsActive(initialData.is_active);

      // Parse conditions
      const cond = initialData.conditions || {};
      if (cond.threshold) setConfidenceThreshold(cond.threshold * 100);
      if (cond.document_type) setDocumentType(cond.document_type);
      if (cond.field_pattern) setFieldPattern(cond.field_pattern);
      if (cond.error_pattern) setErrorPattern(cond.error_pattern);
    } else {
      // Reset form
      setName('');
      setDescription('');
      setRuleType(ValidationRuleType.CONFIDENCE_THRESHOLD);
      setPriority(50);
      setIsActive(true);
      setConfidenceThreshold(70);
      setDocumentType('');
      setFieldPattern('');
      setErrorPattern('');
    }
  }, [initialData, open]);

  const handleSubmit = () => {
    if (!name.trim()) return;

    // Build conditions based on rule type
    let conditions: Record<string, unknown> = {};

    switch (ruleType) {
      case ValidationRuleType.CONFIDENCE_THRESHOLD:
        conditions = { threshold: confidenceThreshold / 100 };
        break;
      case ValidationRuleType.DOCUMENT_TYPE:
        conditions = { document_type: documentType };
        break;
      case ValidationRuleType.FIELD_PATTERN:
        conditions = { field_pattern: fieldPattern };
        break;
      case ValidationRuleType.ERROR_PATTERN:
        conditions = { error_pattern: errorPattern };
        break;
    }

    const data: ValidationRuleCreate | ValidationRuleUpdate = {
      name: name.trim(),
      description: description.trim() || undefined,
      rule_type: ruleType,
      conditions,
      priority,
      is_active: isActive,
    };

    onSubmit(data);
  };

  const handleClose = () => {
    if (!isLoading) {
      onOpenChange(false);
    }
  };

  const isFormValid = () => {
    if (!name.trim()) return false;

    switch (ruleType) {
      case ValidationRuleType.DOCUMENT_TYPE:
        return !!documentType;
      case ValidationRuleType.FIELD_PATTERN:
        return !!fieldPattern.trim();
      case ValidationRuleType.ERROR_PATTERN:
        return !!errorPattern.trim();
      default:
        return true;
    }
  };

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-[550px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Settings2 className="w-5 h-5" />
            {isEdit ? 'Regel bearbeiten' : 'Neue Regel erstellen'}
          </DialogTitle>
          <DialogDescription>
            {isEdit
              ? 'Aktualisieren Sie die Regeleinstellungen'
              : 'Erstellen Sie eine neue Validierungsregel für automatische Stichproben'}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4 max-h-[60vh] overflow-y-auto">
          {/* Name */}
          <div className="space-y-2">
            <Label htmlFor="rule-name">
              Name <span className="text-destructive">*</span>
            </Label>
            <Input
              id="rule-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="z.B. Niedrige Konfidenz Schwellenwert"
            />
          </div>

          {/* Beschreibung */}
          <div className="space-y-2">
            <Label htmlFor="rule-description">Beschreibung</Label>
            <Textarea
              id="rule-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Optionale Beschreibung der Regel..."
              className="min-h-[80px]"
            />
          </div>

          {/* Regel-Typ */}
          <div className="space-y-2">
            <Label htmlFor="rule-type">Regeltyp</Label>
            <Select
              value={ruleType}
              onValueChange={(value) => setRuleType(value as ValidationRuleType)}
              disabled={isEdit}
            >
              <SelectTrigger id="rule-type">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {Object.entries(RULE_TYPE_LABELS).map(([value, label]) => (
                  <SelectItem key={value} value={value}>
                    {label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {isEdit && (
              <p className="text-xs text-muted-foreground">
                Der Regeltyp kann nachträglich nicht geändert werden
              </p>
            )}
          </div>

          {/* Typ-spezifische Bedingungen */}
          {ruleType === ValidationRuleType.CONFIDENCE_THRESHOLD && (
            <div className="space-y-2">
              <Label>
                Konfidenz-Schwellenwert: {confidenceThreshold}%
              </Label>
              <Slider
                value={[confidenceThreshold]}
                onValueChange={([value]) => setConfidenceThreshold(value)}
                min={0}
                max={100}
                step={5}
                className="py-4"
              />
              <p className="text-xs text-muted-foreground">
                Dokumente mit Konfidenz unter diesem Wert werden zur Validierung markiert
              </p>
            </div>
          )}

          {ruleType === ValidationRuleType.DOCUMENT_TYPE && (
            <div className="space-y-2">
              <Label htmlFor="doc-type">
                Dokumenttyp <span className="text-destructive">*</span>
              </Label>
              <Select value={documentType} onValueChange={setDocumentType}>
                <SelectTrigger id="doc-type">
                  <SelectValue placeholder="Dokumenttyp auswählen" />
                </SelectTrigger>
                <SelectContent>
                  {DOCUMENT_TYPE_OPTIONS.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">
                Alle Dokumente dieses Typs werden zur Validierung markiert
              </p>
            </div>
          )}

          {ruleType === ValidationRuleType.FIELD_PATTERN && (
            <div className="space-y-2">
              <Label htmlFor="field-pattern">
                Feld-Muster (Regex) <span className="text-destructive">*</span>
              </Label>
              <Input
                id="field-pattern"
                value={fieldPattern}
                onChange={(e) => setFieldPattern(e.target.value)}
                placeholder="z.B. ^iban$|^bic$"
                className="font-mono"
              />
              <p className="text-xs text-muted-foreground">
                Dokumente mit Feldern, die diesem Muster entsprechen, werden markiert
              </p>
            </div>
          )}

          {ruleType === ValidationRuleType.ERROR_PATTERN && (
            <div className="space-y-2">
              <Label htmlFor="error-pattern">
                Fehler-Muster (Regex) <span className="text-destructive">*</span>
              </Label>
              <Input
                id="error-pattern"
                value={errorPattern}
                onChange={(e) => setErrorPattern(e.target.value)}
                placeholder="z.B. umlaut_error|format_error"
                className="font-mono"
              />
              <p className="text-xs text-muted-foreground">
                Dokumente mit Fehlern, die diesem Muster entsprechen, werden markiert
              </p>
            </div>
          )}

          {/* Priorität */}
          <div className="space-y-2">
            <Label>Priorität: {priority}</Label>
            <Slider
              value={[priority]}
              onValueChange={([value]) => setPriority(value)}
              min={0}
              max={100}
              step={10}
              className="py-4"
            />
            <p className="text-xs text-muted-foreground">
              Höhere Priorität = wird früher in der Queue angezeigt
            </p>
          </div>

          {/* Aktiv */}
          <div className="flex items-center justify-between p-3 border rounded-md">
            <div>
              <Label htmlFor="rule-active">Regel aktiviert</Label>
              <p className="text-xs text-muted-foreground">
                Nur aktive Regeln werden bei der Stichprobenauswahl berücksichtigt
              </p>
            </div>
            <Switch
              id="rule-active"
              checked={isActive}
              onCheckedChange={setIsActive}
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={handleClose} disabled={isLoading}>
            Abbrechen
          </Button>
          <Button onClick={handleSubmit} disabled={isLoading || !isFormValid()}>
            {isLoading
              ? isEdit
                ? 'Speichern...'
                : 'Erstellen...'
              : isEdit
                ? 'Speichern'
                : 'Erstellen'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default RuleFormDialog;
