/**
 * FilterBuilder Component
 *
 * Haupt-UI für die Filter-Konfiguration im Report-Builder.
 * Ermöglicht Hinzufügen, Bearbeiten und Löschen von Filtern.
 */

import { useState } from 'react';
import { Plus, Filter, AlertCircle, Loader2, Sparkles } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Separator } from '@/components/ui/separator';
import { FilterRow } from './FilterRow';
import {
    useFilters,
    useAddFilter,
    useDeleteFilter,
    useFields,
    useOperators,
} from '../hooks/useReports';
import type {
    ReportTemplate,
    FieldDefinition,
    DataType,
    FilterOperator,
} from '../types';

interface FilterBuilderProps {
    template: ReportTemplate;
}

const dynamicSourceOptions: { value: string; label: string }[] = [
    { value: 'today', label: 'Heute' },
    { value: 'last_7_days', label: 'Letzte 7 Tage' },
    { value: 'last_30_days', label: 'Letzte 30 Tage' },
    { value: 'current_user', label: 'Aktueller Benutzer' },
    { value: 'current_company', label: 'Aktuelle Firma' },
];

/**
 * Bestimmt den Standard-Operator basierend auf dem Datentyp.
 */
function getDefaultOperator(dataType: DataType): FilterOperator {
    switch (dataType) {
        case 'string':
            return 'contains';
        case 'number':
        case 'currency':
            return 'equals';
        case 'date':
            return 'between';
        case 'boolean':
            return 'equals';
        default:
            return 'equals';
    }
}

/**
 * FilterBuilder - Haupt-Komponente für Filter-Konfiguration.
 */
export function FilterBuilder({ template }: FilterBuilderProps) {
    const [selectedFieldPath, setSelectedFieldPath] = useState<string>('');

    // Data fetching
    const { data: filters = [], isLoading: filtersLoading } = useFilters(template.id);
    const { data: fields = [], isLoading: fieldsLoading } = useFields(template.data_source);
    const { data: operators = [], isLoading: operatorsLoading } = useOperators();

    // Mutations
    const addFilterMutation = useAddFilter();
    const deleteFilterMutation = useDeleteFilter();

    const isLoading = filtersLoading || fieldsLoading || operatorsLoading;
    const isMutating = addFilterMutation.isPending || deleteFilterMutation.isPending;

    // Gruppiere Felder nach Kategorie
    const groupedFields = fields.reduce<Record<string, FieldDefinition[]>>((acc, field) => {
        const category = field.category || 'Allgemein';
        if (!acc[category]) {
            acc[category] = [];
        }
        acc[category].push(field);
        return acc;
    }, {});

    const handleAddFilter = () => {
        const field = fields.find((f) => f.path === selectedFieldPath);
        if (!field) return;

        addFilterMutation.mutate({
            templateId: template.id,
            data: {
                field_path: field.path,
                operator: getDefaultOperator(field.data_type),
                value_type: field.data_type,
                logic_operator: filters.length > 0 ? 'AND' : 'AND',
            },
        });

        setSelectedFieldPath('');
    };

    const handleDeleteFilter = (filterId: string) => {
        deleteFilterMutation.mutate({
            templateId: template.id,
            filterId,
        });
    };

    // Loading State
    if (isLoading) {
        return (
            <Card>
                <CardContent className="flex items-center justify-center py-12">
                    <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                </CardContent>
            </Card>
        );
    }

    // No Fields Available
    if (fields.length === 0) {
        return (
            <Card>
                <CardContent className="pt-6">
                    <Alert>
                        <AlertCircle className="h-4 w-4" />
                        <AlertDescription>
                            Keine Felder für die Datenquelle "{template.data_source}" verfügbar.
                            Bitte wählen Sie eine andere Datenquelle.
                        </AlertDescription>
                    </Alert>
                </CardContent>
            </Card>
        );
    }

    return (
        <div className="space-y-4">
            {/* Header mit Filter-Hinzufügen */}
            <Card>
                <CardHeader className="pb-3">
                    <CardTitle className="text-sm flex items-center gap-2">
                        <Filter className="h-4 w-4" />
                        Filter hinzufügen
                    </CardTitle>
                    <CardDescription>
                        Wählen Sie ein Feld, um einen neuen Filter hinzuzufügen.
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    <div className="flex items-center gap-2">
                        <Select
                            value={selectedFieldPath}
                            onValueChange={setSelectedFieldPath}
                            disabled={isMutating}
                        >
                            <SelectTrigger className="flex-1">
                                <SelectValue placeholder="Feld auswählen..." />
                            </SelectTrigger>
                            <SelectContent>
                                {Object.entries(groupedFields).map(([category, categoryFields]) => (
                                    <div key={category}>
                                        <div className="px-2 py-1.5 text-xs font-medium text-muted-foreground uppercase">
                                            {category}
                                        </div>
                                        {categoryFields.map((field) => (
                                            <SelectItem key={field.path} value={field.path}>
                                                <div className="flex items-center gap-2">
                                                    <span>{field.display_name}</span>
                                                    <Badge variant="outline" className="text-xs">
                                                        {field.data_type}
                                                    </Badge>
                                                </div>
                                            </SelectItem>
                                        ))}
                                        <Separator className="my-1" />
                                    </div>
                                ))}
                            </SelectContent>
                        </Select>
                        <Button
                            onClick={handleAddFilter}
                            disabled={!selectedFieldPath || isMutating}
                        >
                            {addFilterMutation.isPending ? (
                                <Loader2 className="h-4 w-4 animate-spin" />
                            ) : (
                                <Plus className="h-4 w-4" />
                            )}
                            <span className="ml-2">Hinzufügen</span>
                        </Button>
                    </div>
                </CardContent>
            </Card>

            {/* Aktive Filter */}
            {filters.length > 0 ? (
                <Card>
                    <CardHeader className="pb-3">
                        <CardTitle className="text-sm flex items-center justify-between">
                            <span className="flex items-center gap-2">
                                <Sparkles className="h-4 w-4" />
                                Aktive Filter ({filters.length})
                            </span>
                            <Badge variant="secondary">
                                {filters.every((f) => f.logic_operator === 'AND')
                                    ? 'Alle Bedingungen (UND)'
                                    : filters.every((f) => f.logic_operator === 'OR')
                                    ? 'Eine Bedingung (ODER)'
                                    : 'Gemischte Logik'}
                            </Badge>
                        </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-4">
                        {filters
                            .sort((a, b) => a.sort_order - b.sort_order)
                            .map((filter, index) => (
                                <FilterRow
                                    key={filter.id}
                                    filter={filter}
                                    fields={fields}
                                    operators={operators}
                                    isFirst={index === 0}
                                    onDelete={() => handleDeleteFilter(filter.id)}
                                    disabled={isMutating}
                                />
                            ))}
                    </CardContent>
                </Card>
            ) : (
                <Card>
                    <CardContent className="pt-6">
                        <div className="text-center text-muted-foreground py-8">
                            <Filter className="h-12 w-12 mx-auto mb-4 opacity-50" />
                            <p className="font-medium">Keine Filter konfiguriert</p>
                            <p className="text-sm mt-1">
                                Fügen Sie Filter hinzu, um die Daten einzuschränken.
                            </p>
                        </div>
                    </CardContent>
                </Card>
            )}

            {/* Dynamische Quellen Info */}
            <Card>
                <CardHeader className="pb-2">
                    <CardTitle className="text-sm">Dynamische Werte</CardTitle>
                    <CardDescription>
                        Diese Platzhalter werden bei der Report-Ausführung automatisch ersetzt.
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    <div className="flex flex-wrap gap-2">
                        {dynamicSourceOptions.map((option) => (
                            <Badge key={option.value} variant="outline" className="text-xs">
                                ${option.value} = {option.label}
                            </Badge>
                        ))}
                    </div>
                </CardContent>
            </Card>
        </div>
    );
}

export default FilterBuilder;
