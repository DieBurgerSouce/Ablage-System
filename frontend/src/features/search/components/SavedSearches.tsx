/**
 * SavedSearches - Gespeicherte Suchen Komponente
 *
 * Zeigt gespeicherte Suchen als Chips an und ermoeglicht deren Auswahl.
 */

import { useState } from 'react';
import { Bookmark, X, MoreHorizontal, Pin, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuSeparator,
    DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
    Collapsible,
    CollapsibleContent,
    CollapsibleTrigger,
} from '@/components/ui/collapsible';
import { cn } from '@/lib/utils';
import { useSavedSearches } from '../hooks/use-saved-searches';
import type { SearchParams } from '../types/search-params';
import type { SavedSearch } from '../types/saved-search';

// ==================== Types ====================

interface SavedSearchesProps {
    /** Aktuelle Suchparameter (fuer Highlighting) */
    currentParams: SearchParams;
    /** Callback wenn eine Suche ausgewaehlt wird */
    onSelectSearch: (params: SearchParams) => void;
}

// ==================== Component ====================

export function SavedSearches({ currentParams, onSelectSearch }: SavedSearchesProps) {
    const { savedSearches, pinnedSearches, deleteSearch, togglePin, recordAccess } =
        useSavedSearches();
    const [isOpen, setIsOpen] = useState(true);

    if (savedSearches.length === 0) {
        return null;
    }

    const handleSelectSearch = (search: SavedSearch) => {
        recordAccess(search.id);
        onSelectSearch(search.params);
    };

    const isCurrentSearch = (search: SavedSearch): boolean => {
        return (
            search.params.q === currentParams.q &&
            search.params.mode === currentParams.mode &&
            JSON.stringify(search.params.type) === JSON.stringify(currentParams.type) &&
            JSON.stringify(search.params.ocrStatus) === JSON.stringify(currentParams.ocrStatus) &&
            search.params.dateRange === currentParams.dateRange
        );
    };

    return (
        <Collapsible open={isOpen} onOpenChange={setIsOpen}>
            <div className="flex items-center justify-between">
                <CollapsibleTrigger asChild>
                    <Button variant="ghost" size="sm" className="gap-2 text-muted-foreground">
                        <Bookmark className="w-4 h-4" />
                        Gespeicherte Suchen
                        <Badge variant="secondary" className="ml-1">
                            {savedSearches.length}
                        </Badge>
                    </Button>
                </CollapsibleTrigger>
            </div>

            <CollapsibleContent className="mt-2">
                <div className="flex flex-wrap gap-2">
                    {/* Pinned searches first */}
                    {pinnedSearches.map((search) => (
                        <SavedSearchChip
                            key={search.id}
                            search={search}
                            isActive={isCurrentSearch(search)}
                            onSelect={() => handleSelectSearch(search)}
                            onDelete={() => deleteSearch(search.id)}
                            onTogglePin={() => togglePin(search.id)}
                        />
                    ))}

                    {/* Then non-pinned */}
                    {savedSearches
                        .filter((s) => !s.pinned)
                        .map((search) => (
                            <SavedSearchChip
                                key={search.id}
                                search={search}
                                isActive={isCurrentSearch(search)}
                                onSelect={() => handleSelectSearch(search)}
                                onDelete={() => deleteSearch(search.id)}
                                onTogglePin={() => togglePin(search.id)}
                            />
                        ))}
                </div>
            </CollapsibleContent>
        </Collapsible>
    );
}

// ==================== Chip Component ====================

interface SavedSearchChipProps {
    search: SavedSearch;
    isActive: boolean;
    onSelect: () => void;
    onDelete: () => void;
    onTogglePin: () => void;
}

function SavedSearchChip({
    search,
    isActive,
    onSelect,
    onDelete,
    onTogglePin,
}: SavedSearchChipProps) {
    return (
        <div
            className={cn(
                'group flex items-center gap-1 px-3 py-1.5 rounded-full border transition-colors',
                'hover:bg-muted/50 cursor-pointer',
                isActive && 'bg-primary/10 border-primary text-primary',
                search.pinned && !isActive && 'border-amber-500/50 bg-amber-500/5'
            )}
        >
            {search.pinned && <Pin className="w-3 h-3 text-amber-500" />}
            <span className="text-sm" onClick={onSelect}>
                {search.name}
            </span>

            <DropdownMenu>
                <DropdownMenuTrigger asChild>
                    <Button
                        variant="ghost"
                        size="icon"
                        className="h-5 w-5 opacity-0 group-hover:opacity-100 transition-opacity"
                    >
                        <MoreHorizontal className="w-3 h-3" />
                    </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                    <DropdownMenuItem onClick={onTogglePin}>
                        <Pin className="w-4 h-4 mr-2" />
                        {search.pinned ? 'Loesung' : 'Anpinnen'}
                    </DropdownMenuItem>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem
                        onClick={onDelete}
                        className="text-destructive focus:text-destructive"
                    >
                        <Trash2 className="w-4 h-4 mr-2" />
                        Loeschen
                    </DropdownMenuItem>
                </DropdownMenuContent>
            </DropdownMenu>
        </div>
    );
}

export default SavedSearches;
