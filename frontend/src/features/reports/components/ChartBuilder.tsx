/**
 * ChartBuilder Component
 *
 * Konfigurations-UI für Report-Charts.
 * Ermöglicht das Erstellen und Bearbeiten von Charts.
 */

import { useState } from 'react';
import {
    BarChart3,
    LineChart,
    PieChart,
    AreaChart,
    Layers,
    Plus,
    Trash2,
    Settings2,
    Palette,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Switch } from '@/components/ui/switch';
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select';
import {
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
} from '@/components/ui/card';
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from '@/components/ui/dialog';
import {
    Accordion,
    AccordionContent,
    AccordionItem,
    AccordionTrigger,
} from '@/components/ui/accordion';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { useFields, useAddChart, useDeleteChart, usePreview } from '../hooks/useReports';
import { ChartPreview } from './ChartPreview';
import type {
    ReportTemplate,
    ReportChart,
    ReportChartCreate,
    ChartType,
    AggregationType,
    FieldDefinition,
} from '../types';

// =============================================================================
// Types
// =============================================================================

interface ChartBuilderProps {
    template: ReportTemplate;
}

interface ChartFormData extends Omit<ReportChartCreate, 'styling'> {
    show_legend: boolean;
    legend_position: 'top' | 'bottom' | 'left' | 'right';
    show_data_labels: boolean;
    stacked: boolean;
}

// =============================================================================
// Constants
// =============================================================================

const CHART_TYPES: { value: ChartType; label: string; icon: React.ElementType }[] = [
    { value: 'bar', label: 'Balkendiagramm', icon: BarChart3 },
    { value: 'line', label: 'Liniendiagramm', icon: LineChart },
    { value: 'pie', label: 'Kreisdiagramm', icon: PieChart },
    { value: 'area', label: 'Flächendiagramm', icon: AreaChart },
    { value: 'stacked_bar', label: 'Gestapeltes Balken', icon: Layers },
];

const AGGREGATION_OPTIONS: { value: AggregationType; label: string }[] = [
    { value: 'count', label: 'Anzahl' },
    { value: 'sum', label: 'Summe' },
    { value: 'avg', label: 'Durchschnitt' },
    { value: 'min', label: 'Minimum' },
    { value: 'max', label: 'Maximum' },
    { value: 'none', label: 'Keine Aggregation' },
];

const LEGEND_POSITIONS: { value: 'top' | 'bottom' | 'left' | 'right'; label: string }[] = [
    { value: 'top', label: 'Oben' },
    { value: 'bottom', label: 'Unten' },
    { value: 'left', label: 'Links' },
    { value: 'right', label: 'Rechts' },
];

const DEFAULT_FORM_DATA: ChartFormData = {
    chart_type: 'bar',
    title: '',
    description: '',
    x_axis_field: '',
    y_axis_field: '',
    group_by_field: '',
    aggregation: 'count',
    show_legend: true,
    legend_position: 'bottom',
    show_data_labels: false,
    stacked: false,
};

// =============================================================================
// Helper Functions
// =============================================================================

function getChartLabel(chartType: ChartType): string {
    const chartConfig = CHART_TYPES.find(c => c.value === chartType);
    return chartConfig?.label || chartType;
}

function filterNumericFields(fields: FieldDefinition[] | undefined): FieldDefinition[] {
    if (!fields) return [];
    return fields.filter(f => f.data_type === 'number' || f.data_type === 'currency');
}

function filterCategoryFields(fields: FieldDefinition[] | undefined): FieldDefinition[] {
    if (!fields) return [];
    return fields.filter(f => f.data_type === 'string' || f.data_type === 'date');
}

// =============================================================================
// Chart Card Component
// =============================================================================

interface ChartCardProps {
    chart: ReportChart;
    onDelete: () => void;
    isDeleting: boolean;
    preview: ReturnType<typeof usePreview>['data'];
    previewLoading: boolean;
}

const CHART_TYPE_ICONS: Record<ChartType, React.ElementType> = {
    bar: BarChart3,
    line: LineChart,
    pie: PieChart,
    area: AreaChart,
    stacked_bar: Layers,
};

function ChartCardIcon({ chartType }: { chartType: ChartType }) {
    const Icon = CHART_TYPE_ICONS[chartType] ?? BarChart3;
    return <Icon className="h-4 w-4 text-primary" />;
}

function ChartCard({ chart, onDelete, isDeleting, preview, previewLoading }: ChartCardProps) {
    return (
        <Card className="relative">
            <CardHeader className="pb-2">
                <div className="flex items-start justify-between">
                    <div className="flex items-center gap-2">
                        <div className="p-2 rounded-lg bg-primary/10">
                            <ChartCardIcon chartType={chart.chart_type} />
                        </div>
                        <div>
                            <CardTitle className="text-sm">
                                {chart.title || 'Unbenanntes Chart'}
                            </CardTitle>
                            <CardDescription className="text-xs">
                                {getChartLabel(chart.chart_type)}
                            </CardDescription>
                        </div>
                    </div>
                    <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8 text-muted-foreground hover:text-destructive"
                        onClick={onDelete}
                        disabled={isDeleting}
                    >
                        <Trash2 className="h-4 w-4" />
                    </Button>
                </div>
            </CardHeader>
            <CardContent className="space-y-3">
                <div className="flex flex-wrap gap-2 text-xs">
                    {chart.x_axis_field && (
                        <Badge variant="outline">X: {chart.x_axis_field}</Badge>
                    )}
                    {chart.y_axis_field && (
                        <Badge variant="outline">Y: {chart.y_axis_field}</Badge>
                    )}
                    {chart.aggregation && chart.aggregation !== 'none' && (
                        <Badge variant="secondary">{chart.aggregation}</Badge>
                    )}
                </div>

                {/* Mini Preview */}
                <div className="border rounded-lg overflow-hidden">
                    <ChartPreview
                        chart={chart}
                        data={preview}
                        isLoading={previewLoading}
                    />
                </div>
            </CardContent>
        </Card>
    );
}

// =============================================================================
// Add Chart Dialog
// =============================================================================

interface AddChartDialogProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    fields: FieldDefinition[] | undefined;
    onSubmit: (data: ReportChartCreate) => void;
    isSubmitting: boolean;
}

function AddChartDialog({
    open,
    onOpenChange,
    fields,
    onSubmit,
    isSubmitting,
}: AddChartDialogProps) {
    const [formData, setFormData] = useState<ChartFormData>(DEFAULT_FORM_DATA);

    const numericFields = filterNumericFields(fields);
    const categoryFields = filterCategoryFields(fields);

    const handleSubmit = () => {
        const chartCreate: ReportChartCreate = {
            chart_type: formData.chart_type,
            title: formData.title || undefined,
            description: formData.description || undefined,
            x_axis_field: formData.x_axis_field || undefined,
            y_axis_field: formData.y_axis_field || undefined,
            group_by_field: formData.group_by_field || undefined,
            aggregation: formData.aggregation,
            styling: {
                show_legend: formData.show_legend,
                legend_position: formData.legend_position,
                show_data_labels: formData.show_data_labels,
                stacked: formData.stacked,
            },
        };

        onSubmit(chartCreate);
        setFormData(DEFAULT_FORM_DATA);
    };

    const isPie = formData.chart_type === 'pie';
    const isStacked = formData.chart_type === 'stacked_bar';

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
                <DialogHeader>
                    <DialogTitle>Neues Chart hinzufügen</DialogTitle>
                    <DialogDescription>
                        Konfigurieren Sie ein neues Chart für Ihren Report.
                    </DialogDescription>
                </DialogHeader>

                <div className="space-y-6 py-4">
                    {/* Chart Type Selection */}
                    <div className="space-y-3">
                        <Label>Chart-Typ</Label>
                        <div className="grid grid-cols-3 gap-2">
                            {CHART_TYPES.map(({ value, label, icon: Icon }) => (
                                <button
                                    key={value}
                                    type="button"
                                    onClick={() => setFormData(prev => ({ ...prev, chart_type: value }))}
                                    className={`flex flex-col items-center gap-1 p-3 rounded-lg border transition-colors ${
                                        formData.chart_type === value
                                            ? 'border-primary bg-primary/5 text-primary'
                                            : 'border-border hover:border-primary/50'
                                    }`}
                                >
                                    <Icon className="h-5 w-5" />
                                    <span className="text-xs">{label}</span>
                                </button>
                            ))}
                        </div>
                    </div>

                    <Separator />

                    {/* Basic Info */}
                    <div className="space-y-4">
                        <div className="space-y-2">
                            <Label htmlFor="chart-title">Titel</Label>
                            <Input
                                id="chart-title"
                                value={formData.title}
                                onChange={(e) => setFormData(prev => ({ ...prev, title: e.target.value }))}
                                placeholder="z.B. Dokumentenverteilung nach Typ"
                            />
                        </div>

                        <div className="space-y-2">
                            <Label htmlFor="chart-description">Beschreibung</Label>
                            <Textarea
                                id="chart-description"
                                value={formData.description}
                                onChange={(e) => setFormData(prev => ({ ...prev, description: e.target.value }))}
                                placeholder="Optionale Beschreibung..."
                                rows={2}
                            />
                        </div>
                    </div>

                    <Separator />

                    {/* Data Configuration */}
                    <div className="space-y-4">
                        <div className="flex items-center gap-2 text-sm font-medium">
                            <Settings2 className="h-4 w-4" />
                            Daten-Konfiguration
                        </div>

                        <div className="space-y-2">
                            <Label>
                                {isPie ? 'Kategorie (Segmente)' : 'X-Achse (Kategorien)'}
                            </Label>
                            <Select
                                value={formData.x_axis_field || 'none'}
                                onValueChange={(v) => setFormData(prev => ({
                                    ...prev,
                                    x_axis_field: v === 'none' ? '' : v,
                                }))}
                            >
                                <SelectTrigger>
                                    <SelectValue placeholder="Feld auswählen..." />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="none">-- Kein Feld --</SelectItem>
                                    {categoryFields.map(field => (
                                        <SelectItem key={field.path} value={field.path}>
                                            {field.display_name}
                                        </SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </div>

                        {!isPie && (
                            <div className="space-y-2">
                                <Label>Y-Achse (Werte)</Label>
                                <Select
                                    value={formData.y_axis_field || 'none'}
                                    onValueChange={(v) => setFormData(prev => ({
                                        ...prev,
                                        y_axis_field: v === 'none' ? '' : v,
                                    }))}
                                >
                                    <SelectTrigger>
                                        <SelectValue placeholder="Feld auswählen..." />
                                    </SelectTrigger>
                                    <SelectContent>
                                        <SelectItem value="none">-- Anzahl (Count) --</SelectItem>
                                        {numericFields.map(field => (
                                            <SelectItem key={field.path} value={field.path}>
                                                {field.display_name}
                                            </SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                            </div>
                        )}

                        {isStacked && (
                            <div className="space-y-2">
                                <Label>Gruppierung (Stapel)</Label>
                                <Select
                                    value={formData.group_by_field || 'none'}
                                    onValueChange={(v) => setFormData(prev => ({
                                        ...prev,
                                        group_by_field: v === 'none' ? '' : v,
                                    }))}
                                >
                                    <SelectTrigger>
                                        <SelectValue placeholder="Feld auswählen..." />
                                    </SelectTrigger>
                                    <SelectContent>
                                        <SelectItem value="none">-- Keine Gruppierung --</SelectItem>
                                        {categoryFields.map(field => (
                                            <SelectItem key={field.path} value={field.path}>
                                                {field.display_name}
                                            </SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                            </div>
                        )}

                        <div className="space-y-2">
                            <Label>Aggregation</Label>
                            <Select
                                value={formData.aggregation}
                                onValueChange={(v: AggregationType) => setFormData(prev => ({
                                    ...prev,
                                    aggregation: v,
                                }))}
                            >
                                <SelectTrigger>
                                    <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                    {AGGREGATION_OPTIONS.map(opt => (
                                        <SelectItem key={opt.value} value={opt.value}>
                                            {opt.label}
                                        </SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </div>
                    </div>

                    <Separator />

                    {/* Styling Options */}
                    <Accordion type="single" collapsible defaultValue="styling">
                        <AccordionItem value="styling" className="border-none">
                            <AccordionTrigger className="py-2">
                                <div className="flex items-center gap-2 text-sm font-medium">
                                    <Palette className="h-4 w-4" />
                                    Darstellung
                                </div>
                            </AccordionTrigger>
                            <AccordionContent className="space-y-4 pt-2">
                                <div className="flex items-center justify-between">
                                    <div className="space-y-0.5">
                                        <Label>Legende anzeigen</Label>
                                        <p className="text-xs text-muted-foreground">
                                            Zeigt die Legende für das Chart an
                                        </p>
                                    </div>
                                    <Switch
                                        checked={formData.show_legend}
                                        onCheckedChange={(checked) => setFormData(prev => ({
                                            ...prev,
                                            show_legend: checked,
                                        }))}
                                    />
                                </div>

                                {formData.show_legend && (
                                    <div className="space-y-2">
                                        <Label>Legendenposition</Label>
                                        <Select
                                            value={formData.legend_position}
                                            onValueChange={(v: 'top' | 'bottom' | 'left' | 'right') =>
                                                setFormData(prev => ({ ...prev, legend_position: v }))
                                            }
                                        >
                                            <SelectTrigger>
                                                <SelectValue />
                                            </SelectTrigger>
                                            <SelectContent>
                                                {LEGEND_POSITIONS.map(pos => (
                                                    <SelectItem key={pos.value} value={pos.value}>
                                                        {pos.label}
                                                    </SelectItem>
                                                ))}
                                            </SelectContent>
                                        </Select>
                                    </div>
                                )}

                                <div className="flex items-center justify-between">
                                    <div className="space-y-0.5">
                                        <Label>Datenbeschriftung</Label>
                                        <p className="text-xs text-muted-foreground">
                                            Zeigt Werte direkt im Chart an
                                        </p>
                                    </div>
                                    <Switch
                                        checked={formData.show_data_labels}
                                        onCheckedChange={(checked) => setFormData(prev => ({
                                            ...prev,
                                            show_data_labels: checked,
                                        }))}
                                    />
                                </div>

                                {(formData.chart_type === 'area' || formData.chart_type === 'bar') && (
                                    <div className="flex items-center justify-between">
                                        <div className="space-y-0.5">
                                            <Label>Gestapelt</Label>
                                            <p className="text-xs text-muted-foreground">
                                                Stapelt mehrere Serien übereinander
                                            </p>
                                        </div>
                                        <Switch
                                            checked={formData.stacked}
                                            onCheckedChange={(checked) => setFormData(prev => ({
                                                ...prev,
                                                stacked: checked,
                                            }))}
                                        />
                                    </div>
                                )}
                            </AccordionContent>
                        </AccordionItem>
                    </Accordion>
                </div>

                <DialogFooter>
                    <Button variant="outline" onClick={() => onOpenChange(false)}>
                        Abbrechen
                    </Button>
                    <Button
                        onClick={handleSubmit}
                        disabled={!formData.x_axis_field || isSubmitting}
                    >
                        {isSubmitting ? 'Wird hinzugefügt...' : 'Chart hinzufügen'}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

// =============================================================================
// Main Component
// =============================================================================

export function ChartBuilder({ template }: ChartBuilderProps) {
    const [showAddDialog, setShowAddDialog] = useState(false);

    const { data: fields } = useFields(template.data_source);
    const { data: preview, isLoading: previewLoading } = usePreview(template.id, 100);
    const addChartMutation = useAddChart();
    const deleteChartMutation = useDeleteChart();

    const charts = template.charts || [];

    const handleAddChart = (data: ReportChartCreate) => {
        addChartMutation.mutate(
            { templateId: template.id, data },
            { onSuccess: () => setShowAddDialog(false) }
        );
    };

    const handleDeleteChart = (chartId: string) => {
        deleteChartMutation.mutate({ templateId: template.id, chartId });
    };

    return (
        <div className="space-y-4">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h3 className="text-sm font-medium">Charts ({charts.length})</h3>
                    <p className="text-xs text-muted-foreground">
                        Visualisieren Sie Ihre Report-Daten
                    </p>
                </div>
                <Button
                    size="sm"
                    onClick={() => setShowAddDialog(true)}
                    className="gap-2"
                >
                    <Plus className="h-4 w-4" />
                    Chart hinzufügen
                </Button>
            </div>

            {/* Charts List */}
            {charts.length === 0 ? (
                <Card>
                    <CardContent className="flex flex-col items-center justify-center py-12 text-center">
                        <BarChart3 className="h-12 w-12 text-muted-foreground mb-4" />
                        <p className="text-muted-foreground mb-4">
                            Noch keine Charts konfiguriert.
                        </p>
                        <Button
                            variant="outline"
                            onClick={() => setShowAddDialog(true)}
                            className="gap-2"
                        >
                            <Plus className="h-4 w-4" />
                            Erstes Chart erstellen
                        </Button>
                    </CardContent>
                </Card>
            ) : (
                <div className="space-y-4">
                    {charts.map(chart => (
                        <ChartCard
                            key={chart.id}
                            chart={chart}
                            onDelete={() => handleDeleteChart(chart.id)}
                            isDeleting={deleteChartMutation.isPending}
                            preview={preview}
                            previewLoading={previewLoading}
                        />
                    ))}
                </div>
            )}

            {/* Add Chart Dialog */}
            <AddChartDialog
                open={showAddDialog}
                onOpenChange={setShowAddDialog}
                fields={fields}
                onSubmit={handleAddChart}
                isSubmitting={addChartMutation.isPending}
            />
        </div>
    );
}

export default ChartBuilder;
