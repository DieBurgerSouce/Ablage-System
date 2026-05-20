/**
 * FieldDefinitionDialog
 *
 * Dialog zum Erstellen und Bearbeiten von benutzerdefinierten Felddefinitionen.
 */

import { useState, useEffect } from 'react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Switch } from '@/components/ui/switch'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Loader2, Plus, X } from 'lucide-react'
import { toast } from '@/components/ui/use-toast'
import { useCreateFieldDefinition, useUpdateFieldDefinition } from '../api'
import type {
  CustomFieldDefinitionResponse,
  CustomFieldDefinitionCreate,
  FieldType,
  DropdownOption,
} from '../types'
import {
  FIELD_TYPE_LABELS,
  DOCUMENT_TYPE_OPTIONS,
  LOOKUP_ENTITY_OPTIONS,
} from '../types'

interface FieldDefinitionDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  definition: CustomFieldDefinitionResponse | null
}

export function FieldDefinitionDialog({
  open,
  onOpenChange,
  definition,
}: FieldDefinitionDialogProps) {
  const isEdit = !!definition

  // Form State
  const [name, setName] = useState('')
  const [label, setLabel] = useState('')
  const [description, setDescription] = useState('')
  const [fieldType, setFieldType] = useState<FieldType>('text')
  const [documentType, setDocumentType] = useState<string>('all')
  const [required, setRequired] = useState(false)
  const [defaultValue, setDefaultValue] = useState('')
  const [sortOrder, setSortOrder] = useState(0)
  const [isSearchable, setIsSearchable] = useState(true)
  const [isFilterable, setIsFilterable] = useState(true)
  const [lookupEntity, setLookupEntity] = useState<string>('business_entity')

  // Validation Rules
  const [minValue, setMinValue] = useState('')
  const [maxValue, setMaxValue] = useState('')
  const [minLength, setMinLength] = useState('')
  const [maxLength, setMaxLength] = useState('')
  const [pattern, setPattern] = useState('')

  // Dropdown Options
  const [dropdownOptions, setDropdownOptions] = useState<DropdownOption[]>([])

  const createMutation = useCreateFieldDefinition()
  const updateMutation = useUpdateFieldDefinition()

  // Reset form
  useEffect(() => {
    if (open) {
      if (definition) {
        setName(definition.name)
        setLabel(definition.label)
        setDescription(definition.description ?? '')
        setFieldType(definition.field_type)
        setDocumentType(definition.document_type ?? 'all')
        setRequired(definition.required)
        setDefaultValue(definition.default_value ?? '')
        setSortOrder(definition.sort_order)
        setIsSearchable(definition.is_searchable)
        setIsFilterable(definition.is_filterable)
        setLookupEntity(definition.lookup_entity ?? 'business_entity')

        // Validation rules
        const rules = definition.validation_rules ?? {}
        setMinValue(rules.min_value != null ? String(rules.min_value) : '')
        setMaxValue(rules.max_value != null ? String(rules.max_value) : '')
        setMinLength(rules.min_length != null ? String(rules.min_length) : '')
        setMaxLength(rules.max_length != null ? String(rules.max_length) : '')
        setPattern((rules.pattern as string) ?? '')

        // Dropdown options
        setDropdownOptions(definition.dropdown_options ?? [])
      } else {
        setName('')
        setLabel('')
        setDescription('')
        setFieldType('text')
        setDocumentType('all')
        setRequired(false)
        setDefaultValue('')
        setSortOrder(0)
        setIsSearchable(true)
        setIsFilterable(true)
        setLookupEntity('business_entity')
        setMinValue('')
        setMaxValue('')
        setMinLength('')
        setMaxLength('')
        setPattern('')
        setDropdownOptions([])
      }
    }
  }, [open, definition])

  const addDropdownOption = () => {
    setDropdownOptions([...dropdownOptions, { value: '', label: '' }])
  }

  const removeDropdownOption = (index: number) => {
    setDropdownOptions(dropdownOptions.filter((_, i) => i !== index))
  }

  const updateDropdownOption = (
    index: number,
    field: 'value' | 'label',
    val: string
  ) => {
    const updated = [...dropdownOptions]
    updated[index] = { ...updated[index], [field]: val }
    setDropdownOptions(updated)
  }

  const needsDropdownOptions =
    fieldType === 'dropdown' || fieldType === 'multi_select'
  const needsLookupEntity = fieldType === 'lookup'
  const needsTextValidation = fieldType === 'text'
  const needsNumberValidation = fieldType === 'number'

  const handleSave = async () => {
    // Validierung
    if (!name.trim()) {
      toast({
        title: 'Fehler',
        description: 'Bitte geben Sie einen Feldnamen ein.',
        variant: 'destructive',
      })
      return
    }

    if (!label.trim()) {
      toast({
        title: 'Fehler',
        description: 'Bitte geben Sie ein Anzeige-Label ein.',
        variant: 'destructive',
      })
      return
    }

    if (needsDropdownOptions && dropdownOptions.length === 0) {
      toast({
        title: 'Fehler',
        description: 'Bitte fuegen Sie mindestens eine Option hinzu.',
        variant: 'destructive',
      })
      return
    }

    // Validation Rules zusammenstellen
    const validationRules: Record<string, number | string | null> = {}
    if (needsNumberValidation) {
      if (minValue) validationRules.min_value = Number(minValue)
      if (maxValue) validationRules.max_value = Number(maxValue)
    }
    if (needsTextValidation) {
      if (minLength) validationRules.min_length = Number(minLength)
      if (maxLength) validationRules.max_length = Number(maxLength)
      if (pattern) validationRules.pattern = pattern
    }

    try {
      if (isEdit) {
        await updateMutation.mutateAsync({
          id: definition.id,
          data: {
            label: label.trim(),
            description: description.trim() || undefined,
            required,
            default_value: defaultValue.trim() || undefined,
            validation_rules:
              Object.keys(validationRules).length > 0
                ? validationRules
                : undefined,
            dropdown_options: needsDropdownOptions
              ? dropdownOptions
              : undefined,
            sort_order: sortOrder,
            is_searchable: isSearchable,
            is_filterable: isFilterable,
          },
        })
        toast({
          title: 'Feld aktualisiert',
          description: `"${label}" wurde gespeichert.`,
        })
      } else {
        const createData: CustomFieldDefinitionCreate = {
          name: name.trim(),
          label: label.trim(),
          description: description.trim() || undefined,
          field_type: fieldType,
          document_type: documentType === 'all' ? undefined : documentType,
          required,
          default_value: defaultValue.trim() || undefined,
          validation_rules:
            Object.keys(validationRules).length > 0
              ? validationRules
              : undefined,
          dropdown_options: needsDropdownOptions ? dropdownOptions : undefined,
          lookup_entity: needsLookupEntity ? lookupEntity : undefined,
          sort_order: sortOrder,
          is_searchable: isSearchable,
          is_filterable: isFilterable,
        }
        await createMutation.mutateAsync(createData)
        toast({
          title: 'Feld erstellt',
          description: `"${label}" wurde erstellt.`,
        })
      }
      onOpenChange(false)
    } catch {
      toast({
        title: 'Fehler',
        description: 'Das Feld konnte nicht gespeichert werden.',
        variant: 'destructive',
      })
    }
  }

  const isPending = createMutation.isPending || updateMutation.isPending

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[90vh] flex flex-col">
        <DialogHeader>
          <DialogTitle>
            {isEdit ? 'Feld bearbeiten' : 'Neues Feld erstellen'}
          </DialogTitle>
          <DialogDescription>
            Definieren Sie ein benutzerdefiniertes Feld fuer Ihre Dokumente.
          </DialogDescription>
        </DialogHeader>

        <ScrollArea className="flex-1 pr-4">
          <div className="space-y-6 py-4">
            {/* Grundlagen */}
            <div className="space-y-4">
              <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider">
                Grundlagen
              </h3>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="cf-name">Feldname (intern) *</Label>
                  <Input
                    id="cf-name"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="z.B. lieferanten_nr"
                    className="font-mono"
                    disabled={isEdit}
                  />
                  <p className="text-xs text-muted-foreground">
                    Kleinbuchstaben, Ziffern, Unterstriche
                  </p>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="cf-label">Anzeige-Label *</Label>
                  <Input
                    id="cf-label"
                    value={label}
                    onChange={(e) => setLabel(e.target.value)}
                    placeholder="z.B. Lieferanten-Nr."
                  />
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="cf-description">Beschreibung</Label>
                <Textarea
                  id="cf-description"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Optionale Beschreibung des Feldes"
                  rows={2}
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label>Feldtyp *</Label>
                  <Select
                    value={fieldType}
                    onValueChange={(v) => setFieldType(v as FieldType)}
                    disabled={isEdit}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {(
                        Object.entries(FIELD_TYPE_LABELS) as [
                          FieldType,
                          string,
                        ][]
                      ).map(([value, ftLabel]) => (
                        <SelectItem key={value} value={value}>
                          {ftLabel}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-2">
                  <Label>Dokumenttyp</Label>
                  <Select value={documentType} onValueChange={setDocumentType}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">Alle Dokumenttypen</SelectItem>
                      {DOCUMENT_TYPE_OPTIONS.map((opt) => (
                        <SelectItem key={opt.value} value={opt.value}>
                          {opt.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </div>

            {/* Dropdown/Multi-Select Optionen */}
            {needsDropdownOptions && (
              <div className="space-y-4">
                <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider">
                  Optionen
                </h3>

                {dropdownOptions.map((option, index) => (
                  <div key={option.value || index} className="flex items-center gap-2">
                    <Input
                      value={option.value}
                      onChange={(e) =>
                        updateDropdownOption(index, 'value', e.target.value)
                      }
                      placeholder="Wert"
                      className="font-mono flex-1"
                    />
                    <Input
                      value={option.label}
                      onChange={(e) =>
                        updateDropdownOption(index, 'label', e.target.value)
                      }
                      placeholder="Anzeige-Label"
                      className="flex-1"
                    />
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => removeDropdownOption(index)}
                    >
                      <X className="h-4 w-4" />
                    </Button>
                  </div>
                ))}

                <Button
                  variant="outline"
                  size="sm"
                  onClick={addDropdownOption}
                >
                  <Plus className="h-4 w-4 mr-2" />
                  Option hinzufuegen
                </Button>
              </div>
            )}

            {/* Lookup Entity */}
            {needsLookupEntity && (
              <div className="space-y-4">
                <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider">
                  Verweis-Konfiguration
                </h3>
                <div className="space-y-2">
                  <Label>Ziel-Entitaet</Label>
                  <Select
                    value={lookupEntity}
                    onValueChange={setLookupEntity}
                    disabled={isEdit}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {LOOKUP_ENTITY_OPTIONS.map((opt) => (
                        <SelectItem key={opt.value} value={opt.value}>
                          {opt.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
            )}

            {/* Validierung */}
            {(needsTextValidation || needsNumberValidation) && (
              <div className="space-y-4">
                <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider">
                  Validierung
                </h3>

                {needsNumberValidation && (
                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <Label>Minimalwert</Label>
                      <Input
                        type="number"
                        value={minValue}
                        onChange={(e) => setMinValue(e.target.value)}
                        placeholder="Optional"
                      />
                    </div>
                    <div className="space-y-2">
                      <Label>Maximalwert</Label>
                      <Input
                        type="number"
                        value={maxValue}
                        onChange={(e) => setMaxValue(e.target.value)}
                        placeholder="Optional"
                      />
                    </div>
                  </div>
                )}

                {needsTextValidation && (
                  <>
                    <div className="grid grid-cols-2 gap-4">
                      <div className="space-y-2">
                        <Label>Min. Laenge</Label>
                        <Input
                          type="number"
                          value={minLength}
                          onChange={(e) => setMinLength(e.target.value)}
                          placeholder="Optional"
                          min={0}
                        />
                      </div>
                      <div className="space-y-2">
                        <Label>Max. Laenge</Label>
                        <Input
                          type="number"
                          value={maxLength}
                          onChange={(e) => setMaxLength(e.target.value)}
                          placeholder="Optional"
                          min={1}
                        />
                      </div>
                    </div>
                    <div className="space-y-2">
                      <Label>Regex-Muster</Label>
                      <Input
                        value={pattern}
                        onChange={(e) => setPattern(e.target.value)}
                        placeholder="z.B. ^[A-Z]{2}-\\d{4}$"
                        className="font-mono"
                      />
                    </div>
                  </>
                )}
              </div>
            )}

            {/* Optionen */}
            <div className="space-y-4">
              <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider">
                Optionen
              </h3>

              <div className="space-y-2">
                <Label>Standardwert</Label>
                <Input
                  value={defaultValue}
                  onChange={(e) => setDefaultValue(e.target.value)}
                  placeholder="Optional"
                />
              </div>

              <div className="space-y-2">
                <Label>Sortierreihenfolge</Label>
                <Input
                  type="number"
                  value={sortOrder}
                  onChange={(e) => setSortOrder(Number(e.target.value))}
                  min={0}
                />
              </div>

              <div className="flex flex-wrap items-center gap-8 py-2">
                <div className="flex items-center gap-2">
                  <Switch checked={required} onCheckedChange={setRequired} />
                  <Label>Pflichtfeld</Label>
                </div>

                <div className="flex items-center gap-2">
                  <Switch
                    checked={isSearchable}
                    onCheckedChange={setIsSearchable}
                  />
                  <Label>Suchbar</Label>
                </div>

                <div className="flex items-center gap-2">
                  <Switch
                    checked={isFilterable}
                    onCheckedChange={setIsFilterable}
                  />
                  <Label>Filterbar</Label>
                </div>
              </div>
            </div>
          </div>
        </ScrollArea>

        <DialogFooter className="border-t pt-4">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Abbrechen
          </Button>
          <Button onClick={handleSave} disabled={isPending}>
            {isPending && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
            {isEdit ? 'Speichern' : 'Erstellen'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
