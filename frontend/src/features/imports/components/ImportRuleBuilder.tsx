/**
 * ImportRuleBuilder Component
 *
 * Visueller Rule Builder für Import-Regeln mit Bedingungen und Aktionen.
 */

import { useState } from 'react';
import { useForm, useFieldArray, Controller } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import {
  Plus,
  Trash2,
  Settings,
  FileText,
  Tag,
  Folder,
  Mail,
  AlertTriangle,
  Loader2,
  Save,
  X,
  ChevronDown,
  ChevronUp,
  GripVertical,
} from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import { Textarea } from '@/components/ui/textarea';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  CardFooter,
} from '@/components/ui/card';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import { Separator } from '@/components/ui/separator';
import { useToast } from '@/components/ui/use-toast';

import {
  useCreateImportRule,
  useUpdateImportRule,
  useRuleSchema,
} from '../hooks/use-import-queries';
import type {
  ImportRuleResponse,
  ImportRuleCreate,
  ImportRuleUpdate,
  RuleActions,
} from '../types/import-types';

// ==================== Schema ====================

const conditionSchema = z.object({
  field: z.string().min(1, 'Feld erforderlich'),
  operator: z.string().min(1, 'Operator erforderlich'),
  value: z.string().min(1, 'Wert erforderlich'),
});

const actionSchema = z.object({
  type: z.string().min(1, 'Aktionstyp erforderlich'),
  value: z.string().min(1, 'Wert erforderlich'),
});

const importRuleSchema = z.object({
  name: z.string().min(2, 'Name muss mindestens 2 Zeichen haben'),
  description: z.string().optional(),
  isActive: z.boolean(),
  priority: z.number().int().min(0).max(100),
  conditions: z.array(conditionSchema).min(1, 'Mindestens eine Bedingung erforderlich'),
  actions: z.array(actionSchema).min(1, 'Mindestens eine Aktion erforderlich'),
});

/** UI-Aktionszeilen <-> RuleActions-Objekt (Backend-Schema) */
function ruleActionsToRows(
  actions: ImportRuleResponse['actions']
): Array<{ type: string; value: string }> {
  const rows: Array<{ type: string; value: string }> = [];
  if (actions.setFolder) rows.push({ type: 'set_folder', value: actions.setFolder });
  if (actions.setDocumentType)
    rows.push({ type: 'set_document_type', value: actions.setDocumentType });
  if (actions.addTags?.length)
    rows.push({ type: 'add_tags', value: actions.addTags.join(',') });
  if (actions.setMetadata && Object.keys(actions.setMetadata).length > 0)
    rows.push({ type: 'set_metadata', value: JSON.stringify(actions.setMetadata) });
  if (actions.skipProcessing) rows.push({ type: 'skip_processing', value: 'ja' });
  if (actions.markAsUrgent) rows.push({ type: 'mark_as_urgent', value: 'ja' });
  return rows.length > 0 ? rows : [{ type: 'set_folder', value: '' }];
}

function rowsToRuleActions(
  rows: Array<{ type: string; value: string }>
): RuleActions {
  const actions: RuleActions = {};
  for (const row of rows) {
    switch (row.type) {
      case 'set_folder':
        actions.setFolder = row.value;
        break;
      case 'set_document_type':
        actions.setDocumentType = row.value;
        break;
      case 'add_tags':
        actions.addTags = row.value
          .split(',')
          .map((t) => t.trim())
          .filter((t) => t.length > 0);
        break;
      case 'set_metadata':
        try {
          actions.setMetadata = JSON.parse(row.value) as Record<string, string>;
        } catch {
          // Ungueltiges JSON wird ignoriert (Validierung erfolgt im Backend)
        }
        break;
      case 'skip_processing':
        actions.skipProcessing = true;
        break;
      case 'mark_as_urgent':
        actions.markAsUrgent = true;
        break;
    }
  }
  return actions;
}

type ImportRuleFormData = z.infer<typeof importRuleSchema>;

// ==================== Condition Row ====================

interface ConditionRowProps {
  index: number;
  control: any;
  remove: (index: number) => void;
  fields: string[];
  operators: Record<string, string[]>;
}

function ConditionRow({ index, control, remove, fields, operators }: ConditionRowProps) {
  const [selectedField, setSelectedField] = useState<string>('');

  return (
    <div className="flex items-start gap-2 p-3 rounded-lg border bg-muted/30">
      <GripVertical className="h-5 w-5 text-muted-foreground mt-2 cursor-move" />

      <div className="flex-1 grid grid-cols-3 gap-2">
        <Controller
          name={`conditions.${index}.field`}
          control={control}
          render={({ field }) => (
            <Select
              value={field.value}
              onValueChange={(value) => {
                field.onChange(value);
                setSelectedField(value);
              }}
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
          )}
        />

        <Controller
          name={`conditions.${index}.operator`}
          control={control}
          render={({ field }) => (
            <Select value={field.value} onValueChange={field.onChange}>
              <SelectTrigger>
                <SelectValue placeholder="Operator" />
              </SelectTrigger>
              <SelectContent>
                {(operators[selectedField] || operators['default'] || [
                  'equals',
                  'contains',
                  'starts_with',
                  'ends_with',
                  'matches_regex',
                ]).map((op) => (
                  <SelectItem key={op} value={op}>
                    {op === 'equals' && 'Gleich'}
                    {op === 'not_equals' && 'Ungleich'}
                    {op === 'contains' && 'Enthält'}
                    {op === 'not_contains' && 'Enthält nicht'}
                    {op === 'starts_with' && 'Beginnt mit'}
                    {op === 'ends_with' && 'Endet mit'}
                    {op === 'matches_regex' && 'Regex'}
                    {op === 'greater_than' && 'Größer als'}
                    {op === 'less_than' && 'Kleiner als'}
                    {!['equals', 'not_equals', 'contains', 'not_contains', 'starts_with', 'ends_with', 'matches_regex', 'greater_than', 'less_than'].includes(op) && op}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        />

        <Controller
          name={`conditions.${index}.value`}
          control={control}
          render={({ field }) => (
            <Input {...field} placeholder="Wert" />
          )}
        />
      </div>

      <Button
        type="button"
        variant="ghost"
        size="icon"
        className="text-destructive hover:text-destructive"
        onClick={() => remove(index)}
      >
        <Trash2 className="h-4 w-4" />
      </Button>
    </div>
  );
}

// ==================== Action Row ====================

interface ActionRowProps {
  index: number;
  control: any;
  remove: (index: number) => void;
  actionTypes: string[];
}

function ActionRow({ index, control, remove, actionTypes }: ActionRowProps) {
  return (
    <div className="flex items-start gap-2 p-3 rounded-lg border bg-muted/30">
      <GripVertical className="h-5 w-5 text-muted-foreground mt-2 cursor-move" />

      <div className="flex-1 grid grid-cols-2 gap-2">
        <Controller
          name={`actions.${index}.type`}
          control={control}
          render={({ field }) => (
            <Select value={field.value} onValueChange={field.onChange}>
              <SelectTrigger>
                <SelectValue placeholder="Aktion wählen" />
              </SelectTrigger>
              <SelectContent>
                {actionTypes.map((type) => (
                  <SelectItem key={type} value={type}>
                    {type === 'set_folder' && (
                      <span className="flex items-center gap-2">
                        <Folder className="h-4 w-4" />
                        Ordner setzen
                      </span>
                    )}
                    {type === 'add_tags' && (
                      <span className="flex items-center gap-2">
                        <Tag className="h-4 w-4" />
                        Tags hinzufügen
                      </span>
                    )}
                    {type === 'set_document_type' && (
                      <span className="flex items-center gap-2">
                        <FileText className="h-4 w-4" />
                        Dokumenttyp setzen
                      </span>
                    )}
                    {type === 'set_metadata' && (
                      <span className="flex items-center gap-2">
                        <Settings className="h-4 w-4" />
                        Metadaten setzen
                      </span>
                    )}
                    {type === 'skip_processing' && (
                      <span className="flex items-center gap-2">
                        <AlertTriangle className="h-4 w-4" />
                        Verarbeitung überspringen
                      </span>
                    )}
                    {type === 'mark_as_urgent' && (
                      <span className="flex items-center gap-2">
                        <Mail className="h-4 w-4" />
                        Als dringend markieren
                      </span>
                    )}
                    {!['set_folder', 'add_tags', 'set_document_type', 'set_metadata', 'skip_processing', 'mark_as_urgent'].includes(type) && type}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        />

        <Controller
          name={`actions.${index}.value`}
          control={control}
          render={({ field }) => (
            <Input {...field} placeholder="Wert" />
          )}
        />
      </div>

      <Button
        type="button"
        variant="ghost"
        size="icon"
        className="text-destructive hover:text-destructive"
        onClick={() => remove(index)}
      >
        <Trash2 className="h-4 w-4" />
      </Button>
    </div>
  );
}

// ==================== Main Component ====================

interface ImportRuleBuilderProps {
  rule?: ImportRuleResponse;
  onSave?: () => void;
  onCancel?: () => void;
}

export function ImportRuleBuilder({ rule, onSave, onCancel }: ImportRuleBuilderProps) {
  const { toast } = useToast();
  const [isAdvancedOpen, setIsAdvancedOpen] = useState(false);

  // Queries
  const ruleSchemaData = useRuleSchema();

  // Mutations
  const createRule = useCreateImportRule();
  const updateRule = useUpdateImportRule();

  // Form
  const form = useForm<ImportRuleFormData>({
    resolver: zodResolver(importRuleSchema),
    defaultValues: rule
      ? {
          name: rule.name,
          description: rule.description ?? '',
          isActive: rule.isActive,
          priority: rule.priority,
          conditions: rule.conditions.rules.map((r) => ({
            field: r.field,
            operator: r.operator,
            value: r.value ?? '',
          })),
          actions: ruleActionsToRows(rule.actions),
        }
      : {
          name: '',
          description: '',
          isActive: true,
          priority: 50,
          conditions: [{ field: '', operator: 'contains', value: '' }],
          actions: [{ type: 'set_folder', value: '' }],
        },
  });

  const {
    fields: conditionFields,
    append: appendCondition,
    remove: removeCondition,
  } = useFieldArray({
    control: form.control,
    name: 'conditions',
  });

  const {
    fields: actionFields,
    append: appendAction,
    remove: removeAction,
  } = useFieldArray({
    control: form.control,
    name: 'actions',
  });

  // Schema defaults
  const availableFields = ruleSchemaData.fields.length
    ? ruleSchemaData.fields.map((field) => field.name)
    : [
        'sender_email',
        'sender_name',
        'subject',
        'filename',
        'file_extension',
        'file_size',
        'folder_path',
      ];

  const availableOperators: Record<string, string[]> = {
    default: ruleSchemaData.operators.length
      ? ruleSchemaData.operators.map((op) => op.name)
      : ['equals', 'not_equals', 'contains', 'not_contains', 'starts_with', 'ends_with', 'matches_regex'],
    file_size: ['equals', 'greater_than', 'less_than'],
  };

  const availableActionTypes = ruleSchemaData.actions.length
    ? ruleSchemaData.actions.map((action) => action.name)
    : [
        'set_folder',
        'set_document_type',
        'add_tags',
        'set_metadata',
        'skip_processing',
        'mark_as_urgent',
      ];

  // Handlers
  const onSubmit = async (data: ImportRuleFormData) => {
    try {
      if (rule) {
        const updateData: ImportRuleUpdate = {
          name: data.name,
          description: data.description || undefined,
          isActive: data.isActive,
          priority: data.priority,
          conditions: { operator: 'AND', rules: data.conditions },
          actions: rowsToRuleActions(data.actions),
        };
        await updateRule.mutateAsync({ ruleId: rule.id, data: updateData });
        toast({
          title: 'Regel aktualisiert',
          description: `Die Regel "${data.name}" wurde erfolgreich aktualisiert.`,
        });
      } else {
        const createData: ImportRuleCreate = {
          name: data.name,
          description: data.description || undefined,
          isActive: data.isActive,
          priority: data.priority,
          conditions: { operator: 'AND', rules: data.conditions },
          actions: rowsToRuleActions(data.actions),
        };
        await createRule.mutateAsync(createData);
        toast({
          title: 'Regel erstellt',
          description: `Die Regel "${data.name}" wurde erfolgreich erstellt.`,
        });
      }
      onSave?.();
    } catch (err) {
      toast({
        title: 'Fehler',
        description: err instanceof Error ? err.message : 'Unbekannter Fehler',
        variant: 'destructive',
      });
    }
  };

  const isPending = createRule.isPending || updateRule.isPending;

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Settings className="h-5 w-5" />
              {rule ? 'Regel bearbeiten' : 'Neue Import-Regel'}
            </CardTitle>
            <CardDescription>
              Definieren Sie Bedingungen und Aktionen für den automatischen Import.
            </CardDescription>
          </CardHeader>

          <CardContent className="space-y-6">
            {/* Basic Info */}
            <div className="grid gap-4 md:grid-cols-2">
              <FormField
                control={form.control}
                name="name"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Name</FormLabel>
                    <FormControl>
                      <Input {...field} placeholder="z.B. Rechnungen von Lieferant X" />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

            </div>

            <FormField
              control={form.control}
              name="description"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Beschreibung (optional)</FormLabel>
                  <FormControl>
                    <Textarea
                      {...field}
                      placeholder="Kurze Beschreibung der Regel..."
                      rows={2}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <Separator />

            {/* Conditions */}
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-lg font-medium">Bedingungen</h3>
                  <p className="text-sm text-muted-foreground">
                    Alle Bedingungen müssen erfüllt sein (UND-Verknüpfung)
                  </p>
                </div>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() =>
                    appendCondition({ field: '', operator: 'contains', value: '' })
                  }
                >
                  <Plus className="mr-2 h-4 w-4" />
                  Bedingung
                </Button>
              </div>

              <div className="space-y-2">
                {conditionFields.map((field, index) => (
                  <ConditionRow
                    key={field.id}
                    index={index}
                    control={form.control}
                    remove={removeCondition}
                    fields={availableFields}
                    operators={availableOperators}
                  />
                ))}
              </div>

              {form.formState.errors.conditions?.message && (
                <p className="text-sm text-destructive">
                  {form.formState.errors.conditions.message}
                </p>
              )}
            </div>

            <Separator />

            {/* Actions */}
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-lg font-medium">Aktionen</h3>
                  <p className="text-sm text-muted-foreground">
                    Aktionen werden in der angegebenen Reihenfolge ausgeführt
                  </p>
                </div>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => appendAction({ type: 'set_folder', value: '' })}
                >
                  <Plus className="mr-2 h-4 w-4" />
                  Aktion
                </Button>
              </div>

              <div className="space-y-2">
                {actionFields.map((field, index) => (
                  <ActionRow
                    key={field.id}
                    index={index}
                    control={form.control}
                    remove={removeAction}
                    actionTypes={availableActionTypes}
                  />
                ))}
              </div>

              {form.formState.errors.actions?.message && (
                <p className="text-sm text-destructive">
                  {form.formState.errors.actions.message}
                </p>
              )}
            </div>

            <Separator />

            {/* Advanced Settings */}
            <Collapsible open={isAdvancedOpen} onOpenChange={setIsAdvancedOpen}>
              <CollapsibleTrigger asChild>
                <Button variant="ghost" className="w-full justify-between">
                  Erweiterte Einstellungen
                  {isAdvancedOpen ? (
                    <ChevronUp className="h-4 w-4" />
                  ) : (
                    <ChevronDown className="h-4 w-4" />
                  )}
                </Button>
              </CollapsibleTrigger>
              <CollapsibleContent className="pt-4 space-y-4">
                <div className="grid gap-4 md:grid-cols-2">
                  <FormField
                    control={form.control}
                    name="priority"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Priorität (0-100)</FormLabel>
                        <FormControl>
                          <Input
                            type="number"
                            min={0}
                            max={100}
                            {...field}
                            onChange={(e) => field.onChange(parseInt(e.target.value, 10))}
                          />
                        </FormControl>
                        <FormDescription>
                          Höhere Werte werden zuerst ausgeführt
                        </FormDescription>
                        <FormMessage />
                      </FormItem>
                    )}
                  />

                  <FormField
                    control={form.control}
                    name="isActive"
                    render={({ field }) => (
                      <FormItem className="flex flex-row items-center justify-between rounded-lg border p-4">
                        <div className="space-y-0.5">
                          <FormLabel className="text-base">Aktiv</FormLabel>
                          <FormDescription>
                            Regel wird auf neue Importe angewendet
                          </FormDescription>
                        </div>
                        <FormControl>
                          <Switch
                            checked={field.value}
                            onCheckedChange={field.onChange}
                          />
                        </FormControl>
                      </FormItem>
                    )}
                  />
                </div>

              </CollapsibleContent>
            </Collapsible>
          </CardContent>

          <CardFooter className="flex justify-between">
            {onCancel && (
              <Button type="button" variant="outline" onClick={onCancel}>
                <X className="mr-2 h-4 w-4" />
                Abbrechen
              </Button>
            )}
            <Button type="submit" disabled={isPending} className={onCancel ? '' : 'ml-auto'}>
              {isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Save className="mr-2 h-4 w-4" />
              )}
              {rule ? 'Aktualisieren' : 'Erstellen'}
            </Button>
          </CardFooter>
        </Card>
      </form>
    </Form>
  );
}
