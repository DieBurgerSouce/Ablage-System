/**
 * ImportRuleBuilder - Visueller Regel-Editor für E-Mail-Import-Regeln.
 *
 * Ermöglicht Erstellung von Bedingungen und Aktionen mit Test-Funktion.
 */

import { useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import {
  Plus,
  Trash2,
  Loader2,
  Save,
  X,
  FlaskConical,
  CheckCircle2,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Separator } from '@/components/ui/separator';
import { useToast } from '@/components/ui/use-toast';
import {
  emailImportKeys,
  getRuleSchema,
  testImportRule,
} from '../api/email-import-api';
import type { ImportRule, RuleCondition, RuleAction } from '../types/email-types';

// ==================== Field/operator/action defaults ====================

const DEFAULT_FIELDS = [
  'sender_email',
  'sender_name',
  'subject',
  'filename',
  'file_extension',
  'file_size',
];

const DEFAULT_OPERATORS = [
  'equals',
  'not_equals',
  'contains',
  'not_contains',
  'starts_with',
  'ends_with',
  'matches_regex',
];

const DEFAULT_ACTIONS = [
  'set_folder',
  'add_tag',
  'set_category',
  'set_priority',
  'notify',
];

const OPERATOR_LABELS: Record<string, string> = {
  equals: 'Gleich',
  not_equals: 'Ungleich',
  contains: 'Enthält',
  not_contains: 'Enthält nicht',
  starts_with: 'Beginnt mit',
  ends_with: 'Endet mit',
  matches_regex: 'Regex',
  greater_than: 'Größer als',
  less_than: 'Kleiner als',
};

const ACTION_LABELS: Record<string, string> = {
  set_folder: 'Ordner setzen',
  add_tag: 'Tag hinzufügen',
  set_category: 'Kategorie setzen',
  set_priority: 'Priorität setzen',
  notify: 'Benachrichtigen',
};

// ==================== Sub-components ====================

interface ConditionRowProps {
  condition: RuleCondition;
  onChange: (updated: RuleCondition) => void;
  onRemove: () => void;
  fields: string[];
  operators: string[];
}

function ConditionRow({ condition, onChange, onRemove, fields, operators }: ConditionRowProps) {
  return (
    <div className="flex items-center gap-2 p-3 rounded-lg border bg-muted/30">
      <div className="flex-1 grid grid-cols-3 gap-2">
        <Select
          value={condition.field}
          onValueChange={(v) => onChange({ ...condition, field: v })}
        >
          <SelectTrigger>
            <SelectValue placeholder="Feld wählen" />
          </SelectTrigger>
          <SelectContent>
            {fields.map((f) => (
              <SelectItem key={f} value={f}>
                {f}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select
          value={condition.operator}
          onValueChange={(v) => onChange({ ...condition, operator: v })}
        >
          <SelectTrigger>
            <SelectValue placeholder="Operator" />
          </SelectTrigger>
          <SelectContent>
            {operators.map((op) => (
              <SelectItem key={op} value={op}>
                {OPERATOR_LABELS[op] ?? op}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Input
          value={condition.value}
          onChange={(e) => onChange({ ...condition, value: e.target.value })}
          placeholder="Wert"
        />
      </div>

      <Button
        type="button"
        variant="ghost"
        size="icon"
        className="text-destructive hover:text-destructive"
        onClick={onRemove}
      >
        <Trash2 className="h-4 w-4" />
      </Button>
    </div>
  );
}

interface ActionRowProps {
  action: RuleAction;
  onChange: (updated: RuleAction) => void;
  onRemove: () => void;
  actionTypes: string[];
}

function ActionRow({ action, onChange, onRemove, actionTypes }: ActionRowProps) {
  return (
    <div className="flex items-center gap-2 p-3 rounded-lg border bg-muted/30">
      <div className="flex-1 grid grid-cols-2 gap-2">
        <Select
          value={action.type}
          onValueChange={(v) => onChange({ ...action, type: v })}
        >
          <SelectTrigger>
            <SelectValue placeholder="Aktion wählen" />
          </SelectTrigger>
          <SelectContent>
            {actionTypes.map((t) => (
              <SelectItem key={t} value={t}>
                {ACTION_LABELS[t] ?? t}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Input
          value={action.value}
          onChange={(e) => onChange({ ...action, value: e.target.value })}
          placeholder="Wert"
        />
      </div>

      <Button
        type="button"
        variant="ghost"
        size="icon"
        className="text-destructive hover:text-destructive"
        onClick={onRemove}
      >
        <Trash2 className="h-4 w-4" />
      </Button>
    </div>
  );
}

// ==================== Main Component ====================

interface ImportRuleBuilderProps {
  rule?: ImportRule;
  onSave: (rule: ImportRule) => void;
  onCancel: () => void;
  isSubmitting?: boolean;
}

export function EmailImportRuleBuilder({
  rule,
  onSave,
  onCancel,
  isSubmitting = false,
}: ImportRuleBuilderProps) {
  const { toast } = useToast();

  const [name, setName] = useState(rule?.name ?? '');
  const [isActive, setIsActive] = useState(rule?.is_active ?? true);
  const [logic, setLogic] = useState<'AND' | 'OR'>(rule?.logic ?? 'AND');
  const [conditions, setConditions] = useState<RuleCondition[]>(
    rule?.conditions ?? [{ field: '', operator: 'contains', value: '' }],
  );
  const [actions, setActions] = useState<RuleAction[]>(
    rule?.actions ?? [{ type: 'set_folder', value: '' }],
  );
  const [priority, setPriority] = useState(rule?.priority ?? 50);
  const [testResult, setTestResult] = useState<{
    matches: number;
    sample_results: string[];
  } | null>(null);

  const { data: schema } = useQuery({
    queryKey: emailImportKeys.ruleSchema('email'),
    queryFn: () => getRuleSchema('email'),
  });

  const testMutation = useMutation({
    mutationFn: testImportRule,
    onSuccess: (data) => {
      setTestResult(data);
      toast({
        title: 'Test abgeschlossen',
        description: `${data.matches} Treffer gefunden`,
      });
    },
    onError: () => {
      toast({
        title: 'Testfehler',
        description: 'Regel konnte nicht getestet werden',
        variant: 'destructive',
      });
    },
  });

  const availableFields = schema?.fields ?? DEFAULT_FIELDS;
  const availableOperators = schema?.operators ?? DEFAULT_OPERATORS;
  const availableActions = schema?.actions ?? DEFAULT_ACTIONS;

  const updateCondition = (index: number, updated: RuleCondition) => {
    setConditions((prev) => prev.map((c, i) => (i === index ? updated : c)));
  };

  const removeCondition = (index: number) => {
    setConditions((prev) => prev.filter((_, i) => i !== index));
  };

  const updateAction = (index: number, updated: RuleAction) => {
    setActions((prev) => prev.map((a, i) => (i === index ? updated : a)));
  };

  const removeAction = (index: number) => {
    setActions((prev) => prev.filter((_, i) => i !== index));
  };

  const handleTest = () => {
    const ruleData: ImportRule = {
      id: rule?.id,
      name,
      is_active: isActive,
      logic,
      conditions,
      actions,
      priority,
    };
    testMutation.mutate(ruleData);
  };

  const handleSave = () => {
    if (!name.trim()) {
      toast({
        title: 'Fehler',
        description: 'Bitte geben Sie einen Namen ein',
        variant: 'destructive',
      });
      return;
    }
    if (conditions.length === 0) {
      toast({
        title: 'Fehler',
        description: 'Mindestens eine Bedingung erforderlich',
        variant: 'destructive',
      });
      return;
    }
    if (actions.length === 0) {
      toast({
        title: 'Fehler',
        description: 'Mindestens eine Aktion erforderlich',
        variant: 'destructive',
      });
      return;
    }

    onSave({
      id: rule?.id,
      name,
      is_active: isActive,
      logic,
      conditions,
      actions,
      priority,
    });
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>{rule ? 'Regel bearbeiten' : 'Neue Import-Regel'}</CardTitle>
        <CardDescription>
          Definieren Sie Bedingungen und Aktionen für den automatischen Import.
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-6">
        {/* Name + Active */}
        <div className="flex items-center gap-4">
          <div className="flex-1 space-y-2">
            <Label>Regelname</Label>
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="z.B. Rechnungen von Lieferant X"
            />
          </div>
          <div className="flex items-center gap-2 pt-6">
            <Switch checked={isActive} onCheckedChange={setIsActive} />
            <Label className="text-sm">Aktiv</Label>
          </div>
        </div>

        <Separator />

        {/* Logic selector */}
        <div className="flex items-center gap-4">
          <Label className="text-sm font-medium">Verknüpfung:</Label>
          <div className="flex gap-2">
            <Button
              type="button"
              variant={logic === 'AND' ? 'default' : 'outline'}
              size="sm"
              onClick={() => setLogic('AND')}
            >
              UND
            </Button>
            <Button
              type="button"
              variant={logic === 'OR' ? 'default' : 'outline'}
              size="sm"
              onClick={() => setLogic('OR')}
            >
              ODER
            </Button>
          </div>
        </div>

        {/* Conditions */}
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <Label className="text-sm font-medium">Bedingungen</Label>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() =>
                setConditions((prev) => [
                  ...prev,
                  { field: '', operator: 'contains', value: '' },
                ])
              }
            >
              <Plus className="h-4 w-4 mr-1" />
              Bedingung hinzufügen
            </Button>
          </div>

          <div className="space-y-2">
            {conditions.map((cond, idx) => (
              <ConditionRow
                key={idx}
                condition={cond}
                onChange={(updated) => updateCondition(idx, updated)}
                onRemove={() => removeCondition(idx)}
                fields={availableFields}
                operators={availableOperators}
              />
            ))}
          </div>
        </div>

        <Separator />

        {/* Actions */}
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <Label className="text-sm font-medium">Aktionen</Label>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() =>
                setActions((prev) => [...prev, { type: 'set_folder', value: '' }])
              }
            >
              <Plus className="h-4 w-4 mr-1" />
              Aktion hinzufügen
            </Button>
          </div>

          <div className="space-y-2">
            {actions.map((act, idx) => (
              <ActionRow
                key={idx}
                action={act}
                onChange={(updated) => updateAction(idx, updated)}
                onRemove={() => removeAction(idx)}
                actionTypes={availableActions}
              />
            ))}
          </div>
        </div>

        <Separator />

        {/* Priority */}
        <div className="space-y-2">
          <Label>Priorität (0-100)</Label>
          <Input
            type="number"
            min={0}
            max={100}
            value={priority}
            onChange={(e) => setPriority(parseInt(e.target.value, 10) || 0)}
          />
          <p className="text-xs text-muted-foreground">
            Höhere Werte werden zuerst ausgeführt
          </p>
        </div>

        {/* Test button + results */}
        <div className="space-y-3">
          <Button
            type="button"
            variant="outline"
            onClick={handleTest}
            disabled={testMutation.isPending}
          >
            {testMutation.isPending ? (
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            ) : (
              <FlaskConical className="h-4 w-4 mr-2" />
            )}
            Mit Beispiel testen
          </Button>

          {testResult && (
            <div className="rounded-md border p-3 bg-muted/30">
              <div className="flex items-center gap-2 mb-2">
                <CheckCircle2 className="h-4 w-4 text-green-500" />
                <span className="text-sm font-medium">
                  {testResult.matches} Treffer
                </span>
              </div>
              {testResult.sample_results.length > 0 && (
                <div className="space-y-1">
                  {testResult.sample_results.map((result, idx) => (
                    <p key={idx} className="text-xs text-muted-foreground">
                      {result}
                    </p>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </CardContent>

      <CardFooter className="flex justify-between">
        <Button type="button" variant="outline" onClick={onCancel}>
          <X className="h-4 w-4 mr-2" />
          Abbrechen
        </Button>
        <Button onClick={handleSave} disabled={isSubmitting}>
          {isSubmitting ? (
            <Loader2 className="h-4 w-4 mr-2 animate-spin" />
          ) : (
            <Save className="h-4 w-4 mr-2" />
          )}
          Speichern
        </Button>
      </CardFooter>
    </Card>
  );
}
