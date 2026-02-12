/**
 * CategoryStatsCards - Statistik-Karten nach Vorlagen-Kategorien
 *
 * Features:
 * - Anzahl Vorlagen pro Kategorie
 * - Standard-Vorlage Anzeige
 * - Klickbare Karten für Filter
 */

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import {
  FileText,
  FileCheck,
  FileSignature,
  Mail,
  Bell,
  AlertTriangle,
  CheckSquare,
  BarChart,
  Award,
  File,
} from 'lucide-react';
import type { CategorySummary } from '../types/template-types';
import { TemplateCategory, TEMPLATE_CATEGORY_LABELS } from '../types/template-types';

interface CategoryStatsCardsProps {
  categories: CategorySummary[];
  isLoading: boolean;
  selectedCategory?: TemplateCategory;
  onCategoryClick?: (category: TemplateCategory) => void;
}

const categoryIcons: Record<TemplateCategory, typeof FileText> = {
  [TemplateCategory.INVOICE]: FileText,
  [TemplateCategory.OFFER]: FileCheck,
  [TemplateCategory.CONTRACT]: FileSignature,
  [TemplateCategory.LETTER]: Mail,
  [TemplateCategory.REMINDER]: Bell,
  [TemplateCategory.DUNNING]: AlertTriangle,
  [TemplateCategory.CONFIRMATION]: CheckSquare,
  [TemplateCategory.REPORT]: BarChart,
  [TemplateCategory.CERTIFICATE]: Award,
  [TemplateCategory.OTHER]: File,
};

const categoryColors: Record<TemplateCategory, string> = {
  [TemplateCategory.INVOICE]: 'text-blue-500',
  [TemplateCategory.OFFER]: 'text-green-500',
  [TemplateCategory.CONTRACT]: 'text-purple-500',
  [TemplateCategory.LETTER]: 'text-gray-500',
  [TemplateCategory.REMINDER]: 'text-yellow-500',
  [TemplateCategory.DUNNING]: 'text-red-500',
  [TemplateCategory.CONFIRMATION]: 'text-teal-500',
  [TemplateCategory.REPORT]: 'text-indigo-500',
  [TemplateCategory.CERTIFICATE]: 'text-amber-500',
  [TemplateCategory.OTHER]: 'text-slate-500',
};

export function CategoryStatsCards({
  categories,
  isLoading,
  selectedCategory,
  onCategoryClick,
}: CategoryStatsCardsProps) {
  if (isLoading) {
    return (
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
        {[1, 2, 3, 4, 5].map((i) => (
          <Card key={i}>
            <CardHeader className="pb-2">
              <Skeleton className="h-4 w-24" />
            </CardHeader>
            <CardContent>
              <Skeleton className="h-8 w-12" />
            </CardContent>
          </Card>
        ))}
      </div>
    );
  }

  // Sort by count descending, then filter only categories with templates
  const sortedCategories = [...categories]
    .filter((c) => c.count > 0)
    .sort((a, b) => b.count - a.count);

  if (sortedCategories.length === 0) {
    return null;
  }

  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
      {sortedCategories.map((cat) => {
        const Icon = categoryIcons[cat.category as TemplateCategory] || File;
        const colorClass = categoryColors[cat.category as TemplateCategory] || 'text-gray-500';
        const isSelected = selectedCategory === cat.category;

        return (
          <Card
            key={cat.category}
            className={`cursor-pointer transition-all hover:shadow-md ${
              isSelected ? 'ring-2 ring-primary' : ''
            }`}
            onClick={() => onCategoryClick?.(cat.category)}
          >
            <CardHeader className="pb-2 flex flex-row items-center justify-between space-y-0">
              <CardTitle className="text-sm font-medium">
                {TEMPLATE_CATEGORY_LABELS[cat.category as TemplateCategory] || cat.category}
              </CardTitle>
              <Icon className={`h-4 w-4 ${colorClass}`} />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{cat.count}</div>
              {cat.default_template_name && (
                <p className="text-xs text-muted-foreground truncate mt-1">
                  Standard: {cat.default_template_name}
                </p>
              )}
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}
