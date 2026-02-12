/**
 * CrossCompanyPage Component
 *
 * Hauptseite für die Cross-Company Übersicht.
 * Zeigt Entities mit Präsenz in beiden Firmen (Folie & Messer).
 */

import { useState, useCallback, useEffect, memo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Layers, Search, Filter, Building2, ChevronLeft, ChevronRight } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import {
    fetchCrossCompanyEntities,
    relationshipsQueryKeys,
    type CrossCompanyParams,
    type EntityType,
} from '../api/relationships-api';
import { CompanyComparisonCard } from './CompanyComparisonCard';
import { CrossCompanyTable } from './CrossCompanyTable';

const PAGE_SIZE = 50;

/**
 * Debounced Search Input
 */
const SearchInput = memo(function SearchInput({
    value,
    onChange,
}: {
    value: string;
    onChange: (value: string) => void;
}) {
    return (
        <div className="relative max-w-md">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
                placeholder="Suche nach Name oder Nummer..."
                value={value}
                onChange={(e) => onChange(e.target.value)}
                className="pl-10"
            />
        </div>
    );
});

/**
 * CrossCompanyPage - Übersicht der Geschäftspartner in mehreren Firmen.
 */
export function CrossCompanyPage() {
    // Filter State
    const [searchQuery, setSearchQuery] = useState('');
    const [debouncedSearch, setDebouncedSearch] = useState('');
    const [entityType, setEntityType] = useState<EntityType | 'all'>('all');
    const [companyFilter, setCompanyFilter] = useState<'all' | 'folie' | 'messer'>('all');
    const [multiCompanyOnly, setMultiCompanyOnly] = useState(false);
    const [page, setPage] = useState(1);

    // Debounce search
    useEffect(() => {
        const timer = setTimeout(() => {
            setDebouncedSearch(searchQuery);
            setPage(1); // Reset page on search
        }, 300);
        return () => clearTimeout(timer);
    }, [searchQuery]);

    // Reset page on filter change
    useEffect(() => {
        setPage(1);
    }, [entityType, companyFilter, multiCompanyOnly]);

    // Build query params
    const queryParams: CrossCompanyParams = {
        page,
        perPage: PAGE_SIZE,
        search: debouncedSearch || undefined,
        entityType: entityType !== 'all' ? entityType : undefined,
        companyFilter: companyFilter !== 'all' ? companyFilter : undefined,
        multiCompanyOnly,
    };

    // Fetch data
    const { data, isLoading, isFetching } = useQuery({
        queryKey: relationshipsQueryKeys.crossCompany(queryParams),
        queryFn: () => fetchCrossCompanyEntities(queryParams),
        placeholderData: (prev) => prev,
    });

    const handleSearchChange = useCallback((value: string) => {
        setSearchQuery(value);
    }, []);

    const handleEntityTypeChange = useCallback((value: string) => {
        setEntityType(value as EntityType | 'all');
    }, []);

    const handleCompanyFilterChange = useCallback((value: string) => {
        setCompanyFilter(value as 'all' | 'folie' | 'messer');
    }, []);

    const handleMultiCompanyToggle = useCallback((checked: boolean) => {
        setMultiCompanyOnly(checked);
    }, []);

    const entities = data?.items ?? [];
    const summary = data?.summary ?? {
        multiCompanyCount: 0,
        folieOnlyCount: 0,
        messerOnlyCount: 0,
        totalEntities: 0,
    };
    const totalPages = data?.totalPages ?? 1;

    return (
        <div className="p-8 space-y-6">
            {/* Header */}
            <div>
                <h1 className="text-3xl font-bold tracking-tight flex items-center gap-3">
                    <Layers className="h-8 w-8 text-emerald-500" />
                    Cross-Company Übersicht
                </h1>
                <p className="text-muted-foreground mt-2">
                    Vergleichen Sie Geschäftspartner zwischen Spargelfolie und Spargelmesser
                </p>
            </div>

            {/* Summary Cards */}
            <CompanyComparisonCard summary={summary} />

            {/* Filters */}
            <Card>
                <CardHeader className="pb-3">
                    <div className="flex items-center gap-2">
                        <Filter className="h-4 w-4 text-muted-foreground" />
                        <CardTitle className="text-base">Filter</CardTitle>
                    </div>
                </CardHeader>
                <CardContent>
                    <div className="flex flex-wrap items-center gap-4">
                        {/* Search */}
                        <SearchInput value={searchQuery} onChange={handleSearchChange} />

                        {/* Entity Type Filter */}
                        <Select value={entityType} onValueChange={handleEntityTypeChange}>
                            <SelectTrigger className="w-40">
                                <SelectValue placeholder="Typ" />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value="all">Alle Typen</SelectItem>
                                <SelectItem value="customer">Kunden</SelectItem>
                                <SelectItem value="supplier">Lieferanten</SelectItem>
                                <SelectItem value="both">Beides</SelectItem>
                            </SelectContent>
                        </Select>

                        {/* Company Filter */}
                        <Select value={companyFilter} onValueChange={handleCompanyFilterChange}>
                            <SelectTrigger className="w-48">
                                <SelectValue placeholder="Firma" />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value="all">Alle Firmen</SelectItem>
                                <SelectItem value="folie">Nur Spargelfolie</SelectItem>
                                <SelectItem value="messer">Nur Spargelmesser</SelectItem>
                            </SelectContent>
                        </Select>

                        {/* Multi-Company Toggle */}
                        <div className="flex items-center gap-2">
                            <Switch
                                id="multi-company"
                                checked={multiCompanyOnly}
                                onCheckedChange={handleMultiCompanyToggle}
                            />
                            <Label htmlFor="multi-company" className="text-sm cursor-pointer">
                                Nur in beiden Firmen
                            </Label>
                        </div>
                    </div>
                </CardContent>
            </Card>

            {/* Results Count */}
            <div className="flex items-center justify-between">
                <p className="text-sm text-muted-foreground">
                    {isFetching && !isLoading ? (
                        <span className="animate-pulse">Aktualisiere...</span>
                    ) : (
                        <>
                            {data?.total ?? 0} Geschäftspartner gefunden
                        </>
                    )}
                </p>

                {/* Pagination */}
                {totalPages > 1 && (
                    <div className="flex items-center gap-2">
                        <Button
                            variant="outline"
                            size="sm"
                            onClick={() => setPage((p) => Math.max(1, p - 1))}
                            disabled={page === 1}
                        >
                            <ChevronLeft className="h-4 w-4" />
                        </Button>
                        <span className="text-sm text-muted-foreground px-2">
                            Seite {page} von {totalPages}
                        </span>
                        <Button
                            variant="outline"
                            size="sm"
                            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                            disabled={page === totalPages}
                        >
                            <ChevronRight className="h-4 w-4" />
                        </Button>
                    </div>
                )}
            </div>

            {/* Table */}
            <CrossCompanyTable entities={entities} isLoading={isLoading} />
        </div>
    );
}

export default CrossCompanyPage;
