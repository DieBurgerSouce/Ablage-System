import { Check, FileEdit, Loader2 } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import type { RenameSuggestion } from '../types';

interface RenameSuggestionBadgeProps {
    /** Rename-Vorschlag aus der Quick Classification */
    suggestion: RenameSuggestion;
    /** Callback wenn Benutzer Umbenennung bestätigt */
    onConfirm: () => void;
    /** Wurde die Umbenennung bereits bestätigt? */
    isConfirmed?: boolean;
    /** Läuft gerade die Bestätigung? */
    isLoading?: boolean;
}

/**
 * RenameSuggestionBadge - Zeigt Rename-Vorschlag mit Bestätigungs-Button
 *
 * Wird nur für Eingangsrechnungen angezeigt.
 * Schema: Lieferantenname_Rechnungsnummer
 */
export function RenameSuggestionBadge({
    suggestion,
    onConfirm,
    isConfirmed = false,
    isLoading = false,
}: RenameSuggestionBadgeProps) {
    // Bereits umbenannt (entweder im Backend oder gerade bestätigt)
    if (suggestion.applied || isConfirmed) {
        return (
            <Badge
                variant="outline"
                className="gap-1 bg-emerald-500/10 text-emerald-600 border-emerald-500/30 dark:text-emerald-400"
            >
                <Check className="w-3 h-3" />
                Umbenannt
            </Badge>
        );
    }

    // Vorschlag anzeigen mit Bestätigungs-Button
    return (
        <div className="flex items-center gap-1">
            <Badge
                variant="outline"
                className={cn(
                    "gap-1 max-w-[200px]",
                    "bg-purple-500/10 text-purple-600 border-purple-500/30",
                    "dark:bg-purple-500/20 dark:text-purple-400 dark:border-purple-500/40"
                )}
                title={`Vorschlag: ${suggestion.suggestedFilename}\nLieferant: ${suggestion.supplierName}\nRechnungsnr: ${suggestion.invoiceNumber}\nQuelle: ${suggestion.source === 'entity_match' ? 'Erkannter Lieferant' : 'OCR-Extraktion'}`}
            >
                <FileEdit className="w-3 h-3 flex-shrink-0" />
                <span className="truncate">{suggestion.suggestedFilename}</span>
            </Badge>
            <Button
                variant="ghost"
                size="icon"
                className={cn(
                    "h-6 w-6",
                    "text-purple-600 hover:text-purple-700 hover:bg-purple-100",
                    "dark:text-purple-400 dark:hover:text-purple-300 dark:hover:bg-purple-900/30"
                )}
                onClick={(e) => {
                    e.stopPropagation();
                    onConfirm();
                }}
                disabled={isLoading}
                title="Umbenennung bestätigen"
            >
                {isLoading ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                    <Check className="w-4 h-4" />
                )}
            </Button>
        </div>
    );
}
