/**
 * ReportBuilder Component
 *
 * Visueller Report-Builder mit Tabs für Datenquelle, Spalten, Filter, Charts.
 */

import { useState } from 'react';
import {
  BarChart3,
  Calendar,
  Columns,
  FileText,
  Filter,
  Loader2,
  PieChart,
  Save,
  Settings,
  X,
} from 'lucide-react';
import { FilterBuilder } from './FilterBuilder';
import { ChartBuilder } from './ChartBuilder';
import { ScheduleConfig } from './ScheduleConfig';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
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
import { Switch } from '@/components/ui/switch';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';
import {
  useDataSources,
  useFields,
  useCreateTemplate,
  useUpdateTemplate,
  useAddColumn,
  useDeleteColumn,
  usePreview,
} from '../hooks/useReports';
import type {
  ReportTemplate,
  ReportTemplateCreate,
  ReportType,
  DataSource,
  ExportFormat,
  FieldDefinition,
  DataType,
} from '../types';

interface ReportBuilderProps {
  template?: ReportTemplate;
  open: boolean;
  onClose: () => void;
}

const reportTypes: { value: ReportType; label: string }[] = [
  { value: 'document', label: 'Dokument-Report' },
  { value: 'finance', label: 'Finanz-Report' },
  { value: 'ocr', label: 'OCR-Qualitäts-Report' },
  { value: 'custom', label: 'Benutzerdefiniert' },
];

const formatOptions: { value: ExportFormat; label: string }[] = [
  { value: 'excel', label: 'Excel (.xlsx)' },
  { value: 'pdf', label: 'PDF' },
  { value: 'csv', label: 'CSV' },
  { value: 'json', label: 'JSON' },
];

const dataTypeLabels: Record<DataType, string> = {
  string: 'Text',
  number: 'Zahl',
  date: 'Datum',
  currency: 'Währung',
  boolean: 'Ja/Nein',
};


export function ReportBuilder({ template, open, onClose }: ReportBuilderProps) {
  const [activeTab, setActiveTab] = useState('basics');
  const [formData, setFormData] = useState<Partial<ReportTemplateCreate>>(() =>
    template
      ? {
          name: template.name,
          description: template.description || '',
          report_type: template.report_type,
          data_source: template.data_source,
          default_format: template.default_format,
          is_public: template.is_public,
          enable_aggregations: template.enable_aggregations,
          row_limit: template.row_limit || 1000,
        }
      : {
          name: '',
          description: '',
          report_type: 'document',
          data_source: 'documents',
          default_format: 'excel',
          is_public: false,
          enable_aggregations: false,
          row_limit: 1000,
        }
  );

  const [selectedFields, setSelectedFields] = useState<string[]>(
    () => template?.columns?.map((c) => c.field_path) || []
  );

  // Track template identity for resetting form
  const [prevTemplateId, setPrevTemplateId] = useState<string | undefined>(template?.id);
  if (template?.id !== prevTemplateId) {
    setPrevTemplateId(template?.id);
    if (template) {
      setFormData({
        name: template.name,
        description: template.description || '',
        report_type: template.report_type,
        data_source: template.data_source,
        default_format: template.default_format,
        is_public: template.is_public,
        enable_aggregations: template.enable_aggregations,
        row_limit: template.row_limit || 1000,
      });
      setSelectedFields(template.columns?.map((c) => c.field_path) || []);
    } else {
      setFormData({
        name: '',
        description: '',
        report_type: 'document',
        data_source: 'documents',
        default_format: 'excel',
        is_public: false,
        enable_aggregations: false,
        row_limit: 1000,
      });
      setSelectedFields([]);
    }
  }

  const { data: dataSources } = useDataSources();
  const { data: fields } = useFields(formData.data_source);
  const { data: preview, isLoading: previewLoading } = usePreview(
    template?.id,
    10
  );

  const createMutation = useCreateTemplate();
  const updateMutation = useUpdateTemplate();
  const addColumnMutation = useAddColumn();
  const deleteColumnMutation = useDeleteColumn();

  const isEditing = !!template;

  const handleSave = () => {
    if (!formData.name) {
      return;
    }

    if (isEditing && template) {
      updateMutation.mutate(
        {
          templateId: template.id,
          data: formData,
        },
        { onSuccess: onClose }
      );
    } else {
      createMutation.mutate(formData as ReportTemplateCreate, {
        onSuccess: onClose,
      });
    }
  };

  const handleFieldToggle = (field: FieldDefinition) => {
    if (!template) return;

    const isSelected = selectedFields.includes(field.path);

    if (isSelected) {
      // Spalte entfernen
      const column = template.columns?.find((c) => c.field_path === field.path);
      if (column) {
        deleteColumnMutation.mutate({
          templateId: template.id,
          columnId: column.id,
        });
        setSelectedFields((prev) => prev.filter((f) => f !== field.path));
      }
    } else {
      // Spalte hinzufügen
      addColumnMutation.mutate({
        templateId: template.id,
        data: {
          field_path: field.path,
          display_name: field.display_name,
          data_type: field.data_type,
        },
      });
      setSelectedFields((prev) => [...prev, field.path]);
    }
  };

  const isSaving = createMutation.isPending || updateMutation.isPending;

  // Gruppiere Felder nach Kategorie
  const groupedFields = fields?.reduce<Record<string, FieldDefinition[]>>((acc, field) => {
    const category = field.category || 'Allgemein';
    if (!acc[category]) {
      acc[category] = [];
    }
    acc[category].push(field);
    return acc;
  }, {});

  return (
    <Sheet open={open} onOpenChange={(isOpen) => !isOpen && onClose()}>
      <SheetContent className="w-full sm:max-w-2xl">
        <SheetHeader>
          <SheetTitle>
            {isEditing ? 'Report bearbeiten' : 'Neuer Report'}
          </SheetTitle>
          <SheetDescription>
            {isEditing
              ? 'Bearbeiten Sie die Konfiguration des Reports.'
              : 'Erstellen Sie einen neuen Report-Template.'}
          </SheetDescription>
        </SheetHeader>

        <Tabs value={activeTab} onValueChange={setActiveTab} className="mt-6">
          <TabsList className="grid w-full grid-cols-6">
            <TabsTrigger value="basics" className="gap-2">
              <Settings className="h-4 w-4" />
              <span className="hidden sm:inline">Basics</span>
            </TabsTrigger>
            <TabsTrigger value="columns" className="gap-2" disabled={!isEditing}>
              <Columns className="h-4 w-4" />
              <span className="hidden sm:inline">Spalten</span>
            </TabsTrigger>
            <TabsTrigger value="filters" className="gap-2" disabled={!isEditing}>
              <Filter className="h-4 w-4" />
              <span className="hidden sm:inline">Filter</span>
            </TabsTrigger>
            <TabsTrigger value="charts" className="gap-2" disabled={!isEditing}>
              <PieChart className="h-4 w-4" />
              <span className="hidden sm:inline">Charts</span>
            </TabsTrigger>
            <TabsTrigger value="schedule" className="gap-2" disabled={!isEditing}>
              <Calendar className="h-4 w-4" />
              <span className="hidden sm:inline">Zeitplan</span>
            </TabsTrigger>
            <TabsTrigger value="preview" className="gap-2" disabled={!isEditing}>
              <FileText className="h-4 w-4" />
              <span className="hidden sm:inline">Vorschau</span>
            </TabsTrigger>
          </TabsList>

          <ScrollArea className="h-[calc(100vh-280px)] mt-4">
            <TabsContent value="basics" className="space-y-4 pr-4">
              <div className="space-y-2">
                <Label htmlFor="name">Name *</Label>
                <Input
                  id="name"
                  value={formData.name}
                  onChange={(e) =>
                    setFormData((prev) => ({ ...prev, name: e.target.value }))
                  }
                  placeholder="z.B. Monatlicher Rechnungsreport"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="description">Beschreibung</Label>
                <Textarea
                  id="description"
                  value={formData.description}
                  onChange={(e) =>
                    setFormData((prev) => ({ ...prev, description: e.target.value }))
                  }
                  placeholder="Optionale Beschreibung des Reports..."
                  rows={3}
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label>Report-Typ</Label>
                  <Select
                    value={formData.report_type}
                    onValueChange={(value: ReportType) =>
                      setFormData((prev) => ({ ...prev, report_type: value }))
                    }
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {reportTypes.map((type) => (
                        <SelectItem key={type.value} value={type.value}>
                          {type.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-2">
                  <Label>Datenquelle</Label>
                  <Select
                    value={formData.data_source}
                    onValueChange={(value: DataSource) =>
                      setFormData((prev) => ({ ...prev, data_source: value }))
                    }
                    disabled={isEditing}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {dataSources?.map((source) => (
                        <SelectItem key={source.source} value={source.source}>
                          {source.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label>Standard-Format</Label>
                  <Select
                    value={formData.default_format}
                    onValueChange={(value: ExportFormat) =>
                      setFormData((prev) => ({ ...prev, default_format: value }))
                    }
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {formatOptions.map((format) => (
                        <SelectItem key={format.value} value={format.value}>
                          {format.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="rowLimit">Max. Zeilen</Label>
                  <Input
                    id="rowLimit"
                    type="number"
                    value={formData.row_limit}
                    onChange={(e) =>
                      setFormData((prev) => ({
                        ...prev,
                        row_limit: parseInt(e.target.value) || 1000,
                      }))
                    }
                    min={1}
                    max={100000}
                  />
                </div>
              </div>

              <Separator />

              <div className="flex items-center justify-between">
                <div className="space-y-0.5">
                  <Label>Öffentlich</Label>
                  <p className="text-xs text-muted-foreground">
                    Öffentliche Reports sind für alle Administratoren sichtbar.
                  </p>
                </div>
                <Switch
                  checked={formData.is_public}
                  onCheckedChange={(checked) =>
                    setFormData((prev) => ({ ...prev, is_public: checked }))
                  }
                />
              </div>

              <div className="flex items-center justify-between">
                <div className="space-y-0.5">
                  <Label>Aggregationen aktivieren</Label>
                  <p className="text-xs text-muted-foreground">
                    Ermöglicht Summen, Durchschnitte und andere Berechnungen.
                  </p>
                </div>
                <Switch
                  checked={formData.enable_aggregations}
                  onCheckedChange={(checked) =>
                    setFormData((prev) => ({ ...prev, enable_aggregations: checked }))
                  }
                />
              </div>
            </TabsContent>

            <TabsContent value="columns" className="space-y-4 pr-4">
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm">Verfügbare Felder</CardTitle>
                </CardHeader>
                <CardContent>
                  {groupedFields &&
                    Object.entries(groupedFields).map(([category, categoryFields]) => (
                      <div key={category} className="mb-4 last:mb-0">
                        <h4 className="text-xs font-medium text-muted-foreground uppercase mb-2">
                          {category}
                        </h4>
                        <div className="space-y-1">
                          {categoryFields.map((field) => {
                            const isSelected = selectedFields.includes(field.path);
                            return (
                              <div
                                key={field.path}
                                className={`flex items-center justify-between p-2 rounded-md cursor-pointer transition-colors ${
                                  isSelected
                                    ? 'bg-primary/10 border border-primary/20'
                                    : 'hover:bg-muted'
                                }`}
                                onClick={() => handleFieldToggle(field)}
                              >
                                <div className="flex-1 min-w-0">
                                  <p className="text-sm font-medium truncate">
                                    {field.display_name}
                                  </p>
                                  <p className="text-xs text-muted-foreground truncate">
                                    {field.path}
                                  </p>
                                </div>
                                <Badge variant="outline" className="ml-2 shrink-0">
                                  {dataTypeLabels[field.data_type]}
                                </Badge>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    ))}
                </CardContent>
              </Card>

              {selectedFields.length > 0 && (
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm">
                      Ausgewählte Spalten ({selectedFields.length})
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="flex flex-wrap gap-2">
                      {selectedFields.map((fieldPath) => {
                        const field = fields?.find((f) => f.path === fieldPath);
                        return (
                          <Badge
                            key={fieldPath}
                            variant="secondary"
                            className="gap-1 cursor-pointer"
                            onClick={() => field && handleFieldToggle(field)}
                          >
                            {field?.display_name || fieldPath}
                            <X className="h-3 w-3" />
                          </Badge>
                        );
                      })}
                    </div>
                  </CardContent>
                </Card>
              )}
            </TabsContent>

            <TabsContent value="filters" className="space-y-4 pr-4">
              {template ? (
                <FilterBuilder template={template} />
              ) : (
                <Card>
                  <CardContent className="pt-6">
                    <div className="text-center text-muted-foreground py-8">
                      <p>Bitte speichern Sie zuerst das Template.</p>
                    </div>
                  </CardContent>
                </Card>
              )}
            </TabsContent>

            <TabsContent value="charts" className="space-y-4 pr-4">
              {template ? (
                <ChartBuilder template={template} />
              ) : (
                <Card>
                  <CardContent className="pt-6">
                    <div className="text-center text-muted-foreground py-8">
                      <p>Bitte speichern Sie zuerst das Template.</p>
                    </div>
                  </CardContent>
                </Card>
              )}
            </TabsContent>

            <TabsContent value="schedule" className="space-y-4 pr-4">
              {template ? (
                <ScheduleConfig template={template} />
              ) : (
                <Card>
                  <CardContent className="pt-6">
                    <div className="text-center text-muted-foreground py-8">
                      <p>Bitte speichern Sie zuerst das Template.</p>
                    </div>
                  </CardContent>
                </Card>
              )}
            </TabsContent>

            <TabsContent value="preview" className="space-y-4 pr-4">
              {previewLoading ? (
                <Card>
                  <CardContent className="flex items-center justify-center py-12">
                    <Loader2 className="h-6 w-6 animate-spin" />
                  </CardContent>
                </Card>
              ) : preview ? (
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm">
                      Vorschau ({preview.preview_limit} von {preview.total_available} Zeilen)
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="border-b">
                            {preview.columns.map((col) => (
                              <th
                                key={col}
                                className="text-left py-2 px-3 font-medium whitespace-nowrap"
                              >
                                {col}
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {preview.data.map((row, idx) => (
                            <tr key={idx} className="border-b last:border-0">
                              {preview.columns.map((col) => (
                                <td
                                  key={col}
                                  className="py-2 px-3 whitespace-nowrap max-w-[200px] truncate"
                                >
                                  {String(row[col] ?? '-')}
                                </td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </CardContent>
                </Card>
              ) : (
                <Card>
                  <CardContent className="flex flex-col items-center justify-center py-12">
                    <BarChart3 className="h-12 w-12 text-muted-foreground mb-4" />
                    <p className="text-muted-foreground">
                      Keine Vorschau verfügbar.
                    </p>
                  </CardContent>
                </Card>
              )}
            </TabsContent>
          </ScrollArea>
        </Tabs>

        <div className="flex justify-end gap-2 mt-6 pt-4 border-t">
          <Button variant="outline" onClick={onClose}>
            Abbrechen
          </Button>
          <Button onClick={handleSave} disabled={!formData.name || isSaving}>
            {isSaving && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
            <Save className="h-4 w-4 mr-2" />
            {isEditing ? 'Speichern' : 'Erstellen'}
          </Button>
        </div>
      </SheetContent>
    </Sheet>
  );
}
