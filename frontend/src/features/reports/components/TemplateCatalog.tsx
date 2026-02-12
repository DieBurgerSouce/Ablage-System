/**
 * TemplateCatalog Component
 *
 * Zeigt den Katalog vordefinierter Report-Templates.
 * Ermöglicht Filtern nach Kategorie und Erstellen neuer Reports aus Templates.
 */

import { useState, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from '@tanstack/react-router';
import {
    BookTemplate,
    Search,
    Loader2,
    RefreshCw,
    ArrowRight,
    LayoutGrid,
    List,
    FileText,
    Receipt,
    Users,
    BarChart3,
} from 'lucide-react';
import type { LucideProps } from 'lucide-react';

// Type for Lucide React icon components
type LucideIcon = React.ComponentType<LucideProps>;
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Skeleton } from '@/components/ui/skeleton';
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { useToast } from '@/hooks/use-toast';
import { TemplatePreviewCard } from './TemplatePreviewCard';
import { getCatalog, instantiateTemplate as apiInstantiateTemplate, reportKeys } from '../api';
import type { CatalogTemplate, CatalogCategory } from '../types';

// ==================== Types ====================

interface TemplateCatalogProps {
    onTemplateCreated?: (templateId: string) => void;
    compact?: boolean;
}

// ==================== Category Icons ====================

const CATEGORY_ICONS: Record<string, LucideIcon> = {
    finanzen: Receipt,
    dokumente: FileText,
    geschäftspartner: Users,
    ocr: BarChart3,
};

// ==================== Loading Skeleton ====================

function CatalogSkeleton() {
    return (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {[1, 2, 3, 4, 5, 6].map((i) => (
                <Card key={i} className="h-56">
                    <CardHeader className="pb-3">
                        <div className="flex items-start justify-between">
                            <Skeleton className="h-10 w-10 rounded-lg" />
                            <Skeleton className="h-5 w-20 rounded" />
                        </div>
                        <Skeleton className="h-5 w-3/4 mt-3" />
                        <Skeleton className="h-4 w-full mt-2" />
                    </CardHeader>
                    <CardContent className="pb-3">
                        <div className="flex gap-2">
                            <Skeleton className="h-4 w-12" />
                            <Skeleton className="h-4 w-12" />
                            <Skeleton className="h-4 w-12" />
                        </div>
                    </CardContent>
                </Card>
            ))}
        </div>
    );
}

// ==================== Empty State ====================

function CatalogEmpty({ searchQuery }: { searchQuery: string }) {
    return (
        <div className="flex flex-col items-center justify-center py-16 text-center">
            <BookTemplate className="h-12 w-12 text-muted-foreground mb-4" />
            <p className="text-muted-foreground">
                {searchQuery
                    ? `Keine Templates gefunden für "${searchQuery}"`
                    : 'Keine Templates im Katalog'}
            </p>
        </div>
    );
}

// ==================== Instantiate Dialog ====================

interface InstantiateDialogProps {
    template: CatalogTemplate | null;
    open: boolean;
    onOpenChange: (open: boolean) => void;
    onConfirm: (name: string) => void;
    isLoading: boolean;
}

function InstantiateDialog({
    template,
    open,
    onOpenChange,
    onConfirm,
    isLoading,
}: InstantiateDialogProps) {
    const [name, setName] = useState('');

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        onConfirm(name || template?.name || 'Neuer Report');
    };

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent>
                <form onSubmit={handleSubmit}>
                    <DialogHeader>
                        <DialogTitle>Report aus Vorlage erstellen</DialogTitle>
                        <DialogDescription>
                            {template?.description}
                        </DialogDescription>
                    </DialogHeader>

                    <div className="py-4 space-y-4">
                        <div className="space-y-2">
                            <Label htmlFor="report-name">Name des Reports</Label>
                            <Input
                                id="report-name"
                                placeholder={template?.name || 'Neuer Report'}
                                value={name}
                                onChange={(e) => setName(e.target.value)}
                                autoFocus
                            />
                            <p className="text-xs text-muted-foreground">
                                Leer lassen für Standardname
                            </p>
                        </div>

                        {template && (
                            <div className="rounded-lg border bg-muted/50 p-3 space-y-2">
                                <p className="text-sm font-medium">Vorlage enthält:</p>
                                <div className="flex flex-wrap gap-2 text-xs">
                                    <Badge variant="secondary">
                                        {template.default_columns.length} Spalten
                                    </Badge>
                                    {template.default_filters && template.default_filters.length > 0 && (
                                        <Badge variant="secondary">
                                            {template.default_filters.length} Filter
                                        </Badge>
                                    )}
                                    {template.default_charts && template.default_charts.length > 0 && (
                                        <Badge variant="secondary">
                                            {template.default_charts.length} Charts
                                        </Badge>
                                    )}
                                </div>
                            </div>
                        )}
                    </div>

                    <DialogFooter>
                        <Button
                            type="button"
                            variant="outline"
                            onClick={() => onOpenChange(false)}
                            disabled={isLoading}
                        >
                            Abbrechen
                        </Button>
                        <Button type="submit" disabled={isLoading}>
                            {isLoading ? (
                                <>
                                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                                    Wird erstellt...
                                </>
                            ) : (
                                <>
                                    <ArrowRight className="h-4 w-4 mr-2" />
                                    Report erstellen
                                </>
                            )}
                        </Button>
                    </DialogFooter>
                </form>
            </DialogContent>
        </Dialog>
    );
}

// ==================== Main Component ====================

export function TemplateCatalog({ onTemplateCreated, compact = false }: TemplateCatalogProps) {
    const navigate = useNavigate();
    const queryClient = useQueryClient();
    const { toast } = useToast();

    const [searchQuery, setSearchQuery] = useState('');
    const [selectedCategory, setSelectedCategory] = useState<string>('all');
    const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid');
    const [selectedTemplate, setSelectedTemplate] = useState<CatalogTemplate | null>(null);

    // Fetch catalog
    const {
        data,
        isLoading,
        isError,
        error,
        refetch,
        isFetching,
    } = useQuery({
        queryKey: reportKeys.catalogList(selectedCategory === 'all' ? undefined : selectedCategory),
        queryFn: () => getCatalog(selectedCategory === 'all' ? undefined : selectedCategory),
    });

    // Instantiate mutation
    const instantiateMutation = useMutation({
        mutationFn: ({ templateId, name }: { templateId: string; name?: string }) =>
            apiInstantiateTemplate(templateId, name ? { name } : undefined),
        onSuccess: (newTemplate) => {
            toast({
                title: 'Report erstellt',
                description: `"${newTemplate.name}" wurde erfolgreich erstellt.`,
            });
            queryClient.invalidateQueries({ queryKey: reportKeys.templates() });
            setSelectedTemplate(null);

            if (onTemplateCreated) {
                onTemplateCreated(newTemplate.id);
            } else {
                // Navigate to the new template
                navigate({ to: '/reports/builder/$templateId', params: { templateId: newTemplate.id } });
            }
        },
        onError: (err) => {
            toast({
                title: 'Fehler',
                description: err instanceof Error ? err.message : 'Report konnte nicht erstellt werden',
                variant: 'destructive',
            });
        },
    });

    // Filter templates
    const filteredTemplates = useMemo(() => {
        if (!data?.templates) return [];

        let templates = data.templates;

        // Search filter
        if (searchQuery.trim()) {
            const query = searchQuery.toLowerCase();
            templates = templates.filter(
                (t) =>
                    t.name.toLowerCase().includes(query) ||
                    t.description.toLowerCase().includes(query) ||
                    t.tags.some((tag) => tag.toLowerCase().includes(query))
            );
        }

        return templates;
    }, [data?.templates, searchQuery]);

    // Handle instantiate
    const handleInstantiate = (templateId: string) => {
        const template = data?.templates.find((t) => t.id === templateId);
        if (template) {
            setSelectedTemplate(template);
        }
    };

    const handleConfirmInstantiate = (name: string) => {
        if (selectedTemplate) {
            instantiateMutation.mutate({
                templateId: selectedTemplate.id,
                name: name,
            });
        }
    };

    // Categories for tabs
    const categories: CatalogCategory[] = data?.categories || [];

    return (
        <div className={compact ? '' : 'space-y-6'}>
            {/* Header */}
            {!compact && (
                <Card>
                    <CardHeader>
                        <div className="flex items-start justify-between">
                            <div>
                                <CardTitle className="text-xl flex items-center gap-2">
                                    <BookTemplate className="h-5 w-5" />
                                    Vorlagen-Katalog
                                </CardTitle>
                                <CardDescription>
                                    Wähle eine vordefinierte Vorlage, um schnell einen neuen Report zu erstellen.
                                </CardDescription>
                            </div>
                            <Button
                                variant="ghost"
                                size="icon"
                                onClick={() => refetch()}
                                disabled={isFetching}
                            >
                                <RefreshCw className={`h-4 w-4 ${isFetching ? 'animate-spin' : ''}`} />
                            </Button>
                        </div>
                    </CardHeader>
                </Card>
            )}

            {/* Filters & View Toggle */}
            <div className="flex flex-col sm:flex-row gap-4 items-start sm:items-center justify-between">
                <div className="flex-1 max-w-sm">
                    <div className="relative">
                        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                        <Input
                            placeholder="Vorlagen durchsuchen..."
                            value={searchQuery}
                            onChange={(e) => setSearchQuery(e.target.value)}
                            className="pl-9"
                        />
                    </div>
                </div>

                <div className="flex items-center gap-2">
                    {/* Category Tabs */}
                    <Tabs value={selectedCategory} onValueChange={setSelectedCategory}>
                        <TabsList>
                            <TabsTrigger value="all">
                                Alle
                                {data && (
                                    <Badge variant="secondary" className="ml-1.5 h-5 px-1.5">
                                        {data.total}
                                    </Badge>
                                )}
                            </TabsTrigger>
                            {categories.map((cat) => {
                                const CategoryIcon = CATEGORY_ICONS[cat.id] || FileText;
                                return (
                                    <TabsTrigger key={cat.id} value={cat.id} className="gap-1.5">
                                        <CategoryIcon className="h-3.5 w-3.5" />
                                        <span className="hidden sm:inline">{cat.name}</span>
                                        <Badge variant="secondary" className="ml-1 h-5 px-1.5">
                                            {cat.template_count}
                                        </Badge>
                                    </TabsTrigger>
                                );
                            })}
                        </TabsList>
                    </Tabs>

                    {/* View Toggle */}
                    <div className="flex border rounded-md">
                        <Button
                            variant={viewMode === 'grid' ? 'secondary' : 'ghost'}
                            size="icon"
                            className="h-9 w-9 rounded-r-none"
                            onClick={() => setViewMode('grid')}
                        >
                            <LayoutGrid className="h-4 w-4" />
                        </Button>
                        <Button
                            variant={viewMode === 'list' ? 'secondary' : 'ghost'}
                            size="icon"
                            className="h-9 w-9 rounded-l-none"
                            onClick={() => setViewMode('list')}
                        >
                            <List className="h-4 w-4" />
                        </Button>
                    </div>
                </div>
            </div>

            {/* Content */}
            {isLoading ? (
                <CatalogSkeleton />
            ) : isError ? (
                <Card>
                    <CardContent className="py-12 text-center">
                        <p className="text-destructive mb-2">
                            Fehler beim Laden des Katalogs
                        </p>
                        <p className="text-sm text-muted-foreground mb-4">
                            {error instanceof Error ? error.message : 'Unbekannter Fehler'}
                        </p>
                        <Button variant="outline" onClick={() => refetch()}>
                            Erneut versuchen
                        </Button>
                    </CardContent>
                </Card>
            ) : filteredTemplates.length === 0 ? (
                <CatalogEmpty searchQuery={searchQuery} />
            ) : viewMode === 'grid' ? (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    {filteredTemplates.map((template) => (
                        <TemplatePreviewCard
                            key={template.id}
                            template={template}
                            onInstantiate={handleInstantiate}
                            isInstantiating={
                                instantiateMutation.isPending &&
                                selectedTemplate?.id === template.id
                            }
                        />
                    ))}
                </div>
            ) : (
                <div className="space-y-3">
                    {filteredTemplates.map((template) => (
                        <Card key={template.id} className="hover:shadow-md transition-shadow">
                            <CardContent className="py-4">
                                <div className="flex items-center justify-between gap-4">
                                    <div className="flex-1 min-w-0">
                                        <div className="flex items-center gap-3">
                                            <h4 className="font-medium truncate">{template.name}</h4>
                                            <Badge variant="secondary" className="text-xs">
                                                {template.data_source}
                                            </Badge>
                                        </div>
                                        <p className="text-sm text-muted-foreground truncate mt-0.5">
                                            {template.description}
                                        </p>
                                    </div>
                                    <div className="flex items-center gap-2 shrink-0">
                                        <div className="flex gap-1 text-xs text-muted-foreground">
                                            {template.tags.slice(0, 2).map((tag) => (
                                                <Badge key={tag} variant="outline" className="text-[10px]">
                                                    {tag}
                                                </Badge>
                                            ))}
                                        </div>
                                        <Button
                                            size="sm"
                                            onClick={() => handleInstantiate(template.id)}
                                            disabled={
                                                instantiateMutation.isPending &&
                                                selectedTemplate?.id === template.id
                                            }
                                        >
                                            Verwenden
                                        </Button>
                                    </div>
                                </div>
                            </CardContent>
                        </Card>
                    ))}
                </div>
            )}

            {/* Instantiate Dialog */}
            <InstantiateDialog
                template={selectedTemplate}
                open={!!selectedTemplate}
                onOpenChange={(open) => !open && setSelectedTemplate(null)}
                onConfirm={handleConfirmInstantiate}
                isLoading={instantiateMutation.isPending}
            />
        </div>
    );
}

export default TemplateCatalog;
