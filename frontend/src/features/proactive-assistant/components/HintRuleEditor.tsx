// Hint Rule Editor - Form for editing hint generation rules

import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { Save, X } from 'lucide-react';
import {
  UI_LABELS,
  type HintRule,
  type HintPriority,
  type HintCategory,
} from '../types/proactive-assistant-types';
import { useUpdateRuleMutation } from '../hooks/use-proactive-assistant-queries';

interface HintRuleEditorProps {
  rule: HintRule;
  onCancel?: () => void;
}

export function HintRuleEditor({ rule, onCancel }: HintRuleEditorProps) {
  const [name, setName] = useState(rule.name);
  const [enabled, setEnabled] = useState(rule.enabled);
  const [priority, setPriority] = useState<HintPriority>(rule.priority);
  const [category, setCategory] = useState<HintCategory>(rule.category);
  const [template, setTemplate] = useState(rule.template);

  const updateMutation = useUpdateRuleMutation();

  const handleSave = () => {
    updateMutation.mutate({
      ruleId: rule.ruleId,
      data: {
        name,
        enabled,
        priority,
        template,
      },
    });
  };

  const hasChanges =
    name !== rule.name ||
    enabled !== rule.enabled ||
    priority !== rule.priority ||
    template !== rule.template;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{rule.name}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Name */}
        <div className="space-y-2">
          <Label htmlFor={`rule-name-${rule.ruleId}`}>Regelname</Label>
          <Input
            id={`rule-name-${rule.ruleId}`}
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Regelname eingeben"
          />
        </div>

        {/* Enabled Toggle */}
        <div className="flex items-center justify-between">
          <Label htmlFor={`rule-enabled-${rule.ruleId}`}>Aktiv</Label>
          <Switch
            id={`rule-enabled-${rule.ruleId}`}
            checked={enabled}
            onCheckedChange={setEnabled}
          />
        </div>

        {/* Category */}
        <div className="space-y-2">
          <Label htmlFor={`rule-category-${rule.ruleId}`}>Kategorie</Label>
          <Select value={category} onValueChange={(v) => setCategory(v as HintCategory)}>
            <SelectTrigger id={`rule-category-${rule.ruleId}`}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="fristen">
                {UI_LABELS.categories.fristen}
              </SelectItem>
              <SelectItem value="anomalien">
                {UI_LABELS.categories.anomalien}
              </SelectItem>
              <SelectItem value="optimierung">
                {UI_LABELS.categories.optimierung}
              </SelectItem>
            </SelectContent>
          </Select>
        </div>

        {/* Priority */}
        <div className="space-y-2">
          <Label htmlFor={`rule-priority-${rule.ruleId}`}>Priorität</Label>
          <Select value={priority} onValueChange={(v) => setPriority(v as HintPriority)}>
            <SelectTrigger id={`rule-priority-${rule.ruleId}`}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="low">
                {UI_LABELS.priorities.low}
              </SelectItem>
              <SelectItem value="medium">
                {UI_LABELS.priorities.medium}
              </SelectItem>
              <SelectItem value="high">
                {UI_LABELS.priorities.high}
              </SelectItem>
              <SelectItem value="critical">
                {UI_LABELS.priorities.critical}
              </SelectItem>
            </SelectContent>
          </Select>
        </div>

        {/* Template */}
        <div className="space-y-2">
          <Label htmlFor={`rule-template-${rule.ruleId}`}>
            Hinweis-Vorlage
          </Label>
          <Textarea
            id={`rule-template-${rule.ruleId}`}
            value={template}
            onChange={(e) => setTemplate(e.target.value)}
            placeholder="Vorlage für den Hinweistext"
            rows={4}
          />
          <p className="text-xs text-muted-foreground">
            Verwenden Sie Platzhalter wie {'{entity_name}'}, {'{amount}'}, usw.
          </p>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2 pt-4 border-t">
          <Button
            onClick={handleSave}
            disabled={!hasChanges || updateMutation.isPending}
          >
            <Save className="h-4 w-4 mr-2" />
            Speichern
          </Button>
          {onCancel && (
            <Button
              variant="outline"
              onClick={onCancel}
              disabled={updateMutation.isPending}
            >
              <X className="h-4 w-4 mr-2" />
              Abbrechen
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
