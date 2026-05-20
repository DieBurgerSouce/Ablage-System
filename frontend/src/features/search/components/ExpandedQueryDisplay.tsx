/**
 * ExpandedQueryDisplay Component
 *
 * Zeigt die verwendeten Synonyme nach einer Suche an.
 * Hilft dem Benutzer zu verstehen, welche Begriffe gesucht wurden.
 */

import { Badge } from '@/components/ui/badge';
import { Languages, ChevronRight } from 'lucide-react';
import {
    Tooltip,
    TooltipContent,
    TooltipProvider,
    TooltipTrigger,
} from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';
import type { SynonymExpansion } from '../api/search-api';

interface ExpandedQueryDisplayProps {
    expansions: SynonymExpansion[];
    className?: string;
}

/**
 * Zeigt welche Synonyme in der Suche verwendet wurden.
 *
 * Beispiel: "Rechnung" -> "Invoice, Faktura, Abrechnung"
 */
export function ExpandedQueryDisplay({ expansions, className }: ExpandedQueryDisplayProps) {
    if (!expansions || expansions.length === 0) {
        return null;
    }

    return (
        <div
            className={cn(
                'flex flex-wrap items-center gap-2 p-3 rounded-lg',
                'bg-blue-50/50 border border-blue-100 dark:bg-blue-950/20 dark:border-blue-900/30',
                className
            )}
        >
            <div className="flex items-center gap-1.5 text-blue-600 dark:text-blue-400 shrink-0">
                <Languages className="h-4 w-4" />
                <span className="text-sm font-medium">Synonyme:</span>
            </div>

            <div className="flex flex-wrap items-center gap-2">
                {expansions.map((expansion, index) => (
                    <TooltipProvider key={index}>
                        <Tooltip>
                            <TooltipTrigger asChild>
                                <div className="flex items-center gap-1">
                                    <Badge
                                        variant="secondary"
                                        className="bg-white dark:bg-gray-800 text-blue-700 dark:text-blue-300 border border-blue-200 dark:border-blue-800"
                                    >
                                        {expansion.original}
                                    </Badge>
                                    <ChevronRight className="h-3 w-3 text-muted-foreground" />
                                    <div className="flex gap-1">
                                        {expansion.synonyms.slice(0, 3).map((syn, synIndex) => (
                                            <Badge
                                                key={synIndex}
                                                variant="outline"
                                                className="text-xs bg-blue-50/80 dark:bg-blue-900/30 border-blue-200 dark:border-blue-800"
                                            >
                                                {syn}
                                            </Badge>
                                        ))}
                                        {expansion.synonyms.length > 3 && (
                                            <Badge
                                                variant="outline"
                                                className="text-xs text-muted-foreground"
                                            >
                                                +{expansion.synonyms.length - 3}
                                            </Badge>
                                        )}
                                    </div>
                                </div>
                            </TooltipTrigger>
                            <TooltipContent side="bottom" className="max-w-xs">
                                <div className="space-y-1">
                                    <p className="font-medium">
                                        "{expansion.original}" wurde erweitert um:
                                    </p>
                                    <p className="text-sm text-muted-foreground">
                                        {expansion.synonyms.join(', ')}
                                    </p>
                                </div>
                            </TooltipContent>
                        </Tooltip>
                    </TooltipProvider>
                ))}
            </div>
        </div>
    );
}

export default ExpandedQueryDisplay;
