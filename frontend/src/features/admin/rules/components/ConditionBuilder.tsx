/**
 * ConditionBuilder Component
 *
 * Visueller Builder für Regel-Bedingungen.
 */

import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Switch } from '@/components/ui/switch'
import { Plus, Trash2, GitBranch } from 'lucide-react'
import type { RuleCondition, SimpleCondition, CompositeCondition, ConditionOperator } from '../types'

// Vordefinierte Felder für Dokumentkontext
const COMMON_FIELDS = [
  { value: 'amount', label: 'Betrag' },
  { value: 'document_type', label: 'Dokumenttyp' },
  { value: 'status', label: 'Status' },
  { value: 'tags', label: 'Tags' },
  { value: 'supplier.name', label: 'Lieferant' },
  { value: 'supplier.is_new', label: 'Neuer Lieferant' },
  { value: 'confidence', label: 'OCR-Confidence' },
  { value: 'created_at', label: 'Erstellt am' },
  { value: 'invoice_date', label: 'Rechnungsdatum' },
  { value: 'due_date', label: 'Fälligkeitsdatum' },
]

const OPERATOR_OPTIONS: { value: ConditionOperator; label: string; group: string }[] = [
  // Vergleich
  { value: '==', label: 'ist gleich', group: 'Vergleich' },
  { value: '!=', label: 'ist ungleich', group: 'Vergleich' },
  { value: '>', label: 'größer als', group: 'Vergleich' },
  { value: '>=', label: 'größer oder gleich', group: 'Vergleich' },
  { value: '<', label: 'kleiner als', group: 'Vergleich' },
  { value: '<=', label: 'kleiner oder gleich', group: 'Vergleich' },
  // String
  { value: 'contains', label: 'enthält', group: 'Text' },
  { value: 'not_contains', label: 'enthält nicht', group: 'Text' },
  { value: 'starts_with', label: 'beginnt mit', group: 'Text' },
  { value: 'ends_with', label: 'endet mit', group: 'Text' },
  { value: 'matches', label: 'Regex-Match', group: 'Text' },
  // Collection
  { value: 'in', label: 'in Liste', group: 'Liste' },
  { value: 'not_in', label: 'nicht in Liste', group: 'Liste' },
  { value: 'is_empty', label: 'ist leer', group: 'Liste' },
  { value: 'is_not_empty', label: 'ist nicht leer', group: 'Liste' },
  // Existence
  { value: 'is_null', label: 'ist null', group: 'Existenz' },
  { value: 'is_not_null', label: 'existiert', group: 'Existenz' },
  // Zeit
  { value: 'in_period', label: 'in Periode', group: 'Zeit' },
  { value: 'before', label: 'vor Datum', group: 'Zeit' },
  { value: 'after', label: 'nach Datum', group: 'Zeit' },
  { value: 'between', label: 'zwischen', group: 'Zeit' },
  // Tags
  { value: 'has_tag', label: 'hat Tag', group: 'Tags' },
  { value: 'has_any_tag', label: 'hat einen der Tags', group: 'Tags' },
  { value: 'has_all_tags', label: 'hat alle Tags', group: 'Tags' },
]

// Operatoren die keinen Wert brauchen
const NO_VALUE_OPERATORS: ConditionOperator[] = ['is_empty', 'is_not_empty', 'is_null', 'is_not_null']

interface SimpleConditionEditorProps {
  condition: SimpleCondition
  onChange: (condition: SimpleCondition) => void
  onRemove: () => void
}

function SimpleConditionEditor({
  condition,
  onChange,
  onRemove,
}: SimpleConditionEditorProps) {
  const needsValue = !NO_VALUE_OPERATORS.includes(condition.op)

  return (
    <Card className="border-l-4 border-l-blue-500">
      <CardContent className="p-4">
        <div className="grid grid-cols-12 gap-2 items-end">
          {/* Feld */}
          <div className="col-span-3">
            <Label className="text-xs">Feld</Label>
            <Select
              value={condition.field || 'amount'}
              onValueChange={(value) => onChange({ ...condition, field: value })}
            >
              <SelectTrigger>
                <SelectValue placeholder="Feld wählen" />
              </SelectTrigger>
              <SelectContent>
                {COMMON_FIELDS.map((field) => (
                  <SelectItem key={field.value} value={field.value}>
                    {field.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Operator */}
          <div className="col-span-3">
            <Label className="text-xs">Operator</Label>
            <Select
              value={condition.op}
              onValueChange={(value) =>
                onChange({ ...condition, op: value as ConditionOperator })
              }
            >
              <SelectTrigger>
                <SelectValue placeholder="Operator" />
              </SelectTrigger>
              <SelectContent>
                {OPERATOR_OPTIONS.map((op) => (
                  <SelectItem key={op.value} value={op.value}>
                    {op.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Wert */}
          <div className="col-span-4">
            <Label className="text-xs">Wert</Label>
            <Input
              value={needsValue ? String(condition.value ?? '') : ''}
              onChange={(e) => {
                const val = e.target.value
                // Versuche Zahl zu parsen
                const numVal = parseFloat(val)
                onChange({
                  ...condition,
                  value: !isNaN(numVal) && val.trim() !== '' ? numVal : val,
                })
              }}
              placeholder={needsValue ? 'Wert eingeben' : '(nicht benötigt)'}
              disabled={!needsValue}
            />
          </div>

          {/* Negieren Toggle */}
          <div className="col-span-1 flex flex-col items-center">
            <Label className="text-xs">NOT</Label>
            <Switch
              checked={condition.negate ?? false}
              onCheckedChange={(checked) => onChange({ ...condition, negate: checked })}
            />
          </div>

          {/* Löschen */}
          <div className="col-span-1">
            <Button variant="ghost" size="icon" onClick={onRemove}>
              <Trash2 className="h-4 w-4 text-destructive" />
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

interface ConditionGroupEditorProps {
  type: 'and' | 'or'
  conditions: Array<SimpleCondition | CompositeCondition>
  onChange: (conditions: Array<SimpleCondition | CompositeCondition>) => void
  onChangeType: (type: 'and' | 'or') => void
  onRemove?: () => void
  depth?: number
}

function ConditionGroupEditor({
  type,
  conditions,
  onChange,
  onChangeType,
  onRemove,
  depth = 0,
}: ConditionGroupEditorProps) {
  const addSimpleCondition = () => {
    const newCondition: SimpleCondition = {
      field: 'amount',
      op: '>',
      value: 0,
    }
    onChange([...conditions, newCondition])
  }

  const addGroup = () => {
    const newGroup: CompositeCondition = {
      and: [{ field: 'amount', op: '>', value: 0 }],
    }
    onChange([...conditions, newGroup])
  }

  const updateCondition = (index: number, updated: SimpleCondition | CompositeCondition) => {
    const newConditions = [...conditions]
    newConditions[index] = updated
    onChange(newConditions)
  }

  const removeCondition = (index: number) => {
    const newConditions = conditions.filter((_, i) => i !== index)
    onChange(newConditions)
  }

  const isSimple = (c: SimpleCondition | CompositeCondition): c is SimpleCondition => {
    return 'field' in c && 'op' in c
  }

  const bgColors = ['bg-muted/30', 'bg-muted/50', 'bg-muted/70']
  const bgColor = bgColors[Math.min(depth, bgColors.length - 1)]

  return (
    <div className={`p-4 rounded-lg ${bgColor} space-y-3`}>
      <div className="flex items-center gap-2">
        <Badge
          variant="outline"
          className={`cursor-pointer ${
            type === 'and'
              ? 'bg-green-100 border-green-500 text-green-700'
              : 'bg-orange-100 border-orange-500 text-orange-700'
          }`}
          onClick={() => onChangeType(type === 'and' ? 'or' : 'and')}
        >
          <GitBranch className="h-3 w-3 mr-1" />
          {type === 'and' ? 'UND (alle müssen zutreffen)' : 'ODER (eine muss zutreffen)'}
        </Badge>

        <span className="text-xs text-muted-foreground">
          Klicken zum Wechseln
        </span>

        {onRemove && depth > 0 && (
          <Button variant="ghost" size="sm" onClick={onRemove} className="ml-auto">
            <Trash2 className="h-4 w-4" />
          </Button>
        )}
      </div>

      <div className="space-y-2">
        {conditions.map((condition, index) => (
          <div key={index}>
            {isSimple(condition) ? (
              <SimpleConditionEditor
                condition={condition}
                onChange={(updated) => updateCondition(index, updated)}
                onRemove={() => removeCondition(index)}
              />
            ) : (
              <ConditionGroupEditor
                type={'and' in condition ? 'and' : 'or'}
                conditions={
                  ('and' in condition ? condition.and : condition.or) ?? []
                }
                onChange={(newConditions) => {
                  const updated: CompositeCondition =
                    'and' in condition
                      ? { and: newConditions }
                      : { or: newConditions }
                  updateCondition(index, updated)
                }}
                onChangeType={(newType) => {
                  const currentConditions =
                    ('and' in condition ? condition.and : condition.or) ?? []
                  const updated: CompositeCondition =
                    newType === 'and'
                      ? { and: currentConditions }
                      : { or: currentConditions }
                  updateCondition(index, updated)
                }}
                onRemove={() => removeCondition(index)}
                depth={depth + 1}
              />
            )}
          </div>
        ))}
      </div>

      <div className="flex gap-2">
        <Button variant="outline" size="sm" onClick={addSimpleCondition}>
          <Plus className="h-4 w-4 mr-1" />
          Bedingung
        </Button>
        {depth < 2 && (
          <Button variant="outline" size="sm" onClick={addGroup}>
            <GitBranch className="h-4 w-4 mr-1" />
            Gruppe
          </Button>
        )}
      </div>
    </div>
  )
}

interface ConditionBuilderProps {
  condition: RuleCondition
  onChange: (condition: RuleCondition) => void
}

export function ConditionBuilder({ condition, onChange }: ConditionBuilderProps) {
  // Normalisiere zu CompositeCondition für den Editor
  const isSimple = (c: RuleCondition): c is SimpleCondition => {
    return 'field' in c && 'op' in c
  }

  // Wenn es eine einfache Bedingung ist, wrappe sie in AND
  const normalizedCondition: CompositeCondition = isSimple(condition)
    ? { and: [condition] }
    : condition

  const type: 'and' | 'or' = 'and' in normalizedCondition ? 'and' : 'or'
  const conditions = ('and' in normalizedCondition
    ? normalizedCondition.and
    : normalizedCondition.or) ?? []

  const handleChange = (newConditions: Array<SimpleCondition | CompositeCondition>) => {
    // Wenn nur eine einfache Bedingung, gib sie direkt zurück
    if (newConditions.length === 1 && isSimple(newConditions[0])) {
      onChange(newConditions[0])
    } else {
      onChange(type === 'and' ? { and: newConditions } : { or: newConditions })
    }
  }

  const handleTypeChange = (newType: 'and' | 'or') => {
    onChange(newType === 'and' ? { and: conditions } : { or: conditions })
  }

  return (
    <div className="space-y-4">
      <div className="text-sm text-muted-foreground">
        Definieren Sie die Bedingungen, unter denen diese Regel ausgeführt wird.
      </div>

      <ConditionGroupEditor
        type={type}
        conditions={conditions}
        onChange={handleChange}
        onChangeType={handleTypeChange}
      />
    </div>
  )
}
