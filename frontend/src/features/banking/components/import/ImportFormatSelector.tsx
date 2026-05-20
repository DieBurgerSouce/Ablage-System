/**
 * Import Format Selector
 * Auswahl des Importformats für Banktransaktionen
 */

import { Label } from '@/components/ui/label';
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select';
import type { ImportFormat } from '@/lib/api/services/banking';

interface ImportFormatSelectorProps {
    value: ImportFormat;
    onChange: (value: ImportFormat) => void;
}

const FORMAT_OPTIONS: { value: ImportFormat; label: string; description: string }[] = [
    {
        value: 'mt940',
        label: 'MT940 (SWIFT)',
        description: 'Standard Bankauszugsformat',
    },
    {
        value: 'camt053',
        label: 'CAMT.053 (ISO 20022)',
        description: 'Modernes XML-Format',
    },
    {
        value: 'csv_sparkasse',
        label: 'CSV Sparkasse',
        description: 'Sparkassen CSV-Export',
    },
    {
        value: 'csv_volksbank',
        label: 'CSV Volksbank',
        description: 'Volksbank CSV-Export',
    },
    {
        value: 'csv_generic',
        label: 'CSV Generisch',
        description: 'Standard CSV mit Kopfzeile',
    },
];

export function ImportFormatSelector({ value, onChange }: ImportFormatSelectorProps) {
    return (
        <div className="space-y-2">
            <Label>Importformat</Label>
            <Select value={value} onValueChange={onChange}>
                <SelectTrigger>
                    <SelectValue placeholder="Format wählen..." />
                </SelectTrigger>
                <SelectContent>
                    {FORMAT_OPTIONS.map((option) => (
                        <SelectItem key={option.value} value={option.value}>
                            <div className="flex flex-col">
                                <span>{option.label}</span>
                                <span className="text-xs text-muted-foreground">
                                    {option.description}
                                </span>
                            </div>
                        </SelectItem>
                    ))}
                </SelectContent>
            </Select>
        </div>
    );
}
