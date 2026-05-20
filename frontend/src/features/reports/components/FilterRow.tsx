/**
 * FilterRow Component
 *
 * Einzelne Filter-Zeile im Filter-Builder.
 * Ermöglicht Konfiguration von Feld, Operator und Wert.
 */

import { GripVertical, Trash2, ToggleLeft, ToggleRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select';
import {
    Tooltip,
    TooltipContent,
    TooltipProvider,
    TooltipTrigger,
} from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';
import { FilterValueInput } from './FilterValueInput';
import type {
    ReportFilter,
    FieldDefinition,
    OperatorInfo,
    DataType,
    FilterOperator,
} from '../types';

interface FilterRowProps {
    filter: ReportFilter;
    fields: FieldDefinition[];
    operators: OperatorInfo[];
    isFirst: boolean;
    onDelete: () => void;
    onUpdate?: (updates: Partial<ReportFilter>) => void;
    disabled?: boolean;
}

const dataTypeLabels: Record<DataType, string> = {
    string: 'Text',
    number: 'Zahl',
    date: 'Datum',
    currency: 'Währung',
    boolean: 'Ja/Nein',
};

const operatorLabels: Record<FilterOperator, string> = {
    equals: 'ist gleich',
    not_equals: 'ist nicht gleich',
    contains: 'enthält',
    starts_with: 'beginnt mit',
    ends_with: 'endet mit',
    greater_than: 'größer als',
    greater_equal: 'größer oder gleich',
    less_than: 'kleiner als',
    less_equal: 'kleiner oder gleich',
    between: 'zwischen',
    in: 'ist in Liste',
    not_in: 'ist nicht in Liste',
    is_null: 'ist leer',
    is_not_null: 'ist nicht leer',
};

/**
 * Zeile im Filter-Builder mit Drag-Handle, Feld-Auswahl, Operator und Wert.
 */
export function FilterRow({
    filter,
    fields,
    operators,
    isFirst,
    onDelete,
    onUpdate,
    disabled = false,
}: FilterRowProps) {
    const selectedField = fields.find((f) => f.path === filter.field_path);

    // Filter Operatoren basierend auf Datentyp
    const availableOperators = operators.filter((op) =>
        op.allowed_types.includes(filter.value_type)
    );

    const handleFieldChange = (fieldPath: string) => {
        const field = fields.find((f) => f.path === fieldPath);
        if (field && onUpdate) {
            onUpdate({
                field_path: fieldPath,
                value_type: field.data_type,
                value: undefined, // Reset value when field changes
            });
        }
    };

    const handleOperatorChange = (operator: FilterOperator) => {
        if (onUpdate) {
            // Reset value for operators that don't need one
            const needsValue = operator !== 'is_null' && operator !== 'is_not_null';
            onUpdate({
                operator,
                value: needsValue ? filter.value : undefined,
            });
        }
    };

    const handleValueChange = (value: string | number | boolean | string[] | number[] | undefined) => {
        if (onUpdate) {
            onUpdate({ value });
        }
    };

    const handleLogicToggle = () => {
        if (onUpdate) {
            onUpdate({
                logic_operator: filter.logic_operator === 'AND' ? 'OR' : 'AND',
            });
        }
    };

    return (
        <div className="group relative">
            {/* Logic Operator zwischen Filtern */}
            {!isFirst && (
                <div className="absolute -top-3 left-4 z-10">
                    <TooltipProvider>
                        <Tooltip>
                            <TooltipTrigger asChild>
                                <Button
                                    variant="outline"
                                    size="sm"
                                    className={cn(
                                        'h-6 px-2 text-xs font-medium',
                                        filter.logic_operator === 'AND'
                                            ? 'bg-blue-50 border-blue-200 text-blue-700 hover:bg-blue-100'
                                            : 'bg-orange-50 border-orange-200 text-orange-700 hover:bg-orange-100'
                                    )}
                                    onClick={handleLogicToggle}
                                    disabled={disabled}
                                >
                                    {filter.logic_operator === 'AND' ? (
                                        <>
                                            <ToggleLeft className="h-3 w-3 mr-1" />
                                            UND
                                        </>
                                    ) : (
                                        <>
                                            <ToggleRight className="h-3 w-3 mr-1" />
                                            ODER
                                        </>
                                    )}
                                </Button>
                            </TooltipTrigger>
                            <TooltipContent>
                                Klicken zum Wechseln zwischen UND/ODER
                            </TooltipContent>
                        </Tooltip>
                    </TooltipProvider>
                </div>
            )}

            {/* Filter Row Content */}
            <div
                className={cn(
                    'flex items-start gap-2 p-3 rounded-lg border bg-card transition-colors',
                    'hover:border-primary/30',
                    disabled && 'opacity-60'
                )}
            >
                {/* Drag Handle */}
                <div className="flex items-center h-9 cursor-grab text-muted-foreground hover:text-foreground">
                    <GripVertical className="h-4 w-4" />
                </div>

                {/* Field Select */}
                <div className="flex-1 min-w-0 space-y-1">
                    <Select
                        value={filter.field_path}
                        onValueChange={handleFieldChange}
                        disabled={disabled}
                    >
                        <SelectTrigger className="w-full">
                            <SelectValue placeholder="Feld wählen..." />
                        </SelectTrigger>
                        <SelectContent>
                            {fields.map((field) => (
                                <SelectItem key={field.path} value={field.path}>
                                    <div className="flex items-center gap-2">
                                        <span>{field.display_name}</span>
                                        <Badge variant="outline" className="text-xs ml-auto">
                                            {dataTypeLabels[field.data_type]}
                                        </Badge>
                                    </div>
                                </SelectItem>
                            ))}
                        </SelectContent>
                    </Select>
                    {selectedField && (
                        <p className="text-xs text-muted-foreground truncate">
                            {selectedField.path}
                        </p>
                    )}
                </div>

                {/* Operator Select */}
                <div className="w-44">
                    <Select
                        value={filter.operator}
                        onValueChange={handleOperatorChange}
                        disabled={disabled || !filter.field_path}
                    >
                        <SelectTrigger>
                            <SelectValue placeholder="Operator..." />
                        </SelectTrigger>
                        <SelectContent>
                            {availableOperators.map((op) => (
                                <SelectItem key={op.operator} value={op.operator}>
                                    {operatorLabels[op.operator] || op.name}
                                </SelectItem>
                            ))}
                        </SelectContent>
                    </Select>
                </div>

                {/* Value Input */}
                <div className="flex-1 min-w-0">
                    <FilterValueInput
                        dataType={filter.value_type}
                        operator={filter.operator}
                        value={filter.value}
                        onChange={handleValueChange}
                        disabled={disabled || !filter.field_path}
                    />
                </div>

                {/* Delete Button */}
                <TooltipProvider>
                    <Tooltip>
                        <TooltipTrigger asChild>
                            <Button
                                variant="ghost"
                                size="icon"
                                className="h-9 w-9 text-muted-foreground hover:text-destructive"
                                onClick={onDelete}
                                disabled={disabled}
                            >
                                <Trash2 className="h-4 w-4" />
                            </Button>
                        </TooltipTrigger>
                        <TooltipContent>Filter entfernen</TooltipContent>
                    </Tooltip>
                </TooltipProvider>
            </div>
        </div>
    );
}

export default FilterRow;
