import { useEffect, useState } from 'react';
import { Search, Calendar, FileType, CheckCircle2, Sparkles, FileText, Layers } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Checkbox } from '@/components/ui/checkbox';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { cn } from '@/lib/utils';
import { motion } from 'framer-motion';
import { motionTokens } from '@/lib/motion-tokens';

interface SearchFilters {
    type: string[];
    ocrStatus: string[];
    dateRange: string;
}

interface SearchPanelProps {
    onSearch: (params: { query: string; mode: string; filters: SearchFilters }) => void;
}

// Simple debounce hook
function useDebounce<T>(value: T, delay: number): T {
    const [debouncedValue, setDebouncedValue] = useState<T>(value);
    useEffect(() => {
        const handler = setTimeout(() => setDebouncedValue(value), delay);
        return () => clearTimeout(handler);
    }, [value, delay]);
    return debouncedValue;
}

const MotionDiv = motion.div;

export function SearchPanel({ onSearch }: SearchPanelProps) {
    const [query, setQuery] = useState('');
    const [searchMode, setSearchMode] = useState('hybrid');
    const [filters, setFilters] = useState<SearchFilters>({
        type: [],
        ocrStatus: [],
        dateRange: 'all'
    });

    const debouncedQuery = useDebounce(query, 300);

    useEffect(() => {
        onSearch({ query: debouncedQuery, mode: searchMode, filters });
    }, [debouncedQuery, searchMode, filters, onSearch]);

    const updateFilter = (key: keyof SearchFilters, value: string | string[] | Date | undefined) => {
        setFilters(prev => ({ ...prev, [key]: value }));
    };

    return (
        <div className="space-y-4 w-full max-w-4xl mx-auto">
            {/* Search Bar */}
            <div className="relative group">
                <div className="absolute inset-0 bg-gradient-to-r from-primary/20 to-accent/20 rounded-xl blur-xl opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
                <div className="relative flex items-center bg-background/80 backdrop-blur-xl border rounded-xl shadow-sm focus-within:shadow-md focus-within:border-primary/50 transition-all overflow-hidden">
                    <div className="pl-4 text-muted-foreground">
                        <Search className="w-5 h-5" />
                    </div>
                    <Input
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                        placeholder="Dokumente durchsuchen (Volltext & Semantisch)..."
                        className="border-none shadow-none focus-visible:ring-0 h-14 text-lg bg-transparent"
                    />
                    <div className="pr-2 flex items-center gap-2">
                        <div className="h-8 w-px bg-border mx-2" />
                        <ToggleGroup type="single" value={searchMode} onValueChange={(v) => v && setSearchMode(v)} className="bg-muted/50 p-1 rounded-lg">
                            <ToggleGroupItem value="fulltext" size="sm" aria-label="Volltext" className="data-[state=on]:bg-background data-[state=on]:shadow-sm">
                                <FileText className="w-4 h-4 mr-2" /> Text
                            </ToggleGroupItem>
                            <ToggleGroupItem value="semantic" size="sm" aria-label="Semantisch" className="data-[state=on]:bg-background data-[state=on]:shadow-sm">
                                <Sparkles className="w-4 h-4 mr-2" /> KI
                            </ToggleGroupItem>
                            <ToggleGroupItem value="hybrid" size="sm" aria-label="Hybrid" className="data-[state=on]:bg-background data-[state=on]:shadow-sm">
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
                        { id: 'office', label: 'Office Dateien' }
                    ]}
                    selected={filters.type}
                    onChange={(v) => updateFilter('type', v)}
                />

                <FilterDropdown
                    icon={CheckCircle2}
                    label="OCR Status"
                    options={[
                        { id: 'completed', label: 'Verarbeitet' },
                        { id: 'pending', label: 'In Bearbeitung' },
                        { id: 'failed', label: 'Fehlerhaft' }
                    ]}
                    selected={filters.ocrStatus}
                    onChange={(v) => updateFilter('ocrStatus', v)}
                />

                <FilterDropdown
                    icon={Calendar}
                    label="Zeitraum"
                    options={[
                        { id: 'today', label: 'Heute' },
                        { id: 'week', label: 'Diese Woche' },
                        { id: 'month', label: 'Dieser Monat' },
                        { id: 'year', label: 'Dieses Jahr' }
                    ]}
                    selected={filters.dateRange}
                    onChange={(v) => updateFilter('dateRange', v)} // Single select for date
                    single
                />

                {(filters.type.length > 0 || filters.ocrStatus.length > 0 || filters.dateRange !== 'all') && (
                    <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setFilters({ type: [], ocrStatus: [], dateRange: 'all' })}
                        className="text-muted-foreground hover:text-destructive"
                    >
                        Filter zurücksetzen
                    </Button>
                )}

            </MotionDiv>
        </div >
    );
}

interface FilterDropdownProps {
    icon: React.ElementType;
    label: string;
    options: { id: string; label: string }[];
    selected: string[] | string;
    onChange: (value: string | string[]) => void;
    single?: boolean;
}

function FilterDropdown({ icon: Icon, label, options, selected, onChange, single }: FilterDropdownProps) {
    const isSelected = single ? selected !== 'all' : (selected as string[]).length > 0;
    const count = single ? 0 : (selected as string[]).length;

    return (
        <Popover>
            <PopoverTrigger asChild>
                <Button variant="outline" size="sm" className={cn("h-9 border-dashed", isSelected && "border-primary bg-primary/5 text-primary border-solid")}>
                    <Icon className="w-4 h-4 mr-2" />
                    {label}
                    {count > 0 && (
                        <Badge variant="secondary" className="ml-2 h-5 px-1.5 rounded-sm bg-primary/10 text-primary hover:bg-primary/20">
                            {count}
                        </Badge>
                    )}
                </Button>
            </PopoverTrigger>
            <PopoverContent className="w-56 p-2" align="start">
                <div className="space-y-1">
                    {options.map((option) => {
                        const checked = single ? selected === option.id : (selected as string[]).includes(option.id);
                        return (
                            <div
                                key={option.id}
                                className="flex items-center gap-2 px-2 py-1.5 hover:bg-muted rounded-sm cursor-pointer"
                                onClick={() => {
                                    if (single) {
                                        onChange(checked ? 'all' : option.id);
                                    } else {
                                        const newSelected = checked
                                            ? (selected as string[]).filter(id => id !== option.id)
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
