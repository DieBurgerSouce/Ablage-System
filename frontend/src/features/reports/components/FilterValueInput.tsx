/**
 * FilterValueInput Component
 *
 * Typ-spezifische Eingabefelder für Filter-Werte.
 * Unterstützt: Text, Zahl, Datum, Währung, Boolean, Arrays
 */

import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import { Calendar } from '@/components/ui/calendar';
import {
    Popover,
    PopoverContent,
    PopoverTrigger,
} from '@/components/ui/popover';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { CalendarIcon, X } from 'lucide-react';
import { format } from 'date-fns';
import { de } from 'date-fns/locale';
import { cn } from '@/lib/utils';
import type { DataType, FilterOperator } from '../types';

interface FilterValueInputProps {
    dataType: DataType;
    operator: FilterOperator;
    value: string | number | boolean | string[] | number[] | undefined;
    onChange: (value: string | number | boolean | string[] | number[] | undefined) => void;
    placeholder?: string;
    disabled?: boolean;
}

/**
 * Dynamische Eingabe basierend auf Datentyp und Operator.
 */
export function FilterValueInput({
    dataType,
    operator,
    value,
    onChange,
    placeholder,
    disabled = false,
}: FilterValueInputProps) {
    // Keine Eingabe für is_null / is_not_null
    if (operator === 'is_null' || operator === 'is_not_null') {
        return (
            <div className="text-xs text-muted-foreground italic px-2 py-1.5">
                Kein Wert erforderlich
            </div>
        );
    }

    // Between braucht zwei Werte
    if (operator === 'between') {
        return (
            <BetweenInput
                dataType={dataType}
                value={value as [string | number, string | number] | undefined}
                onChange={onChange}
                disabled={disabled}
            />
        );
    }

    // In / Not In braucht Array
    if (operator === 'in' || operator === 'not_in') {
        return (
            <ArrayInput
                dataType={dataType}
                value={(value as string[] | number[]) || []}
                onChange={onChange}
                placeholder={placeholder}
                disabled={disabled}
            />
        );
    }

    // Standard-Eingaben basierend auf Datentyp
    switch (dataType) {
        case 'boolean':
            return (
                <div className="flex items-center gap-2">
                    <Switch
                        checked={Boolean(value)}
                        onCheckedChange={(checked) => onChange(checked)}
                        disabled={disabled}
                    />
                    <span className="text-sm text-muted-foreground">
                        {value ? 'Ja' : 'Nein'}
                    </span>
                </div>
            );

        case 'date':
            return (
                <DateInput
                    value={value as string | undefined}
                    onChange={onChange}
                    placeholder={placeholder}
                    disabled={disabled}
                />
            );

        case 'number':
        case 'currency':
            return (
                <Input
                    type="number"
                    value={value !== undefined ? String(value) : ''}
                    onChange={(e) => {
                        const val = e.target.value;
                        onChange(val === '' ? undefined : parseFloat(val));
                    }}
                    placeholder={placeholder || (dataType === 'currency' ? '0.00' : '0')}
                    step={dataType === 'currency' ? '0.01' : '1'}
                    disabled={disabled}
                    className="w-full"
                />
            );

        case 'string':
        default:
            return (
                <Input
                    type="text"
                    value={String(value ?? '')}
                    onChange={(e) => onChange(e.target.value || undefined)}
                    placeholder={placeholder || 'Wert eingeben...'}
                    disabled={disabled}
                    className="w-full"
                />
            );
    }
}

/**
 * Datumseingabe mit Calendar-Popover.
 */
function DateInput({
    value,
    onChange,
    placeholder,
    disabled,
}: {
    value: string | undefined;
    onChange: (value: string | undefined) => void;
    placeholder?: string;
    disabled?: boolean;
}) {
    const date = value ? new Date(value) : undefined;

    return (
        <Popover>
            <PopoverTrigger asChild>
                <Button
                    variant="outline"
                    className={cn(
                        'w-full justify-start text-left font-normal',
                        !date && 'text-muted-foreground'
                    )}
                    disabled={disabled}
                >
                    <CalendarIcon className="mr-2 h-4 w-4" />
                    {date ? format(date, 'PPP', { locale: de }) : placeholder || 'Datum wählen...'}
                </Button>
            </PopoverTrigger>
            <PopoverContent className="w-auto p-0" align="start">
                <Calendar
                    mode="single"
                    selected={date}
                    onSelect={(d) => onChange(d ? d.toISOString().split('T')[0] : undefined)}
                    locale={de}
                    initialFocus
                />
            </PopoverContent>
        </Popover>
    );
}

/**
 * Between-Eingabe für Bereichsfilter (von - bis).
 */
function BetweenInput({
    dataType,
    value,
    onChange,
    disabled,
}: {
    dataType: DataType;
    value: [string | number, string | number] | undefined;
    onChange: (value: [string | number, string | number] | undefined) => void;
    disabled?: boolean;
}) {
    const [from, to] = value || ['', ''];

    const handleFromChange = (newFrom: string | number | undefined) => {
        if (newFrom === undefined && to === '') {
            onChange(undefined);
        } else {
            onChange([newFrom ?? '', to]);
        }
    };

    const handleToChange = (newTo: string | number | undefined) => {
        if (from === '' && newTo === undefined) {
            onChange(undefined);
        } else {
            onChange([from, newTo ?? '']);
        }
    };

    if (dataType === 'date') {
        return (
            <div className="flex items-center gap-2">
                <DateInput
                    value={from as string | undefined}
                    onChange={(v) => handleFromChange(v)}
                    placeholder="Von..."
                    disabled={disabled}
                />
                <span className="text-muted-foreground">-</span>
                <DateInput
                    value={to as string | undefined}
                    onChange={(v) => handleToChange(v)}
                    placeholder="Bis..."
                    disabled={disabled}
                />
            </div>
        );
    }

    const inputType = dataType === 'number' || dataType === 'currency' ? 'number' : 'text';

    return (
        <div className="flex items-center gap-2">
            <Input
                type={inputType}
                value={from !== '' ? String(from) : ''}
                onChange={(e) => {
                    const val = e.target.value;
                    handleFromChange(inputType === 'number' ? (val === '' ? undefined : parseFloat(val)) : val || undefined);
                }}
                placeholder="Von..."
                disabled={disabled}
                className="flex-1"
            />
            <span className="text-muted-foreground">-</span>
            <Input
                type={inputType}
                value={to !== '' ? String(to) : ''}
                onChange={(e) => {
                    const val = e.target.value;
                    handleToChange(inputType === 'number' ? (val === '' ? undefined : parseFloat(val)) : val || undefined);
                }}
                placeholder="Bis..."
                disabled={disabled}
                className="flex-1"
            />
        </div>
    );
}

/**
 * Array-Eingabe für in/not_in Operatoren.
 */
function ArrayInput({
    dataType,
    value,
    onChange,
    placeholder,
    disabled,
}: {
    dataType: DataType;
    value: string[] | number[];
    onChange: (value: string[] | number[]) => void;
    placeholder?: string;
    disabled?: boolean;
}) {
    const handleAddValue = (newValue: string) => {
        if (!newValue.trim()) return;

        const parsedValue = dataType === 'number' || dataType === 'currency'
            ? parseFloat(newValue)
            : newValue.trim();

        if (dataType === 'number' || dataType === 'currency') {
            if (isNaN(parsedValue as number)) return;
            if (!(value as number[]).includes(parsedValue as number)) {
                onChange([...(value as number[]), parsedValue as number]);
            }
        } else {
            if (!(value as string[]).includes(parsedValue as string)) {
                onChange([...(value as string[]), parsedValue as string]);
            }
        }
    };

    const handleRemoveValue = (index: number) => {
        const newValues = [...value];
        newValues.splice(index, 1);
        onChange(newValues as string[] | number[]);
    };

    return (
        <div className="space-y-2">
            <Input
                type={dataType === 'number' || dataType === 'currency' ? 'number' : 'text'}
                placeholder={placeholder || 'Wert eingeben und Enter drücken...'}
                disabled={disabled}
                onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                        e.preventDefault();
                        handleAddValue((e.target as HTMLInputElement).value);
                        (e.target as HTMLInputElement).value = '';
                    }
                }}
                className="w-full"
            />
            {value.length > 0 && (
                <div className="flex flex-wrap gap-1">
                    {value.map((v, index) => (
                        <Badge
                            key={index}
                            variant="secondary"
                            className="gap-1 cursor-pointer"
                            onClick={() => !disabled && handleRemoveValue(index)}
                        >
                            {String(v)}
                            {!disabled && <X className="h-3 w-3" />}
                        </Badge>
                    ))}
                </div>
            )}
        </div>
    );
}

export default FilterValueInput;
