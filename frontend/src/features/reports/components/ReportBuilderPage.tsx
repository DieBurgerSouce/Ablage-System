/**
 * ReportBuilderPage Component
 *
 * Volle Seite für den visuellen Report-Builder mit Multi-Step-Navigation:
 * 1. Datenquelle - Auswahl der Basis-Datenquelle
 * 2. Filter - Filter-Regeln hinzufügen
 * 3. Gruppierung & Aggregation - Felder gruppieren, Summen/Durchschnitte
 * 4. Darstellung - Diagramm-Typ wählen
 * 5. Zeitplan (optional) - Automatische Ausführung konfigurieren
 *
 * Rechts: Vorschau-Panel
 */

import { useState } from 'react';
import { useNavigate } from '@tanstack/react-router';
import {
  ArrowLeft,
  ArrowRight,
  BarChart3,
  Calendar,
  Check,
  Database,
  Filter,
  Group,
  Loader2,
  PieChart,
  Play,
  Save,
} from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Separator } from '@/components/ui/separator';
import { ReportPreview } from './ReportPreview';
import {
  useDataSources,
  useFields,
  useCreateTemplate,
  useExecuteReport,
} from '../hooks/useReports';
import type {
  DataSource,
  ReportType,
  ExportFormat,
  ChartType,
  AggregationType,
  FilterOperator,
} from '../types';

// =============================================================================
// Step definitions
// =============================================================================

interface Step {
  id: string;
  label: string;
  icon: typeof Database;
}

const STEPS: Step[] = [
  { id: 'source', label: 'Datenquelle', icon: Database },
  { id: 'filter', label: 'Filter', icon: Filter },
  { id: 'group', label: 'Gruppierung', icon: Group },
  { id: 'chart', label: 'Darstellung', icon: PieChart },
  { id: 'schedule', label: 'Zeitplan', icon: Calendar },
];

// =============================================================================
// Options
// =============================================================================

const dataSourceOptions: { value: DataSource; label: string; description: string }[] = [
  { value: 'documents', label: 'Dokumente', description: 'Alle erfassten Dokumente' },
  { value: 'invoices', label: 'Rechnungen', description: 'Rechnungen und Zahlungen' },
  { value: 'entities', label: 'Geschäftspartner', description: 'Kunden und Lieferanten' },
  { value: 'ocr_results', label: 'OCR-Ergebnisse', description: 'OCR-Verarbeitungsergebnisse' },
];

const chartTypeOptions: { value: ChartType | 'table'; label: string; description: string }[] = [
  { value: 'table', label: 'Tabelle', description: 'Klassische Tabellenansicht' },
  { value: 'bar', label: 'Balkendiagramm', description: 'Vergleich von Werten' },
  { value: 'line', label: 'Liniendiagramm', description: 'Trends über Zeit' },
  { value: 'pie', label: 'Kreisdiagramm', description: 'Anteile und Verteilungen' },
  { value: 'area', label: 'Flächendiagramm', description: 'Mengenentwicklungen' },
  { value: 'stacked_bar', label: 'Gestapelt', description: 'Gestapelter Vergleich' },
];

const aggregationOptions: { value: AggregationType; label: string }[] = [
  { value: 'count', label: 'Anzahl' },
  { value: 'sum', label: 'Summe' },
  { value: 'avg', label: 'Durchschnitt' },
  { value: 'min', label: 'Minimum' },
  { value: 'max', label: 'Maximum' },
];

const operatorOptions: { value: FilterOperator; label: string }[] = [
  { value: 'equals', label: 'Gleich' },
  { value: 'not_equals', label: 'Ungleich' },
  { value: 'contains', label: 'Enthält' },
  { value: 'greater_than', label: 'Größer als' },
  { value: 'less_than', label: 'Kleiner als' },
  { value: 'between', label: 'Zwischen' },
  { value: 'is_null', label: 'Ist leer' },
  { value: 'is_not_null', label: 'Ist nicht leer' },
];

const scheduleOptions = [
  { value: 'none', label: 'Kein Zeitplan' },
  { value: 'daily', label: 'Täglich', cron: '0 8 * * *' },
  { value: 'weekly', label: 'Wöchentlich (Montag)', cron: '0 8 * * 1' },
  { value: 'monthly', label: 'Monatlich (1.)', cron: '0 8 1 * *' },
];

const formatOptions: { value: ExportFormat; label: string }[] = [
  { value: 'excel', label: 'Excel (.xlsx)' },
  { value: 'pdf', label: 'PDF' },
  { value: 'csv', label: 'CSV' },
  { value: 'json', label: 'JSON' },
];

// =============================================================================
// Local filter type
// =============================================================================

interface LocalFilter {
  id: string;
  field: string;
  operator: FilterOperator;
  value: string;
}

// =============================================================================
// Component
// =============================================================================

export function ReportBuilderPage() {
  const navigate = useNavigate();
  const [currentStep, setCurrentStep] = useState(0);

  // Form state
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [dataSource, setDataSource] = useState<DataSource>('documents');
  const [reportType, _setReportType] = useState<ReportType>('document');
  const [filters, setFilters] = useState<LocalFilter[]>([]);
  const [groupByField, setGroupByField] = useState('');
  const [aggregationType, setAggregationType] = useState<AggregationType>('count');
  const [chartType, setChartType] = useState<ChartType | 'table'>('table');
  const [scheduleType, setScheduleType] = useState('none');
  const [exportFormat, setExportFormat] = useState<ExportFormat>('excel');
  const [emailRecipients, setEmailRecipients] = useState('');

  // API hooks
  const { data: _dataSources } = useDataSources();
  const { data: fields } = useFields(dataSource);
  const createMutation = useCreateTemplate();
  const executeMutation = useExecuteReport();

  // Navigation
  const canGoNext = () => {
    if (currentStep === 0) return !!name && !!dataSource;
    return true;
  };

  const handleNext = () => {
    if (currentStep < STEPS.length - 1) {
      setCurrentStep(currentStep + 1);
    }
  };

  const handlePrev = () => {
    if (currentStep > 0) {
      setCurrentStep(currentStep - 1);
    }
  };

  // Filter management
  const handleAddFilter = () => {
    setFilters((prev) => [
      ...prev,
      {
        id: crypto.randomUUID(),
        field: fields?.[0]?.path || '',
        operator: 'equals',
        value: '',
      },
    ]);
  };

  const handleRemoveFilter = (id: string) => {
    setFilters((prev) => prev.filter((f) => f.id !== id));
  };

  const handleFilterChange = (
    id: string,
    key: keyof LocalFilter,
    value: string
  ) => {
    setFilters((prev) =>
      prev.map((f) => (f.id === id ? { ...f, [key]: value } : f))
    );
  };

  // Save
  const handleSave = () => {
    const _schedule = scheduleOptions.find((s) => s.value === scheduleType);

    createMutation.mutate(
      {
        name,
        description: description || undefined,
        report_type: reportType,
        data_source: dataSource,
        default_format: exportFormat,
        is_public: false,
        enable_aggregations: aggregationType !== 'count',
        row_limit: 10000,
      },
      {
        onSuccess: () => {
          navigate({ to: '/berichte' });
        },
      }
    );
  };

  // Execute
  const handleExecute = () => {
    if (createMutation.data?.id) {
      executeMutation.mutate({
        templateId: createMutation.data.id,
        data: { format: exportFormat },
      });
    } else {
      handleSave();
    }
  };

  const isSaving = createMutation.isPending;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Button
            variant="ghost"
            size="icon"
            onClick={() => navigate({ to: '/berichte' })}
          >
            <ArrowLeft className="h-5 w-5" />
          </Button>
          <div>
            <h1 className="text-2xl font-bold tracking-tight">Neuer Bericht</h1>
            <p className="text-sm text-muted-foreground">
              Schritt {currentStep + 1} von {STEPS.length}:{' '}
              {STEPS[currentStep].label}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            onClick={handleSave}
            disabled={!name || isSaving}
          >
            {isSaving ? (
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            ) : (
              <Save className="h-4 w-4 mr-2" />
            )}
            Speichern
          </Button>
          <Button
            onClick={handleExecute}
            disabled={!name || isSaving}
          >
            <Play className="h-4 w-4 mr-2" />
            Ausführen
          </Button>
        </div>
      </div>

      {/* Step Indicator */}
      <div className="flex items-center gap-2">
        {STEPS.map((step, idx) => {
          const StepIcon = step.icon;
          const isActive = idx === currentStep;
          const isCompleted = idx < currentStep;

          return (
            <div key={step.id} className="flex items-center gap-2">
              {idx > 0 && (
                <div
                  className={`h-px w-8 ${
                    isCompleted ? 'bg-primary' : 'bg-border'
                  }`}
                />
              )}
              <button
                onClick={() => setCurrentStep(idx)}
                className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-primary text-primary-foreground'
                    : isCompleted
                      ? 'bg-primary/10 text-primary'
                      : 'bg-muted text-muted-foreground hover:bg-muted/80'
                }`}
              >
                {isCompleted ? (
                  <Check className="h-4 w-4" />
                ) : (
                  <StepIcon className="h-4 w-4" />
                )}
                <span className="hidden sm:inline">{step.label}</span>
              </button>
            </div>
          );
        })}
      </div>

      {/* Content Area */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Panel: Form */}
        <div className="lg:col-span-2 space-y-4">
          {/* Step 1: Datenquelle */}
          {currentStep === 0 && (
            <Card>
              <CardHeader>
                <CardTitle>Datenquelle wählen</CardTitle>
                <CardDescription>
                  Wählen Sie die Basis-Datenquelle für Ihren Bericht.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="report-name">Name *</Label>
                  <Input
                    id="report-name"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="z.B. Monatlicher Rechnungsbericht"
                  />
                </div>

                <div className="space-y-2">
                  <Label htmlFor="report-desc">Beschreibung</Label>
                  <Textarea
                    id="report-desc"
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    placeholder="Optionale Beschreibung..."
                    rows={2}
                  />
                </div>

                <Separator />

                <div className="space-y-2">
                  <Label>Datenquelle</Label>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    {dataSourceOptions.map((option) => (
                      <button
                        key={option.value}
                        onClick={() => setDataSource(option.value)}
                        className={`p-4 rounded-lg border text-left transition-colors ${
                          dataSource === option.value
                            ? 'border-primary bg-primary/5'
                            : 'border-border hover:border-primary/50'
                        }`}
                      >
                        <div className="font-medium text-sm">{option.label}</div>
                        <div className="text-xs text-muted-foreground mt-1">
                          {option.description}
                        </div>
                      </button>
                    ))}
                  </div>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Step 2: Filter */}
          {currentStep === 1 && (
            <Card>
              <CardHeader>
                <CardTitle>Filter konfigurieren</CardTitle>
                <CardDescription>
                  Fügen Sie Filter hinzu, um die Daten einzuschränken.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {filters.map((filter) => (
                  <div key={filter.id} className="flex items-end gap-2">
                    <div className="flex-1 space-y-1">
                      <Label className="text-xs">Feld</Label>
                      <Select
                        value={filter.field}
                        onValueChange={(v) =>
                          handleFilterChange(filter.id, 'field', v)
                        }
                      >
                        <SelectTrigger>
                          <SelectValue placeholder="Feld wählen" />
                        </SelectTrigger>
                        <SelectContent>
                          {fields?.map((f) => (
                            <SelectItem key={f.path} value={f.path}>
                              {f.display_name}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>

                    <div className="w-40 space-y-1">
                      <Label className="text-xs">Operator</Label>
                      <Select
                        value={filter.operator}
                        onValueChange={(v) =>
                          handleFilterChange(filter.id, 'operator', v)
                        }
                      >
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {operatorOptions.map((op) => (
                            <SelectItem key={op.value} value={op.value}>
                              {op.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>

                    <div className="flex-1 space-y-1">
                      <Label className="text-xs">Wert</Label>
                      <Input
                        value={filter.value}
                        onChange={(e) =>
                          handleFilterChange(filter.id, 'value', e.target.value)
                        }
                        placeholder="Filterwert"
                      />
                    </div>

                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleRemoveFilter(filter.id)}
                      className="text-destructive"
                    >
                      Entfernen
                    </Button>
                  </div>
                ))}

                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleAddFilter}
                >
                  <Filter className="h-4 w-4 mr-2" />
                  Filter hinzufügen
                </Button>

                {filters.length === 0 && (
                  <div className="text-center text-muted-foreground py-8">
                    <Filter className="h-10 w-10 mx-auto mb-3 opacity-50" />
                    <p className="text-sm">
                      Keine Filter konfiguriert. Alle Daten werden einbezogen.
                    </p>
                  </div>
                )}
              </CardContent>
            </Card>
          )}

          {/* Step 3: Gruppierung & Aggregation */}
          {currentStep === 2 && (
            <Card>
              <CardHeader>
                <CardTitle>Gruppierung & Aggregation</CardTitle>
                <CardDescription>
                  Gruppieren Sie Daten und berechnen Sie Aggregationen.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <Label>Gruppieren nach</Label>
                  <Select
                    value={groupByField || 'none'}
                    onValueChange={(v) => setGroupByField(v === 'none' ? '' : v)}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Feld wählen" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="none">Keine Gruppierung</SelectItem>
                      {fields?.map((f) => (
                        <SelectItem key={f.path} value={f.path}>
                          {f.display_name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-2">
                  <Label>Aggregation</Label>
                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                    {aggregationOptions.map((agg) => (
                      <button
                        key={agg.value}
                        onClick={() => setAggregationType(agg.value)}
                        className={`p-3 rounded-lg border text-sm font-medium transition-colors ${
                          aggregationType === agg.value
                            ? 'border-primary bg-primary/5 text-primary'
                            : 'border-border hover:border-primary/50'
                        }`}
                      >
                        {agg.label}
                      </button>
                    ))}
                  </div>
                </div>

                {groupByField && (
                  <div className="rounded-md bg-muted/50 p-3 text-sm">
                    <p className="font-medium mb-1">Vorschau-Konfiguration:</p>
                    <p className="text-muted-foreground">
                      Gruppiert nach:{' '}
                      <Badge variant="secondary">
                        {fields?.find((f) => f.path === groupByField)?.display_name || groupByField}
                      </Badge>
                      {' '}mit{' '}
                      <Badge variant="secondary">
                        {aggregationOptions.find((a) => a.value === aggregationType)?.label}
                      </Badge>
                    </p>
                  </div>
                )}
              </CardContent>
            </Card>
          )}

          {/* Step 4: Darstellung */}
          {currentStep === 3 && (
            <Card>
              <CardHeader>
                <CardTitle>Darstellung wählen</CardTitle>
                <CardDescription>
                  Wählen Sie, wie die Ergebnisse dargestellt werden sollen.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                  {chartTypeOptions.map((option) => (
                    <button
                      key={option.value}
                      onClick={() => setChartType(option.value)}
                      className={`p-4 rounded-lg border text-left transition-colors ${
                        chartType === option.value
                          ? 'border-primary bg-primary/5'
                          : 'border-border hover:border-primary/50'
                      }`}
                    >
                      <div className="font-medium text-sm">{option.label}</div>
                      <div className="text-xs text-muted-foreground mt-1">
                        {option.description}
                      </div>
                    </button>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Step 5: Zeitplan */}
          {currentStep === 4 && (
            <Card>
              <CardHeader>
                <CardTitle>Zeitplan (optional)</CardTitle>
                <CardDescription>
                  Konfigurieren Sie eine automatische Ausführung.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <Label>Automatische Ausführung</Label>
                  <Select
                    value={scheduleType}
                    onValueChange={setScheduleType}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {scheduleOptions.map((s) => (
                        <SelectItem key={s.value} value={s.value}>
                          {s.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-2">
                  <Label>Export-Format</Label>
                  <Select
                    value={exportFormat}
                    onValueChange={(v: ExportFormat) => setExportFormat(v)}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {formatOptions.map((f) => (
                        <SelectItem key={f.value} value={f.value}>
                          {f.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                {scheduleType !== 'none' && (
                  <div className="space-y-2">
                    <Label htmlFor="email-recipients">
                      E-Mail-Empfänger (optional)
                    </Label>
                    <Input
                      id="email-recipients"
                      value={emailRecipients}
                      onChange={(e) => setEmailRecipients(e.target.value)}
                      placeholder="email@beispiel.de, weitere@beispiel.de"
                    />
                    <p className="text-xs text-muted-foreground">
                      Kommagetrennte E-Mail-Adressen
                    </p>
                  </div>
                )}

                {scheduleType === 'none' && (
                  <div className="rounded-md bg-muted/50 p-4 text-center">
                    <Calendar className="h-8 w-8 mx-auto mb-2 text-muted-foreground" />
                    <p className="text-sm text-muted-foreground">
                      Kein Zeitplan konfiguriert. Der Bericht kann manuell
                      ausgeführt werden.
                    </p>
                  </div>
                )}
              </CardContent>
            </Card>
          )}

          {/* Navigation Buttons */}
          <div className="flex items-center justify-between pt-4">
            <Button
              variant="outline"
              onClick={handlePrev}
              disabled={currentStep === 0}
            >
              <ArrowLeft className="h-4 w-4 mr-2" />
              Zurück
            </Button>

            {currentStep < STEPS.length - 1 ? (
              <Button onClick={handleNext} disabled={!canGoNext()}>
                Weiter
                <ArrowRight className="h-4 w-4 ml-2" />
              </Button>
            ) : (
              <Button onClick={handleSave} disabled={!name || isSaving}>
                {isSaving ? (
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                ) : (
                  <Save className="h-4 w-4 mr-2" />
                )}
                Bericht erstellen
              </Button>
            )}
          </div>
        </div>

        {/* Right Panel: Preview */}
        <div className="space-y-4">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base flex items-center gap-2">
                <BarChart3 className="h-4 w-4" />
                Konfiguration
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              {name && (
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Name:</span>
                  <span className="font-medium truncate ml-2">{name}</span>
                </div>
              )}
              <div className="flex justify-between">
                <span className="text-muted-foreground">Datenquelle:</span>
                <Badge variant="outline">
                  {dataSourceOptions.find((d) => d.value === dataSource)?.label}
                </Badge>
              </div>
              {filters.length > 0 && (
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Filter:</span>
                  <Badge variant="secondary">{filters.length}</Badge>
                </div>
              )}
              {groupByField && (
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Gruppierung:</span>
                  <Badge variant="secondary">
                    {fields?.find((f) => f.path === groupByField)?.display_name || groupByField}
                  </Badge>
                </div>
              )}
              <div className="flex justify-between">
                <span className="text-muted-foreground">Darstellung:</span>
                <Badge variant="outline">
                  {chartTypeOptions.find((c) => c.value === chartType)?.label}
                </Badge>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Format:</span>
                <Badge variant="outline">
                  {formatOptions.find((f) => f.value === exportFormat)?.label}
                </Badge>
              </div>
              {scheduleType !== 'none' && (
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Zeitplan:</span>
                  <Badge variant="secondary" className="bg-green-500/10 text-green-600">
                    {scheduleOptions.find((s) => s.value === scheduleType)?.label}
                  </Badge>
                </div>
              )}
            </CardContent>
          </Card>

          <ReportPreview
            templateId={createMutation.data?.id}
            chartType={chartType === 'table' ? undefined : chartType}
          />
        </div>
      </div>
    </div>
  );
}
