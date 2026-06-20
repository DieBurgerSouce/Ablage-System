/**
 * SearchModeToggle Component
 *
 * Ermöglicht Umschaltung zwischen den Suchmodi:
 * - Dokument-Suche
 * - Chunk-Suche (RAG)
 * - Kombinierte Suche
 */

import { FileText, Layers, Combine } from 'lucide-react';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import {
    Tooltip,
    TooltipContent,
    TooltipProvider,
    TooltipTrigger,
} from '@/components/ui/tooltip';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import type { UnifiedSearchMode } from '../api/search-api';

// ==================== Types ====================

interface SearchModeToggleProps {
    value: UnifiedSearchMode;
    onChange: (value: UnifiedSearchMode) => void;
    disabled?: boolean;
    className?: string;
}

// ==================== Mode Config ====================

const MODES: Array<{
    id: UnifiedSearchMode;
    label: string;
    shortLabel: string;
    icon: typeof FileText;
    description: string;
}> = [
    {
        id: 'document',
        label: 'Dokument',
        shortLabel: 'Dok',
        icon: FileText,
        description: 'Durchsucht ganze Dokumente mit Volltext und semantischer Suche',
    },
    {
        id: 'chunk',
        label: 'Abschnitte',
        shortLabel: 'RAG',
        icon: Layers,
        description: 'Durchsucht einzelne Dokumenten-Abschnitte für präzisere Treffer',
    },
    {
        id: 'combined',
        label: 'Kombiniert',
        shortLabel: 'Alle',
        icon: Combine,
        description: 'Kombination aus Dokument- und Abschnitt-Suche (empfohlen)',
    },
];

// ==================== Component ====================

export function SearchModeToggle({
    value,
    onChange,
    disabled = false,
    className,
}: SearchModeToggleProps) {
    return (
        <TooltipProvider delayDuration={300}>
            <div className={cn('flex items-center gap-2', className)}>
                <ToggleGroup
                    type="single"
                    value={value}
                    onValueChange={(newValue) => {
                        if (newValue) {
                            onChange(newValue as UnifiedSearchMode);
                        }
                    }}
                    disabled={disabled}
                    className="border rounded-lg p-1 bg-muted/30"
                >
                    {MODES.map((mode) => (
                        <Tooltip key={mode.id}>
                            <TooltipTrigger asChild>
                                <ToggleGroupItem
                                    value={mode.id}
                                    aria-label={mode.label}
                                    className={cn(
                                        'flex items-center gap-1.5 px-3 py-1.5 text-sm',
                                        'data-[state=on]:bg-background data-[state=on]:shadow-sm',
                                        'transition-all'
                                    )}
                                >
                                    <mode.icon className="h-4 w-4" />
                                    <span className="hidden sm:inline">{mode.label}</span>
                                    <span className="sm:hidden">{mode.shortLabel}</span>
                                </ToggleGroupItem>
                            </TooltipTrigger>
                            <TooltipContent side="bottom" className="max-w-[250px]">
                                <p className="font-medium mb-1">{mode.label}</p>
                                <p className="text-xs text-muted-foreground">
                                    {mode.description}
                                </p>
                                {mode.id === 'combined' && (
                                    <Badge variant="secondary" className="mt-2 text-[10px]">
                                        Empfohlen
                                    </Badge>
                                )}
                            </TooltipContent>
                        </Tooltip>
                    ))}
                </ToggleGroup>
            </div>
        </TooltipProvider>
    );
}

export default SearchModeToggle;
