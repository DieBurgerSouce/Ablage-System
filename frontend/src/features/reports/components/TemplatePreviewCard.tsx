/**
 * TemplatePreviewCard Component
 *
 * Zeigt eine Vorschau eines Katalog-Templates mit Icons, Tags und Aktionen.
 */

import {
    FileText,
    Receipt,
    Users,
    BarChart3,
    FileCheck,
    Truck,
    CreditCard,
    Building2,
    Plus,
    Eye,
    Columns,
    Filter,
    PieChart,
} from 'lucide-react';
import type { LucideProps } from 'lucide-react';

// Type for Lucide React icon components
type LucideIcon = React.ComponentType<LucideProps>;
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import type { CatalogTemplate } from '../types';

// ==================== Types ====================

interface TemplatePreviewCardProps {
    template: CatalogTemplate;
    onInstantiate: (templateId: string, name?: string) => void;
    onPreview?: (templateId: string) => void;
    isInstantiating?: boolean;
}

// ==================== Icon Mapping ====================

const ICON_MAP: Record<string, LucideIcon> = {
    'file-text': FileText,
    'receipt': Receipt,
    'users': Users,
    'bar-chart': BarChart3,
    'file-check': FileCheck,
    'truck': Truck,
    'credit-card': CreditCard,
    'building': Building2,
};

// ==================== Category Styles ====================

const CATEGORY_STYLES: Record<string, { bg: string; border: string; text: string }> = {
    finanzen: {
        bg: 'bg-emerald-50 dark:bg-emerald-900/20',
        border: 'border-emerald-200 dark:border-emerald-800',
        text: 'text-emerald-600 dark:text-emerald-400',
    },
    dokumente: {
        bg: 'bg-blue-50 dark:bg-blue-900/20',
        border: 'border-blue-200 dark:border-blue-800',
        text: 'text-blue-600 dark:text-blue-400',
    },
    geschaeftspartner: {
        bg: 'bg-purple-50 dark:bg-purple-900/20',
        border: 'border-purple-200 dark:border-purple-800',
        text: 'text-purple-600 dark:text-purple-400',
    },
    ocr: {
        bg: 'bg-amber-50 dark:bg-amber-900/20',
        border: 'border-amber-200 dark:border-amber-800',
        text: 'text-amber-600 dark:text-amber-400',
    },
};

// ==================== Data Source Labels ====================

const DATA_SOURCE_LABELS: Record<string, string> = {
    documents: 'Dokumente',
    invoices: 'Rechnungen',
    entities: 'Geschaeftspartner',
    ocr_results: 'OCR-Ergebnisse',
};

// ==================== Component ====================

export function TemplatePreviewCard({
    template,
    onInstantiate,
    onPreview,
    isInstantiating = false,
}: TemplatePreviewCardProps) {
    const Icon = ICON_MAP[template.icon] || FileText;
    const categoryStyle = CATEGORY_STYLES[template.category] || CATEGORY_STYLES.dokumente;

    return (
        <Card className={`transition-all hover:shadow-md ${categoryStyle.border}`}>
            <CardHeader className="pb-3">
                <div className="flex items-start justify-between gap-3">
                    <div className={`p-2.5 rounded-lg ${categoryStyle.bg}`}>
                        <Icon className={`h-5 w-5 ${categoryStyle.text}`} />
                    </div>
                    <Badge variant="secondary" className="text-xs">
                        {DATA_SOURCE_LABELS[template.data_source] || template.data_source}
                    </Badge>
                </div>
                <CardTitle className="text-base mt-3">{template.name}</CardTitle>
                <CardDescription className="line-clamp-2">
                    {template.description}
                </CardDescription>
            </CardHeader>

            <CardContent className="pb-3">
                {/* Template Stats */}
                <div className="flex items-center gap-4 text-xs text-muted-foreground">
                    <Tooltip>
                        <TooltipTrigger asChild>
                            <span className="flex items-center gap-1">
                                <Columns className="h-3.5 w-3.5" />
                                {template.default_columns.length}
                            </span>
                        </TooltipTrigger>
                        <TooltipContent>
                            {template.default_columns.length} Spalten
                        </TooltipContent>
                    </Tooltip>

                    {template.default_filters && template.default_filters.length > 0 && (
                        <Tooltip>
                            <TooltipTrigger asChild>
                                <span className="flex items-center gap-1">
                                    <Filter className="h-3.5 w-3.5" />
                                    {template.default_filters.length}
                                </span>
                            </TooltipTrigger>
                            <TooltipContent>
                                {template.default_filters.length} Filter
                            </TooltipContent>
                        </Tooltip>
                    )}

                    {template.default_charts && template.default_charts.length > 0 && (
                        <Tooltip>
                            <TooltipTrigger asChild>
                                <span className="flex items-center gap-1">
                                    <PieChart className="h-3.5 w-3.5" />
                                    {template.default_charts.length}
                                </span>
                            </TooltipTrigger>
                            <TooltipContent>
                                {template.default_charts.length} Charts
                            </TooltipContent>
                        </Tooltip>
                    )}
                </div>

                {/* Tags */}
                {template.tags.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-3">
                        {template.tags.slice(0, 3).map((tag) => (
                            <Badge key={tag} variant="outline" className="text-[10px] px-1.5 py-0">
                                {tag}
                            </Badge>
                        ))}
                        {template.tags.length > 3 && (
                            <Badge variant="outline" className="text-[10px] px-1.5 py-0">
                                +{template.tags.length - 3}
                            </Badge>
                        )}
                    </div>
                )}
            </CardContent>

            <CardFooter className="pt-0 gap-2">
                {onPreview && (
                    <Button
                        variant="ghost"
                        size="sm"
                        className="flex-1"
                        onClick={() => onPreview(template.id)}
                    >
                        <Eye className="h-4 w-4 mr-1.5" />
                        Details
                    </Button>
                )}
                <Button
                    variant="default"
                    size="sm"
                    className="flex-1"
                    onClick={() => onInstantiate(template.id)}
                    disabled={isInstantiating}
                >
                    <Plus className="h-4 w-4 mr-1.5" />
                    Verwenden
                </Button>
            </CardFooter>
        </Card>
    );
}

export default TemplatePreviewCard;
