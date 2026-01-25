/**
 * ActionBuilder Component
 *
 * Visueller Builder fuer Regel-Aktionen.
 */

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
import { Plus, Trash2, GripVertical } from 'lucide-react'
import type { RuleAction, ActionType } from '../types'

// Aktionstypen mit Gruppen und Parameter-Schema
const ACTION_OPTIONS: {
  value: ActionType
  label: string
  group: string
  params?: { key: string; label: string; type: 'text' | 'select'; options?: string[] }[]
}[] = [
  // Genehmigung
  {
    value: 'require_approval',
    label: 'Genehmigung erforderlich',
    group: 'Genehmigung',
    params: [{ key: 'approver_role', label: 'Genehmiger-Rolle', type: 'text' }],
  },
  { value: 'require_cfo_approval', label: 'CFO-Genehmigung', group: 'Genehmigung' },
  { value: 'require_manager_approval', label: 'Manager-Genehmigung', group: 'Genehmigung' },
  // Flags
  {
    value: 'set_flag',
    label: 'Flag setzen',
    group: 'Status',
    params: [{ key: 'flag', label: 'Flag-Name', type: 'text' }],
  },
  {
    value: 'remove_flag',
    label: 'Flag entfernen',
    group: 'Status',
    params: [{ key: 'flag', label: 'Flag-Name', type: 'text' }],
  },
  {
    value: 'set_status',
    label: 'Status setzen',
    group: 'Status',
    params: [
      {
        key: 'status',
        label: 'Status',
        type: 'select',
        options: ['pending', 'processing', 'approved', 'rejected', 'archived'],
      },
    ],
  },
  {
    value: 'set_priority',
    label: 'Prioritaet setzen',
    group: 'Status',
    params: [
      {
        key: 'priority',
        label: 'Prioritaet',
        type: 'select',
        options: ['low', 'normal', 'high', 'urgent'],
      },
    ],
  },
  // Benachrichtigung
  {
    value: 'notify_user',
    label: 'Benutzer benachrichtigen',
    group: 'Benachrichtigung',
    params: [
      { key: 'user_id', label: 'Benutzer-ID', type: 'text' },
      { key: 'message', label: 'Nachricht', type: 'text' },
    ],
  },
  {
    value: 'notify_team',
    label: 'Team benachrichtigen',
    group: 'Benachrichtigung',
    params: [
      { key: 'team_id', label: 'Team-ID', type: 'text' },
      { key: 'message', label: 'Nachricht', type: 'text' },
    ],
  },
  { value: 'notify_admin', label: 'Admin benachrichtigen', group: 'Benachrichtigung' },
  {
    value: 'send_email',
    label: 'E-Mail senden',
    group: 'Benachrichtigung',
    params: [
      { key: 'to', label: 'Empfaenger', type: 'text' },
      { key: 'subject', label: 'Betreff', type: 'text' },
    ],
  },
  {
    value: 'send_slack',
    label: 'Slack-Nachricht',
    group: 'Benachrichtigung',
    params: [
      { key: 'channel', label: 'Kanal', type: 'text' },
      { key: 'message', label: 'Nachricht', type: 'text' },
    ],
  },
  // Workflow
  {
    value: 'start_workflow',
    label: 'Workflow starten',
    group: 'Workflow',
    params: [{ key: 'workflow_id', label: 'Workflow-ID', type: 'text' }],
  },
  {
    value: 'assign_to_user',
    label: 'Benutzer zuweisen',
    group: 'Workflow',
    params: [{ key: 'user_id', label: 'Benutzer-ID', type: 'text' }],
  },
  {
    value: 'assign_to_team',
    label: 'Team zuweisen',
    group: 'Workflow',
    params: [{ key: 'team_id', label: 'Team-ID', type: 'text' }],
  },
  // Daten
  {
    value: 'set_field',
    label: 'Feld setzen',
    group: 'Daten',
    params: [
      { key: 'field', label: 'Feldname', type: 'text' },
      { key: 'value', label: 'Wert', type: 'text' },
    ],
  },
  {
    value: 'add_tag',
    label: 'Tag hinzufuegen',
    group: 'Daten',
    params: [{ key: 'tag', label: 'Tag', type: 'text' }],
  },
  {
    value: 'remove_tag',
    label: 'Tag entfernen',
    group: 'Daten',
    params: [{ key: 'tag', label: 'Tag', type: 'text' }],
  },
  {
    value: 'add_comment',
    label: 'Kommentar hinzufuegen',
    group: 'Daten',
    params: [{ key: 'comment', label: 'Kommentar', type: 'text' }],
  },
  // Verarbeitung
  {
    value: 'trigger_ocr',
    label: 'OCR ausloesen',
    group: 'Verarbeitung',
    params: [
      {
        key: 'backend',
        label: 'Backend',
        type: 'select',
        options: ['auto', 'deepseek', 'got_ocr', 'surya'],
      },
    ],
  },
  { value: 'flag_for_review', label: 'Zur Pruefung markieren', group: 'Verarbeitung' },
  { value: 'manual_review_required', label: 'Manuelle Pruefung', group: 'Verarbeitung' },
  { value: 'block_processing', label: 'Verarbeitung blockieren', group: 'Verarbeitung' },
  // Archivierung
  { value: 'flag_for_archive', label: 'Zur Archivierung markieren', group: 'Archivierung' },
  {
    value: 'flag_for_period_close',
    label: 'Fuer Periodenabschluss',
    group: 'Archivierung',
  },
]

interface ActionEditorProps {
  action: RuleAction
  onChange: (action: RuleAction) => void
  onRemove: () => void
}

function ActionEditor({ action, onChange, onRemove }: ActionEditorProps) {
  const actionConfig = ACTION_OPTIONS.find((a) => a.value === action.type)

  return (
    <Card className="border-l-4 border-l-green-500">
      <CardContent className="p-4">
        <div className="flex items-start gap-4">
          <div className="flex items-center h-9 text-muted-foreground cursor-move">
            <GripVertical className="h-4 w-4" />
          </div>

          <div className="flex-1 space-y-3">
            {/* Aktionstyp */}
            <div>
              <Label className="text-xs">Aktion</Label>
              <Select
                value={action.type}
                onValueChange={(value) =>
                  onChange({ type: value as ActionType, params: {} })
                }
              >
                <SelectTrigger>
                  <SelectValue placeholder="Aktion waehlen" />
                </SelectTrigger>
                <SelectContent>
                  {ACTION_OPTIONS.map((opt) => (
                    <SelectItem key={opt.value} value={opt.value}>
                      <span className="flex items-center gap-2">
                        <Badge variant="outline" className="text-xs">
                          {opt.group}
                        </Badge>
                        {opt.label}
                      </span>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Parameter */}
            {actionConfig?.params && actionConfig.params.length > 0 && (
              <div className="grid grid-cols-2 gap-3">
                {actionConfig.params.map((param) => (
                  <div key={param.key}>
                    <Label className="text-xs">{param.label}</Label>
                    {param.type === 'select' ? (
                      <Select
                        value={String(action.params[param.key] ?? '')}
                        onValueChange={(value) =>
                          onChange({
                            ...action,
                            params: { ...action.params, [param.key]: value },
                          })
                        }
                      >
                        <SelectTrigger>
                          <SelectValue placeholder="Waehlen..." />
                        </SelectTrigger>
                        <SelectContent>
                          {param.options?.map((opt) => (
                            <SelectItem key={opt} value={opt}>
                              {opt}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    ) : (
                      <Input
                        value={String(action.params[param.key] ?? '')}
                        onChange={(e) =>
                          onChange({
                            ...action,
                            params: { ...action.params, [param.key]: e.target.value },
                          })
                        }
                        placeholder={param.label}
                      />
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>

          <Button variant="ghost" size="icon" onClick={onRemove}>
            <Trash2 className="h-4 w-4 text-destructive" />
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

interface ActionBuilderProps {
  actions: RuleAction[]
  onChange: (actions: RuleAction[]) => void
  title?: string
  description?: string
}

export function ActionBuilder({
  actions,
  onChange,
  title = 'Aktionen',
  description = 'Diese Aktionen werden ausgefuehrt, wenn die Bedingungen erfuellt sind.',
}: ActionBuilderProps) {
  const addAction = () => {
    const newAction: RuleAction = {
      type: 'flag_for_review',
      params: {},
    }
    onChange([...actions, newAction])
  }

  const updateAction = (index: number, updated: RuleAction) => {
    const newActions = [...actions]
    newActions[index] = updated
    onChange(newActions)
  }

  const removeAction = (index: number) => {
    const newActions = actions.filter((_, i) => i !== index)
    onChange(newActions)
  }

  return (
    <div className="space-y-4">
      <div>
        <h4 className="font-medium">{title}</h4>
        <p className="text-sm text-muted-foreground">{description}</p>
      </div>

      <div className="space-y-2">
        {actions.map((action, index) => (
          <ActionEditor
            key={index}
            action={action}
            onChange={(updated) => updateAction(index, updated)}
            onRemove={() => removeAction(index)}
          />
        ))}
      </div>

      <Button variant="outline" onClick={addAction}>
        <Plus className="h-4 w-4 mr-2" />
        Aktion hinzufuegen
      </Button>
    </div>
  )
}
