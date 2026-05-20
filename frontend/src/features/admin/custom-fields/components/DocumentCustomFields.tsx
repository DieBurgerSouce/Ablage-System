/**
 * DocumentCustomFields
 *
 * Abschnitt im Dokument-Detail zum Anzeigen und Bearbeiten
 * benutzerdefinierter Feldwerte.
 */

import { useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Pencil, Save, X, Settings2 } from 'lucide-react'
import { toast } from '@/components/ui/use-toast'
import {
  useCustomFieldDefinitions,
  useDocumentFieldValues,
  useSetDocumentFieldValues,
} from '../api'
import { FIELD_TYPE_LABELS } from '../types'
import type { CustomFieldDefinitionResponse } from '../types'

interface DocumentCustomFieldsProps {
  documentId: string
  documentType?: string
}

export function DocumentCustomFields({
  documentId,
  documentType,
}: DocumentCustomFieldsProps) {
  const [isEditing, setIsEditing] = useState(false)
  const [editValues, setEditValues] = useState<
    Record<string, string | number | boolean | string[] | null>
  >({})

  const { data: defsData, isLoading: defsLoading } =
    useCustomFieldDefinitions({
      document_type: documentType,
    })
  const { data: valuesData, isLoading: valuesLoading } =
    useDocumentFieldValues(documentId)
  const setValuesMutation = useSetDocumentFieldValues()

  const definitions = defsData?.items ?? []
  const currentValues = valuesData?.values ?? {}

  const isLoading = defsLoading || valuesLoading

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Settings2 className="h-4 w-4" />
            Benutzerdefinierte Felder
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-8 w-full" />
          ))}
        </CardContent>
      </Card>
    )
  }

  if (definitions.length === 0) {
    return null
  }

  const startEditing = () => {
    setEditValues({ ...currentValues })
    setIsEditing(true)
  }

  const cancelEditing = () => {
    setIsEditing(false)
    setEditValues({})
  }

  const handleSave = async () => {
    // Nur geaenderte Werte senden
    const changedValues: Record<
      string,
      string | number | boolean | string[] | null
    > = {}
    for (const def of definitions) {
      const newVal = editValues[def.name]
      const oldVal = currentValues[def.name]
      if (newVal !== oldVal) {
        changedValues[def.name] = newVal ?? null
      }
    }

    if (Object.keys(changedValues).length === 0) {
      setIsEditing(false)
      return
    }

    try {
      await setValuesMutation.mutateAsync({
        documentId,
        data: { values: changedValues },
      })
      toast({
        title: 'Felder gespeichert',
        description: 'Die benutzerdefinierten Felder wurden aktualisiert.',
      })
      setIsEditing(false)
    } catch {
      toast({
        title: 'Fehler',
        description: 'Die Felder konnten nicht gespeichert werden.',
        variant: 'destructive',
      })
    }
  }

  const updateEditValue = (
    fieldName: string,
    value: string | number | boolean | string[] | null
  ) => {
    setEditValues((prev) => ({ ...prev, [fieldName]: value }))
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base flex items-center gap-2">
            <Settings2 className="h-4 w-4" />
            Benutzerdefinierte Felder
          </CardTitle>
          {isEditing ? (
            <div className="flex gap-2">
              <Button
                variant="ghost"
                size="sm"
                onClick={cancelEditing}
              >
                <X className="h-4 w-4 mr-1" />
                Abbrechen
              </Button>
              <Button
                size="sm"
                onClick={handleSave}
                disabled={setValuesMutation.isPending}
              >
                <Save className="h-4 w-4 mr-1" />
                Speichern
              </Button>
            </div>
          ) : (
            <Button variant="ghost" size="sm" onClick={startEditing}>
              <Pencil className="h-4 w-4 mr-1" />
              Bearbeiten
            </Button>
          )}
        </div>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          {definitions.map((def) => (
            <FieldRow
              key={def.id}
              definition={def}
              value={
                isEditing
                  ? editValues[def.name] ?? null
                  : currentValues[def.name] ?? null
              }
              isEditing={isEditing}
              onChange={(val) => updateEditValue(def.name, val)}
            />
          ))}
        </div>
      </CardContent>
    </Card>
  )
}

// =============================================================================
// FieldRow - Einzelnes Feld
// =============================================================================

interface FieldRowProps {
  definition: CustomFieldDefinitionResponse
  value: string | number | boolean | string[] | null
  isEditing: boolean
  onChange: (value: string | number | boolean | string[] | null) => void
}

function FieldRow({ definition, value, isEditing, onChange }: FieldRowProps) {
  if (isEditing) {
    return (
      <div className="space-y-1">
        <Label className="text-sm">
          {definition.label}
          {definition.required && (
            <span className="text-destructive ml-1">*</span>
          )}
        </Label>
        <FieldInput definition={definition} value={value} onChange={onChange} />
      </div>
    )
  }

  return (
    <div className="flex items-start justify-between py-1">
      <div className="text-sm text-muted-foreground">{definition.label}</div>
      <div className="text-sm font-medium text-right max-w-[60%]">
        <FieldDisplay definition={definition} value={value} />
      </div>
    </div>
  )
}

// =============================================================================
// FieldInput - Eingabefeld je nach Typ
// =============================================================================

interface FieldInputProps {
  definition: CustomFieldDefinitionResponse
  value: string | number | boolean | string[] | null
  onChange: (value: string | number | boolean | string[] | null) => void
}

function FieldInput({ definition, value, onChange }: FieldInputProps) {
  switch (definition.field_type) {
    case 'text':
      return (
        <Input
          value={(value as string) ?? ''}
          onChange={(e) => onChange(e.target.value || null)}
          placeholder={definition.description ?? undefined}
        />
      )

    case 'number':
      return (
        <Input
          type="number"
          value={value != null ? String(value) : ''}
          onChange={(e) =>
            onChange(e.target.value ? Number(e.target.value) : null)
          }
          placeholder={definition.description ?? undefined}
        />
      )

    case 'date':
      return (
        <Input
          type="date"
          value={(value as string) ?? ''}
          onChange={(e) => onChange(e.target.value || null)}
        />
      )

    case 'boolean':
      return (
        <div className="flex items-center gap-2 pt-1">
          <Switch
            checked={(value as boolean) ?? false}
            onCheckedChange={(checked) => onChange(checked)}
          />
          <span className="text-sm text-muted-foreground">
            {value ? 'Ja' : 'Nein'}
          </span>
        </div>
      )

    case 'dropdown':
      return (
        <Select
          value={(value as string) ?? 'none'}
          onValueChange={(v) => onChange(v === 'none' ? null : v)}
        >
          <SelectTrigger>
            <SelectValue placeholder="Bitte waehlen" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="none">-- Keine Auswahl --</SelectItem>
            {(definition.dropdown_options ?? []).map((opt) => (
              <SelectItem key={opt.value} value={opt.value}>
                {opt.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      )

    case 'multi_select': {
      const selected = Array.isArray(value) ? value : []
      const options = definition.dropdown_options ?? []
      return (
        <div className="flex flex-wrap gap-2">
          {options.map((opt) => {
            const isSelected = selected.includes(opt.value)
            return (
              <Badge
                key={opt.value}
                variant={isSelected ? 'default' : 'outline'}
                className="cursor-pointer"
                onClick={() => {
                  const newSelected = isSelected
                    ? selected.filter((v) => v !== opt.value)
                    : [...selected, opt.value]
                  onChange(newSelected.length > 0 ? newSelected : null)
                }}
              >
                {opt.label}
              </Badge>
            )
          })}
        </div>
      )
    }

    case 'lookup':
      return (
        <Input
          value={(value as string) ?? ''}
          onChange={(e) => onChange(e.target.value || null)}
          placeholder="UUID eingeben"
          className="font-mono"
        />
      )

    default:
      return (
        <Input
          value={(value as string) ?? ''}
          onChange={(e) => onChange(e.target.value || null)}
        />
      )
  }
}

// =============================================================================
// FieldDisplay - Anzeigefeld je nach Typ
// =============================================================================

interface FieldDisplayProps {
  definition: CustomFieldDefinitionResponse
  value: string | number | boolean | string[] | null
}

function FieldDisplay({ definition, value }: FieldDisplayProps) {
  if (value == null) {
    return <span className="text-muted-foreground italic">--</span>
  }

  switch (definition.field_type) {
    case 'boolean':
      return (
        <Badge variant={value ? 'default' : 'secondary'}>
          {value ? 'Ja' : 'Nein'}
        </Badge>
      )

    case 'dropdown': {
      const opt = (definition.dropdown_options ?? []).find(
        (o) => o.value === value
      )
      return <span>{opt?.label ?? String(value)}</span>
    }

    case 'multi_select': {
      const vals = Array.isArray(value) ? value : []
      const options = definition.dropdown_options ?? []
      return (
        <div className="flex flex-wrap gap-1 justify-end">
          {vals.map((v) => {
            const opt = options.find((o) => o.value === v)
            return (
              <Badge key={v} variant="secondary">
                {opt?.label ?? v}
              </Badge>
            )
          })}
        </div>
      )
    }

    case 'date':
      return (
        <span>
          {new Date(value as string).toLocaleDateString('de-DE')}
        </span>
      )

    case 'number':
      return (
        <span>
          {typeof value === 'number'
            ? value.toLocaleString('de-DE')
            : String(value)}
        </span>
      )

    default:
      return <span>{String(value)}</span>
  }
}
