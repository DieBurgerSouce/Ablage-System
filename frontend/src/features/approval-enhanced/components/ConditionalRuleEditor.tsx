/**
 * ConditionalRuleEditor Component
 * Form for creating/editing conditional approval rules
 */

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';
import { Plus, Trash2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { type Condition, type Action, CONDITION_OPERATORS, CONDITION_FIELDS, ACTION_TYPES, type ConditionField, type ConditionOperator, type ActionType } from '../types/approval-enhanced-types';

interface ConditionalRuleEditorProps {
  initialName?: string;
  initialConditions?: Condition[];
  initialActions?: Action[];
  initialPriority?: number;
  initialIsActive?: boolean;
  onSave: (data: {
    name: string;
    conditions: Record<string, unknown>;
    actions: Record<string, unknown>;
    priority: number;
    is_active: boolean;
  }) => void;
  onCancel: () => void;
  isLoading?: boolean;
}

export function ConditionalRuleEditor({
  initialName = '',
  initialConditions = [],
  initialActions = [],
  initialPriority = 0,
  initialIsActive = true,
  onSave,
  onCancel,
  isLoading = false,
}: ConditionalRuleEditorProps) {
  const [name, setName] = useState(initialName);
  const [conditions, setConditions] = useState<Condition[]>(
    initialConditions.length > 0 ? initialConditions : [{ field: 'amount', operator: 'greater_than', value: '' }]
  );
  const [actions, setActions] = useState<Action[]>(
    initialActions.length > 0 ? initialActions : [{ type: 'add_approver', parameters: {} }]
  );
  const [priority, setPriority] = useState(initialPriority);
  const [isActive, setIsActive] = useState(initialIsActive);

  const addCondition = () => {
    setConditions([...conditions, { field: 'amount', operator: 'equals', value: '' }]);
  };

  const removeCondition = (index: number) => {
    if (conditions.length > 1) {
      setConditions(conditions.filter((_, i) => i !== index));
    }
  };

  const updateCondition = (index: number, updates: Partial<Condition>) => {
    setConditions(
      conditions.map((cond, i) => (i === index ? { ...cond, ...updates } : cond))
    );
  };

  const addAction = () => {
    setActions([...actions, { type: 'notify', parameters: {} }]);
  };

  const removeAction = (index: number) => {
    if (actions.length > 1) {
      setActions(actions.filter((_, i) => i !== index));
    }
  };

  const updateAction = (index: number, type: ActionType) => {
    setActions(
      actions.map((act, i) => (i === index ? { ...act, type } : act))
    );
  };

  const handleSubmit = () => {
    const conditionsObj = conditions.reduce((acc, cond, idx) => {
      acc[`condition_${idx}`] = cond;
      return acc;
    }, {} as Record<string, unknown>);

    const actionsObj = actions.reduce((acc, act, idx) => {
      acc[`action_${idx}`] = act;
      return acc;
    }, {} as Record<string, unknown>);

    onSave({
      name,
      conditions: conditionsObj,
      actions: actionsObj,
      priority,
      is_active: isActive,
    });
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          {initialName ? 'Regel bearbeiten' : 'Neue Regel erstellen'}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Name */}
        <div className="space-y-2">
          <Label htmlFor="rule-name">Regelname</Label>
          <Input
            id="rule-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="z.B. Hohe Beträge erfordern zusätzliche Genehmigung"
          />
        </div>

        <Separator />

        {/* Conditions */}
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <Label>Bedingungen</Label>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={addCondition}
            >
              <Plus className="h-4 w-4 mr-2" />
              Bedingung hinzufügen
            </Button>
          </div>

          {conditions.map((condition, index) => (
            <Card key={index} className="p-3">
              <div className="flex items-center gap-2">
                <span className="text-sm text-muted-foreground">Wenn</span>
                <Select
                  value={condition.field}
                  onValueChange={(value) =>
                    updateCondition(index, { field: value as ConditionField })
                  }
                >
                  <SelectTrigger className="w-[160px]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {Object.entries(CONDITION_FIELDS).map(([key, label]) => (
                      <SelectItem key={key} value={key}>
                        {label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>

                <Select
                  value={condition.operator}
                  onValueChange={(value) =>
                    updateCondition(index, { operator: value as ConditionOperator })
                  }
                >
                  <SelectTrigger className="w-[140px]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {Object.entries(CONDITION_OPERATORS).map(([key, label]) => (
                      <SelectItem key={key} value={key}>
                        {label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>

                <Input
                  value={condition.value}
                  onChange={(e) => updateCondition(index, { value: e.target.value })}
                  placeholder="Wert eingeben"
                  className="flex-1"
                />

                {conditions.length > 1 && (
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    onClick={() => removeCondition(index)}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                )}
              </div>
            </Card>
          ))}
        </div>

        <Separator />

        {/* Actions */}
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <Label>Dann (Aktionen)</Label>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={addAction}
            >
              <Plus className="h-4 w-4 mr-2" />
              Aktion hinzufügen
            </Button>
          </div>

          {actions.map((action, index) => (
            <Card key={index} className="p-3">
              <div className="flex items-center gap-2">
                <span className="text-sm text-muted-foreground">Dann</span>
                <Select
                  value={action.type}
                  onValueChange={(value) => updateAction(index, value as ActionType)}
                >
                  <SelectTrigger className="flex-1">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {Object.entries(ACTION_TYPES).map(([key, label]) => (
                      <SelectItem key={key} value={key}>
                        {label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>

                {actions.length > 1 && (
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    onClick={() => removeAction(index)}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                )}
              </div>
            </Card>
          ))}
        </div>

        <Separator />

        {/* Priority & Active */}
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-2">
            <Label htmlFor="priority">Priorität</Label>
            <Input
              id="priority"
              type="number"
              value={priority}
              onChange={(e) => setPriority(Number(e.target.value))}
              min={0}
              max={100}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="is-active">Aktiv</Label>
            <div className="flex items-center h-10">
              <Switch
                id="is-active"
                checked={isActive}
                onCheckedChange={setIsActive}
              />
              <span className={cn('ml-2 text-sm', isActive ? 'text-green-600' : 'text-muted-foreground')}>
                {isActive ? 'Aktiviert' : 'Deaktiviert'}
              </span>
            </div>
          </div>
        </div>

        <Separator />

        {/* Actions */}
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={onCancel} disabled={isLoading}>
            Abbrechen
          </Button>
          <Button onClick={handleSubmit} disabled={isLoading || !name.trim()}>
            {isLoading ? 'Speichert...' : 'Speichern'}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
