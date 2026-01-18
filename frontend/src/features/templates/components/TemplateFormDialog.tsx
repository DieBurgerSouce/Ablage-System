/**
 * TemplateFormDialog - Dialog zum Erstellen/Bearbeiten von Vorlagen
 *
 * Features:
 * - Formular fuer alle Vorlagen-Felder
 * - Variablen-Editor
 * - Template-Code Editor mit Syntax-Highlighting (Jinja2)
 * - Vorschau-Funktion
 */

import { useState, useEffect } from 'react';
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Switch } from '@/components/ui/switch';
import { Loader2, Plus, Trash2 } from 'lucide-react';
import type {
  Template,
  TemplateCreateRequest,
  TemplateUpdateRequest,
  TemplateVariable,
} from '../types/template-types';
import {
  TemplateCategory,
  TemplateOutputFormat,
  VariableType,
  TEMPLATE_CATEGORY_LABELS,
  OUTPUT_FORMAT_LABELS,
  VARIABLE_TYPE_LABELS,
} from '../types/template-types';

interface TemplateFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  template?: Template | null;
  onSubmit: (data: TemplateCreateRequest | TemplateUpdateRequest) => Promise<void>;
  isSubmitting?: boolean;
}

const defaultMargins = { top: 20, right: 15, bottom: 20, left: 15 };

export function TemplateFormDialog({
  open,
  onOpenChange,
  template,
  onSubmit,
  isSubmitting = false,
}: TemplateFormDialogProps) {
  const isEditing = !!template;
  const [activeTab, setActiveTab] = useState('general');

  // Form state
  const [name, setName] = useState('');
  const [code, setCode] = useState('');
  const [description, setDescription] = useState('');
  const [category, setCategory] = useState<TemplateCategory>(TemplateCategory.OTHER);
  const [outputFormat, setOutputFormat] = useState<TemplateOutputFormat>(TemplateOutputFormat.PDF);
  const [content, setContent] = useState('');
  const [headerContent, setHeaderContent] = useState('');
  const [footerContent, setFooterContent] = useState('');
  const [cssStyles, setCssStyles] = useState('');
  const [pageSize, setPageSize] = useState('A4');
  const [orientation, setOrientation] = useState('portrait');
  const [margins, setMargins] = useState(defaultMargins);
  const [variables, setVariables] = useState<TemplateVariable[]>([]);
  const [tags, setTags] = useState<string[]>([]);
  const [isDefault, setIsDefault] = useState(false);
  const [createNewVersion, setCreateNewVersion] = useState(false);

  // Reset form when dialog opens/closes or template changes
  useEffect(() => {
    if (open && template) {
      setName(template.name);
      setCode(template.code);
      setDescription(template.description || '');
      setCategory(template.category);
      setOutputFormat(template.output_format);
      setContent(template.content);
      setHeaderContent(template.header_content || '');
      setFooterContent(template.footer_content || '');
      setCssStyles(template.css_styles || '');
      setPageSize(template.page_size);
      setOrientation(template.orientation);
      setMargins(template.margins || defaultMargins);
      setVariables(template.variables || []);
      setTags(template.tags || []);
      setIsDefault(template.is_default);
      setCreateNewVersion(false);
    } else if (open && !template) {
      // Reset to defaults for new template
      setName('');
      setCode('');
      setDescription('');
      setCategory(TemplateCategory.OTHER);
      setOutputFormat(TemplateOutputFormat.PDF);
      setContent('');
      setHeaderContent('');
      setFooterContent('');
      setCssStyles('');
      setPageSize('A4');
      setOrientation('portrait');
      setMargins(defaultMargins);
      setVariables([]);
      setTags([]);
      setIsDefault(false);
      setCreateNewVersion(false);
    }
    setActiveTab('general');
  }, [open, template]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    const data: TemplateCreateRequest | TemplateUpdateRequest = {
      name,
      code: isEditing ? undefined : code, // Code can't be changed
      description: description || undefined,
      category,
      output_format: outputFormat,
      content,
      header_content: headerContent || undefined,
      footer_content: footerContent || undefined,
      css_styles: cssStyles || undefined,
      page_size: pageSize,
      orientation,
      margins,
      variables,
      tags,
      is_default: isDefault,
    };

    if (isEditing) {
      (data as TemplateUpdateRequest).create_new_version = createNewVersion;
    }

    await onSubmit(data);
  };

  const addVariable = () => {
    setVariables([
      ...variables,
      {
        name: '',
        type: VariableType.TEXT,
        label: '',
        required: false,
      },
    ]);
  };

  const updateVariable = (index: number, field: keyof TemplateVariable, value: unknown) => {
    const newVariables = [...variables];
    newVariables[index] = { ...newVariables[index], [field]: value };
    setVariables(newVariables);
  };

  const removeVariable = (index: number) => {
    setVariables(variables.filter((_, i) => i !== index));
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>
              {isEditing ? 'Vorlage bearbeiten' : 'Neue Vorlage erstellen'}
            </DialogTitle>
            <DialogDescription>
              {isEditing
                ? 'Bearbeiten Sie die Vorlage. Sie koennen optional eine neue Version erstellen.'
                : 'Erstellen Sie eine neue Dokumentvorlage mit Jinja2-Syntax.'}
            </DialogDescription>
          </DialogHeader>

          <Tabs value={activeTab} onValueChange={setActiveTab} className="mt-4">
            <TabsList className="grid w-full grid-cols-4">
              <TabsTrigger value="general">Allgemein</TabsTrigger>
              <TabsTrigger value="content">Inhalt</TabsTrigger>
              <TabsTrigger value="variables">Variablen</TabsTrigger>
              <TabsTrigger value="layout">Layout</TabsTrigger>
            </TabsList>

            {/* General Tab */}
            <TabsContent value="general" className="space-y-4 mt-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="name">Name *</Label>
                  <Input
                    id="name"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="z.B. Standard-Rechnung"
                    required
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="code">Code * {isEditing && '(nicht aenderbar)'}</Label>
                  <Input
                    id="code"
                    value={code}
                    onChange={(e) => setCode(e.target.value.toUpperCase().replace(/[^A-Z0-9_-]/g, ''))}
                    placeholder="z.B. INV-STANDARD"
                    disabled={isEditing}
                    required={!isEditing}
                  />
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="description">Beschreibung</Label>
                <Textarea
                  id="description"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Kurze Beschreibung der Vorlage..."
                  rows={2}
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="category">Kategorie</Label>
                  <Select value={category} onValueChange={(v) => setCategory(v as TemplateCategory)}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {Object.entries(TEMPLATE_CATEGORY_LABELS).map(([value, label]) => (
                        <SelectItem key={value} value={value}>
                          {label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="outputFormat">Ausgabeformat</Label>
                  <Select
                    value={outputFormat}
                    onValueChange={(v) => setOutputFormat(v as TemplateOutputFormat)}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {Object.entries(OUTPUT_FORMAT_LABELS).map(([value, label]) => (
                        <SelectItem key={value} value={value}>
                          {label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <div className="flex items-center justify-between">
                <div className="space-y-0.5">
                  <Label>Als Standard setzen</Label>
                  <p className="text-sm text-muted-foreground">
                    Diese Vorlage als Standard fuer die Kategorie verwenden
                  </p>
                </div>
                <Switch checked={isDefault} onCheckedChange={setIsDefault} />
              </div>

              {isEditing && (
                <div className="flex items-center justify-between border-t pt-4">
                  <div className="space-y-0.5">
                    <Label>Neue Version erstellen</Label>
                    <p className="text-sm text-muted-foreground">
                      Erstellt eine neue Version anstatt die aktuelle zu ueberschreiben
                    </p>
                  </div>
                  <Switch checked={createNewVersion} onCheckedChange={setCreateNewVersion} />
                </div>
              )}
            </TabsContent>

            {/* Content Tab */}
            <TabsContent value="content" className="space-y-4 mt-4">
              <div className="space-y-2">
                <Label htmlFor="content">Template-Inhalt (Jinja2) *</Label>
                <Textarea
                  id="content"
                  value={content}
                  onChange={(e) => setContent(e.target.value)}
                  placeholder={'<h1>{{ titel }}</h1>\n<p>Sehr geehrte/r {{ kunde.name }},</p>\n...'}
                  className="font-mono text-sm"
                  rows={12}
                  required
                />
                <p className="text-xs text-muted-foreground">
                  Verwenden Sie {'{{ variable }}'} fuer Platzhalter, {'{% if %}...{% endif %}'} fuer
                  Bedingungen
                </p>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="headerContent">Kopfzeile (optional)</Label>
                  <Textarea
                    id="headerContent"
                    value={headerContent}
                    onChange={(e) => setHeaderContent(e.target.value)}
                    className="font-mono text-sm"
                    rows={4}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="footerContent">Fusszeile (optional)</Label>
                  <Textarea
                    id="footerContent"
                    value={footerContent}
                    onChange={(e) => setFooterContent(e.target.value)}
                    className="font-mono text-sm"
                    rows={4}
                  />
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="cssStyles">CSS-Styles (optional)</Label>
                <Textarea
                  id="cssStyles"
                  value={cssStyles}
                  onChange={(e) => setCssStyles(e.target.value)}
                  placeholder="body { font-family: Arial, sans-serif; }"
                  className="font-mono text-sm"
                  rows={4}
                />
              </div>
            </TabsContent>

            {/* Variables Tab */}
            <TabsContent value="variables" className="space-y-4 mt-4">
              <div className="flex items-center justify-between">
                <Label>Template-Variablen</Label>
                <Button type="button" variant="outline" size="sm" onClick={addVariable}>
                  <Plus className="h-4 w-4 mr-1" />
                  Variable hinzufuegen
                </Button>
              </div>

              {variables.length === 0 ? (
                <div className="text-center py-8 text-muted-foreground">
                  <p>Keine Variablen definiert</p>
                  <p className="text-sm">
                    Variablen werden in Templates mit {'{{ variable_name }}'} verwendet
                  </p>
                </div>
              ) : (
                <div className="space-y-4">
                  {variables.map((variable, index) => (
                    <div key={index} className="p-4 border rounded-lg space-y-3">
                      <div className="flex items-center justify-between">
                        <span className="font-medium text-sm">Variable #{index + 1}</span>
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          onClick={() => removeVariable(index)}
                        >
                          <Trash2 className="h-4 w-4 text-destructive" />
                        </Button>
                      </div>
                      <div className="grid grid-cols-3 gap-3">
                        <div className="space-y-1">
                          <Label className="text-xs">Name (technisch)</Label>
                          <Input
                            value={variable.name}
                            onChange={(e) =>
                              updateVariable(
                                index,
                                'name',
                                e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, '')
                              )
                            }
                            placeholder="kunde_name"
                          />
                        </div>
                        <div className="space-y-1">
                          <Label className="text-xs">Anzeigename</Label>
                          <Input
                            value={variable.label}
                            onChange={(e) => updateVariable(index, 'label', e.target.value)}
                            placeholder="Kundenname"
                          />
                        </div>
                        <div className="space-y-1">
                          <Label className="text-xs">Typ</Label>
                          <Select
                            value={variable.type}
                            onValueChange={(v) => updateVariable(index, 'type', v)}
                          >
                            <SelectTrigger>
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              {Object.entries(VARIABLE_TYPE_LABELS).map(([value, label]) => (
                                <SelectItem key={value} value={value}>
                                  {label}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        </div>
                      </div>
                      <div className="flex items-center gap-4">
                        <div className="flex items-center gap-2">
                          <Switch
                            checked={variable.required}
                            onCheckedChange={(v) => updateVariable(index, 'required', v)}
                          />
                          <Label className="text-sm">Pflichtfeld</Label>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </TabsContent>

            {/* Layout Tab */}
            <TabsContent value="layout" className="space-y-4 mt-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="pageSize">Seitengroesse</Label>
                  <Select value={pageSize} onValueChange={setPageSize}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="A4">A4</SelectItem>
                      <SelectItem value="A5">A5</SelectItem>
                      <SelectItem value="Letter">Letter</SelectItem>
                      <SelectItem value="Legal">Legal</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="orientation">Ausrichtung</Label>
                  <Select value={orientation} onValueChange={setOrientation}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="portrait">Hochformat</SelectItem>
                      <SelectItem value="landscape">Querformat</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <div className="space-y-2">
                <Label>Seitenraender (mm)</Label>
                <div className="grid grid-cols-4 gap-4">
                  <div className="space-y-1">
                    <Label className="text-xs">Oben</Label>
                    <Input
                      type="number"
                      value={margins.top}
                      onChange={(e) => setMargins({ ...margins, top: parseInt(e.target.value) || 0 })}
                    />
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs">Rechts</Label>
                    <Input
                      type="number"
                      value={margins.right}
                      onChange={(e) =>
                        setMargins({ ...margins, right: parseInt(e.target.value) || 0 })
                      }
                    />
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs">Unten</Label>
                    <Input
                      type="number"
                      value={margins.bottom}
                      onChange={(e) =>
                        setMargins({ ...margins, bottom: parseInt(e.target.value) || 0 })
                      }
                    />
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs">Links</Label>
                    <Input
                      type="number"
                      value={margins.left}
                      onChange={(e) =>
                        setMargins({ ...margins, left: parseInt(e.target.value) || 0 })
                      }
                    />
                  </div>
                </div>
              </div>
            </TabsContent>
          </Tabs>

          <DialogFooter className="mt-6">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Abbrechen
            </Button>
            <Button type="submit" disabled={isSubmitting || !name || !content}>
              {isSubmitting && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              {isEditing ? 'Speichern' : 'Erstellen'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
