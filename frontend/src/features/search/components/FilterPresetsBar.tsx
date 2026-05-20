/**
 * FilterPresetsBar - Schnellfilter-Voreinstellungen
 *
 * Horizontale Chip-Leiste mit vorkonfigurierten Filtervoreinstellungen.
 * Ermöglicht schnellen Zugriff auf häufig verwendete Filter-Kombinationen.
 *
 * @example
 * ```tsx
 * <FilterPresetsBar
 *   activeFilters={{ status: 'open' }}
 *   onFilterChange={(filters) => applyFilters(filters)}
 * />
 * ```
 */

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
    FileText,
    Clock,
    TrendingUp,
    User,
    AlertCircle,
    Calendar,
    CheckCircle2,
    Tag,
} from 'lucide-react';
import { cn } from '@/lib/utils';

// ==================== Types ====================

export interface FilterPreset {
    /** Eindeutige ID */
    id: string;
    /** Anzeigename (Deutsch) */
    label: string;
    /** Optionales Icon */
    icon?: React.ReactNode;
    /** Filter-Werte die angewendet werden */
    filters: Record<string, string | number | boolean | string[]>;
    /** Badge-Farbe */
    variant?: 'default' | 'secondary' | 'destructive' | 'outline';
}

export interface FilterPresetsBarProps {
    /** Aktuell aktive Filter */
    activeFilters: Record<string, string | number | boolean | string[]>;
    /** Callback wenn Filter geändert werden */
    onFilterChange: (filters: Record<string, string | number | boolean | string[]>) => void;
    /** Zusätzliche CSS-Klassen */
    className?: string;
}

// ==================== Preset Definitions ====================

const DEFAULT_PRESETS: FilterPreset[] = [
    {
        id: 'open-invoices',
        label: 'Offene Rechnungen',
        icon: <FileText className="h-3 w-3" />,
        filters: { status: 'open', documentType: 'invoice' },
        variant: 'default',
    },
    {
        id: 'last-7-days',
        label: 'Letzte 7 Tage',
        icon: <Clock className="h-3 w-3" />,
        filters: { dateRange: '7d' },
        variant: 'secondary',
    },
    {
        id: 'high-amounts',
        label: 'Hohe Beträge',
        icon: <TrendingUp className="h-3 w-3" />,
        filters: { amountMin: 1000 },
        variant: 'secondary',
    },
    {
        id: 'my-documents',
        label: 'Meine Dokumente',
        icon: <User className="h-3 w-3" />,
        filters: { assignedTo: 'me' },
        variant: 'outline',
    },
    {
        id: 'overdue',
        label: 'Überfällig',
        icon: <AlertCircle className="h-3 w-3" />,
        filters: { status: 'overdue' },
        variant: 'destructive',
    },
    {
        id: 'this-month',
        label: 'Dieser Monat',
        icon: <Calendar className="h-3 w-3" />,
        filters: { dateRange: '30d' },
        variant: 'outline',
    },
    {
        id: 'completed',
        label: 'Verarbeitet',
        icon: <CheckCircle2 className="h-3 w-3" />,
        filters: { ocrStatus: ['completed'] },
        variant: 'outline',
    },
    {
        id: 'tagged',
        label: 'Mit Tags',
        icon: <Tag className="h-3 w-3" />,
        filters: { hasTags: true },
        variant: 'outline',
    },
];

// ==================== Helper Functions ====================

/**
 * Prüft ob ein Preset aktiv ist (alle Filter übereinstimmen)
 */
function isPresetActive(
    preset: FilterPreset,
    activeFilters: Record<string, string | number | boolean | string[]>
): boolean {
    return Object.entries(preset.filters).every(([key, value]) => {
        const activeValue = activeFilters[key];

        // Array-Vergleich
        if (Array.isArray(value) && Array.isArray(activeValue)) {
            return (
                value.length === activeValue.length &&
                value.every((v) => activeValue.includes(v))
            );
        }

        // Einfacher Wert-Vergleich
        return activeValue === value;
    });
}

// ==================== Component ====================

export function FilterPresetsBar({
    activeFilters,
    onFilterChange,
    className,
}: FilterPresetsBarProps) {
    const handlePresetClick = (preset: FilterPreset) => {
        const isActive = isPresetActive(preset, activeFilters);

        if (isActive) {
            // Preset deaktivieren - Filter entfernen
            const newFilters = { ...activeFilters };
            Object.keys(preset.filters).forEach((key) => {
                delete newFilters[key];
            });
            onFilterChange(newFilters);
        } else {
            // Preset aktivieren - Filter anwenden
            onFilterChange({
                ...activeFilters,
                ...preset.filters,
            });
        }
    };

    return (
        <div
            className={cn(
                'flex items-center gap-2 overflow-x-auto py-2 px-1',
                'scrollbar-thin scrollbar-thumb-muted scrollbar-track-transparent',
                className
            )}
            role="toolbar"
            aria-label="Schnellfilter"
        >
            <span className="text-xs font-medium text-muted-foreground whitespace-nowrap pr-2">
                Schnellfilter:
            </span>

            {DEFAULT_PRESETS.map((preset) => {
                const isActive = isPresetActive(preset, activeFilters);

                return (
                    <Button
                        key={preset.id}
                        variant={isActive ? 'default' : 'outline'}
                        size="sm"
                        onClick={() => handlePresetClick(preset)}
                        className={cn(
                            'h-8 gap-1.5 whitespace-nowrap transition-all',
                            isActive && 'shadow-sm',
                            !isActive && 'hover:bg-accent hover:text-accent-foreground'
                        )}
                        aria-pressed={isActive}
                        title={`Filter: ${preset.label}`}
                    >
                        {preset.icon}
                        <span className="text-xs">{preset.label}</span>
                    </Button>
                );
            })}
        </div>
    );
}

/**
 * Alternative Darstellung als Badge-Chips (kompakter)
 */
export function FilterPresetsBarCompact({
    activeFilters,
    onFilterChange,
    className,
}: FilterPresetsBarProps) {
    const handlePresetClick = (preset: FilterPreset) => {
        const isActive = isPresetActive(preset, activeFilters);

        if (isActive) {
            const newFilters = { ...activeFilters };
            Object.keys(preset.filters).forEach((key) => {
                delete newFilters[key];
            });
            onFilterChange(newFilters);
        } else {
            onFilterChange({
                ...activeFilters,
                ...preset.filters,
            });
        }
    };

    return (
        <div
            className={cn(
                'flex items-center gap-1.5 overflow-x-auto py-1.5 px-1',
                'scrollbar-thin scrollbar-thumb-muted scrollbar-track-transparent',
                className
            )}
            role="toolbar"
            aria-label="Schnellfilter"
        >
            {DEFAULT_PRESETS.map((preset) => {
                const isActive = isPresetActive(preset, activeFilters);

                return (
                    <Badge
                        key={preset.id}
                        variant={isActive ? 'default' : 'outline'}
                        className={cn(
                            'cursor-pointer gap-1 transition-all hover:scale-105',
                            'px-2.5 py-1',
                            isActive && 'shadow-sm'
                        )}
                        onClick={() => handlePresetClick(preset)}
                        role="button"
                        aria-pressed={isActive}
                        title={`Filter: ${preset.label}`}
                    >
                        {preset.icon}
                        <span className="text-xs">{preset.label}</span>
                    </Badge>
                );
            })}
        </div>
    );
}

export default FilterPresetsBar;
