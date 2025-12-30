/**
 * SearchPanel - Controlled Search Component
 *
 * URL-synchronisierte Suchkomponente fuer die Dokumentensuche.
 * Akzeptiert kontrollierte Props statt internem State.
 *
 * @example
 * ```tsx
 * <SearchPanel
 *   value={{ query: 'rechnung', mode: 'hybrid', filters: {...} }}
 *   onChange={(updates) => updateURL(updates)}
 *   onReset={() => clearURL()}
 * />
 * ```
 */

import { useEffect, useState, useCallback } from 'react';
import {
    Calendar,
    FileType,
    CheckCircle2,
    Sparkles,
    FileText,
    Layers,
    Bookmark,
} from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Checkbox } from '@/components/ui/checkbox';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { cn } from '@/lib/utils';
import { motion } from 'framer-motion';
import { motionTokens } from '@/lib/motion-tokens';
import { useSavedSearches } from '../hooks/use-saved-searches';
import { useRecentSearches } from '../hooks/use-recent-searches';
import { generateSearchName, type SavedSearch } from '../types/saved-search';
import type { SearchParams } from '../types/search-params';
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { SearchAutocomplete } from './SearchAutocomplete';

// ==================== Types ====================

interface SearchFilters {
    type: string[];
    ocrStatus: string[];
    dateRange: string;
}

interface SearchPanelValue {
    query: string;
    mode: string;
    filters: SearchFilters;
}

interface SearchPanelProps {
    /** Aktuelle Suchwerte (kontrolliert) */
    value: SearchPanelValue;
    /** Callback wenn sich Werte aendern */
    onChange: (updates: Partial<SearchPanelValue>) => void;
    /** Callback um alle Filter zurueckzusetzen */
    onReset?: () => void;
}

// ==================== Debounce Hook ====================

function useDebounce<T>(value: T, delay: number): T {
    const [debouncedValue, setDebouncedValue] = useState<T>(value);
    useEffect(() => {
        const handler = setTimeout(() => setDebouncedValue(value), delay);
        return () => clearTimeout(handler);
    }, [value, delay]);
    return debouncedValue;
}

// ==================== Components ====================

const MotionDiv = motion.div;

export function SearchPanel({ value, onChange, onReset }: SearchPanelProps) {
    // Local state for input (debounced before sending to parent)
    const [localQuery, setLocalQuery] = useState(value.query);
    const debouncedQuery = useDebounce(localQuery, 300);

    // Sync local query when prop changes (e.g., from URL)
    useEffect(() => {
        setLocalQuery(value.query);
    }, [value.query]);

    // Notify parent of debounced query changes
    useEffect(() => {
        if (debouncedQuery !== value.query) {
            onChange({ query: debouncedQuery });
        }
    }, [debouncedQuery, value.query, onChange]);

    // Save Search Dialog
    const [showSaveDialog, setShowSaveDialog] = useState(false);
    const [saveName, setSaveName] = useState('');
    const { saveSearch, isLimitReached } = useSavedSearches();
    const { addRecentSearch } = useRecentSearches();

    // Handle search from autocomplete
    const handleSearch = useCallback(
        (query: string) => {
            setLocalQuery(query);
            onChange({ query });
            addRecentSearch(query);
        },
        [onChange, addRecentSearch]
    );

    const handleSaveSearch = () => {
        const currentParams: SearchParams = {
            q: value.query,
            mode: value.mode as SearchParams['mode'],
            type: value.filters.type as SearchParams['type'],
            ocrStatus: value.filters.ocrStatus as SearchParams['ocrStatus'],
            dateRange: value.filters.dateRange as SearchParams['dateRange'],
        };

        saveSearch({
            name: saveName || generateSearchName(currentParams),
            params: currentParams,
        });

        setShowSaveDialog(false);
        setSaveName('');
    };

    const updateFilter = useCallback(
        (key: keyof SearchFilters, filterValue: string | string[]) => {
            onChange({
                filters: { ...value.filters, [key]: filterValue },
            });
        },
        [value.filters, onChange]
    );

    const hasActiveFilters =
        value.filters.type.length > 0 ||
        value.filters.ocrStatus.length > 0 ||
        value.filters.dateRange !== 'all';

    const canSaveSearch = value.query.trim() || hasActiveFilters;

    return (
        <div
            className="space-y-4 w-full max-w-4xl mx-auto"
            role="search"
            aria-label="Dokumentensuche"
        >
            {/* Search Bar */}
            <div className="relative group">
                <div
                    className="absolute inset-0 bg-gradient-to-r from-primary/20 to-accent/20 rounded-xl blur-xl opacity-0 group-hover:opacity-100 transition-opacity duration-500"
                    aria-hidden="true"
                />
                <div className="relative flex items-center bg-background/80 backdrop-blur-xl border rounded-xl shadow-sm focus-within:shadow-md focus-within:border-primary/50 transition-all overflow-hidden">
                    {/* SearchAutocomplete mit Vorschlaegen und letzten Suchen */}
                    <div className="flex-1">
                        <SearchAutocomplete
                            value={localQuery}
                            onChange={setLocalQuery}
                            onSearch={handleSearch}
                            placeholder="Dokumente durchsuchen (Volltext & Semantisch)..."
                            className="[&_input]:border-none [&_input]:shadow-none [&_input]:focus-visible:ring-0 [&_input]:bg-transparent"
                        />
                    </div>
                    <div className="pr-2 flex items-center gap-2">
                        {/* Save Search Button */}
                        {canSaveSearch && (
                            <Button
                                variant="ghost"
                                size="icon"
                                className="h-9 w-9"
                                onClick={() => setShowSaveDialog(true)}
                                disabled={isLimitReached}
                                title="Suche speichern"
                            >
                                <Bookmark className="w-4 h-4" />
                            </Button>
                        )}
                        <div className="h-8 w-px bg-border mx-2" />
                        <ToggleGroup
                            type="single"
                            value={value.mode}
                            onValueChange={(v) => v && onChange({ mode: v })}
                            className="bg-muted/50 p-1 rounded-lg"
                        >
                            <ToggleGroupItem
                                value="fulltext"
                                size="sm"
                                aria-label="Volltext"
                                className="data-[state=on]:bg-background data-[state=on]:shadow-sm"
                            >
                                <FileText className="w-4 h-4 mr-2" /> Text
                            </ToggleGroupItem>
                            <ToggleGroupItem
                                value="semantic"
                                size="sm"
                                aria-label="Semantisch"
                                className="data-[state=on]:bg-background data-[state=on]:shadow-sm"
                            >
                                <Sparkles className="w-4 h-4 mr-2" /> KI
                            </ToggleGroupItem>
                            <ToggleGroupItem
                                value="hybrid"
                                size="sm"
                                aria-label="Hybrid"
                                className="data-[state=on]:bg-background data-[state=on]:shadow-sm"
                            >
                                <Layers className="w-4 h-4 mr-2" /> Hybrid
                            </ToggleGroupItem>
                        </ToggleGroup>
                    </div>
                </div>
            </div>

            {/* Filters */}
            <MotionDiv
                initial={{ opacity: 0, y: -10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={motionTokens.spring.gentle}
                className="flex gap-3 flex-wrap"
            >
                <FilterDropdown
                    icon={FileType}
                    label="Dokumenttyp"
                    options={[
                        { id: 'pdf', label: 'PDF Dokumente' },
                        { id: 'image', label: 'Bilder (PNG/JPG)' },
                        { id: 'office', label: 'Office Dateien' },
                    ]}
                    selected={value.filters.type}
                    onChange={(v) => updateFilter('type', v)}
                />

                <FilterDropdown
                    icon={CheckCircle2}
                    label="OCR Status"
                    options={[
                        { id: 'completed', label: 'Verarbeitet' },
                        { id: 'pending', label: 'In Bearbeitung' },
                        { id: 'failed', label: 'Fehlerhaft' },
                    ]}
                    selected={value.filters.ocrStatus}
                    onChange={(v) => updateFilter('ocrStatus', v)}
                />

                <FilterDropdown
                    icon={Calendar}
                    label="Zeitraum"
                    options={[
                        { id: 'today', label: 'Heute' },
                        { id: 'week', label: 'Diese Woche' },
                        { id: 'month', label: 'Dieser Monat' },
                        { id: 'year', label: 'Dieses Jahr' },
                    ]}
                    selected={value.filters.dateRange}
                    onChange={(v) => updateFilter('dateRange', v)}
                    single
                />

                {hasActiveFilters && onReset && (
                    <Button
                        variant="ghost"
                        size="sm"
                        onClick={onReset}
                        className="text-muted-foreground hover:text-destructive"
                    >
                        Filter zuruecksetzen
                    </Button>
                )}
            </MotionDiv>

            {/* Save Search Dialog */}
            <Dialog open={showSaveDialog} onOpenChange={setShowSaveDialog}>
                <DialogContent>
                    <DialogHeader>
                        <DialogTitle>Suche speichern</DialogTitle>
                        <DialogDescription>
                            Speichern Sie diese Suche fuer schnellen Zugriff in der Sidebar.
                        </DialogDescription>
                    </DialogHeader>
                    <div className="grid gap-4 py-4">
                        <div className="grid gap-2">
                            <Label htmlFor="search-name">Name</Label>
                            <Input
                                id="search-name"
                                value={saveName}
                                onChange={(e) => setSaveName(e.target.value)}
                                placeholder={generateSearchName({
                                    q: value.query,
                                    mode: value.mode as SearchParams['mode'],
                                    type: value.filters.type as SearchParams['type'],
                                    ocrStatus: value.filters.ocrStatus as SearchParams['ocrStatus'],
                                    dateRange: value.filters.dateRange as SearchParams['dateRange'],
                                })}
                            />
                        </div>
                    </div>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setShowSaveDialog(false)}>
                            Abbrechen
                        </Button>
                        <Button onClick={handleSaveSearch}>Speichern</Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    );
}

// ==================== Filter Dropdown ====================

interface FilterDropdownProps {
    icon: React.ElementType;
    label: string;
    options: { id: string; label: string }[];
    selected: string[] | string;
    onChange: (value: string | string[]) => void;
    single?: boolean;
}

function FilterDropdown({
    icon: Icon,
    label,
    options,
    selected,
    onChange,
    single,
}: FilterDropdownProps) {
    const isSelected = single ? selected !== 'all' : (selected as string[]).length > 0;
    const count = single ? 0 : (selected as string[]).length;

    return (
        <Popover>
            <PopoverTrigger asChild>
                <Button
                    variant="outline"
                    size="sm"
                    className={cn(
                        'h-9 border-dashed',
                        isSelected && 'border-primary bg-primary/5 text-primary border-solid'
                    )}
                >
                    <Icon className="w-4 h-4 mr-2" />
                    {label}
                    {count > 0 && (
                        <Badge
                            variant="secondary"
                            className="ml-2 h-5 px-1.5 rounded-sm bg-primary/10 text-primary hover:bg-primary/20"
                        >
                            {count}
                        </Badge>
                    )}
                </Button>
            </PopoverTrigger>
            <PopoverContent className="w-56 p-2" align="start">
                <div className="space-y-1">
                    {options.map((option) => {
                        const checked = single
                            ? selected === option.id
                            : (selected as string[]).includes(option.id);
                        return (
                            <div
                                key={option.id}
                                className="flex items-center gap-2 px-2 py-1.5 hover:bg-muted rounded-sm cursor-pointer"
                                onClick={() => {
                                    if (single) {
                                        onChange(checked ? 'all' : option.id);
                                    } else {
                                        const newSelected = checked
                                            ? (selected as string[]).filter((id) => id !== option.id)
                                            : [...(selected as string[]), option.id];
                                        onChange(newSelected);
                                    }
                                }}
                            >
                                <Checkbox checked={checked} />
                                <span className="text-sm">{option.label}</span>
                            </div>
                        );
                    })}
                </div>
            </PopoverContent>
        </Popover>
    );
}

export default SearchPanel;
